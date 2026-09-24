"""Searchable knowledge cards, optionally grounded in an issue's practice."""

import re

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_
from sqlalchemy.orm import joinedload

from .extensions import db
from .models import Cell, Issue, KnowledgeEntry, utcnow
from .services import audit, render_markdown, save_attachment


bp = Blueprint("knowledge", __name__)


def create_entry(title, content, *, issue=None, files=(), create_cell=True):
    title = title.strip()
    content = content.strip()
    if not title or not content:
        raise ValueError("知识小标题和正文都不能为空。")
    if len(title) > 200 or len(content) > 50_000:
        raise ValueError("知识小标题最多 200 字，正文最多 50,000 字。")

    cell = None
    if issue is not None and create_cell:
        cell = Cell(
            issue=issue, kind="知识积累", content_md=title,
            rendered_html=render_markdown(title), author_id=current_user.id,
        )
        db.session.add(cell)
    if issue is not None:
        issue.updated_at = utcnow()
    entry = KnowledgeEntry(
        title=title, content_md=content, rendered_html=render_markdown(content),
        source_issue=issue, source_cell=cell, author_id=current_user.id,
    )
    db.session.add(entry)
    db.session.flush()
    for file in files:
        save_attachment(file, issue=issue, cell=cell, pcb=issue.pcb if issue else None, user=current_user)
    audit("knowledge.create", entry, title)
    db.session.commit()
    return entry


def issue_from_reference(value):
    """Resolve a bounded picker value such as '#42 · 问题标题'."""
    value = value.strip()
    if not value:
        return None
    match = re.fullmatch(r"#(\d+)(?:\s+.*)?", value)
    if not match:
        raise ValueError("请从问题下拉列表中选择有效的问题。")
    if len(match.group(1)) > 18:
        raise ValueError("关联的问题不存在或已移入回收站。")
    issue = Issue.query.filter_by(id=int(match.group(1)), deleted_at=None).first()
    if issue is None:
        raise ValueError("关联的问题不存在或已移入回收站。")
    return issue


@bp.get("/knowledge/issue-options")
@login_required
def issue_options():
    q = request.args.get("q", "").strip()[:100]
    query = Issue.query.filter(Issue.deleted_at.is_(None))
    if q:
        if q.lstrip("#").isdigit():
            if len(q.lstrip("#")) > 18:
                return jsonify(options=[])
            query = query.filter(Issue.id == int(q.lstrip("#")))
        else:
            escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            query = query.filter(Issue.title.ilike(f"%{escaped}%", escape="\\"))
    issues = query.order_by(Issue.updated_at.desc(), Issue.id.desc()).limit(20).all()
    return jsonify(options=[f"#{issue.id} · {issue.title}" for issue in issues])


@bp.route("/knowledge", methods=["GET", "POST"])
@login_required
def index():
    if request.method == "POST":
        try:
            issue = issue_from_reference(request.form.get("issue_ref", ""))
            entry = create_entry(request.form.get("title", ""), request.form.get("content", ""), issue=issue, create_cell=False)
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "error")
            return redirect(url_for("knowledge.index"))
        flash("知识已保存。", "success")
        return redirect(url_for("knowledge.detail", entry_id=entry.id))

    q = request.args.get("q", "").strip()[:100]
    issue_id = request.args.get("issue_id", type=int)
    issue_filter = Issue.query.filter_by(id=issue_id, deleted_at=None).first_or_404() if issue_id else None
    query = KnowledgeEntry.query.options(joinedload(KnowledgeEntry.source_issue)).filter(KnowledgeEntry.deleted_at.is_(None))
    if issue_filter:
        query = query.filter(KnowledgeEntry.source_issue_id == issue_filter.id)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(KnowledgeEntry.title.ilike(like), KnowledgeEntry.content_md.ilike(like)))
    page = max(request.args.get("page", 1, type=int), 1)
    pagination = query.order_by(KnowledgeEntry.updated_at.desc(), KnowledgeEntry.id.desc()).paginate(
        page=page, per_page=20, error_out=False,
    )
    return render_template("knowledge/list.html", q=q, pagination=pagination, issue_filter=issue_filter)


@bp.get("/knowledge/<int:entry_id>")
@login_required
def detail(entry_id):
    entry = KnowledgeEntry.query.filter_by(id=entry_id, deleted_at=None).first_or_404()
    issue = entry.source_issue if entry.source_issue and entry.source_issue.deleted_at is None else None
    practice_cells = (
        issue.cells.filter(Cell.deleted_at.is_(None), Cell.kind.notin_(("知识积累", "状态变化")))
        .order_by(Cell.created_at.desc(), Cell.id.desc()).limit(8).all()
        if issue else []
    )
    return render_template("knowledge/detail.html", entry=entry, issue=issue, practice_cells=practice_cells)


@bp.post("/knowledge/<int:entry_id>/update")
@login_required
def update(entry_id):
    entry = KnowledgeEntry.query.filter_by(id=entry_id, deleted_at=None).first_or_404()
    title = request.form.get("title", "").strip()
    content = request.form.get("content", "").strip()
    if not title or not content or len(title) > 200 or len(content) > 50_000:
        flash("小标题和正文必填，且不能超过长度限制。", "error")
        return redirect(url_for("knowledge.detail", entry_id=entry.id))
    if "issue_ref" in request.form:
        try:
            issue = issue_from_reference(request.form.get("issue_ref", ""))
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for("knowledge.detail", entry_id=entry.id))
        if entry.source_cell_id and (issue is None or issue.id != entry.source_issue_id):
            flash("来自问题 Cell 的知识需保留原始问题关联。", "error")
            return redirect(url_for("knowledge.detail", entry_id=entry.id))
        entry.source_issue = issue
    entry.title = title
    entry.content_md = content
    entry.rendered_html = render_markdown(content)
    if entry.source_cell:
        entry.source_cell.content_md = title
        entry.source_cell.rendered_html = render_markdown(title)
    audit("knowledge.update", entry, title)
    db.session.commit()
    flash("知识已更新。", "success")
    return redirect(url_for("knowledge.detail", entry_id=entry.id))
