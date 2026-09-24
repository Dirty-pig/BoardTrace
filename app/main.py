from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, send_file, send_from_directory, url_for
from flask_login import current_user, login_required
from sqlalchemy import func, literal, select, union_all

from .display import pcb_label
from .extensions import db
from .issue_workflow import CELL_KINDS, ISSUE_STATUSES, PRIORITIES, apply_cell_status, duration_label, elapsed_seconds, set_issue_status
from .models import ActiveTimer, Attachment, AuditLog, Cell, DailySummary, Issue, KnowledgeEntry, ObjectCell, PCB, Project, SystemSetting, User, WorkLog, utcnow
from .services import audit, build_daily_summary, export_pcb, render_markdown, run_backup, save_attachment, setting, set_setting


bp = Blueprint("main", __name__)
OBJECT_CELL_KINDS = tuple(kind for kind in CELL_KINDS if kind != "知识积累")


@bp.app_context_processor
def inject_globals():
    return {
        "system_name": setting("system_name", "板迹"),
        "issue_statuses": ISSUE_STATUSES,
        "priorities": PRIORITIES,
        "cell_kinds": CELL_KINDS,
        "object_cell_kinds": OBJECT_CELL_KINDS,
        "active_timer": ActiveTimer.query.filter_by(user_id=current_user.id).first() if current_user.is_authenticated else None,
        "quick_pcbs": PCB.query.filter_by(deleted_at=None).order_by(PCB.updated_at.desc()).limit(100).all() if current_user.is_authenticated else [],
    }


def _pagination(query, default_order):
    page = max(request.args.get("page", 1, type=int), 1)
    per_page = min(max(request.args.get("per_page", current_app.config["ITEMS_PER_PAGE"], type=int), 1), current_app.config["MAX_ITEMS_PER_PAGE"])
    return query.order_by(default_order).paginate(page=page, per_page=per_page, error_out=False)


@bp.get("/")
@login_required
def dashboard():
    today = date.today()
    day_start = datetime.combine(today, datetime.min.time())
    work_today = WorkLog.query.filter(WorkLog.deleted_at.is_(None), WorkLog.created_at >= day_start).all()
    cells_today = (
        Cell.query.filter(Cell.deleted_at.is_(None), Cell.created_at >= day_start).count()
        + ObjectCell.query.filter(ObjectCell.deleted_at.is_(None), ObjectCell.created_at >= day_start).count()
    )
    open_issues = Issue.query.filter(Issue.deleted_at.is_(None), Issue.status != "已解决").count()
    waiting = Issue.query.filter_by(status="等待中", deleted_at=None).count()
    recent_pcbs = PCB.query.filter(PCB.deleted_at.is_(None)).order_by(PCB.updated_at.desc()).limit(8).all()
    recent_issues = Issue.query.filter(Issue.deleted_at.is_(None)).order_by(Issue.updated_at.desc()).limit(8).all()
    recent_logs = WorkLog.query.filter(WorkLog.deleted_at.is_(None)).order_by(WorkLog.created_at.desc()).limit(8).all()
    unfiled = Issue.query.filter_by(pcb_id=None, project_id=None, deleted_at=None).order_by(Issue.created_at.desc()).limit(5).all()
    summary = DailySummary.query.filter_by(summary_date=today).first()
    return render_template(
        "dashboard.html", today=today, total_minutes=sum(row.minutes for row in work_today), cells_today=cells_today,
        open_issues=open_issues, waiting=waiting, recent_pcbs=recent_pcbs, recent_issues=recent_issues,
        recent_logs=recent_logs, unfiled=unfiled, summary=summary,
    )


