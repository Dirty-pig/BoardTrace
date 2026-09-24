import sqlite3

from app import create_app


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
