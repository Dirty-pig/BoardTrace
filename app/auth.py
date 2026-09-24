from datetime import timedelta

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_user, logout_user

from .extensions import db
from .models import User, utcnow
from .services import audit, setting, set_setting


bp = Blueprint("auth", __name__)
ph = PasswordHasher()


@bp.before_app_request
def require_initialization():
    endpoint = request.endpoint or ""
    if endpoint.startswith("static") or endpoint in {"auth.initialize", "auth.login", "healthz"}:
        return None
    if User.query.count() == 0:
        return redirect(url_for("auth.initialize"))
    return None


@bp.route("/initialize", methods=["GET", "POST"])
def initialize():
    if User.query.count() > 0:
        return redirect(url_for("auth.login"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        system_name = request.form.get("system_name", "板迹").strip() or "板迹"
        if len(username) < 3:
            flash("ROOT用户名至少3个字符。", "error")
        elif len(password) < 10:
            flash("密码至少10个字符。", "error")
        elif password != confirm:
            flash("两次输入的密码不一致。", "error")
        else:
            user = User(username=username, password_hash=ph.hash(password), role="root")
            db.session.add(user)
            set_setting("system_name", system_name)
            audit("system.initialize", user_id=None, detail=f"ROOT={username}")
            db.session.commit()
            login_user(user, remember=False)
            flash("系统初始化完成。", "success")
            return redirect(url_for("main.dashboard"))
    return render_template("auth/initialize.html", system_name=setting("system_name", "板迹"))


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    if User.query.count() == 0:
        return redirect(url_for("auth.initialize"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter(db.func.lower(User.username) == username.lower()).first()
        now = utcnow()
        if user and user.locked_until and user.locked_until > now:
            flash("登录失败次数过多，请稍后再试。", "error")
            return render_template("auth/login.html")
        valid = False
        if user and user.active:
            try:
                valid = ph.verify(user.password_hash, password)
            except VerifyMismatchError:
                valid = False
        if not valid:
            if user:
                user.login_failures += 1
                if user.login_failures >= 5:
                    user.locked_until = now + timedelta(minutes=15)
                    user.login_failures = 0
                audit("auth.login_failed", user_id=user.id, detail=username)
                db.session.commit()
            flash("用户名或密码错误。", "error")
        else:
            user.login_failures = 0
            user.locked_until = None
            user.last_login_at = now
            login_user(user, remember=False)
            audit("auth.login", user_id=user.id)
            db.session.commit()
            return redirect(request.args.get("next") or url_for("main.dashboard"))
    return render_template("auth/login.html", system_name=setting("system_name", "板迹"))


@bp.post("/logout")
def logout():
    if current_user.is_authenticated:
        audit("auth.logout")
        db.session.commit()
    logout_user()
    return redirect(url_for("auth.login"))
