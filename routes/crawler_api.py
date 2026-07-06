"""
routes/crawler_api.py - Blueprint untuk API endpoint crawler
Menyediakan endpoint untuk menjalankan crawler dan melihat status.
"""

from flask import Blueprint, jsonify, request
from services.crawler_service import CrawlerService
from services.database_service import DatabaseService

bp = Blueprint("crawler_api", __name__, url_prefix="/api/crawler")


@bp.route("/run", methods=["POST"])
def run_crawler():
    """
    Endpoint untuk menjalankan crawler.
    Body JSON opsional: {"keywords": ["keyword1", "keyword2"]}
    Jika tidak ada body, gunakan semua keyword aktif dari database.
    """
    data = request.get_json(silent=True) or {}
    keywords = data.get("keywords", None)

    service = CrawlerService()

    try:
        if keywords:
            # Crawl keyword spesifik yang diberikan
            hasil_list = []
            for kw in keywords:
                hasil = service.crawl_satu_keyword(kw)
                hasil_list.append(hasil)
        else:
            # Crawl semua keyword aktif
            hasil_list = service.crawl_semua_keyword()

        # Agregat total
        total_ditemukan = sum(h["jumlah_ditemukan"] for h in hasil_list)
        total_disimpan = sum(h["jumlah_disimpan"] for h in hasil_list)
        total_duplikat = sum(h["jumlah_duplikat"] for h in hasil_list)

        return jsonify(
            {
                "success": True,
                "message": f"Crawling selesai. Ditemukan {total_ditemukan}, disimpan {total_disimpan} berita baru.",
                "detail": hasil_list,
                "total": {
                    "ditemukan": total_ditemukan,
                    "disimpan": total_disimpan,
                    "duplikat": total_duplikat,
                },
            }
        )

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@bp.route("/keywords", methods=["GET"])
def get_keywords():
    """Mengambil daftar semua keyword crawler."""
    keywords = DatabaseService.get_semua_keyword(hanya_aktif=False)
    return jsonify(
        {
            "success": True,
            "keywords": [
                {"id": kw.id, "kata": kw.kata, "aktif": kw.aktif} for kw in keywords
            ],
        }
    )


@bp.route("/keywords", methods=["POST"])
def tambah_keyword():
    """Menambahkan keyword baru."""
    data = request.get_json(silent=True) or {}
    kata = data.get("kata", "").strip()

    if not kata:
        return jsonify({"success": False, "message": "Keyword tidak boleh kosong."}), 400

    berhasil, pesan = DatabaseService.tambah_keyword(kata)
    status_code = 200 if berhasil else 409
    return jsonify({"success": berhasil, "message": pesan}), status_code


@bp.route("/log", methods=["GET"])
def get_crawl_log():
    """Mengambil log crawling terbaru."""
    limit = request.args.get("limit", 20, type=int)
    logs = DatabaseService.get_crawl_log_terbaru(limit=limit)

    return jsonify(
        {
            "success": True,
            "logs": [
                {
                    "id": log.id,
                    "keyword": log.keyword,
                    "jumlah_ditemukan": log.jumlah_ditemukan,
                    "jumlah_disimpan": log.jumlah_disimpan,
                    "jumlah_duplikat": log.jumlah_duplikat,
                    "status": log.status,
                    "pesan": log.pesan,
                    "created_at": log.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                }
                for log in logs
            ],
        }
    )


@bp.route("/status", methods=["GET"])
def get_status():
    """Mengambil statistik umum crawler."""
    service = CrawlerService()
    stats = service.get_statistik_crawl()

    return jsonify(
        {
            "success": True,
            "statistik": {
                "total_log": stats["total_log"],
                "total_berhasil": stats["total_berhasil"],
                "total_gagal": stats["total_gagal"],
                "crawl_terakhir": (
                    stats["crawl_terakhir"].strftime("%Y-%m-%d %H:%M:%S")
                    if stats["crawl_terakhir"]
                    else None
                ),
            },
        }
    )


@bp.route("/fetch-images", methods=["POST"])
def fetch_images():
    """
    Endpoint untuk mengambil gambar berita yang belum punya gambar_url.
    Menggunakan Playwright untuk resolve Google News redirect URLs.
    Body JSON opsional: {"limit": 10}
    """
    from database.extensions import db
    from database.models import Berita
    from crawler.image_resolver import resolve_and_fetch_image, fetch_og_image

    data = request.get_json(silent=True) or {}
    limit = data.get("limit", 10)  # Default 10 agar tidak terlalu lama

    berita_tanpa_gambar = (
        Berita.query.filter(
            (Berita.gambar_url == None) | (Berita.gambar_url == "")
        )
        .order_by(Berita.tanggal.desc())
        .limit(limit)
        .all()
    )

    if not berita_tanpa_gambar:
        return jsonify({"success": True, "message": "Semua berita sudah punya gambar.", "diupdate": 0})

    diupdate = 0
    gagal = 0
    detail = []

    for berita in berita_tanpa_gambar:
        link = berita.link or ""
        gambar = None

        if "google.com" in link:
            # Gunakan Playwright untuk resolve Google News URL
            result = resolve_and_fetch_image(link)
            gambar = result.get("gambar_url")
            # Simpan actual_url jika ada (untuk referensi)
            if result.get("actual_url"):
                berita.link = result["actual_url"]  # Update ke URL asli
        else:
            # URL sudah asli, langsung fetch og:image
            from crawler.image_resolver import fetch_og_image
            gambar = fetch_og_image(link)

        if gambar:
            berita.gambar_url = gambar
            diupdate += 1
            detail.append({"id": berita.id, "judul": berita.judul[:50], "gambar": gambar[:60]})
        else:
            gagal += 1

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500

    return jsonify({
        "success": True,
        "message": f"Berhasil update {diupdate} gambar berita.",
        "diupdate": diupdate,
        "gagal": gagal,
        "total_diproses": len(berita_tanpa_gambar),
        "detail": detail,
    })
