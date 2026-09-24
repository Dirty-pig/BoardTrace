from datetime import timedelta, timezone
from pathlib import Path

from flask import Flask

from config import Config
from .extensions import csrf, db, login_manager


def create_app(test_config=None):
    app = Flask(__name__, static_folder="../prototype", static_url_path="/static")
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)

    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)
    Path(app.config["BACKUP_FOLDER"]).mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "请先登录。"
    login_manager.login_message_category = "info"

    from .models import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    from .auth import bp as auth_bp
    from .main import bp as main_bp
    from .api import bp as api_bp
    from .knowledge import bp as knowledge_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp, url_prefix="/api/v1")
    app.register_blueprint(knowledge_bp)

    from .display import pcb_label

    app.add_template_filter(pcb_label)

    @app.template_filter("cn_time")
    def cn_time(value, fmt="%Y-%m-%d %H:%M"):
        if value is None:
            return "—"
        return value.replace(tzinfo=timezone.utc).astimezone(timezone(timedelta(hours=8))).strftime(fmt)

    @app.get("/healthz")
    def healthz():
        try:
            db.session.execute(db.text("SELECT 1"))
            return {"status": "ok"}, 200
        except Exception:
            return {"status": "error"}, 503

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data: blob:; style-src 'self'; "
            "script-src 'self'; connect-src 'self'; font-src 'self'; object-src 'none'; "
            "base-uri 'self'; frame-ancestors 'none'",
        )
        return response

    @app.errorhandler(413)
    def upload_too_large(_error):
        return "上传总量超过 100MB，请减少文件数量或压缩后重试。", 413

    with app.app_context():
        from .migrations import upgrade_schema
        upgrade_schema()
        db.create_all()
        from .services import ensure_defaults
        ensure_defaults()

    return app
