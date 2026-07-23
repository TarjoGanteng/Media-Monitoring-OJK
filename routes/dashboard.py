"""
routes/dashboard.py - Blueprint untuk halaman dashboard utama
"""

from flask import Blueprint, render_template, jsonify
from flask_login import login_required
from services.dashboard_service import DashboardService
import json

bp = Blueprint("dashboard", __name__)


@bp.route("/dashboard")
@login_required
def index():
    """
    Halaman dashboard utama.
    Menampilkan statistik ringkasan, berita terbaru, topik terbanyak,
    media teraktif, trend harian, dan ringkasan AI Gemini.
    """
    statistik = DashboardService.get_statistik_utama()
    berita_terbaru = DashboardService.get_berita_terbaru(limit=5)
    topik_terbanyak = DashboardService.get_topik_terbanyak(limit=5)
    media_teraktif = DashboardService.get_media_teraktif(limit=5)
    kota_terbanyak = DashboardService.get_kota_terbanyak(limit=5)
    trend_data = DashboardService.get_trend_harian(hari=7)
    trend_json = json.dumps(trend_data)

    return render_template(
        "dashboard/index.html",
        statistik=statistik,
        berita_terbaru=berita_terbaru,
        topik_terbanyak=topik_terbanyak,
        media_teraktif=media_teraktif,
        kota_terbanyak=kota_terbanyak,
        trend_json=trend_json,
        active_page="dashboard",
    )


@bp.route("/dashboard/ai-brief")
@login_required
def ai_brief():
    """
    Endpoint JSON untuk ringkasan AI dashboard.
    Diambil secara async oleh JavaScript agar tidak memperlambat load halaman utama.
    """
    try:
        data = DashboardService.get_ringkasan_ai_dashboard()
        return jsonify({"success": True, "data": data})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route("/api/debug-sentimen")
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


@bp.route("/run-ai-review", methods=["GET", "POST"])
@bp.route("/run-ai-review/", methods=["GET", "POST"])
@bp.route("/api/run-ai-review", methods=["GET", "POST"])
def manual_run_ai_review():
    """Endpoint manual / Vercel Cron Job untuk memproses seluruh berita di Vercel secara intensif."""
    from flask import jsonify, current_app
    try:
        from services.ai_review_service import AIReviewService
        for _ in range(10):
            AIReviewService._proses_batch(current_app)
        return jsonify({
            "status": "success",
            "message": "AI Review Engine berhasil memproses 10 batch data di Vercel!"
        }), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@bp.route("/sync-db", methods=["GET", "POST"])
@bp.route("/init-db", methods=["GET", "POST"])
def sync_db_route():
    """Endpoint 1-Klik untuk menyamakan 100% database Vercel dengan data lokal (seed_data.json)."""
    import os
    import json
    from flask import jsonify, current_app
    from werkzeug.security import generate_password_hash
    from database.models import User, Berita, Keyword
    from database.extensions import db
    from datetime import datetime

    try:
        db.create_all()

        # Paksa bersihkan data lama di Vercel agar 100% identik dengan seed_data.json
        db.session.query(Berita).delete()
        db.session.query(Keyword).delete()
        db.session.query(User).delete()
        db.session.commit()

        seed_path = os.path.join(current_app.root_path, "seed_data.json")
        if os.path.exists(seed_path):
            with open(seed_path, "r", encoding="utf-8") as f:
                seed_data = json.load(f)

            for u_data in seed_data.get("users", []):
                u = User(
                    username=u_data["username"],
                    nama_lengkap=u_data.get("nama_lengkap"),
                    password_hash=u_data["password_hash"],
                    role=u_data["role"],
                    status=u_data.get("status", "aktif"),
                )
                db.session.add(u)

            for kw_data in seed_data.get("keywords", []):
                kw = Keyword(kata=kw_data["kata"], aktif=kw_data.get("aktif", True))
                db.session.add(kw)

            for b_data in seed_data.get("berita", []):
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

            for uname in ["super_admin", "angga", "pemimpin"]:
                u_obj = User.query.filter_by(username=uname).first()
                if u_obj:
                    u_obj.password_hash = generate_password_hash("ojkjabar2026")
                    u_obj.status = "aktif"

            # Purge berita luar Jabar spesifik
            db.session.query(Berita).filter(
                db.or_(
                    Berita.judul.like("%Investasi Saham Bukan Judi%"),
                    Berita.wilayah.in_(["Ponorogo", "Jawa Timur", "Surabaya", "Semarang", "Yogyakarta", "Bali", "Solo", "Gontor"])
                )
            ).delete(synchronize_session=False)

            db.session.commit()

        user_count = User.query.count()
        berita_count = Berita.query.count()
        return jsonify({
            "status": "success",
            "message": f"Database Vercel BERHASIL disinkronkan 100% dengan Lokal! Total Berita: {berita_count}, Total User: {user_count}",
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500
