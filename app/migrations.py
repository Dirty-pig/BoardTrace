"""Small, explicit SQLite upgrades for existing personal installations."""

import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path

from sqlalchemy import text
from flask import current_app

from .extensions import db


def upgrade_schema():
    engine = db.engine
    if engine.dialect.name != "sqlite":
        return
    with engine.connect() as connection:
        tables = {row[0] for row in connection.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))}
        if "issues" not in tables:
            return
        columns = {row[1] for row in connection.execute(text("PRAGMA table_info(issues)"))}
        attachment_columns = {row[1] for row in connection.execute(text("PRAGMA table_info(attachments)"))} if "attachments" in tables else set()
    need_resolved_at = "resolved_at" not in columns
    need_knowledge = "knowledge_entries" not in tables
    need_object_cells = "object_cells" not in tables
    need_object_cell_attachment = "attachments" in tables and "object_cell_id" not in attachment_columns
    if need_resolved_at or need_knowledge or need_object_cells or need_object_cell_attachment:
        reasons = []
        if need_resolved_at:
            reasons.append("add issues.resolved_at")
        if need_knowledge:
            reasons.append("create knowledge_entries")
        if need_object_cells:
            reasons.append("create object_cells")
        if need_object_cell_attachment:
            reasons.append("add attachments.object_cell_id")
        _backup_before_upgrade(Path(engine.url.database), "; ".join(reasons))
    if need_resolved_at:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE issues ADD COLUMN resolved_at DATETIME"))
            # Older resolved issues had no separate close timestamp. Their last update
            # is the best available approximation; new transitions record the exact time.
            connection.execute(text("UPDATE issues SET resolved_at = updated_at WHERE status = '已解决'"))
    if need_knowledge:
        from .models import KnowledgeEntry

        KnowledgeEntry.__table__.create(engine, checkfirst=True)
    if need_object_cells:
        from .models import ObjectCell

        ObjectCell.__table__.create(engine, checkfirst=True)
    if need_object_cell_attachment:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE attachments ADD COLUMN object_cell_id INTEGER REFERENCES object_cells(id)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_attachments_object_cell_id ON attachments (object_cell_id)"))


def _backup_before_upgrade(source_path: Path, reason: str):
    root = Path(current_app.config["BACKUP_FOLDER"]).resolve()
    root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    folder = root / f"schema-{stamp}"
    folder.mkdir()
    target_path = folder / "app.db"
    with sqlite3.connect(f"file:{source_path.as_posix()}?mode=ro", uri=True) as source:
        with sqlite3.connect(target_path) as target:
            source.backup(target)
    digest = hashlib.sha256(target_path.read_bytes()).hexdigest()
    (folder / "manifest.json").write_text(
        json.dumps({"created_at": datetime.now().isoformat(), "database_sha256": digest, "reason": reason}, indent=2),
        encoding="utf-8",
    )
