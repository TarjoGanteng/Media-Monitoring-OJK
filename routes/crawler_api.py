"""
routes/crawler_api.py - Blueprint untuk API endpoint crawler
Menyediakan endpoint untuk menjalankan crawler dan melihat status.
"""

from flask import Blueprint, jsonify, request
from flask_login import login_required
from services.crawler_service import CrawlerService
from services.database_service import DatabaseService

bp = Blueprint("crawler_api", __name__, url_prefix="/api/crawler")


@bp.route("/run", methods=["POST"])
@login_required
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

        # Trigger AI Review langsung secara synchronous untuk memverifikasi sentimen & menghapus berita non-OJK Jabar
        try:
            from flask import current_app
            from services.ai_review_service import AIReviewService
            AIReviewService._proses_batch(current_app)
        except Exception as ai_err:
            pass

        return jsonify(
            {
                "success": True,
                "message": f"Crawling selesai. Ditemukan {total_ditemukan}, disimpan {total_disimpan} berita baru. AI Review langsung memverifikasi & membersihkan berita.",
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
@login_required
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
@login_required
def tambah_keyword():
    """Menambahkan keyword baru."""
    data = request.get_json(silent=True) or {}
    kata = data.get("kata", "").strip()

    if not kata:
        return jsonify(
            {"success": False, "message": "Keyword tidak boleh kosong."}
        ), 400

    berhasil, pesan = DatabaseService.tambah_keyword(kata)
    status_code = 200 if berhasil else 409
    return jsonify({"success": berhasil, "message": pesan}), status_code


@bp.route("/log", methods=["GET"])
@login_required
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
@login_required
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
@login_required
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
        Berita.query.filter((Berita.gambar_url.is_(None)) | (Berita.gambar_url == ""))
        .order_by(Berita.tanggal.desc())
        .limit(limit)
        .all()
    )

    if not berita_tanpa_gambar:
        return jsonify(
            {
                "success": True,
                "message": "Semua berita sudah punya gambar.",
                "diupdate": 0,
            }
        )

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
            detail.append(
                {"id": berita.id, "judul": berita.judul[:50], "gambar": gambar[:60]}
            )
        else:
            gagal += 1

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500

    return jsonify(
        {
            "success": True,
            "message": f"Berhasil update {diupdate} gambar berita.",
            "diupdate": diupdate,
            "gagal": gagal,
            "total_diproses": len(berita_tanpa_gambar),
            "detail": detail,
        }
    )


# =============================================================================
# ENDPOINT AI — Google Gemini Integration
# =============================================================================


@bp.route("/ai/status", methods=["GET"])
@login_required
def ai_status():
    """
    Cek status dan koneksi multi-provider AI.
    Urutan prioritas: Cohere -> Groq -> OpenRouter -> Gemini.
    Mengembalikan info provider mana yang aktif dan siap digunakan.
    """
    from services.ai_service import gemini

    hasil = gemini.cek_koneksi()
    return jsonify(
        {
            "success": hasil["ok"],
            "pesan": hasil["pesan"],
            "model": hasil["model"],
            "provider": hasil.get("provider"),
            "tersedia": hasil["ok"],
        }
    )


@bp.route("/ai/analisis-batch", methods=["POST"])
@login_required
def ai_analisis_batch():
    """
    Jalankan analisis AI (Gemini) terhadap berita yang belum dianalisis
    atau belum memiliki ringkasan AI.

    Body JSON opsional:
        {
          "limit": 20,          // Jumlah berita per batch (default 20, max 50)
          "hanya_tanpa_ringkasan": true  // Jika true, prioritaskan berita tanpa ringkasan
        }

    Response: statistik {diproses, berhasil, gagal}
    """
    from database.extensions import db
    from database.models import Berita
    from services.ai_service import gemini

    if not gemini.is_available():
        return jsonify(
            {
                "success": False,
                "message": "Gemini AI tidak tersedia. Pastikan GEMINI_API_KEY sudah diisi di file .env",
            }
        ), 503

    data = request.get_json(silent=True) or {}
    limit = min(int(data.get("limit", 20)), 50)  # Batasi maks 50 per batch
    hanya_tanpa_ringkasan = data.get("hanya_tanpa_ringkasan", False)

    # Query berita yang perlu dianalisis ulang
    query = Berita.query.filter_by(status="aktif")
    if hanya_tanpa_ringkasan:
        query = query.filter((Berita.ringkasan.is_(None)) | (Berita.ringkasan == ""))

    from sqlalchemy import case

    order_case = case(
        (Berita.sentimen == "Negatif", 1),
        (Berita.sentimen == "Positif", 2),
        (Berita.sentimen == "Netral", 3),
        else_=4,
    )
    berita_list = query.order_by(order_case, Berita.tanggal.desc()).limit(limit).all()

    if not berita_list:
        return jsonify(
            {
                "success": True,
                "message": "Tidak ada berita yang perlu dianalisis.",
                "statistik": {"diproses": 0, "berhasil": 0, "gagal": 0},
            }
        )

    # Jalankan analisis batch
    stats = gemini.analisis_batch(berita_list, delay_per_request=1.5)

    # Commit semua perubahan sekaligus
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify(
            {"success": False, "message": f"Gagal menyimpan hasil: {str(e)}"}
        ), 500

    return jsonify(
        {
            "success": True,
            "message": (
                f"Analisis AI selesai: {stats['berhasil']} berhasil, "
                f"{stats['gagal']} gagal dari {stats['diproses']} berita."
            ),
            "statistik": stats,
        }
    )


@bp.route("/ai/analisis-satu/<int:berita_id>", methods=["POST"])
@login_required
def ai_analisis_satu(berita_id):
    """
    Analisis ulang satu berita spesifik menggunakan Gemini AI.
    Berguna untuk mengoreksi hasil analisis rule-based pada berita tertentu.
    """
    from database.extensions import db
    from database.models import Berita
    from services.ai_service import gemini

    if not gemini.is_available():
        return jsonify(
            {
                "success": False,
                "message": "Gemini AI tidak tersedia. Cek GEMINI_API_KEY di file .env.",
            }
        ), 503

    berita = db.session.get(Berita, berita_id)
    if not berita:
        return jsonify({"success": False, "message": "Berita tidak ditemukan."}), 404

    result = gemini.analisis_berita(berita.judul, berita.isi, berita.ringkasan, berita.media)
    if not result:
        return jsonify(
            {
                "success": False,
                "message": "Analisis AI gagal. Coba lagi beberapa saat.",
            }
        ), 500

    # Update berita
    berita.sentimen = result["sentimen"]
    berita.topik = result["topik"]
    if result.get("wilayah"):
        berita.wilayah = result["wilayah"]
    if result.get("ringkasan"):
        berita.ringkasan = result["ringkasan"]
    if result.get("narasumber"):
        berita.narasumber = result["narasumber"]

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": f"Gagal menyimpan: {str(e)}"}), 500

    return jsonify(
        {
            "success": True,
            "message": f"Analisis AI berhasil untuk berita ID {berita_id}.",
            "hasil": result,
        }
    )


# =============================================================================
# ENDPOINT DEDUPLIKASI BERITA
# =============================================================================


@bp.route("/dedup/preview", methods=["GET"])
@login_required
def dedup_preview():
    """
    Preview jumlah duplikat yang ada di database tanpa menghapus apapun.
    Gunakan ini dulu sebelum menjalankan penghapusan.
    """
    from services.dedup_service import DeduplicateService

    try:
        hasil = DeduplicateService.preview()
        return jsonify({"success": True, "data": hasil})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@bp.route("/dedup/hapus", methods=["POST"])
@login_required
def dedup_hapus():
    """
    Jalankan deduplikasi 3 lapis:
    1. Duplikat URL (link sama persis)
    2. Duplikat judul (teks sama persis)
    3. Near-duplicate (judul sangat mirip >= threshold)

    Body JSON opsional:
        {
          "mode": "semua" | "url" | "judul" | "mirip",
          "threshold": 0.88
        }
    """
    from services.dedup_service import DeduplicateService

    data = request.get_json(silent=True) or {}
    mode = data.get("mode", "semua")
    threshold = float(data.get("threshold", 0.88))

    try:
        if mode == "url":
            hasil = DeduplicateService.hapus_duplikat_link()
            pesan = f"Lapis 1 (URL) selesai: {hasil['dihapus']} berita dihapus dari {hasil['grup']} grup."
        elif mode == "judul":
            hasil = DeduplicateService.hapus_duplikat_judul_exact()
            pesan = f"Lapis 2 (Judul) selesai: {hasil['dihapus']} berita dihapus dari {hasil['grup']} grup."
        elif mode == "mirip":
            hasil = DeduplicateService.hapus_duplikat_mirip(threshold=threshold)
            pesan = f"Lapis 3 (Near-dup) selesai: {hasil['dihapus']} berita dihapus dari {hasil['grup']} grup."
        else:  # semua
            hasil = DeduplicateService.jalankan_semua(threshold_mirip=threshold)
            pesan = f"Deduplikasi selesai: {hasil['total_dihapus']} berita duplikat dihapus."

        return jsonify({"success": True, "message": pesan, "hasil": hasil})

    except Exception as e:
        return jsonify({"success": False, "message": f"Error: {str(e)}"}), 500


@bp.route("/status-sentimen-public", methods=["GET"])
def status_sentimen_public():
    """Endpoint diagnostik publik transparan untuk mengecek statistik sentimen & berita negatif di Vercel."""
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
