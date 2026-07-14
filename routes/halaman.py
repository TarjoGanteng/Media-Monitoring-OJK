"""
routes/halaman.py - Blueprint untuk halaman-halaman statis/placeholder
Berisi: Analisis, Trend, Sebaran Wilayah, Media, Laporan, Notifikasi, Pencarian
"""

import re
import json
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import func

from database.extensions import db
from database.models import User, Berita
from services.dashboard_service import DashboardService
from services.berita_service import BeritaService
from routes.auth import role_required

bp = Blueprint("halaman", __name__)


@bp.route("/fix-db")
@login_required
@role_required("super_admin")
def fix_db():
    try:
        oldest_berita = db.session.query(func.min(Berita.tanggal)).scalar()
        duplikat_count = (
            db.session.query(Berita.judul, func.count(Berita.id))
            .group_by(Berita.judul)
            .having(func.count(Berita.id) > 1)
            .count()
        )
        return f"Berita paling lama: {oldest_berita.strftime('%d/%m/%Y %H:%M:%S') if oldest_berita else 'Tidak ada'}<br>Jumlah judul berita yang terindikasi duplikat: {duplikat_count}"
    except Exception as e:
        return f"Gagal: {str(e)}"


@bp.route("/analisis")
@login_required
@role_required("super_admin", "pemimpin")
def analisis():
    """Halaman Analisis - Menampilkan visualisasi data mendalam."""
    statistik = DashboardService.get_statistik_utama()
    topik_terbanyak = DashboardService.get_topik_terbanyak(limit=5)
    media_teraktif = DashboardService.get_media_teraktif(limit=5)
    trend_data = DashboardService.get_trend_harian(hari=7)
    trend_json = json.dumps(trend_data)

    trend_mingguan = DashboardService.get_trend_mingguan(minggu=4)
    trend_mingguan_json = json.dumps(trend_mingguan)

    trend_bulanan = DashboardService.get_trend_bulanan(bulan=6)
    trend_bulanan_json = json.dumps(trend_bulanan)

    sebaran_media = DashboardService.get_sebaran_media()

    return render_template(
        "analisis/index.html",
        statistik=statistik,
        topik_terbanyak=topik_terbanyak,
        media_teraktif=media_teraktif,
        trend_json=trend_json,
        trend_mingguan_json=trend_mingguan_json,
        trend_bulanan_json=trend_bulanan_json,
        sebaran_media=sebaran_media,
        active_page="analisis",
    )


