from __future__ import annotations

import hashlib
import json
import re
import shutil
import sqlite3
import uuid
import zipfile
from datetime import date, datetime
from pathlib import Path

import bleach
import markdown
from flask import current_app, request
from PIL import Image, ImageOps
from werkzeug.utils import secure_filename

from .extensions import db
from .models import Attachment, AuditLog, Cell, DailySummary, Issue, ObjectCell, PCB, SystemSetting, WorkLog, utcnow


DEFAULT_SETTINGS = {
    "system_name": "板迹",
    "backup_dir": "",
    "backup_retention_daily": "14",
    "backup_retention_weekly": "8",
    "upload_image_limit_mb": "20",
    "upload_file_limit_mb": "100",
}

ALLOWED_TAGS = {
    "p", "br", "strong", "em", "code", "pre", "blockquote", "ul", "ol", "li",
    "a", "table", "thead", "tbody", "tr", "th", "td", "h1", "h2", "h3", "hr",
    "span", "mark", "input",
}
ALLOWED_ATTRS = {
    "a": ["href", "title", "target", "rel"],
    "span": ["class"],
    "input": ["type", "checked", "disabled"],
}
COLOR_PATTERN = re.compile(r"\[(red|orange|blue|green|gray)\](.*?)\[/\1\]", re.S)
MARK_PATTERN = re.compile(r"==(.+?)==", re.S)


def ensure_defaults():
    changed = False
    for key, value in DEFAULT_SETTINGS.items():
        if db.session.get(SystemSetting, key) is None:
            db.session.add(SystemSetting(key=key, value=value))
            changed = True
    if changed:
        db.session.commit()


def setting(key, default=""):
    row = db.session.get(SystemSetting, key)
    return row.value if row else default


def set_setting(key, value):
    row = db.session.get(SystemSetting, key) or SystemSetting(key=key)
    row.value = str(value)
    db.session.add(row)
    db.session.commit()


def render_markdown(source: str) -> str:
    source = source or ""
    escaped_colors = COLOR_PATTERN.sub(lambda m: f'<span class="text-{m.group(1)}">{m.group(2)}</span>', source)
    escaped_colors = MARK_PATTERN.sub(r"<mark>\1</mark>", escaped_colors)
    html = markdown.markdown(escaped_colors, extensions=["tables", "fenced_code", "sane_lists", "nl2br"])
    return bleach.clean(html, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS, protocols={"http", "https", "mailto"}, strip=True)


def audit(action, entity=None, detail="", user_id=None):
    from flask_login import current_user

    resolved_user = user_id
    if resolved_user is None and getattr(current_user, "is_authenticated", False):
        resolved_user = current_user.id
    row = AuditLog(
        user_id=resolved_user,
        action=action,
        entity_type=entity.__class__.__name__ if entity else "",
        entity_id=getattr(entity, "id", None),
        detail=detail,
        ip_address=(request.remote_addr or "") if request else "",
    )
    db.session.add(row)


def _attachment_dir(now=None):
    now = now or datetime.now()
    root = Path(current_app.config["UPLOAD_FOLDER"])
    folder = root / f"{now:%Y}" / f"{now:%m}"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def save_attachment(file_storage, *, issue=None, cell=None, object_cell=None, pcb=None, user=None):
    original = file_storage.filename or "attachment"
    safe = secure_filename(original)
    suffix = Path(safe or original).suffix.lower()[:12]
    storage_basename = f"{uuid.uuid4().hex}{suffix}"
    mime = file_storage.mimetype or "application/octet-stream"
    limit_key = "upload_image_limit_mb" if mime.startswith("image/") else "upload_file_limit_mb"
    byte_limit = max(int(setting(limit_key, "20" if mime.startswith("image/") else "100")), 1) * 1024 * 1024
    stream = file_storage.stream
    position = stream.tell()
    stream.seek(0, 2)
    incoming_size = stream.tell()
    stream.seek(position)
    if incoming_size > byte_limit:
        raise ValueError(f"{original} 超过单文件 {byte_limit // 1024 // 1024}MB 限制。")
    folder = _attachment_dir()
    target = folder / storage_basename
    file_storage.save(target)
    relative = target.relative_to(Path(current_app.config["UPLOAD_FOLDER"])).as_posix()

    thumb_relative = None
    if mime.startswith("image/"):
        thumb_dir = folder / "_thumbs"
        thumb_dir.mkdir(exist_ok=True)
        thumb_target = thumb_dir / f"{target.stem}.webp"
        try:
            with Image.open(target) as image:
                image = ImageOps.exif_transpose(image)
                image.thumbnail((720, 480))
                if image.mode not in ("RGB", "RGBA"):
                    image = image.convert("RGB")
                image.save(thumb_target, "WEBP", quality=82, method=6)
            thumb_relative = thumb_target.relative_to(Path(current_app.config["UPLOAD_FOLDER"])).as_posix()
        except Exception:
            thumb_relative = None

    record = Attachment(
        original_name=original[:300], storage_name=relative, thumbnail_name=thumb_relative,
        mime_type=mime[:128], size=target.stat().st_size, issue=issue, cell=cell, object_cell=object_cell, pcb=pcb,
        uploaded_by_id=getattr(user, "id", None),
    )
    db.session.add(record)
    return record


