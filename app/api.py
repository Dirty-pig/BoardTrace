from datetime import datetime

from flask import Blueprint, jsonify, request
from flask_login import login_required

from .extensions import db
from .issue_workflow import elapsed_seconds
from .models import Cell, Issue, KnowledgeEntry, ObjectCell, PCB, Project, WorkLog


bp = Blueprint("api", __name__)


def clamp_limit():
    return min(max(request.args.get("limit", 20, type=int), 1), 100)


@bp.get("/pcbs")
@login_required
def pcbs():
    query = request.args.get("q", "").strip()
    rows = PCB.query.filter(PCB.deleted_at.is_(None))
    if query:
        like = f"%{query}%"
        rows = rows.filter(db.or_(PCB.serial.ilike(like), PCB.model.ilike(like), PCB.revision.ilike(like)))
    rows = rows.order_by(PCB.updated_at.desc()).limit(clamp_limit()).all()
    return jsonify([{"id": row.id, "serial": row.serial, "model": row.model, "revision": row.revision, "status": row.status} for row in rows])


@bp.get("/issues/<int:issue_id>")
@login_required
def issue(issue_id):
    row = Issue.query.filter_by(id=issue_id, deleted_at=None).first_or_404()
    limit = clamp_limit()
    before = request.args.get("before", type=int)
    cells = row.cells.filter(Cell.deleted_at.is_(None))
    if before:
        cells = cells.filter(Cell.id < before)
    cells = cells.order_by(Cell.id.desc()).limit(limit).all()
    return jsonify({
        "issue": {"id": row.id, "title": row.title, "status": row.status, "priority": row.priority,
                  "summary": row.current_summary, "pcb": row.pcb.serial if row.pcb else None,
                  "created_at": row.created_at.isoformat() + "Z",
                  "resolved_at": row.resolved_at.isoformat() + "Z" if row.resolved_at else None,
                  "elapsed_seconds": elapsed_seconds(row)},
        "cells": [{"id": cell.id, "kind": cell.kind, "content": cell.content_md, "created_at": cell.created_at.isoformat()} for cell in cells],
        "next_before": cells[-1].id if len(cells) == limit else None,
    })


@bp.get("/work-records")
@login_required
def work_records():
    limit = clamp_limit()
    rows = WorkLog.query.filter(WorkLog.deleted_at.is_(None)).order_by(WorkLog.created_at.desc()).limit(limit).all()
    return jsonify([{"id": row.id, "title": row.title, "minutes": row.minutes, "result": row.result, "pcb": row.pcb.serial if row.pcb else None, "created_at": row.created_at.isoformat()} for row in rows])


@bp.get("/knowledge")
@login_required
def knowledge():
    query = request.args.get("q", "").strip()[:100]
    rows = KnowledgeEntry.query.filter(KnowledgeEntry.deleted_at.is_(None))
    if query:
        like = f"%{query}%"
        rows = rows.filter(db.or_(KnowledgeEntry.title.ilike(like), KnowledgeEntry.content_md.ilike(like)))
    before = request.args.get("before", type=int)
    if before:
        rows = rows.filter(KnowledgeEntry.id < before)
    limit = clamp_limit()
    items = rows.order_by(KnowledgeEntry.id.desc()).limit(limit).all()
    return jsonify({
        "items": [{"id": row.id, "title": row.title, "snippet": row.content_md[:180],
                   "source_issue_id": row.source_issue_id, "updated_at": row.updated_at.isoformat() + "Z"} for row in items],
        "next_before": items[-1].id if len(items) == limit else None,
    })


@bp.get("/search")
@login_required
def search():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify([])
    like = f"%{q}%"
    limit = clamp_limit()
    issues = Issue.query.filter(Issue.deleted_at.is_(None), db.or_(Issue.title.ilike(like), Issue.description.ilike(like), Issue.tags.ilike(like))).limit(limit).all()
    cells = Cell.query.filter(Cell.deleted_at.is_(None), Cell.content_md.ilike(like)).limit(limit).all()
    object_cells = ObjectCell.query.filter(ObjectCell.deleted_at.is_(None), ObjectCell.content_md.ilike(like)).limit(limit).all()
    knowledge_entries = KnowledgeEntry.query.filter(KnowledgeEntry.deleted_at.is_(None), db.or_(KnowledgeEntry.title.ilike(like), KnowledgeEntry.content_md.ilike(like))).limit(limit).all()
    pcbs = PCB.query.filter(PCB.deleted_at.is_(None), db.or_(PCB.serial.ilike(like), PCB.model.ilike(like))).limit(limit).all()
    projects = Project.query.filter(Project.deleted_at.is_(None), db.or_(Project.name.ilike(like), Project.objective.ilike(like))).limit(limit).all()
    results = ([{"type": "pcb", "id": x.id, "title": x.serial, "snippet": f"{x.model} {x.revision}"} for x in pcbs]
        + [{"type": "project", "id": x.id, "title": x.name, "snippet": x.objective[:180]} for x in projects]
        + [{"type": "issue", "id": x.id, "title": x.title, "snippet": x.description[:180]} for x in issues]
        + [{"type": "knowledge", "id": x.id, "title": x.title, "snippet": x.content_md[:180]} for x in knowledge_entries]
        + [{"type": "cell", "id": x.id, "issue_id": x.issue_id, "title": x.kind, "snippet": x.content_md[:180]} for x in cells]
        + [{"type": "object_cell", "id": x.id, "pcb_id": x.pcb_id, "project_id": x.project_id,
            "title": x.kind, "snippet": x.content_md[:180]} for x in object_cells])
    return jsonify(results[:limit])