@bp.route("/analisis/ai-insight")
@login_required
def ai_insight():
    """
    Endpoint JSON untuk 4 Insight AI & Rekomendasi di halaman Analisis.
    Diambil secara async oleh JavaScript agar tidak memperlambat load halaman.
    """
    from flask import jsonify

    try:
        # Kumpulkan data aktual dari database
        statistik = DashboardService.get_statistik_utama()
        topik_list = DashboardService.get_topik_terbanyak(limit=5)
        media_list = DashboardService.get_media_teraktif(limit=3)
        trend_7hr = DashboardService.get_trend_harian(hari=7)

        # Hitung perubahan tren sentimen (hari ini vs kemarin)
        total_d = trend_7hr.get("total", [])
        positif_d = trend_7hr.get("positif", [])
        negatif_d = trend_7hr.get("negatif", [])

        def pct_change(series):
            if len(series) >= 2 and series[-2] > 0:
                return round((series[-1] - series[-2]) / series[-2] * 100, 1)
            return 0

        perubahan_total = pct_change(total_d)
        perubahan_positif = pct_change(positif_d)
        perubahan_negatif = pct_change(negatif_d)

        topik_utama = topik_list[0]["topik"] if topik_list else "Regulasi"
        topik_ke2 = topik_list[1]["topik"] if len(topik_list) > 1 else "-"
        media_utama = media_list[0]["media"] if media_list else "-"
        topik_negatif = "-"  # default

        # Cari topik dengan persentase negatif tertinggi (dari data mentah)
        try:
            from sqlalchemy import func as sqlfunc
            from database.models import Berita

            neg_topik = (
                db.session.query(Berita.topik, sqlfunc.count(Berita.id).label("jml"))
                .filter(
                    Berita.status == "aktif",
                    Berita.sentimen == "Negatif",
                    Berita.topik.isnot(None),
                )
                .group_by(Berita.topik)
                .order_by(sqlfunc.count(Berita.id).desc())
                .first()
            )
            if neg_topik:
                topik_negatif = neg_topik.topik
        except Exception:
            pass

        # Prompt ke Gemini
        prompt = f"""Anda adalah analis media senior untuk OJK (Otoritas Jasa Keuangan) Jawa Barat, Indonesia.
Berdasarkan data pemberitaan berikut, hasilkan tepat 4 insight & rekomendasi yang berbeda, spesifik, dan berbasis data.

=== DATA AKTUAL ===
Total berita keseluruhan : {statistik["total"]}
Sentimen Positif         : {statistik["positif"]} ({statistik["pct_positif"]}%)
Sentimen Netral          : {statistik["netral"]} ({statistik["pct_netral"]}%)
Sentimen Negatif         : {statistik["negatif"]} ({statistik["pct_negatif"]}%)
Perubahan total berita (vs kemarin): {perubahan_total:+.1f}%
Perubahan sentimen positif (vs kemarin): {perubahan_positif:+.1f}%
Perubahan sentimen negatif (vs kemarin): {perubahan_negatif:+.1f}%
Topik utama  : {topik_utama}
Topik ke-2   : {topik_ke2}
Topik negatif terbanyak: {topik_negatif}
Media paling aktif: {media_utama}

=== FORMAT RESPONS (JSON WAJIB, tanpa teks lain) ===
{{
  "insights": [
    {{
      "tipe": "positif",
      "ikon": "bi-graph-up-arrow",
      "teks": "<insight 1 tentang sentimen/tren positif, spesifik dan berbasis angka di atas>"
    }},
    {{
      "tipe": "negatif",
      "ikon": "bi-bullseye",
      "teks": "<insight 2 tentang risiko/isu negatif yang perlu diwaspadai OJK>"
    }},
    {{
      "tipe": "peringatan",
      "ikon": "bi-megaphone",
      "teks": "<insight 3 tentang topik yang paling banyak pemberitaan negatif dan rekomendasi tindakan>"
    }},
    {{
      "tipe": "informasi",
      "ikon": "bi-bar-chart",
      "teks": "<insight 4 tentang media atau distribusi pemberitaan yang perlu diperhatikan>"
    }}
  ]
}}

Gunakan bahasa Indonesia formal, singkat (maks 20 kata per insight), dan langsung ke inti."""

        try:
            import google.generativeai as genai
            import json as _json
            from config import Config

            genai.configure(api_key=Config.GEMINI_API_KEY)
            model = genai.GenerativeModel(
                "gemini-3.5-flash",
                generation_config={
                    "temperature": 0.3,
                    "response_mime_type": "application/json",
                },
            )
            resp = model.generate_content(prompt)
            data = _json.loads(resp.text)
            return jsonify({"success": True, "insights": data.get("insights", [])})
        except Exception:
            # Fallback: hasilkan insight berbasis data tanpa AI
            insights = [
                {
                    "tipe": "positif",
                    "ikon": "bi-graph-up-arrow",
                    "teks": f"Sentimen positif {statistik['pct_positif']}% ({statistik['positif']} berita), "
                    f"{'meningkat' if perubahan_positif > 0 else 'menurun'} {abs(perubahan_positif):.1f}% dibanding kemarin.",
                },
                {
                    "tipe": "negatif",
                    "ikon": "bi-bullseye",
                    "teks": f"Topik '{topik_utama}' mendominasi pemberitaan, perlu pemantauan intensif.",
                },
                {
                    "tipe": "peringatan",
                    "ikon": "bi-megaphone",
                    "teks": f"Topik '{topik_negatif}' mencatat pemberitaan negatif terbanyak — disarankan respons proaktif.",
                },
                {
                    "tipe": "informasi",
                    "ikon": "bi-bar-chart",
                    "teks": f"'{media_utama}' menjadi media paling aktif memberitakan isu OJK saat ini.",
                },
            ]
            return jsonify({"success": True, "insights": insights, "fallback": True})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route("/trend")
