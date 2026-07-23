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
