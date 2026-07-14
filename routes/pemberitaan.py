"""
routes/pemberitaan.py - Blueprint untuk halaman daftar berita dan detail berita
"""

from flask import Blueprint, render_template, request, abort, jsonify
from flask_login import login_required
from services.berita_service import BeritaService

bp = Blueprint("pemberitaan", __name__, url_prefix="/pemberitaan")





@bp.route("/")
@login_required
def index():
    """
    Halaman daftar berita dengan filter dan pagination.
    Mendukung filter: tanggal, media, topik, sentimen, keyword.
    """
    # Ambil parameter filter dari query string
    page = request.args.get("page", 1, type=int)
    tanggal_dari = request.args.get("tanggal_dari", "")
    tanggal_sampai = request.args.get("tanggal_sampai", "")
    media = request.args.get("media", "")
    topik = request.args.get("topik", "")
    sentimen = request.args.get("sentimen", "")
    keyword = request.args.get("keyword", "")
    wilayah = request.args.get("wilayah", "")

    # Ambil data dengan filter
    pagination = BeritaService.get_berita_paginated(
        page=page,
        tanggal_dari=tanggal_dari or None,
        tanggal_sampai=tanggal_sampai or None,
        media=media or None,
        topik=topik or None,
        sentimen=sentimen or None,
        keyword=keyword or None,
        wilayah=wilayah or None,
    )

    # Ambil daftar media, topik, dan wilayah untuk dropdown filter
    daftar_media = BeritaService.get_daftar_media()
    daftar_topik = BeritaService.get_daftar_topik()
    daftar_wilayah = BeritaService.get_daftar_wilayah()

    return render_template(
        "pemberitaan/index.html",
        pagination=pagination,
        berita_list=pagination.items,
        daftar_media=daftar_media,
        daftar_topik=daftar_topik,
        daftar_wilayah=daftar_wilayah,
        # Kirim kembali nilai filter untuk mempertahankan state
        filter_tanggal_dari=tanggal_dari,
        filter_tanggal_sampai=tanggal_sampai,
        filter_media=media,
        filter_topik=topik,
        filter_wilayah=wilayah,
        filter_sentimen=sentimen,
        filter_keyword=keyword,
        active_page="pemberitaan",
    )


@bp.route("/<int:berita_id>")
@login_required
def detail(berita_id: int):
    """
    Halaman detail berita.
    Menampilkan konten lengkap beserta metadata klasifikasi.

    Args:
        berita_id: ID berita yang akan ditampilkan
    """
    berita = BeritaService.get_berita_by_id(berita_id)

    if not berita:
        abort(404)

    # Auto-fetch gambar dan isi jika belum ada (On-Demand Extraction)
    if not berita.isi or not berita.gambar_url:
        try:
            from crawler.image_resolver import resolve_and_fetch_image
            from database.extensions import db

            result = resolve_and_fetch_image(berita.link)
            diupdate = False

            if result.get("actual_url"):
                berita.link = result["actual_url"]
                diupdate = True
            if result.get("gambar_url") and not berita.gambar_url:
                berita.gambar_url = result["gambar_url"]
                diupdate = True
            if result.get("isi") and not berita.isi:
                berita.isi = result["isi"]
                diupdate = True

            if diupdate:
                db.session.commit()
        except Exception:
            # Jika gagal, abaikan saja agar halaman tetap bisa dimuat
            pass

    # Data dummy untuk field AI yang belum tersedia
    dummy_ai = {
        "ringkasan": berita.ringkasan
        or "Ringkasan AI akan tersedia setelah fitur analisis diaktifkan. Artikel ini membahas perkembangan kebijakan OJK terkait pengawasan lembaga keuangan di Jawa Barat.",
        "topik": berita.topik or "Pinjaman Online",
        "sentimen": berita.sentimen or "Netral",
        "narasumber": berita.narasumber
        or "Deputi Komisioner OJK Jabar, Kepala OJK Regional Jawa Barat",
        "wilayah": berita.wilayah or "Bandung",
        "tokoh": ["Deputi Komisioner OJK", "Kepala OJK Regional"],
    }

    return render_template(
        "pemberitaan/detail.html",
        berita=berita,
        dummy_ai=dummy_ai,
        active_page="pemberitaan",
    )


@bp.route("/<int:berita_id>/update_sentimen", methods=["POST"])
@login_required
def update_sentimen(berita_id: int):
    """Update sentimen secara manual oleh super_admin"""
    from flask_login import current_user
    from flask import jsonify

    if current_user.role != "super_admin":
        return jsonify({"status": "error", "message": "Akses ditolak"}), 403

    sentimen = request.form.get("sentimen")
    if sentimen not in ["Positif", "Negatif", "Netral"]:
        return jsonify({"status": "error", "message": "Sentimen tidak valid"}), 400

    berita = BeritaService.get_berita_by_id(berita_id)
    if not berita:
        return jsonify({"status": "error", "message": "Berita tidak ditemukan"}), 404

    from database.extensions import db
    try:

        berita.sentimen = sentimen
        db.session.commit()
        return jsonify({"status": "success", "message": "Sentimen berhasil diperbarui"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500