@bp.route("/pcbs", methods=["GET", "POST"])
@login_required
def pcbs():
    if request.method == "POST":
        serial = request.form.get("serial", "").strip()
        if not serial:
            flash("PCB序列号不能为空。", "error")
        elif PCB.query.filter(func.lower(PCB.serial) == serial.lower()).first():
            flash("该PCB序列号已经存在。", "error")
        else:
            pcb = PCB(
                serial=serial, model=request.form.get("model", "").strip(), revision=request.form.get("revision", "").strip(),
                status=request.form.get("status", "处理中"), notes=request.form.get("notes", "").strip(), created_by_id=current_user.id,
            )
            db.session.add(pcb)
            audit("pcb.create", pcb, serial)
            db.session.commit()
            flash("PCB已创建。", "success")
            return redirect(url_for("main.pcb_detail", pcb_id=pcb.id))
    q = request.args.get("q", "").strip()[:128]
    query = PCB.query.filter(PCB.deleted_at.is_(None))
    if q:
        like = f"%{q}%"
        query = query.filter(PCB.serial.ilike(like))
    pagination = _pagination(query, PCB.updated_at.desc())
    return render_template("pcbs/list.html", pagination=pagination, q=q)


@bp.get("/pcbs/<int:pcb_id>")
@login_required
def pcb_detail(pcb_id):
    pcb = PCB.query.filter_by(id=pcb_id, deleted_at=None).first_or_404()
    page = min(max(request.args.get("page", 1, type=int), 1), 1_000_000)
    per_page = 20
    events = union_all(
        select(literal("issue").label("type"), Issue.id.label("item_id"), Issue.created_at.label("at"))
        .where(Issue.pcb_id == pcb.id, Issue.deleted_at.is_(None)),
        select(literal("work"), WorkLog.id, WorkLog.created_at)
        .where(WorkLog.pcb_id == pcb.id, WorkLog.deleted_at.is_(None)),
        select(literal("cell"), ObjectCell.id, ObjectCell.created_at)
        .where(ObjectCell.pcb_id == pcb.id, ObjectCell.deleted_at.is_(None)),
    ).subquery()
    event_rows = db.session.execute(
        select(events.c.type, events.c.item_id, events.c.at)
        .order_by(events.c.at.desc(), events.c.type, events.c.item_id.desc())
        .offset((page - 1) * per_page).limit(per_page + 1)
    ).all()
    has_more = len(event_rows) > per_page
    event_rows = event_rows[:per_page]
    entity_types = {"issue": Issue, "work": WorkLog, "cell": ObjectCell}
    entities = {}
    for kind, entity_type in entity_types.items():
        ids = [row.item_id for row in event_rows if row.type == kind]
        if ids:
            entities[kind] = {item.id: item for item in db.session.query(entity_type).filter(entity_type.id.in_(ids)).all()}
    timeline = [{"type": row.type, "at": row.at, "item": entities[row.type][row.item_id]} for row in event_rows]
    issues = pcb.issues.filter(Issue.deleted_at.is_(None), Issue.status != "已解决").order_by(Issue.updated_at.desc()).limit(20).all()
    unresolved_count = pcb.issues.filter(Issue.deleted_at.is_(None), Issue.status != "已解决").count()
    total_minutes = db.session.query(func.coalesce(func.sum(WorkLog.minutes), 0)).filter(WorkLog.pcb_id == pcb.id, WorkLog.deleted_at.is_(None)).scalar()
    attachments_count = Attachment.query.filter_by(pcb_id=pcb.id, deleted_at=None).count()
    return render_template("pcbs/detail.html", pcb=pcb, issues=issues, unresolved_count=unresolved_count, timeline=timeline, page=page, has_more=has_more, total_minutes=total_minutes, attachments_count=attachments_count)


def _create_object_cell(*, pcb=None, project=None):
    content = request.form.get("content", "").strip()
    files = [file for file in request.files.getlist("attachments") if file and file.filename]
    kind = request.form.get("kind", "普通记录")
    if kind not in OBJECT_CELL_KINDS:
        abort(400)
    if not content and not files:
        raise ValueError("请输入内容或添加附件。")
    cell = ObjectCell(
        pcb=pcb,
        project=project,
        kind=kind,
        content_md=content,
        rendered_html=render_markdown(content),
        author_id=current_user.id,
    )
    db.session.add(cell)
    db.session.flush()
    for file in files:
        save_attachment(file, object_cell=cell, pcb=pcb, user=current_user)
    owner = pcb or project
    owner.updated_at = utcnow()
    audit("object_cell.create", cell, f"{owner.__class__.__name__}:{owner.id} {kind}")
    db.session.commit()
    return cell


