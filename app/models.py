from __future__ import annotations

from datetime import date, datetime, timezone

from flask_login import UserMixin
from sqlalchemy import CheckConstraint, Index, UniqueConstraint

from .extensions import db


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


project_pcbs = db.Table(
    "project_pcbs",
    db.Column("project_id", db.Integer, db.ForeignKey("projects.id"), primary_key=True),
    db.Column("pcb_id", db.Integer, db.ForeignKey("pcbs.id"), primary_key=True),
)


class TimestampMixin:
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False, index=True)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class SoftDeleteMixin:
    deleted_at = db.Column(db.DateTime, nullable=True, index=True)

    @property
    def is_deleted(self):
        return self.deleted_at is not None


class User(UserMixin, TimestampMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(16), default="root", nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)
    login_failures = db.Column(db.Integer, default=0, nullable=False)
    locked_until = db.Column(db.DateTime, nullable=True)
    last_login_at = db.Column(db.DateTime, nullable=True)

    @property
    def is_active(self):
        return self.active


class PCB(TimestampMixin, SoftDeleteMixin, db.Model):
    __tablename__ = "pcbs"
    id = db.Column(db.Integer, primary_key=True)
    serial = db.Column(db.String(128), nullable=False)
    model = db.Column(db.String(128), nullable=False, default="")
    revision = db.Column(db.String(64), nullable=False, default="")
    status = db.Column(db.String(32), nullable=False, default="处理中", index=True)
    notes = db.Column(db.Text, nullable=False, default="")
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    projects = db.relationship("Project", secondary=project_pcbs, back_populates="pcbs")
    issues = db.relationship("Issue", back_populates="pcb", lazy="dynamic")
    work_logs = db.relationship("WorkLog", back_populates="pcb", lazy="dynamic")
    object_cells = db.relationship("ObjectCell", back_populates="pcb", lazy="dynamic", cascade="all, delete-orphan")

    __table_args__ = (UniqueConstraint("serial", name="uq_pcb_serial"), Index("ix_pcb_model_revision", "model", "revision"))


class Project(TimestampMixin, SoftDeleteMixin, db.Model):
    __tablename__ = "projects"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False, index=True)
    objective = db.Column(db.Text, nullable=False, default="")
    status = db.Column(db.String(32), nullable=False, default="进行中", index=True)
    next_action = db.Column(db.Text, nullable=False, default="")
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    pcbs = db.relationship("PCB", secondary=project_pcbs, back_populates="projects")
    issues = db.relationship("Issue", back_populates="project", lazy="dynamic")
    object_cells = db.relationship("ObjectCell", back_populates="project", lazy="dynamic", cascade="all, delete-orphan")


class Issue(TimestampMixin, SoftDeleteMixin, db.Model):
    __tablename__ = "issues"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(300), nullable=False, index=True)
    description = db.Column(db.Text, nullable=False, default="")
    current_summary = db.Column(db.Text, nullable=False, default="")
    status = db.Column(db.String(32), nullable=False, default="未处理", index=True)
    resolved_at = db.Column(db.DateTime, nullable=True)
    priority = db.Column(db.String(16), nullable=False, default="普通", index=True)
    tags = db.Column(db.String(500), nullable=False, default="")
    pcb_id = db.Column(db.Integer, db.ForeignKey("pcbs.id"), nullable=True, index=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=True, index=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    pcb = db.relationship("PCB", back_populates="issues")
    project = db.relationship("Project", back_populates="issues")
    creator = db.relationship("User", foreign_keys=[created_by_id])
    cells = db.relationship("Cell", back_populates="issue", lazy="dynamic", cascade="all, delete-orphan")
    attachments = db.relationship("Attachment", back_populates="issue", lazy="dynamic")
    work_logs = db.relationship("WorkLog", back_populates="issue", lazy="dynamic")

    __table_args__ = (Index("ix_issue_status_updated", "status", "updated_at"),)


class Cell(TimestampMixin, SoftDeleteMixin, db.Model):
    __tablename__ = "cells"
    id = db.Column(db.Integer, primary_key=True)
    issue_id = db.Column(db.Integer, db.ForeignKey("issues.id"), nullable=False, index=True)
    kind = db.Column(db.String(32), nullable=False, default="普通记录", index=True)
    content_md = db.Column(db.Text, nullable=False, default="")
    rendered_html = db.Column(db.Text, nullable=False, default="")
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    issue = db.relationship("Issue", back_populates="cells")
    author = db.relationship("User")
    attachments = db.relationship("Attachment", back_populates="cell", lazy="dynamic")
    knowledge_entry = db.relationship("KnowledgeEntry", back_populates="source_cell", uselist=False)


class ObjectCell(TimestampMixin, SoftDeleteMixin, db.Model):
    """A Cell written directly on a project or a physical PCB."""

    __tablename__ = "object_cells"
    id = db.Column(db.Integer, primary_key=True)
    pcb_id = db.Column(db.Integer, db.ForeignKey("pcbs.id"), nullable=True, index=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=True, index=True)
    kind = db.Column(db.String(32), nullable=False, default="普通记录", index=True)
    content_md = db.Column(db.Text, nullable=False, default="")
    rendered_html = db.Column(db.Text, nullable=False, default="")
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    pcb = db.relationship("PCB", back_populates="object_cells")
    project = db.relationship("Project", back_populates="object_cells")
    author = db.relationship("User")
    attachments = db.relationship("Attachment", back_populates="object_cell", lazy="dynamic")

    __table_args__ = (
        CheckConstraint(
            "(pcb_id IS NOT NULL AND project_id IS NULL) OR "
            "(pcb_id IS NULL AND project_id IS NOT NULL)",
            name="ck_object_cell_exactly_one_owner",
        ),
    )


class KnowledgeEntry(TimestampMixin, SoftDeleteMixin, db.Model):
    __tablename__ = "knowledge_entries"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False, index=True)
    content_md = db.Column(db.Text, nullable=False, default="")
    rendered_html = db.Column(db.Text, nullable=False, default="")
    source_issue_id = db.Column(db.Integer, db.ForeignKey("issues.id"), nullable=True, index=True)
    source_cell_id = db.Column(db.Integer, db.ForeignKey("cells.id"), nullable=True, unique=True)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    source_issue = db.relationship("Issue")
    source_cell = db.relationship("Cell", back_populates="knowledge_entry")
    author = db.relationship("User")


