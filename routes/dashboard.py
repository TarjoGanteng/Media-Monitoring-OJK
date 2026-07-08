"""
routes/dashboard.py - Blueprint untuk halaman dashboard utama
"""

from flask import Blueprint, render_template
from services.dashboard_service import DashboardService
import json

bp = Blueprint("dashboard", __name__)


from flask_login import login_required

@bp.route("/dashboard")
@login_required
def index():
    """
    Halaman dashboard utama.
    Menampilkan statistik ringkasan, berita terbaru, topik terbanyak,
    media teraktif, dan trend harian.
    """
    # Ambil semua data yang dibutuhkan dari DashboardService
    statistik = DashboardService.get_statistik_utama()
    berita_terbaru = DashboardService.get_berita_terbaru(limit=5)
    topik_terbanyak = DashboardService.get_topik_terbanyak(limit=5)
    media_teraktif = DashboardService.get_media_teraktif(limit=5)
    kota_terbanyak = DashboardService.get_kota_terbanyak(limit=5)
    trend_data = DashboardService.get_trend_harian(hari=7)

    # Serialisasi data chart ke JSON untuk digunakan Chart.js
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