@bp.post("/pcbs/<int:pcb_id>/cells")
@login_required
def pcb_cell_create(pcb_id):
    pcb = PCB.query.filter_by(id=pcb_id, deleted_at=None).first_or_404()
    try:
        _create_object_cell(pcb=pcb)
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "error")
    else:
        flash("板卡 Cell 已添加。", "success")
    return redirect(url_for("main.pcb_detail", pcb_id=pcb.id))


@bp.post("/pcbs/<int:pcb_id>/edit")
@login_required
def pcb_edit(pcb_id):
    pcb = PCB.query.filter_by(id=pcb_id, deleted_at=None).first_or_404()
    serial = request.form.get("serial", "").strip()
    duplicate = PCB.query.filter(func.lower(PCB.serial) == serial.lower(), PCB.id != pcb.id).first()
    if not serial or duplicate:
        flash("PCB序列号为空或已经存在。", "error")
    else:
        pcb.serial = serial
        pcb.model = request.form.get("model", "").strip()
        pcb.revision = request.form.get("revision", "").strip()
        pcb.status = request.form.get("status", pcb.status)
        pcb.notes = request.form.get("notes", "").strip()
        audit("pcb.update", pcb)
        db.session.commit()
        flash("PCB信息已更新。", "success")
    return redirect(url_for("main.pcb_detail", pcb_id=pcb.id))


@bp.post("/pcbs/<int:pcb_id>/trash")
@login_required
def pcb_trash(pcb_id):
    pcb = PCB.query.filter_by(id=pcb_id, deleted_at=None).first_or_404()
    pcb.deleted_at = utcnow()
    audit("pcb.trash", pcb)
    db.session.commit()
    flash("PCB已移入回收站。", "success")
    return redirect(url_for("main.pcbs"))


@bp.route("/projects", methods=["GET", "POST"])
@login_required
def projects():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("项目名称不能为空。", "error")
        else:
            project = Project(name=name, objective=request.form.get("objective", "").strip(), status=request.form.get("status", "进行中"), created_by_id=current_user.id)
            db.session.add(project)
            audit("project.create", project, name)
            db.session.commit()
            flash("项目已创建。", "success")
            return redirect(url_for("main.project_detail", project_id=project.id))
    pagination = _pagination(Project.query.filter(Project.deleted_at.is_(None)), Project.updated_at.desc())
    return render_template("projects/list.html", pagination=pagination)


@bp.get("/projects/<int:project_id>")
@login_required
def project_detail(project_id):
    project = Project.query.filter_by(id=project_id, deleted_at=None).first_or_404()
    page = max(request.args.get("page", 1, type=int), 1)
    pagination = (
        project.object_cells.filter(ObjectCell.deleted_at.is_(None))
        .order_by(ObjectCell.created_at.desc(), ObjectCell.id.desc())
        .paginate(page=page, per_page=20, error_out=False)
    )
    pcbs = PCB.query.filter_by(deleted_at=None).order_by(PCB.model, PCB.serial).limit(100).all()
    issues = project.issues.filter(Issue.deleted_at.is_(None)).order_by(Issue.updated_at.desc()).limit(20).all()
    return render_template("projects/detail.html", project=project, pagination=pagination, pcbs=pcbs, issues=issues)


@bp.post("/projects/<int:project_id>/pcbs")
@login_required
def project_pcbs_update(project_id):
    project = Project.query.filter_by(id=project_id, deleted_at=None).first_or_404()
    requested_ids = {int(value) for value in request.form.getlist("pcb_ids") if value.isdigit()}
    selected = PCB.query.filter(PCB.deleted_at.is_(None), PCB.id.in_(requested_ids)).all() if requested_ids else []
    if len(selected) != len(requested_ids):
        abort(400)
    project.pcbs = selected
    project.updated_at = utcnow()
    audit("project.pcbs_update", project, ",".join(str(pcb.id) for pcb in selected))
    db.session.commit()
    flash("项目关联板卡已更新。", "success")
    return redirect(url_for("main.project_detail", project_id=project.id))