class WorkLog(TimestampMixin, SoftDeleteMixin, db.Model):
    __tablename__ = "work_logs"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(300), nullable=False)
    content = db.Column(db.Text, nullable=False, default="")
    result = db.Column(db.Text, nullable=False, default="")
    next_step = db.Column(db.Text, nullable=False, default="")
    minutes = db.Column(db.Integer, nullable=False, default=0)
    started_at = db.Column(db.DateTime, nullable=True, index=True)
    ended_at = db.Column(db.DateTime, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    pcb_id = db.Column(db.Integer, db.ForeignKey("pcbs.id"), nullable=True, index=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=True, index=True)
    issue_id = db.Column(db.Integer, db.ForeignKey("issues.id"), nullable=True, index=True)
    user = db.relationship("User")
    pcb = db.relationship("PCB", back_populates="work_logs")
    project = db.relationship("Project")
    issue = db.relationship("Issue", back_populates="work_logs")


class ActiveTimer(TimestampMixin, db.Model):
    __tablename__ = "active_timers"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(300), nullable=False)
    started_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    paused_at = db.Column(db.DateTime, nullable=True)
    paused_seconds = db.Column(db.Integer, default=0, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, unique=True)
    pcb_id = db.Column(db.Integer, db.ForeignKey("pcbs.id"), nullable=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=True)
    issue_id = db.Column(db.Integer, db.ForeignKey("issues.id"), nullable=True)
    user = db.relationship("User")


class Attachment(TimestampMixin, SoftDeleteMixin, db.Model):
    __tablename__ = "attachments"
    id = db.Column(db.Integer, primary_key=True)
    original_name = db.Column(db.String(300), nullable=False)
    storage_name = db.Column(db.String(500), nullable=False, unique=True)
    thumbnail_name = db.Column(db.String(500), nullable=True)
    mime_type = db.Column(db.String(128), nullable=False, default="application/octet-stream")
    size = db.Column(db.Integer, nullable=False, default=0)
    caption = db.Column(db.String(500), nullable=False, default="")
    issue_id = db.Column(db.Integer, db.ForeignKey("issues.id"), nullable=True, index=True)
    cell_id = db.Column(db.Integer, db.ForeignKey("cells.id"), nullable=True, index=True)
    object_cell_id = db.Column(db.Integer, db.ForeignKey("object_cells.id"), nullable=True, index=True)
    pcb_id = db.Column(db.Integer, db.ForeignKey("pcbs.id"), nullable=True, index=True)
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    issue = db.relationship("Issue", back_populates="attachments")
    cell = db.relationship("Cell", back_populates="attachments")
    object_cell = db.relationship("ObjectCell", back_populates="attachments")
    pcb = db.relationship("PCB")
    uploader = db.relationship("User")


class DailySummary(TimestampMixin, db.Model):
    __tablename__ = "daily_summaries"
    id = db.Column(db.Integer, primary_key=True)
    summary_date = db.Column(db.Date, nullable=False, unique=True, default=date.today)
    content_md = db.Column(db.Text, nullable=False, default="")
    rendered_html = db.Column(db.Text, nullable=False, default="")
    generated = db.Column(db.Boolean, default=True, nullable=False)


class AuditLog(db.Model):
    __tablename__ = "audit_logs"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    action = db.Column(db.String(100), nullable=False, index=True)
    entity_type = db.Column(db.String(64), nullable=False, default="")
    entity_id = db.Column(db.Integer, nullable=True)
    detail = db.Column(db.Text, nullable=False, default="")
    ip_address = db.Column(db.String(64), nullable=False, default="")
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False, index=True)
    user = db.relationship("User")


class SystemSetting(db.Model):
    __tablename__ = "system_settings"
    key = db.Column(db.String(100), primary_key=True)
    value = db.Column(db.Text, nullable=False, default="")