@login_required
@role_required("super_admin", "pemimpin")
def trend():
    """Halaman Trend - grafik tren berita dari waktu ke waktu."""
    # Data trend 30 hari terakhir
    trend_harian = DashboardService.get_trend_harian(hari=30)
    # Data trend 6 bulan terakhir
    trend_bulanan = DashboardService.get_trend_bulanan(bulan=6)

    statistik = DashboardService.get_statistik_utama()

    return render_template(
        "trend/index.html",
        trend_harian_json=json.dumps(trend_harian),
        trend_bulanan_json=json.dumps(trend_bulanan),
        statistik=statistik,
        active_page="trend",
    )


@bp.route("/wilayah")
@login_required
@role_required("super_admin", "pemimpin")
def wilayah():
    """Halaman Sebaran Wilayah - peta dan daftar kota dengan berita terbanyak."""
    sebaran = DashboardService.get_sebaran_wilayah()
    return render_template(
        "wilayah/index.html",
        sebaran=sebaran,
        sebaran_json=json.dumps(sebaran),
        active_page="wilayah",
    )


@bp.route("/media")
@login_required
@role_required("super_admin", "pemimpin")
def media():
    """Halaman Media - daftar media yang paling aktif memberitakan OJK."""
    sebaran_media = DashboardService.get_sebaran_media()
    return render_template(
        "media/index.html",
        sebaran_media=sebaran_media,
        active_page="media",
    )


@bp.route("/laporan")
@login_required
@role_required("super_admin", "pemimpin")
def laporan():
    """Halaman Laporan - arsip laporan dengan berbagai filter."""
    berita_terbaru = DashboardService.get_berita_terbaru(limit=10)
    statistik = DashboardService.get_statistik_utama()
    return render_template(
        "laporan/index.html",
        berita_terbaru=berita_terbaru,
        statistik=statistik,
        active_page="laporan",
    )


@bp.route("/notifikasi")
@login_required
def notifikasi():
    """Halaman Notifikasi - notifikasi penting untuk pimpinan."""
    from services.notifikasi_service import NotifikasiService

    notifikasi_list = NotifikasiService.get_semua_notifikasi(limit=50)
    return render_template(
        "notifikasi/index.html",
        notifikasi_list=notifikasi_list,
        active_page="notifikasi",
    )


@bp.route("/notifikasi/read/<int:notif_id>", methods=["POST"])
@login_required
def notifikasi_read(notif_id):
    from services.notifikasi_service import NotifikasiService

    NotifikasiService.tandai_dibaca(notif_id)
    return redirect(url_for("halaman.notifikasi"))


@bp.route("/notifikasi/read-all", methods=["POST"])
@login_required
def notifikasi_read_all():
    from services.notifikasi_service import NotifikasiService

    NotifikasiService.tandai_semua_dibaca()
    flash("Semua notifikasi telah ditandai sudah dibaca.", "success")
    return redirect(url_for("halaman.notifikasi"))