@bp.post("/projects/<int:project_id>/cells")
@login_required
def project_cell_create(project_id):
    project = Project.query.filter_by(id=project_id, deleted_at=None).first_or_404()
    try:
        _create_object_cell(project=project)
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "error")
    else:
        flash("项目 Cell 已添加。", "success")
    return redirect(url_for("main.project_detail", project_id=project.id))


def _trash_cell(cell, action):
    cell.deleted_at = utcnow()
    if not (isinstance(cell, Cell) and cell.knowledge_entry and cell.knowledge_entry.deleted_at is None):
        for attachment in cell.attachments.filter_by(deleted_at=None).all():
            attachment.deleted_at = cell.deleted_at
    audit(action, cell, cell.kind)
    db.session.commit()
    flash("Cell 已移入回收站，可在回收站恢复。", "success")


@bp.post("/projects/<int:project_id>/cells/<int:cell_id>/trash")
@login_required
def project_cell_trash(project_id, cell_id):
    Project.query.filter_by(id=project_id, deleted_at=None).first_or_404()
    cell = ObjectCell.query.filter_by(id=cell_id, project_id=project_id, deleted_at=None).first_or_404()
    _trash_cell(cell, "object_cell.trash")
    return redirect(url_for("main.project_detail", project_id=project_id))


@bp.post("/pcbs/<int:pcb_id>/cells/<int:cell_id>/trash")
@login_required
def pcb_cell_trash(pcb_id, cell_id):
    PCB.query.filter_by(id=pcb_id, deleted_at=None).first_or_404()
    cell = ObjectCell.query.filter_by(id=cell_id, pcb_id=pcb_id, deleted_at=None).first_or_404()
    _trash_cell(cell, "object_cell.trash")
    return redirect(url_for("main.pcb_detail", pcb_id=pcb_id))


@bp.route("/issues", methods=["GET", "POST"])
@login_required
def issues():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        submitted_status = request.form.get("status", "未处理")
        submitted_priority = request.form.get("priority", "普通")
        if not title:
            flash("问题标题不能为空。", "error")
        elif submitted_status not in ISSUE_STATUSES or submitted_priority not in PRIORITIES:
            abort(400)
        else:
            issue = Issue(
                title=title, description=request.form.get("description", "").strip(), status=submitted_status,
                resolved_at=utcnow() if submitted_status == "已解决" else None,
                priority=submitted_priority, pcb_id=request.form.get("pcb_id", type=int),
                project_id=request.form.get("project_id", type=int), created_by_id=current_user.id,
            )
            db.session.add(issue)
            db.session.flush()
            if issue.project and issue.pcb and issue.pcb not in issue.project.pcbs:
                issue.project.pcbs.append(issue.pcb)
            if issue.description:
                db.session.add(Cell(issue=issue, kind="现象", content_md=issue.description, rendered_html=render_markdown(issue.description), author_id=current_user.id))
            audit("issue.create", issue, title)
            db.session.commit()
            flash("问题已创建。", "success")
            return redirect(url_for("main.issue_detail", issue_id=issue.id))
    query = Issue.query.filter(Issue.deleted_at.is_(None))
    status = request.args.get("status", "")
    priority = request.args.get("priority", "")
    if status:
        query = query.filter_by(status=status)
    if priority:
        query = query.filter_by(priority=priority)
    pagination = _pagination(query, Issue.updated_at.desc())
    return render_template("issues/list.html", pagination=pagination, status=status, priority=priority, pcbs=PCB.query.filter_by(deleted_at=None).order_by(PCB.updated_at.desc()).limit(100).all(), projects=Project.query.filter_by(deleted_at=None).order_by(Project.updated_at.desc()).limit(100).all())


