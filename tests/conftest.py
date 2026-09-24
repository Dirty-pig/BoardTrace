from pathlib import Path

import pytest

from app import create_app
from app.extensions import db


@pytest.fixture()
def app(tmp_path: Path):
    app = create_app({
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
        "UPLOAD_FOLDER": tmp_path / "uploads",
        "BACKUP_FOLDER": tmp_path / "backups",
    })
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def initialized_client(client):
    response = client.post("/initialize", data={
        "system_name": "板迹测试",
        "username": "root",
        "password": "safe-password-123",
        "confirm_password": "safe-password-123",
    }, follow_redirects=True)
    assert response.status_code == 200
    return client
