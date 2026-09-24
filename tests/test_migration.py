import sqlite3

from app import create_app


def test_existing_issue_schema_is_backed_up_and_upgraded(tmp_path):
    database = tmp_path / "legacy.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE issues (id INTEGER PRIMARY KEY, status TEXT, updated_at DATETIME)")
        connection.execute("INSERT INTO issues (status, updated_at) VALUES ('已解决', '2026-09-20 08:00:00')")

    backups = tmp_path / "backups"
    create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database.as_posix()}",
        "UPLOAD_FOLDER": tmp_path / "uploads",
        "BACKUP_FOLDER": backups,
    })
    with sqlite3.connect(database) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(issues)")}
        resolved = connection.execute("SELECT resolved_at FROM issues WHERE id=1").fetchone()[0]
        knowledge_created = connection.execute("SELECT name FROM sqlite_master WHERE name='knowledge_entries'").fetchone()
    assert "resolved_at" in columns
    assert resolved == "2026-09-20 08:00:00"
    assert knowledge_created is not None
    snapshots = list(backups.glob("schema-*/app.db"))
    assert len(snapshots) == 1
    with sqlite3.connect(snapshots[0]) as connection:
        assert "resolved_at" not in {row[1] for row in connection.execute("PRAGMA table_info(issues)")}
        assert connection.execute("SELECT name FROM sqlite_master WHERE name='knowledge_entries'").fetchone() is None