@bp.get("/issues/<int:issue_id>")
@login_required
def issue_detail(issue_id):
    issue = Issue.query.filter_by(id=issue_id, deleted_at=None).first_or_404()
    page = max(request.args.get("page", 1, type=int), 1)
    selected_kind = request.args.get("kind", "").strip()
    if selected_kind and selected_kind not in (*CELL_KINDS, "状态变化"):
        abort(400)
    selected_cell = request.args.get("cell", type=int)
    cells = issue.cells.filter(Cell.deleted_at.is_(None))
    if selected_cell is not None:
        cells = cells.filter(Cell.id == selected_cell)
        if cells.count() == 0:
            abort(404)
    elif selected_kind:
        cells = cells.filter(Cell.kind == selected_kind)
    pagination = cells.order_by(Cell.created_at.desc(), Cell.id.desc()).paginate(page=page, per_page=20, error_out=False)
    kinds_in_use = dict(
        issue.cells.filter(Cell.deleted_at.is_(None))
        .with_entities(Cell.kind, func.count(Cell.id)).group_by(Cell.kind).all()
    )
    related_query = KnowledgeEntry.query.filter_by(source_issue_id=issue.id, deleted_at=None)
    related_knowledge_count = related_query.count()
    related_knowledge = related_query.order_by(KnowledgeEntry.updated_at.desc()).limit(8).all()
    seconds = elapsed_seconds(issue)
    return render_template(
        "issues/detail.html", issue=issue, pagination=pagination, selected_kind=selected_kind,
        selected_cell=selected_cell, kinds_in_use=kinds_in_use, elapsed_label=duration_label(seconds),
        elapsed_seconds=seconds,
        related_knowledge=related_knowledge, related_knowledge_count=related_knowledge_count,
        pcbs=PCB.query.filter_by(deleted_at=None).order_by(PCB.updated_at.desc()).limit(100).all(),
        projects=Project.query.filter_by(deleted_at=None).order_by(Project.updated_at.desc()).limit(100).all(),
    )


@bp.post("/issues/<int:issue_id>/cells")
@login_required
def cell_create(issue_id):
    issue = Issue.query.filter_by(id=issue_id, deleted_at=None).first_or_404()
    content = request.form.get("content", "").strip()
    files = [f for f in request.files.getlist("attachments") if f and f.filename]
    kind = request.form.get("kind", "普通记录")
    if kind not in CELL_KINDS:
        abort(400)
    if kind == "知识积累":
        from .knowledge import create_entry

        try:
            create_entry(request.form.get("title", ""), content, issue=issue, files=files)
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "error")
            return redirect(url_for("main.issue_detail", issue_id=issue.id))
        flash("知识已保存到知识库。", "success")
        return redirect(url_for("main.issue_detail", issue_id=issue.id))
    if not content and not files:
        flash("请输入内容或添加附件。", "error")
        return redirect(url_for("main.issue_detail", issue_id=issue.id))
    cell = Cell(issue=issue, kind=kind, content_md=content, rendered_html=render_markdown(content), author_id=current_user.id)
    db.session.add(cell)
    db.session.flush()
    try:
        for file in files:
            save_attachment(file, issue=issue, cell=cell, pcb=issue.pcb, user=current_user)
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "error")
        return redirect(url_for("main.issue_detail", issue_id=issue.id))
    issue.updated_at = utcnow()
    changed = apply_cell_status(issue, kind, user_id=current_user.id)
    audit("cell.create", cell, cell.kind)
    db.session.commit()
    flash(f"Cell已添加，状态更新为「{issue.status}」。" if changed else "Cell已添加。", "success")
    return redirect(url_for("main.issue_detail", issue_id=issue.id))


@bp.post("/issues/<int:issue_id>/cells/<int:cell_id>/trash")
@login_required
def cell_trash(issue_id, cell_id):
    Issue.query.filter_by(id=issue_id, deleted_at=None).first_or_404()
    cell = Cell.query.filter_by(id=cell_id, issue_id=issue_id, deleted_at=None).first_or_404()
    if cell.kind == "状态变化":
        abort(400)
    _trash_cell(cell, "cell.trash")
    return redirect(url_for("main.issue_detail", issue_id=issue_id))


@bp.post("/issues/<int:issue_id>/state")
@login_required
def issue_state(issue_id):
    issue = Issue.query.filter_by(id=issue_id, deleted_at=None).first_or_404()
    field = request.form.get("field", "")
    value = request.form.get("value", "")
    if field == "status":
        if value not in ISSUE_STATUSES:
            abort(400)
        changed = set_issue_status(issue, value, user_id=current_user.id, source="sidebar")
    elif field == "priority":
        if value not in PRIORITIES:
            abort(400)
        changed = value != issue.priority
        if changed:
            issue.priority = value
            audit("issue.priority_change", issue, detail=value)
    else:
        abort(400)
    if changed:
        db.session.commit()
        flash("问题已更新。", "success")
    return redirect(url_for("main.issue_detail", issue_id=issue.id))


