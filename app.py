"""
app.py - Entry point utama aplikasi Media Monitoring OJK Jawa Barat

Menjalankan:
    python app.py

Akses website di: http://localhost:5000
"""

import os
import logging
from dotenv import load_dotenv
from flask import Flask, render_template
from flask_login import login_required
from routes.auth import role_required
from config import get_config
from database.extensions import db, login_manager
from routes import register_blueprints

# Muat variabel environment dari file .env (wajib sebelum config dibaca)
load_dotenv()

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

    # Pastikan direktori instance ada (fallback jika read-only / Vercel)
    try:
        os.makedirs(app.instance_path, exist_ok=True)
    except Exception:
        pass

    # Inisialisasi ekstensi
    db.init_app(app)
    login_manager.init_app(app)

    # Konfigurasi user_loader untuk Flask-Login
    from database.models import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    # Daftarkan semua blueprint
    register_blueprints(app)

    # Daftarkan error handlers
    register_error_handlers(app)

    # Daftarkan context processor (variabel global template)
    register_context_processors(app)

    # Inisialisasi database (safely wrapped)
    with app.app_context():
        try:
            initialize_database(app)
        except Exception as err:
            logger.warning(f"Inisialisasi database ditunda/gagal: {err}")

    # Setup logger buffer untuk Terminal Console Web Vercel
    try:
        from services.terminal_logger import setup_terminal_logger
        setup_terminal_logger()
    except Exception as err:
        logger.warning(f"Setup terminal logger failed: {err}")

    logger.info(f"Aplikasi '{config.APP_NAME}' berhasil dibuat (env={env})")
    return app