def build_daily_summary(target_date: date):
    start = datetime.combine(target_date, datetime.min.time())
    end = datetime.combine(target_date, datetime.max.time())
    logs = WorkLog.query.filter(WorkLog.deleted_at.is_(None), WorkLog.created_at.between(start, end)).order_by(WorkLog.created_at).all()
    cells = Cell.query.filter(Cell.deleted_at.is_(None), Cell.created_at.between(start, end)).order_by(Cell.created_at).all()
    object_cells = ObjectCell.query.filter(ObjectCell.deleted_at.is_(None), ObjectCell.created_at.between(start, end)).order_by(ObjectCell.created_at).all()
    minutes = sum(log.minutes for log in logs)
    completed = [f"- {log.title}" + (f"：{log.result}" if log.result else "") for log in logs]
    progress = [f"- [{cell.issue.title}] {cell.kind}：{cell.content_md[:180]}" for cell in cells if cell.kind in {"测试记录", "当前判断", "阶段结论"}]
    progress.extend(
        f"- [{cell.pcb.model or cell.pcb.serial if cell.pcb else cell.project.name}] {cell.kind}：{cell.content_md[:180]}"
        for cell in object_cells if cell.kind in {"测试记录", "当前判断", "阶段结论"}
    )
    conclusions = [f"- {cell.content_md[:240]}" for cell in cells if cell.kind == "阶段结论"]
    next_steps = [f"- {log.next_step}" for log in logs if log.next_step]
    next_steps.extend(f"- {cell.content_md[:180]}" for cell in cells if cell.kind == "下一步待办")
    next_steps.extend(f"- {cell.content_md[:180]}" for cell in object_cells if cell.kind == "下一步待办")
    content = "\n".join([
        "## 今日完成", *(completed or ["- 暂无工作记录"]), "",
        "## 问题进展", *(progress or ["- 暂无问题更新"]), "",
        "## 关键结论", *(conclusions or ["- 暂无阶段结论"]), "",
        "## 明日 / 下一步", *(next_steps or ["- 待补充"]), "",
        f"## 今日投入时间\n\n{minutes // 60} 小时 {minutes % 60} 分钟",
    ])
    summary = DailySummary.query.filter_by(summary_date=target_date).first() or DailySummary(summary_date=target_date)
    summary.content_md = content
    summary.rendered_html = render_markdown(content)
    summary.generated = True
    db.session.add(summary)
    db.session.commit()
    return summary


