"""Searchable knowledge cards, stored separately from issue timeline Cells."""

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_
from sqlalchemy.orm import joinedload

from .extensions import db
from .models import Cell, Issue, KnowledgeEntry, utcnow
from .services import audit, render_markdown, save_attachment


bp = Blueprint("knowledge", __name__)


def create_entry(title, content, *, issue=None, files=()):
    title = title.strip()
    content = content.strip()
    if not title or not content:
        raise ValueError("知识小标题和正文都不能为空。")
    if len(title) > 200 or len(content) > 50_000:
        raise ValueError("知识小标题最多 200 字，正文最多 50,000 字。")

    cell = None
    if issue is not None:
        cell = Cell(
            issue=issue, kind="知识积累", content_md=title,
            rendered_html=render_markdown(title), author_id=current_user.id,
        )
        db.session.add(cell)
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


@bp.route("/knowledge", methods=["GET", "POST"])
@login_required
def index():
    if request.method == "POST":
        try:
            entry = create_entry(request.form.get("title", ""), request.form.get("content", ""))
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "error")
            return redirect(url_for("knowledge.index"))
        flash("知识已保存。", "success")
        return redirect(url_for("knowledge.detail", entry_id=entry.id))

    q = request.args.get("q", "").strip()[:100]
    query = KnowledgeEntry.query.options(joinedload(KnowledgeEntry.source_issue)).filter(KnowledgeEntry.deleted_at.is_(None))
    if q:
        like = f"%{q}%"
        query = query.filter(or_(KnowledgeEntry.title.ilike(like), KnowledgeEntry.content_md.ilike(like)))
    page = max(request.args.get("page", 1, type=int), 1)
    pagination = query.order_by(KnowledgeEntry.updated_at.desc(), KnowledgeEntry.id.desc()).paginate(
        page=page, per_page=20, error_out=False,
    )
    return render_template("knowledge/list.html", q=q, pagination=pagination)


@bp.get("/knowledge/<int:entry_id>")
@login_required
def detail(entry_id):
    entry = KnowledgeEntry.query.filter_by(id=entry_id, deleted_at=None).first_or_404()
    return render_template("knowledge/detail.html", entry=entry)


@bp.post("/knowledge/<int:entry_id>/update")
@login_required
def update(entry_id):
    entry = KnowledgeEntry.query.filter_by(id=entry_id, deleted_at=None).first_or_404()
    title = request.form.get("title", "").strip()
    content = request.form.get("content", "").strip()
    if not title or not content or len(title) > 200 or len(content) > 50_000:
        flash("小标题和正文必填，且不能超过长度限制。", "error")
        return redirect(url_for("knowledge.detail", entry_id=entry.id))
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