def initialize_database(app=None):
    """
    Membuat semua tabel database dan mengisi data awal.
    Dipanggil sekali saat aplikasi pertama kali dijalankan.
    """
    from database.models import User
    from services.database_service import DatabaseService
    from werkzeug.security import generate_password_hash

    # Buat semua tabel jika belum ada
    db.create_all()

    # Migrasi manual - cek kolom dulu sebelum ALTER agar tidak ada silent exception setiap startup
    try:
        from sqlalchemy import text, inspect as sa_inspect

        inspector = sa_inspect(db.engine)
        existing_columns = [col["name"] for col in inspector.get_columns("users")]

        if "nama_lengkap" not in existing_columns:
            db.session.execute(
                text("ALTER TABLE users ADD COLUMN nama_lengkap VARCHAR(150)")
            )
            db.session.commit()
            logger.info("Kolom 'nama_lengkap' berhasil ditambahkan ke tabel users.")

        if "last_login" not in existing_columns:
            db.session.execute(text("ALTER TABLE users ADD COLUMN last_login DATETIME"))
            db.session.commit()
            logger.info("Kolom 'last_login' berhasil ditambahkan ke tabel users.")

        # Migrasi kolom ai_checked pada tabel berita
        berita_columns = [col["name"] for col in inspector.get_columns("berita")]
        if "ai_checked" not in berita_columns:
            db.session.execute(
                text(
                    "ALTER TABLE berita ADD COLUMN ai_checked BOOLEAN DEFAULT 0 NOT NULL"
                )
            )
            db.session.commit()
            logger.info("Kolom 'ai_checked' berhasil ditambahkan ke tabel berita.")
    except Exception as e:
        db.session.rollback()
        logger.warning(f"Migrasi kolom users gagal: {e}")

    logger.info("Skema database berhasil diinisialisasi.")

    # Isi keyword default jika tabel kosong
    try:
        DatabaseService.inisialisasi_keyword_default()
    except Exception as e:
        logger.warning(f"Inisialisasi keyword default gagal: {e}")

    # Buat user & data seeder default jika belum ada user
    try:
        if User.query.count() == 0:
            import os
            import json
            from database.models import Berita, Keyword
            from datetime import datetime

            seed_path = os.path.join(os.path.dirname(__file__), "seed_data.json")
            if os.path.exists(seed_path):
                with open(seed_path, "r", encoding="utf-8") as f:
                    seed_data = json.load(f)

                # Import users
                for u_data in seed_data.get("users", []):
                    if not User.query.filter_by(username=u_data["username"]).first():
                        u = User(
                            username=u_data["username"],
                            nama_lengkap=u_data.get("nama_lengkap"),
                            password_hash=u_data["password_hash"],
                            role=u_data["role"],
                            status=u_data.get("status", "aktif"),
                        )
                        db.session.add(u)

                # Import keywords
                for kw_data in seed_data.get("keywords", []):
                    if not Keyword.query.filter_by(kata=kw_data["kata"]).first():
                        kw = Keyword(kata=kw_data["kata"], aktif=kw_data.get("aktif", True))
                        db.session.add(kw)

                # Import & sync berita (seluruh data dari seed_data.json)
                for b_data in seed_data.get("berita", []):
                    existing = Berita.query.filter_by(link=b_data["link"]).first()
                    if not existing:
                        b = Berita(
                            judul=b_data["judul"],
                            link=b_data["link"],
                            media=b_data.get("media"),
                            tanggal=datetime.fromisoformat(b_data["tanggal"]) if b_data.get("tanggal") else None,
                            isi=b_data.get("isi"),
                            ringkasan=b_data.get("ringkasan"),
                            gambar_url=b_data.get("gambar_url"),
                            sentimen=b_data.get("sentimen"),
                            topik=b_data.get("topik"),
                            wilayah=b_data.get("wilayah"),
                            narasumber=b_data.get("narasumber"),
                            bulan=b_data.get("bulan"),
                            tahun=b_data.get("tahun"),
                            triwulan=b_data.get("triwulan"),
                            status=b_data.get("status", "aktif"),
                            keyword=b_data.get("keyword"),
                        )
                        db.session.add(b)
                    else:
                        # Update isi, gambar, dan ringkasan jika di database online masih kosong
                        if not existing.isi and b_data.get("isi"):
                            existing.isi = b_data.get("isi")
                        if not existing.gambar_url and b_data.get("gambar_url"):
                            existing.gambar_url = b_data.get("gambar_url")
                        if not existing.ringkasan and b_data.get("ringkasan"):
                            existing.ringkasan = b_data.get("ringkasan")

                # Pastikan password_hash super_admin, angga, dan pemimpin di-reset ke 'ojkjabar2026'
                for target_uname in ["super_admin", "angga", "pemimpin"]:
                    u_obj = User.query.filter_by(username=target_uname).first()
                    if u_obj:
                        u_obj.password_hash = generate_password_hash("ojkjabar2026")

                db.session.commit()
                logger.info("Database berhasil diisi dari seed_data.json dan password user disesuaikan!")
            else:
                default_admin = User(
                    username="super_admin",
                    password_hash=generate_password_hash("ojkjabar2026"),
                    role="super_admin",
                    status="aktif",
                )
                db.session.add(default_admin)
                db.session.commit()
                logger.info("Default user 'super_admin' berhasil dibuat.")
    except Exception as e:
        db.session.rollback()
        logger.warning(f"Pembuatan user default ditunda: {e}")

    # Bersihkan duplikat yang sudah ada di database (bukan di Vercel serverless)
    import threading
    import os

    def _startup_dedup(flask_app):
        import time

        time.sleep(3)
        with flask_app.app_context():
            try:
                from services.dedup_service import DeduplicateService

                hasil = DeduplicateService.jalankan_semua(threshold_mirip=0.88)
                if hasil["total_dihapus"] > 0:
                    logger.info(
                        f"[Startup Dedup] Selesai: {hasil['total_dihapus']} berita duplikat dihapus"
                    )
            except Exception as e:
                logger.warning(f"[Startup Dedup] Gagal: {e}")

    # JANGAN jalankan background thread jika di environment Vercel
    is_vercel = os.environ.get("VERCEL") == "1" or os.environ.get("VERCEL_ENV") is not None
    if app is not None and os.environ.get("WERKZEUG_RUN_MAIN") != "true" and not is_vercel:
        # Thread 1: Deduplikasi startup
        t_dedup = threading.Thread(target=_startup_dedup, args=(app,), daemon=True)
        t_dedup.start()

        # Thread 2: AI Review Service — selalu aktif
        def _start_ai_review(flask_app):
            import time

            time.sleep(5)
            from services.ai_review_service import AIReviewService

            AIReviewService.start(flask_app)

        t_ai = threading.Thread(target=_start_ai_review, args=(app,), daemon=True)
        t_ai.start()


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
        from services.config_service import ConfigService
        from services.notifikasi_service import NotifikasiService
        from flask_login import current_user

        unread_count = 0
        if current_user and hasattr(current_user, "is_authenticated") and current_user.is_authenticated:
            try:
                unread_count = NotifikasiService.hitung_belum_dibaca()
            except Exception:
                pass


        return {
            "app_name": Config.APP_NAME,
            "app_subtitle": Config.APP_SUBTITLE,
            "app_version": Config.APP_VERSION,
            "now": datetime.now(),
            "system_config": ConfigService.get_config(),
            "unread_notif_count": unread_count,
        }