@bp.post("/issues/<int:issue_id>/update")
@login_required
def issue_update(issue_id):
    issue = Issue.query.filter_by(id=issue_id, deleted_at=None).first_or_404()
    issue.title = request.form.get("title", issue.title).strip() or issue.title
    issue.tags = request.form.get("tags", issue.tags).strip()
    issue.current_summary = request.form.get("current_summary", issue.current_summary).strip()
    pcb_id = request.form.get("pcb_id", type=int)
    project_id = request.form.get("project_id", type=int)
    pcb = PCB.query.filter_by(id=pcb_id, deleted_at=None).first() if pcb_id else None
    project = Project.query.filter_by(id=project_id, deleted_at=None).first() if project_id else None
    if (pcb_id and not pcb) or (project_id and not project):
        abort(400)
    issue.pcb = pcb
    issue.project = project
    if project and pcb and pcb not in project.pcbs:
        project.pcbs.append(pcb)
    audit("issue.update", issue)
    db.session.commit()
    flash("问题信息已更新。", "success")
    return redirect(url_for("main.issue_detail", issue_id=issue.id))


@bp.post("/issues/<int:issue_id>/trash")
@login_required
def issue_trash(issue_id):
    issue = Issue.query.filter_by(id=issue_id, deleted_at=None).first_or_404()
    issue.deleted_at = utcnow()
    audit("issue.trash", issue)
    db.session.commit()
    flash("问题已移入回收站。", "success")
    return redirect(url_for("main.issues"))


@bp.route("/work", methods=["GET", "POST"])
@login_required
def work_logs():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        if not title:
            flash("工作标题不能为空。", "error")
        else:
            row = WorkLog(
                title=title, content=request.form.get("content", "").strip(), result=request.form.get("result", "").strip(),
                next_step=request.form.get("next_step", "").strip(), minutes=max(request.form.get("minutes", 0, type=int), 0),
                pcb_id=request.form.get("pcb_id", type=int), project_id=request.form.get("project_id", type=int), issue_id=request.form.get("issue_id", type=int),
                user_id=current_user.id, started_at=utcnow(), ended_at=utcnow(),
            )
            db.session.add(row)
            audit("work.create", row, title)
            db.session.commit()
            flash("工作记录已保存。", "success")
            return redirect(url_for("main.work_logs"))
    pagination = _pagination(WorkLog.query.filter(WorkLog.deleted_at.is_(None)), WorkLog.created_at.desc())
    return render_template("work/list.html", pagination=pagination, pcbs=PCB.query.filter_by(deleted_at=None).order_by(PCB.updated_at.desc()).limit(100).all(), projects=Project.query.filter_by(deleted_at=None).order_by(Project.updated_at.desc()).limit(100).all(), issues=Issue.query.filter_by(deleted_at=None).order_by(Issue.updated_at.desc()).limit(100).all())


@bp.post("/timer/start")
@login_required
def timer_start():
    if ActiveTimer.query.filter_by(user_id=current_user.id).first():
        flash("已经有一个进行中的计时器。", "error")
    else:
        timer = ActiveTimer(title=request.form.get("title", "未命名工作").strip() or "未命名工作", user_id=current_user.id, pcb_id=request.form.get("pcb_id", type=int), issue_id=request.form.get("issue_id", type=int))
        db.session.add(timer)
        audit("timer.start", timer, timer.title)
        db.session.commit()
        flash("计时已开始。", "success")
    return redirect(request.referrer or url_for("main.dashboard"))


