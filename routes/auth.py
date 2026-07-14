"""
routes/auth.py - Blueprint untuk Autentikasi dan Manajemen Role
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash
from functools import wraps
from database.models import User
from database.extensions import db

bp = Blueprint("auth", __name__)


# --- Decorator RBAC ---
def role_required(*roles):
    """
    Decorator untuk membatasi akses berdasarkan role.
    Contoh: @role_required('super_admin', 'admin')
    """

    def wrapper(fn):
        @wraps(fn)
        def decorated_view(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("auth.login"))
            if current_user.role not in roles:
                flash("Anda tidak memiliki akses ke halaman tersebut.", "error")
                return redirect(url_for("dashboard.index"))
            return fn(*args, **kwargs)

        return decorated_view

    return wrapper


@bp.route("/", methods=["GET", "POST"])
@bp.route("/login", methods=["GET", "POST"])
def login():
    # Jika sudah login, arahkan ke dashboard
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        remember = True if request.form.get("remember") else False

        user = User.query.filter_by(username=username).first()

        # Verifikasi
        if not user or not check_password_hash(user.password_hash, password):
            flash("Username atau password salah.", "error")
            return redirect(url_for("auth.login"))

        if user.status != "aktif":
            flash("Akun Anda telah dinonaktifkan.", "error")
            return redirect(url_for("auth.login"))

        # Simpan waktu login terakhir (WIB = UTC+7)
        from datetime import datetime, timezone, timedelta
        import uuid

        wib = timezone(timedelta(hours=7))
        user.last_login = datetime.now(wib).replace(tzinfo=None)
        db.session.commit()

        # Buat token unik per sesi login untuk kontrol motivasi
        from flask import session as flask_session

        flask_session["login_token"] = str(uuid.uuid4())

        # Login berhasil
        login_user(user, remember=remember)
        return redirect(url_for("dashboard.index"))

    return render_template("auth/login.html")


@bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))


@bp.route("/api/check-session")
def check_session():
    """Endpoint polling ringan untuk mengecek apakah sesi user masih valid."""
    from flask import jsonify
    from database.extensions import db

    if not current_user.is_authenticated:
        return jsonify({"status": "unauthenticated"}), 401

    # Reload user langsung dari database untuk data terkini
    user = db.session.get(User, current_user.id)
    if not user:
        logout_user()
        return jsonify({"status": "deleted"}), 401

    if user.status != "aktif":
        logout_user()
        return jsonify({"status": "nonaktif"}), 401

    return jsonify({"status": "ok"}), 200
