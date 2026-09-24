import os
import secrets
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


def _secret_key():
    configured = os.environ.get("PROBLEM_SYSTEM_SECRET")
    if configured:
        return configured
    secret_path = BASE_DIR / "data" / "secret.key"
    secret_path.parent.mkdir(parents=True, exist_ok=True)
    if secret_path.exists():
        return secret_path.read_text(encoding="utf-8").strip()
    value = secrets.token_urlsafe(48)
    secret_path.write_text(value, encoding="utf-8")
    return value


class Config:
    SECRET_KEY = _secret_key()
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{(BASE_DIR / 'data' / 'app.db').as_posix()}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAX_CONTENT_LENGTH = 100 * 1024 * 1024
    UPLOAD_FOLDER = BASE_DIR / "data" / "uploads"
    BACKUP_FOLDER = BASE_DIR / "data" / "backups"
    ITEMS_PER_PAGE = 20
    MAX_ITEMS_PER_PAGE = 100
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 12
    WTF_CSRF_TIME_LIMIT = None
    TEMPLATES_AUTO_RELOAD = True