@bp.post("/timer/stop")
@login_required
def timer_stop():
    timer = ActiveTimer.query.filter_by(user_id=current_user.id).first()
    if not timer:
        flash("没有进行中的计时器。", "error")
    else:
        ended = utcnow()
        seconds = max(int((ended - timer.started_at).total_seconds()) - timer.paused_seconds, 60)
        log = WorkLog(title=timer.title, minutes=max(round(seconds / 60), 1), started_at=timer.started_at, ended_at=ended, user_id=current_user.id, pcb_id=timer.pcb_id, project_id=timer.project_id, issue_id=timer.issue_id)
        db.session.add(log)
        db.session.delete(timer)
        audit("timer.stop", log, f"{log.minutes} minutes")
        db.session.commit()
        flash("计时已结束，并生成工作记录草稿。", "success")
    return redirect(request.referrer or url_for("main.dashboard"))


@bp.route("/search")
@login_required
def search():
    q = request.args.get("q", "").strip()
    results = []
    if q:
        like = f"%{q}%"
        results.extend({"type": "板卡", "title": row.model or "未填写型号", "snippet": pcb_label(row, include_model=False), "url": url_for("main.pcb_detail", pcb_id=row.id)} for row in PCB.query.filter(PCB.deleted_at.is_(None), db.or_(PCB.serial.ilike(like), PCB.model.ilike(like))).limit(20))
        results.extend({"type": "项目", "title": row.name, "snippet": row.objective[:200], "url": url_for("main.project_detail", project_id=row.id)} for row in Project.query.filter(Project.deleted_at.is_(None), db.or_(Project.name.ilike(like), Project.objective.ilike(like))).limit(20))
        results.extend({"type": "问题", "title": row.title, "snippet": (row.description or row.current_summary)[:200], "url": url_for("main.issue_detail", issue_id=row.id)} for row in Issue.query.filter(Issue.deleted_at.is_(None), db.or_(Issue.title.ilike(like), Issue.description.ilike(like), Issue.tags.ilike(like))).limit(20))
        results.extend({"type": "知识", "title": row.title, "snippet": row.content_md[:200], "url": url_for("knowledge.detail", entry_id=row.id)} for row in KnowledgeEntry.query.filter(KnowledgeEntry.deleted_at.is_(None), db.or_(KnowledgeEntry.title.ilike(like), KnowledgeEntry.content_md.ilike(like))).limit(20))
        results.extend({"type": f"Cell · {row.kind}", "title": row.issue.title, "snippet": row.content_md[:200], "url": url_for("main.issue_detail", issue_id=row.issue_id)} for row in Cell.query.filter(Cell.deleted_at.is_(None), Cell.content_md.ilike(like)).limit(20))
        object_cells = ObjectCell.query.filter(ObjectCell.deleted_at.is_(None), ObjectCell.content_md.ilike(like)).limit(20).all()
        results.extend({
            "type": f"Cell · {row.kind}",
            "title": row.pcb.model or row.pcb.serial,
            "snippet": row.content_md[:200],
            "url": url_for("main.pcb_detail", pcb_id=row.pcb_id),
        } if row.pcb_id else {
            "type": f"Cell · {row.kind}",
            "title": row.project.name,
            "snippet": row.content_md[:200],
            "url": url_for("main.project_detail", project_id=row.project_id),
        } for row in object_cells)
    return render_template("search.html", q=q, results=results[:20])


@bp.get("/attachments/<int:attachment_id>/<kind>")
@login_required
def attachment_file(attachment_id, kind):
    attachment = Attachment.query.filter_by(id=attachment_id, deleted_at=None).first_or_404()
    if kind not in {"thumb", "view", "download"}:
        abort(404)
    if kind == "view" and attachment.mime_type not in {"image/png", "image/jpeg", "image/gif", "image/webp", "image/bmp", "image/avif"}:
        abort(404)
    relative = attachment.thumbnail_name if kind == "thumb" and attachment.thumbnail_name else attachment.storage_name
    path = Path(current_app.config["UPLOAD_FOLDER"]) / relative
    if not path.exists():
        abort(404)
    return send_from_directory(path.parent, path.name, as_attachment=(kind == "download"), download_name=attachment.original_name)


@bp.post("/summary/generate")
@login_required
def summary_generate():
    summary = build_daily_summary(date.today())
    audit("summary.generate", summary)
    db.session.commit()
    flash("今日汇总草稿已生成。", "success")
    return redirect(url_for("main.dashboard"))


