"""
app.py - Entry point utama aplikasi Media Monitoring OJK Jawa Barat

Menjalankan:
    python app.py

Akses website di: http://localhost:5000
"""

import os
import logging
from flask import Flask, render_template
from config import get_config
from database.extensions import db, login_manager
from routes import register_blueprints

# Konfigurasi logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def create_app(env: str = None) -> Flask:
    """
    Application Factory - membuat instance Flask dengan konfigurasi yang tepat.

    Args:
        env: Environment ('development', 'production', 'testing')

    Returns:
        Instance Flask yang sudah dikonfigurasi
    """
    if env is None:
        env = os.environ.get("FLASK_ENV", "development")

    app = Flask(__name__)

    # Muat konfigurasi
    config = get_config(env)
    app.config.from_object(config)

    # Pastikan direktori instance ada
    os.makedirs(app.instance_path, exist_ok=True)

    # Inisialisasi ekstensi
    db.init_app(app)
    login_manager.init_app(app)

    # Konfigurasi user_loader untuk Flask-Login
    from database.models import User
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Daftarkan semua blueprint
    register_blueprints(app)

    # Daftarkan error handlers
    register_error_handlers(app)

    # Daftarkan context processor (variabel global template)
    register_context_processors(app)

    # Inisialisasi database
    with app.app_context():
        initialize_database()

    logger.info(f"Aplikasi '{config.APP_NAME}' berhasil dibuat (env={env})")
    return app


def initialize_database():
    """
    Membuat semua tabel database dan mengisi data awal.
    Dipanggil sekali saat aplikasi pertama kali dijalankan.
    """
    from database.models import Berita, CrawlLog, Keyword, User
    from services.database_service import DatabaseService
    from werkzeug.security import generate_password_hash

    # Buat semua tabel jika belum ada
    db.create_all()
    logger.info("Skema database berhasil diinisialisasi.")

    # Isi keyword default jika tabel kosong
    DatabaseService.inisialisasi_keyword_default()
    
    # Buat user super_admin default jika belum ada user
    if User.query.count() == 0:
        default_admin = User(
            username="super_admin",
            password_hash=generate_password_hash("ojkjabar2026"),
            role="super_admin",
            status="aktif"
        )
        db.session.add(default_admin)
        db.session.commit()
        logger.info("Default user 'super_admin' berhasil dibuat (password: ojkjabar2026).")


def register_error_handlers(app: Flask):
    """Mendaftarkan custom error handler."""

    @app.errorhandler(404)
    def not_found(e):
        """Handler untuk halaman tidak ditemukan."""
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def server_error(e):
        """Handler untuk internal server error."""
        logger.error(f"Server error: {e}")
        return render_template("errors/500.html"), 500


def register_context_processors(app: Flask):
    """
    Mendaftarkan context processor yang menyediakan variabel global
    yang dapat diakses di semua template Jinja2.
    """

    @app.context_processor
    def inject_globals():
        """Menyuntikkan variabel global ke semua template."""
        from config import Config
        from datetime import datetime

        return {
            "app_name": Config.APP_NAME,
            "app_subtitle": Config.APP_SUBTITLE,
            "app_version": Config.APP_VERSION,
            "now": datetime.now(),
        }


# === Entry Point ===
if __name__ == "__main__":
    app = create_app("development")
    logger.info("=" * 60)
    logger.info("  Media Monitoring OJK Jawa Barat")
    logger.info("  Versi: 1.0.0")
    logger.info("  Akses: http://localhost:5000")
    logger.info("=" * 60)
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True,
        use_reloader=True,
    )