def run_backup(destination=None):
    destination = destination or setting("backup_dir") or str(current_app.config["BACKUP_FOLDER"])
    backup_root = Path(destination).expanduser().resolve()
    uploads_source = Path(current_app.config["UPLOAD_FOLDER"]).resolve()
    if backup_root == uploads_source or backup_root.is_relative_to(uploads_source):
        raise ValueError("备份目录不能位于附件目录内部。")
    backup_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = backup_root / stamp
    run_dir.mkdir(parents=True, exist_ok=False)

    database_name = db.engine.url.database
    if not database_name:
        raise RuntimeError("当前数据库不是可备份的文件数据库。")
    source_db = Path(database_name).resolve()
    if not source_db.exists() or source_db.stat().st_size == 0:
        raise RuntimeError("数据库文件不存在或为空。")
    target_db = run_dir / "app.db"
    with sqlite3.connect(source_db) as source, sqlite3.connect(target_db) as target:
        source.backup(target)

    uploads_target = run_dir / "uploads"
    copied = 0
    if uploads_source.exists():
        shutil.copytree(uploads_source, uploads_target, dirs_exist_ok=True)
        copied = sum(1 for p in uploads_target.rglob("*") if p.is_file())

    digest = hashlib.sha256(target_db.read_bytes()).hexdigest()
    manifest = {"created_at": datetime.now().isoformat(), "database_sha256": digest, "attachment_files": copied}
    (run_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    _prune_backups(backup_root, protected=run_dir)
    return run_dir, manifest


def _prune_backups(backup_root: Path, protected: Path):
    """Keep recent daily snapshots plus one snapshot per older ISO week."""
    try:
        daily_keep = max(int(setting("backup_retention_daily", "14")), 1)
        weekly_keep = max(int(setting("backup_retention_weekly", "8")), 0)
    except ValueError:
        daily_keep, weekly_keep = 14, 8
    candidates = []
    for folder in backup_root.iterdir():
        if not folder.is_dir() or not re.fullmatch(r"\d{8}-\d{6}", folder.name):
            continue
        try:
            stamp = datetime.strptime(folder.name, "%Y%m%d-%H%M%S")
        except ValueError:
            continue
        candidates.append((stamp, folder.resolve()))
    candidates.sort(reverse=True)
    keep = {path for _, path in candidates[:daily_keep]}
    weeks = set()
    for stamp, path in candidates[daily_keep:]:
        week = stamp.isocalendar()[:2]
        if len(weeks) < weekly_keep and week not in weeks:
            weeks.add(week)
            keep.add(path)
    root = backup_root.resolve()
    for _, path in candidates:
        if path in keep or path == protected.resolve() or path.parent != root:
            continue
        shutil.rmtree(path)


def export_pcb(pcb: PCB):
    export_dir = Path(current_app.config["BACKUP_FOLDER"]) / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    target = export_dir / f"{secure_filename(pcb.serial) or 'pcb'}-{datetime.now():%Y%m%d-%H%M%S}.zip"
    issues = Issue.query.filter_by(pcb_id=pcb.id).filter(Issue.deleted_at.is_(None)).order_by(Issue.created_at).all()
    data = {
        "pcb": {"serial": pcb.serial, "model": pcb.model, "revision": pcb.revision, "status": pcb.status, "notes": pcb.notes},
        "issues": [],
    }
    md = [f"# {pcb.serial}", "", f"- 型号：{pcb.model}", f"- PCB版本：{pcb.revision}", f"- 状态：{pcb.status}", ""]
    attachment_records = []
    for issue in issues:
        issue_data = {"id": issue.id, "title": issue.title, "status": issue.status, "priority": issue.priority, "cells": []}
        md.extend([f"## {issue.title}", "", f"状态：{issue.status}｜优先级：{issue.priority}", ""])
        for cell in issue.cells.filter(Cell.deleted_at.is_(None)).order_by(Cell.created_at).all():
            issue_data["cells"].append({"kind": cell.kind, "content": cell.content_md, "created_at": cell.created_at.isoformat()})
            md.extend([f"### {cell.kind} · {cell.created_at:%Y-%m-%d %H:%M}", "", cell.content_md, ""])
            attachment_records.extend(cell.attachments.filter(Attachment.deleted_at.is_(None)).all())
        data["issues"].append(issue_data)

    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("records.md", "\n".join(md))
        archive.writestr("data.json", json.dumps(data, ensure_ascii=False, indent=2))
        upload_root = Path(current_app.config["UPLOAD_FOLDER"])
        seen = set()
        for attachment in attachment_records:
            source = upload_root / attachment.storage_name
            if source.exists() and source not in seen:
                archive.write(source, f"attachments/{attachment.id}-{attachment.original_name}")
                seen.add(source)
    return target