@bp.post("/summary/<int:summary_id>/update")
@login_required
def summary_update(summary_id):
    summary = DailySummary.query.get_or_404(summary_id)
    summary.content_md = request.form.get("content", "")
    summary.rendered_html = render_markdown(summary.content_md)
    summary.generated = False
    audit("summary.update", summary)
    db.session.commit()
    flash("今日汇总已保存。", "success")
    return redirect(url_for("main.dashboard"))


@bp.get("/trash")
@login_required
def trash():
    pcbs = PCB.query.filter(PCB.deleted_at.is_not(None)).order_by(PCB.deleted_at.desc()).all()
    issues = Issue.query.filter(Issue.deleted_at.is_not(None)).order_by(Issue.deleted_at.desc()).all()
    work = WorkLog.query.filter(WorkLog.deleted_at.is_not(None)).order_by(WorkLog.deleted_at.desc()).all()
    cells = Cell.query.filter(Cell.deleted_at.is_not(None)).order_by(Cell.deleted_at.desc()).all()
    object_cells = ObjectCell.query.filter(ObjectCell.deleted_at.is_not(None)).order_by(ObjectCell.deleted_at.desc()).all()
    return render_template("trash.html", pcbs=pcbs, issues=issues, work=work, cells=cells, object_cells=object_cells)


@bp.post("/trash/restore/<entity>/<int:entity_id>")
@login_required
def trash_restore(entity, entity_id):
    models = {"pcb": PCB, "issue": Issue, "work": WorkLog, "cell": Cell, "object_cell": ObjectCell}
    model = models.get(entity)
    if not model:
        abort(404)
    row = db.session.get(model, entity_id) or abort(404)
    if row.deleted_at is None:
        abort(404)
    if isinstance(row, Cell) and row.issue.deleted_at is not None:
        flash("请先恢复所属问题。", "error")
        return redirect(url_for("main.trash"))
    if isinstance(row, ObjectCell) and (row.project or row.pcb).deleted_at is not None:
        flash("请先恢复所属项目或板卡。", "error")
        return redirect(url_for("main.trash"))
    row.deleted_at = None
    if isinstance(row, (Cell, ObjectCell)):
        for attachment in row.attachments.filter(Attachment.deleted_at.is_not(None)).all():
            attachment.deleted_at = None
    audit(f"{entity}.restore", row)
    db.session.commit()
    flash("记录已恢复。", "success")
    return redirect(url_for("main.trash"))


@bp.get("/admin")
@login_required
def admin():
    if current_user.role != "root":
        abort(403)
    return render_template("admin.html", users=User.query.order_by(User.created_at).all(), audits=AuditLog.query.order_by(AuditLog.created_at.desc()).limit(50).all(), settings={key: setting(key) for key in ["system_name", "backup_dir", "backup_retention_daily", "backup_retention_weekly"]})


@bp.post("/admin/settings")
@login_required
def admin_settings():
    if current_user.role != "root": abort(403)
    for key in ["system_name", "backup_dir", "backup_retention_daily", "backup_retention_weekly"]:
        set_setting(key, request.form.get(key, "").strip())
    audit("settings.update")
    db.session.commit()
    flash("系统设置已保存。", "success")
    return redirect(url_for("main.admin"))


@bp.post("/admin/backup")
@login_required
def admin_backup():
    if current_user.role != "root": abort(403)
    try:
        folder, manifest = run_backup()
        audit("backup.create", detail=str(folder))
        db.session.commit()
        flash(f"备份完成：{folder}", "success")
    except Exception as exc:
        audit("backup.failed", detail=str(exc))
        db.session.commit()
        flash(f"备份失败：{exc}", "error")
    return redirect(url_for("main.admin"))


@bp.get("/pcbs/<int:pcb_id>/export")
@login_required
def pcb_export(pcb_id):
    pcb = PCB.query.filter_by(id=pcb_id, deleted_at=None).first_or_404()
    path = export_pcb(pcb)
    audit("pcb.export", pcb, str(path))
    db.session.commit()
    return send_file(path, as_attachment=True, download_name=path.name)