# === Buat instance Flask global (diperlukan oleh Gunicorn / Koyeb / Vercel) ===
_flask_env = os.environ.get("FLASK_ENV", "production")
app = create_app(_flask_env)


@app.route("/init-db")
def manual_init_db():
    """Endpoint manual untuk inisialisasi tabel & seeder database Supabase/Neon."""
    from flask import jsonify, request
    from werkzeug.security import generate_password_hash
    import json
    from database.models import User, Berita, Keyword
    from datetime import datetime

    try:
        # Buat tabel jika belum ada
        db.create_all()

        # Bersihkan data lama jika kurang dari 258 berita agar 100% identik dengan lokal
        if Berita.query.count() < 258 or request.args.get("clean") == "1":
            db.session.query(Berita).delete()
            db.session.query(Keyword).delete()
            db.session.query(User).delete()
            db.session.commit()

        seed_path = os.path.join(os.path.dirname(__file__), "seed_data.json")
        if os.path.exists(seed_path):
            with open(seed_path, "r", encoding="utf-8") as f:
                seed_data = json.load(f)

            # Import users
            for u_data in seed_data.get("users", []):
                if not User.query.filter_by(username=u_data["username"]).first():
                    u = User(
                        username=u_data["username"],
                        nama_lengkap=u_data.get("nama_lengkap"),
                        password_hash=u_data["password_hash"],
                        role=u_data["role"],
                        status=u_data.get("status", "aktif"),
                    )
                    db.session.add(u)

            # Import keywords
            for kw_data in seed_data.get("keywords", []):
                if not Keyword.query.filter_by(kata=kw_data["kata"]).first():
                    kw = Keyword(kata=kw_data["kata"], aktif=kw_data.get("aktif", True))
                    db.session.add(kw)

            # Import seluruh 258 berita
            for b_data in seed_data.get("berita", []):
                if not Berita.query.filter_by(link=b_data["link"]).first():
                    b = Berita(
                        judul=b_data["judul"],
                        link=b_data["link"],
                        media=b_data.get("media"),
                        jenis_media=b_data.get("jenis_media"),
                        tanggal=datetime.fromisoformat(b_data["tanggal"]) if b_data.get("tanggal") else None,
                        isi=b_data.get("isi"),
                        ringkasan=b_data.get("ringkasan"),
                        gambar_url=b_data.get("gambar_url"),
                        sentimen=b_data.get("sentimen"),
                        topik=b_data.get("topik"),
                        wilayah=b_data.get("wilayah"),
                        narasumber=b_data.get("narasumber"),
                        bulan=b_data.get("bulan"),
                        tahun=b_data.get("tahun"),
                        triwulan=b_data.get("triwulan"),
                        status=b_data.get("status", "aktif"),
                        keyword=b_data.get("keyword"),
                    )
                    db.session.add(b)

        # Reset password user default ke 'ojkjabar2026'
        for uname in ["super_admin", "angga", "pemimpin"]:
            u_obj = User.query.filter_by(username=uname).first()
            if u_obj:
                u_obj.password_hash = generate_password_hash("ojkjabar2026")
                u_obj.status = "aktif"

        db.session.commit()

        user_count = User.query.count()
        berita_count = Berita.query.count()
        return jsonify({
            "status": "success",
            "message": f"Database Vercel berhasil disinkronisasi 100% dengan Lokal! Total User: {user_count}, Total Berita: {berita_count}",
            "users": [u.username for u in User.query.all()]
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/debug-sentimen")
def debug_sentimen():
    """Endpoint diagnostik transparan untuk mengecek statistik sentimen & berita negatif di database server."""
    from database.models import Berita
    from database.extensions import db
    total = Berita.query.filter_by(status="aktif").count()
    negatif = Berita.query.filter_by(status="aktif", sentimen="Negatif").all()
    positif = Berita.query.filter_by(status="aktif", sentimen="Positif").count()
    netral = Berita.query.filter_by(status="aktif", sentimen="Netral").count()

    return jsonify({
        "database_engine": db.engine.name,
        "total_berita_aktif": total,
        "total_positif": positif,
        "total_netral": netral,
        "total_negatif": len(negatif),
        "detail_berita_negatif": [
            {
                "id": b.id,
                "judul": b.judul,
                "wilayah": b.wilayah,
                "media": b.media,
                "tanggal": b.tanggal.strftime("%Y-%m-%d") if b.tanggal else None,
                "ai_checked": b.ai_checked,
                "ai_last_checked": b.ai_last_checked.strftime("%Y-%m-%d %H:%M:%S") if b.ai_last_checked else None
            } for b in negatif
        ]
    })


from datetime import datetime
_last_auto_ai_check = datetime.min


@app.before_request
def auto_ai_review_trigger():
    """Jalankan AI review otomatis 24/7 tanpa memblokir response halaman."""
    from flask import request as flask_request
    global _last_auto_ai_check

    # Skip untuk static assets, favicon, dll agar tidak memperlambat
    path = flask_request.path
    if any(path.startswith(p) for p in ["/static", "/favicon", "/api/status-ai"]):
        return

    now = datetime.utcnow()
    if (now - _last_auto_ai_check).total_seconds() > 15:
        _last_auto_ai_check = now
        try:
            import threading
            from services.ai_review_service import AIReviewService
            # Jalankan di daemon thread agar tidak memblokir response
            t = threading.Thread(
                target=AIReviewService._proses_batch,
                args=(app,),
                daemon=True
            )
            t.start()
        except Exception as err:
            logger.warning(f"Auto AI Review Error: {err}")


@app.route("/api/status-sentimen", methods=["GET"])
@app.route("/api/status-sentimen/", methods=["GET"])
def status_sentimen():
    """Endpoint diagnostik transparan publik untuk mengecek statistik sentimen & berita negatif di database Vercel."""
    from flask import jsonify
    from database.models import Berita
    from database.extensions import db
    try:
        total = Berita.query.filter_by(status="aktif").count()
        negatif = Berita.query.filter_by(status="aktif", sentimen="Negatif").all()
        positif = Berita.query.filter_by(status="aktif", sentimen="Positif").count()
        netral = Berita.query.filter_by(status="aktif", sentimen="Netral").count()

        return jsonify({
            "status": "success",
            "database_engine": db.engine.name,
            "total_berita_aktif": total,
            "total_positif": positif,
            "total_netral": netral,
            "total_negatif": len(negatif),
            "detail_berita_negatif": [
                {
                    "id": b.id,
                    "judul": b.judul,
                    "wilayah": b.wilayah,
                    "media": b.media,
                    "tanggal": b.tanggal.strftime("%Y-%m-%d") if b.tanggal else None,
                    "ai_checked": b.ai_checked,
                    "ai_last_checked": b.ai_last_checked.strftime("%Y-%m-%d %H:%M:%S") if b.ai_last_checked else None
                } for b in negatif
            ]
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/status-ai", methods=["GET", "POST"])
@app.route("/api/status-ai/", methods=["GET", "POST"])
@app.route("/api/status_ai", methods=["GET", "POST"])
@app.route("/api/status_ai/", methods=["GET", "POST"])
@app.route("/api/status ai", methods=["GET", "POST"])
@app.route("/api/status%20ai", methods=["GET", "POST"])
@app.route("/status-ai", methods=["GET", "POST"])
@app.route("/status-ai/", methods=["GET", "POST"])
@login_required
@role_required("super_admin")
def status_ai():
    """Terminal Live Console UI & Status AI (Khusus Super Admin)."""
    from flask import request, jsonify, render_template
    from database.models import Berita
    from database.extensions import db
    try:
        total = Berita.query.filter_by(status="aktif").count()
        negatif = Berita.query.filter_by(status="aktif", sentimen="Negatif").count()
        positif = Berita.query.filter_by(status="aktif", sentimen="Positif").count()
        netral = Berita.query.filter_by(status="aktif", sentimen="Netral").count()
        sudah_dicek = Berita.query.filter_by(status="aktif", ai_checked=True).count()
        belum_dicek = Berita.query.filter_by(status="aktif", ai_checked=False).count()

        pct_checked = round((sudah_dicek / total * 100), 1) if total > 0 else 0
        pct_positif = round((positif / total * 100), 1) if total > 0 else 0
        pct_netral = round((netral / total * 100), 1) if total > 0 else 0
        pct_negatif = round((negatif / total * 100), 1) if total > 0 else 0

        terakhir_dicek = (
            Berita.query
            .filter(Berita.ai_last_checked.isnot(None))
            .order_by(Berita.ai_last_checked.desc())
            .first()
        )

        data = {
            "status": "ok",
            "server_time": datetime.now().strftime("%H:%M:%S"),
            "database": {
                "total_berita": total,
                "positif": positif,
                "netral": netral,
                "negatif": negatif,
                "pct_positif": pct_positif,
                "pct_netral": pct_netral,
                "pct_negatif": pct_negatif,
            },
            "ai_review": {
                "sudah_dicek": sudah_dicek,
                "belum_dicek": belum_dicek,
                "pct_checked": pct_checked,
                "terakhir_dicek": terakhir_dicek.ai_last_checked.isoformat() if terakhir_dicek and terakhir_dicek.ai_last_checked else None,
                "judul_terakhir": terakhir_dicek.judul if terakhir_dicek else None,
                "sentimen_terakhir": terakhir_dicek.sentimen if terakhir_dicek else None,
                "media_terakhir": terakhir_dicek.media if terakhir_dicek else None,
                "wilayah_terakhir": terakhir_dicek.wilayah if terakhir_dicek else None,
            }
        }

        # Format JSON jika diminta API
        if request.args.get("format") == "json" or request.headers.get("Accept") == "application/json":
            return jsonify(data)

        # Standar browser request: tampilkan Terminal Console UI (Super Admin)
        return render_template("status_ai.html", data=data, active_page="status_ai")
    except Exception as e:
        if request.args.get("format") == "json" or request.headers.get("Accept") == "application/json":
            return jsonify({"status": "error", "message": str(e)}), 500
        return f"Gagal memuat Terminal Console: {e}", 500


@app.route("/api/status-ai/logs", methods=["GET", "POST"])
@app.route("/api/status-ai/logs/", methods=["GET", "POST"])
@app.route("/api/status_ai/logs", methods=["GET", "POST"])
@app.route("/api/status_ai/logs/", methods=["GET", "POST"])
@app.route("/api/status ai/logs", methods=["GET", "POST"])
@app.route("/api/status%20ai/logs", methods=["GET", "POST"])
@login_required
@role_required("super_admin")
def status_ai_logs():
    """Streaming log real-time ke Terminal Console Web (Khusus Super Admin)."""
    from flask import request, jsonify
    from services.terminal_logger import get_terminal_logs
    from database.models import Berita
    try:
        since_id = int(request.args.get("since_id", 0))
        logs = get_terminal_logs(since_id)

        total = Berita.query.filter_by(status="aktif").count()
        negatif = Berita.query.filter_by(status="aktif", sentimen="Negatif").count()
        positif = Berita.query.filter_by(status="aktif", sentimen="Positif").count()
        netral = Berita.query.filter_by(status="aktif", sentimen="Netral").count()
        sudah_dicek = Berita.query.filter_by(status="aktif", ai_checked=True).count()
        belum_dicek = Berita.query.filter_by(status="aktif", ai_checked=False).count()

        pct_checked = round((sudah_dicek / total * 100), 1) if total > 0 else 0

        return jsonify({
            "status": "ok",
            "logs": logs,
            "database": {
                "total_berita": total,
                "positif": positif,
                "netral": netral,
                "negatif": negatif,
            },
            "ai_review": {
                "sudah_dicek": sudah_dicek,
                "belum_dicek": belum_dicek,
                "pct_checked": pct_checked,
            }
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/run-ai-review", methods=["GET", "POST"])
@app.route("/run-ai-review/", methods=["GET", "POST"])
def manual_run_ai_review():
    """Endpoint manual / Vercel Cron Job untuk menjalankan siklus analisis & pembersihan AI di Vercel."""
    from flask import jsonify
    try:
        from services.ai_review_service import AIReviewService
        AIReviewService._proses_batch(app)
        return jsonify({
            "status": "success",
            "message": "Siklus AI Review (Prioritas Sentimen Negatif) berhasil dijalankan di Vercel!"
        }), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# === Entry Point (lokal development) ===
if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("  Media Monitoring OJK Jawa Barat")
    logger.info("  Versi: 1.0.0")
    logger.info("  Akses: http://localhost:5000")
    logger.info("=" * 60)
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=(_flask_env == "development"),
        use_reloader=(_flask_env == "development"),
    )
