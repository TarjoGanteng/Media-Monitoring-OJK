"""
routes/auth.py - Blueprint untuk Autentikasi dan Manajemen Role
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
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
                return redirect(url_for('auth.login'))
            if current_user.role not in roles:
                flash("Anda tidak memiliki akses ke halaman tersebut.", "error")
                return redirect(url_for('dashboard.index'))
            return fn(*args, **kwargs)
        return decorated_view
    return wrapper

@bp.route("/", methods=["GET", "POST"])
@bp.route("/login", methods=["GET", "POST"])
def login():
    # Jika sudah login, arahkan ke dashboard
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        remember = True if request.form.get("remember") else False

        user = User.query.filter_by(username=username).first()

        # Verifikasi
        if not user or not check_password_hash(user.password_hash, password):
            flash("Username atau password salah.", "error")
            return redirect(url_for('auth.login'))

        if user.status != "aktif":
            flash("Akun Anda telah dinonaktifkan.", "error")
            return redirect(url_for('auth.login'))

        # Login berhasil
        login_user(user, remember=remember)
        return redirect(url_for('dashboard.index'))

    return render_template("auth/login.html")


@bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))