@bp.route("/pencarian")
@login_required
def pencarian():
    """Halaman Pencarian - cari berita dengan berbagai filter."""
    query_text = request.args.get("q", "")
    page = request.args.get("page", 1, type=int)
    sentimen = request.args.get("sentimen", "")
    media_filter = request.args.get("media", "")
    topik = request.args.get("topik", "")
    tanggal_dari = request.args.get("tanggal_dari", "")
    tanggal_sampai = request.args.get("tanggal_sampai", "")
    wilayah_filter = request.args.get("wilayah", "")

    pagination = None
    hasil = []

    if query_text:
        pagination = BeritaService.cari_berita(
            query_text=query_text,
            sentimen=sentimen or None,
            media=media_filter or None,
            topik=topik or None,
            tanggal_dari=tanggal_dari or None,
            tanggal_sampai=tanggal_sampai or None,
            wilayah=wilayah_filter or None,
            page=page,
        )
        hasil = pagination.items if pagination else []

    daftar_media = BeritaService.get_daftar_media()
    daftar_topik = BeritaService.get_daftar_topik()

    return render_template(
        "pencarian/index.html",
        query_text=query_text,
        pagination=pagination,
        hasil=hasil,
        daftar_media=daftar_media,
        daftar_topik=daftar_topik,
        filter_sentimen=sentimen,
        filter_media=media_filter,
        filter_topik=topik,
        filter_tanggal_dari=tanggal_dari,
        filter_tanggal_sampai=tanggal_sampai,
        filter_wilayah=wilayah_filter,
        active_page="pencarian",
    )


@bp.route("/pengaturan")
@login_required
@role_required("super_admin", "pemimpin", "staff")
def pengaturan():
    """Halaman Pengaturan."""
    from database.models import User
    from sqlalchemy import case

    order_case = case(
        (User.role == "super_admin", 1),
        (User.role == "pemimpin", 2),
        (User.role == "staff", 3),
        else_=4,
    )
    daftar_user = User.query.order_by(order_case, User.created_at.asc()).all()
    return render_template(
        "pengaturan/index.html",
        active_page="pengaturan",
        daftar_user=daftar_user,
    )


@bp.route("/pengaturan/simpan_sistem", methods=["POST"])
@login_required
@role_required("super_admin")
def simpan_sistem():
    from services.config_service import ConfigService

    jam_update = request.form.get("jam_update", "09:00")
    rentang_data = request.form.get("rentang_data", "5")
    crawler_aktif = request.form.get("crawler_aktif") == "true"
    auto_hapus = request.form.get("auto_hapus") == "true"
    ai_aktif = request.form.get("ai_aktif") == "true"

    ConfigService.save_config(
        {
            "jam_update": jam_update,
            "rentang_data": rentang_data,
            "crawler_aktif": crawler_aktif,
            "auto_hapus": auto_hapus,
            "ai_aktif": ai_aktif,
        }
    )

    # Trigger cleanup jika auto_hapus aktif
    if auto_hapus:
        from services.database_service import DatabaseService

        deleted_count = DatabaseService.cleanup_old_data()
        if deleted_count > 0:
            flash(
                f"Berhasil menghapus {deleted_count} data usang sesuai rentang data.",
                "info",
            )

    flash(
        "Konfigurasi sistem berhasil disimpan dan sinkron dengan jadwal auto-crawler.",
        "success",
    )
    return redirect(url_for("halaman.pengaturan", tab="sistem"))


@bp.route("/pengaturan/tambah_user", methods=["POST"])
@login_required
@role_required("super_admin")
def tambah_user():
    nama_lengkap = request.form.get("nama_lengkap", "").strip()
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    role = request.form.get("role", "staff")
    status = request.form.get("status", "aktif")

    if User.query.filter_by(username=username).first():
        flash(f"Username '{username}' sudah digunakan.", "danger")
        return redirect(url_for("halaman.pengaturan", tab="manajemen-user"))

    errors = []
    if len(password) < 8:
        errors.append("minimal 8 karakter")
    if not re.search(r"[A-Z]", password):
        errors.append("mengandung huruf besar")
    if not re.search(r"\d", password):
        errors.append("mengandung angka")
    if errors:
        flash(f"Password harus: {', '.join(errors)}.", "danger")
        return redirect(url_for("halaman.pengaturan", tab="manajemen-user"))

    user_baru = User(
        username=username,
        nama_lengkap=nama_lengkap,
        password_hash=generate_password_hash(password),
        role=role,
        status=status,
    )
    db.session.add(user_baru)
    db.session.commit()
    flash(f"✅ User '{username}' berhasil ditambahkan.", "success")
    return redirect(url_for("halaman.pengaturan", tab="manajemen-user"))


