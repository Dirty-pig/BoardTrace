import sqlite3

from app import create_app


def test_existing_markdown_html_is_refreshed_without_changing_note_timestamp(app, tmp_path):
    from app.extensions import db
    from app.migrations import upgrade_markdown_lists
    from app.models import DailySummary, SystemSetting

    with app.app_context():
        note = DailySummary(content_md="选型：\n* 工作电压\n* 钳位电压", rendered_html="<p>选型：<br>\n* 工作电压</p>")
        db.session.add(note)
        db.session.delete(db.session.get(SystemSetting, "markdown_lists_version"))
        db.session.commit()
        original_updated_at = note.updated_at
        upgrade_markdown_lists()
        db.session.refresh(note)
        assert "<ul>" in note.rendered_html
        assert "<li>钳位电压</li>" in note.rendered_html
        assert note.updated_at == original_updated_at
        assert list((tmp_path / "backups").glob("schema-*/app.db"))


def test_existing_database_gets_object_cell_schema_and_backup(tmp_path):
    database = tmp_path / "legacy.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE issues (id INTEGER PRIMARY KEY, status TEXT, updated_at DATETIME)"
        )
        connection.execute("CREATE TABLE attachments (id INTEGER PRIMARY KEY)")

    backup_dir = tmp_path / "backups"
    create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database.as_posix()}",
            "UPLOAD_FOLDER": tmp_path / "uploads",
            "BACKUP_FOLDER": backup_dir,
        }
    )

    with sqlite3.connect(database) as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        attachment_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(attachments)")
        }
    assert "object_cells" in tables
    assert "object_cell_id" in attachment_columns
    assert list(backup_dir.glob("schema-*/app.db"))


def test_existing_knowledge_table_gets_project_cell_link_and_backup(tmp_path):
    database = tmp_path / "existing.db"
    settings = {
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database.as_posix()}",
        "UPLOAD_FOLDER": tmp_path / "uploads",
        "BACKUP_FOLDER": tmp_path / "backups",
    }
    create_app(settings)
    with sqlite3.connect(database) as connection:
        connection.execute("DROP TABLE knowledge_entries")
        connection.execute(
            "CREATE TABLE knowledge_entries ("
            "id INTEGER PRIMARY KEY, title VARCHAR(200) NOT NULL, content_md TEXT NOT NULL, "
            "rendered_html TEXT NOT NULL, source_issue_id INTEGER, source_cell_id INTEGER, "
            "author_id INTEGER, created_at DATETIME, updated_at DATETIME, deleted_at DATETIME)"
        )
    create_app(settings)
    with sqlite3.connect(database) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(knowledge_entries)")}
        indexes = {row[1] for row in connection.execute("PRAGMA index_list(knowledge_entries)")}
    assert "source_object_cell_id" in columns
    assert "ix_knowledge_entries_source_object_cell_id" in indexes
    assert list((tmp_path / "backups").glob("schema-*/app.db"))
