"""
routes/halaman.py - Blueprint untuk halaman-halaman statis/placeholder
Berisi: Analisis, Trend, Sebaran Wilayah, Media, Laporan, Notifikasi, Pencarian
"""

import json
from flask import Blueprint, render_template, request, redirect, url_for, flash
from services.dashboard_service import DashboardService
from services.berita_service import BeritaService

from routes.auth import role_required
from flask_login import login_required, current_user

bp = Blueprint("halaman", __name__)

@bp.route("/fix-db")
@login_required
@role_required("super_admin")
def fix_db():
    from database.extensions import db
    from database.models import Berita
    from sqlalchemy import func
    try:
        # 1. Cek tanggal paling lama
        oldest_berita = db.session.query(func.min(Berita.tanggal)).scalar()
        
        # 2. Cek duplikasi judul
        duplikat_count = db.session.query(Berita.judul, func.count(Berita.id)).group_by(Berita.judul).having(func.count(Berita.id) > 1).count()
        
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


@bp.route("/trend")
@login_required
@role_required("super_admin", "admin", "pemimpin")
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
@role_required("super_admin", "admin", "pemimpin")
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
@role_required("super_admin", "admin", "pemimpin")
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
@role_required("super_admin", "admin", "pemimpin")
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
    # Data notifikasi dummy
    notifikasi_list = [
        {
            "tipe": "warning",
            "judul": "Berita Negatif Meningkat",
            "pesan": "Jumlah berita negatif hari ini meningkat 15% dibandingkan kemarin.",
            "waktu": "09:30 WIB",
            "icon": "bi-exclamation-triangle",
        },
        {
            "tipe": "info",
            "judul": "Crawling Selesai",
            "pesan": "Sistem berhasil mengumpulkan 23 berita baru dari Google News RSS.",
            "waktu": "09:15 WIB",
            "icon": "bi-info-circle",
        },
        {
            "tipe": "success",
            "judul": "Topik Pinjaman Online Trending",
            "pesan": "Topik Pinjaman Online menjadi topik utama hari ini di 8 media.",
            "waktu": "08:30 WIB",
            "icon": "bi-graph-up",
        },
        {
            "tipe": "danger",
            "judul": "Media Baru Terdeteksi",
            "pesan": "3 media baru memberitakan OJK Jabar hari ini.",
            "waktu": "08:00 WIB",
            "icon": "bi-newspaper",
        },
    ]
    return render_template(
        "notifikasi/index.html",
        notifikasi_list=notifikasi_list,
        active_page="notifikasi",
    )


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
    daftar_user = User.query.order_by(User.created_at.asc()).all()
    return render_template(
        "pengaturan/index.html",
        active_page="pengaturan",
        daftar_user=daftar_user,
    )

@bp.route("/pengaturan/tambah_user", methods=["POST"])
@login_required
@role_required("super_admin")
def tambah_user():
    import re
    from database.extensions import db
    from database.models import User
    from werkzeug.security import generate_password_hash

    nama_lengkap = request.form.get("nama_lengkap", "").strip()
    username     = request.form.get("username", "").strip()
    password     = request.form.get("password", "")
    role         = request.form.get("role", "staff")
    status       = request.form.get("status", "aktif")

    if User.query.filter_by(username=username).first():
        flash(f"Username '{username}' sudah digunakan.", "danger")
        return redirect(url_for("halaman.pengaturan", tab="manajemen-user"))

    errors = []
    if len(password) < 8: errors.append("minimal 8 karakter")
    if not re.search(r'[A-Z]', password): errors.append("mengandung huruf besar")
    if not re.search(r'\d', password): errors.append("mengandung angka")
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
    import re
    from database.extensions import db
    from database.models import User
    from werkzeug.security import generate_password_hash

    user = User.query.get_or_404(user_id)
    nama_lengkap = request.form.get("nama_lengkap", "").strip()
    username     = request.form.get("username", "").strip()
    password     = request.form.get("password", "")
    role         = request.form.get("role", user.role)
    status       = request.form.get("status", user.status)

    existing = User.query.filter_by(username=username).first()
    if existing and existing.id != user_id:
        flash(f"Username '{username}' sudah digunakan user lain.", "danger")
        return redirect(url_for("halaman.pengaturan", tab="manajemen-user"))

    user.nama_lengkap = nama_lengkap
    user.username     = username
    user.role         = role
    user.status       = status

    if password:
        errors = []
        if len(password) < 8: errors.append("minimal 8 karakter")
        if not re.search(r'[A-Z]', password): errors.append("mengandung huruf besar")
        if not re.search(r'\d', password): errors.append("mengandung angka")
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
    from database.extensions import db
    from database.models import User

    if user_id == current_user.id:
        flash("Tidak bisa menghapus akun sendiri.", "danger")
        return redirect(url_for("halaman.pengaturan", tab="manajemen-user"))

    user = User.query.get_or_404(user_id)
    username = user.username
    db.session.delete(user)
    db.session.commit()
    flash(f"✅ User '{username}' berhasil dihapus.", "success")
    return redirect(url_for("halaman.pengaturan", tab="manajemen-user"))


@bp.route("/pengaturan/update_profil", methods=["POST"])
@login_required
def update_profil():
    from database.extensions import db
    from flask import redirect, url_for, flash
    from flask_login import current_user
    
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
def update_password():
    import re
    from database.extensions import db
    from flask import redirect, url_for, flash, request
    from flask_login import current_user
    from werkzeug.security import check_password_hash, generate_password_hash
    
    old_password     = request.form.get("old_password", "")
    new_password     = request.form.get("new_password", "")
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
    
    if not re.search(r'[A-Z]', new_password):
        flash("Password baru harus mengandung setidaknya satu huruf besar.", "danger")
        return redirect(url_for("halaman.pengaturan"))
    
    if not re.search(r'\d', new_password):
        flash("Password baru harus mengandung setidaknya satu angka.", "danger")
        return redirect(url_for("halaman.pengaturan"))
    
    if new_password == old_password:
        flash("Password baru tidak boleh sama dengan password lama.", "danger")
        return redirect(url_for("halaman.pengaturan"))
    
    current_user.password_hash = generate_password_hash(new_password)
    db.session.commit()
    flash("✅ Password berhasil diubah.", "success")
    return redirect(url_for("halaman.pengaturan"))