@bp.route("/pengaturan/edit_user/<int:user_id>", methods=["POST"])
@login_required
@role_required("super_admin")
def edit_user(user_id):
    user = db.session.get(User, user_id)
    if not user:
        abort(404)
    nama_lengkap = request.form.get("nama_lengkap", "").strip()
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    role = request.form.get("role", user.role)
    status = request.form.get("status", user.status)

    existing = User.query.filter_by(username=username).first()
    if existing and existing.id != user_id:
        flash(f"Username '{username}' sudah digunakan user lain.", "danger")
        return redirect(url_for("halaman.pengaturan", tab="manajemen-user"))

    user.nama_lengkap = nama_lengkap
    user.username = username
    user.role = role
    user.status = status

    if password:
        errors = []
        if len(password) < 8:
            errors.append("minimal 8 karakter")
        if not re.search(r"[A-Z]", password):
            errors.append("mengandung huruf besar")
        if not re.search(r"\d", password):
            errors.append("mengandung angka")
        if errors:
            flash(f"Password baru harus: {', '.join(errors)}.", "danger")
            return redirect(url_for("halaman.pengaturan", tab="manajemen-user"))
        user.password_hash = generate_password_hash(password)

    db.session.commit()
    flash(f"✅ User '{username}' berhasil diperbarui.", "success")
    return redirect(url_for("halaman.pengaturan", tab="manajemen-user"))


@bp.route("/pengaturan/hapus_user/<int:user_id>", methods=["POST"])
@login_required
@role_required("super_admin")
def hapus_user(user_id):
    if user_id == current_user.id:
        flash("Tidak bisa menghapus akun sendiri.", "danger")
        return redirect(url_for("halaman.pengaturan", tab="manajemen-user"))

    user = db.session.get(User, user_id)
    if not user:
        abort(404)
    username = user.username
    db.session.delete(user)
    db.session.commit()
    flash(f"✅ User '{username}' berhasil dihapus.", "success")
    return redirect(url_for("halaman.pengaturan", tab="manajemen-user"))


@bp.route("/pengaturan/update_profil", methods=["POST"])
@login_required
def update_profil():
    nama_lengkap = request.form.get("nama_lengkap", "").strip()
    if nama_lengkap:
        current_user.nama_lengkap = nama_lengkap
        db.session.commit()
        flash("Profil berhasil diperbarui.", "success")
    else:
        flash("Nama lengkap tidak boleh kosong.", "danger")
    return redirect(url_for("halaman.pengaturan"))


@bp.route("/pengaturan/update_password", methods=["POST"])
@login_required
@role_required("super_admin")
def update_password():
    old_password = request.form.get("old_password", "")
    new_password = request.form.get("new_password", "")
    confirm_password = request.form.get("confirm_password", "")

    # Validasi password saat ini
    if not check_password_hash(current_user.password_hash, old_password):
        flash("❌ Password saat ini salah. Silakan coba lagi.", "danger")
        return redirect(url_for("halaman.pengaturan"))

    # Validasi aturan password baru
    if new_password != confirm_password:
        flash("Konfirmasi password baru tidak cocok.", "danger")
        return redirect(url_for("halaman.pengaturan"))

    if len(new_password) < 8:
        flash("Password baru harus minimal 8 karakter.", "danger")
        return redirect(url_for("halaman.pengaturan"))

    if not re.search(r"[A-Z]", new_password):
        flash("Password baru harus mengandung setidaknya satu huruf besar.", "danger")
        return redirect(url_for("halaman.pengaturan"))

    if not re.search(r"\d", new_password):
        flash("Password baru harus mengandung setidaknya satu angka.", "danger")
        return redirect(url_for("halaman.pengaturan"))

    if new_password == old_password:
        flash("Password baru tidak boleh sama dengan password lama.", "danger")
        return redirect(url_for("halaman.pengaturan"))

    current_user.password_hash = generate_password_hash(new_password)
    db.session.commit()
    flash("✅ Password berhasil diubah.", "success")
    return redirect(url_for("halaman.pengaturan"))
