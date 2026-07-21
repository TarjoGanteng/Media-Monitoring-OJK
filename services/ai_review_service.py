"""
services/ai_review_service.py
==============================
Background service yang berjalan terus-menerus.
Tugas:
  1. Ambil berita yang BELUM dicek AI (ai_checked = False/NULL)
  2. Step 0: Resolve link, fetch gambar + isi, validasi aksesibilitas
     - Tidak bisa diakses (404/domain mati) → hapus
  3. Lapis 1 Pre-filter: tolak berita tanpa kata kunci kota Jawa Barat
  4. Lapis 2 AI (Cohere): analisis relevansi, sentimen, topik, wilayah, narasumber
     - TIDAK RELEVAN → hapus
     - Relevan → update semua kolom klasifikasi
  5. Ulangi setiap INTERVAL_DETIK
"""

import logging
import threading
import time

logger = logging.getLogger(__name__)

# ─── Konstanta ────────────────────────────────────────────────────────────────
INTERVAL_DETIK = 60  # Cek ulang berita baru setiap 60 detik
BATCH_SIZE = 2  # Jumlah berita yang diproses per siklus (diubah menjadi 2 agar aman dari limit API)
DELAY_PER_REQ = 12.0  # Jeda antar request ke AI (detik)

JABAR_KEYWORDS = [
    "jawa barat",
    "jabar",
    "bandung",
    "bogor",
    "depok",
    "bekasi",
    "cimahi",
    "cirebon",
    "sukabumi",
    "tasikmalaya",
    "banjar",
    "garut",
    "cianjur",
    "ciamis",
    "kuningan",
    "majalengka",
    "pangandaran",
    "purwakarta",
    "subang",
    "sumedang",
    "indramayu",
    "karawang",
    "ojk jabar",
    "ojk jawa barat",
    "ojk bandung",
]


class AIReviewService:
    """
    Background service: mengecek semua berita yang belum dianalisis AI,
    memverifikasi relevansi OJK Jawa Barat, validasi link, dan menghapus
    yang tidak relevan atau tidak bisa diakses.
    """

    _thread: threading.Thread = None
    _running: bool = False

    # ── Migrasi Database ──────────────────────────────────────────────────────
    @staticmethod
    def ensure_ai_checked_column(app):
        """Memastikan kolom ai_checked dan ai_last_checked ada di tabel berita."""
        with app.app_context():
            from sqlalchemy import text, inspect as sa_inspect
            from database.extensions import db

            try:
                inspector = sa_inspect(db.engine)
                cols = [c["name"] for c in inspector.get_columns("berita")]
                modified = False
                if "ai_checked" not in cols:
                    db.session.execute(
                        text(
                            "ALTER TABLE berita ADD COLUMN ai_checked BOOLEAN DEFAULT 0 NOT NULL"
                        )
                    )
                    modified = True
                    logger.info("[AIReview] Kolom 'ai_checked' berhasil ditambahkan.")
                if "ai_last_checked" not in cols:
                    db.session.execute(
                        text(
                            "ALTER TABLE berita ADD COLUMN ai_last_checked DATETIME NULL"
                        )
                    )
                    modified = True
                    logger.info("[AIReview] Kolom 'ai_last_checked' berhasil ditambahkan.")
                
                if modified:
                    db.session.commit()
            except Exception as e:
                db.session.rollback()
                logger.warning(f"[AIReview] Gagal migrasi kolom berita: {e}")

    # ── Worker Loop ───────────────────────────────────────────────────────────
    @classmethod
    def _worker(cls, app):
        """Thread worker utama."""
        logger.info("[AIReview] Background worker dimulai.")
        while cls._running:
            try:
                with app.app_context():
                    cls._proses_batch(app)
            except Exception as e:
                logger.error(f"[AIReview] Error di worker loop: {e}")
            for _ in range(INTERVAL_DETIK):
                if not cls._running:
                    break
                time.sleep(1)
        logger.info("[AIReview] Background worker berhenti.")

    @classmethod
    def _proses_batch(cls, app):
        """
        Ambil BATCH_SIZE berita yang belum dicek AI,
        analisis, dan update/hapus sesuai hasil.
        """
        from database.extensions import db
        from database.models import Berita
        from services.ai_service import gemini
        from datetime import datetime, timedelta

        # PRIORITAS UTAMA (PALING TINGGI): Re-analisis berita yang saat ini ber-sentimen 'Negatif'!
        # Cek apakah sentimennya benar Negatif atau sebenarnya Netral/Positif/Bukan OJK Jabar
        batas_negatif = datetime.utcnow() - timedelta(minutes=5)
        antrian_negatif = (
            Berita.query.filter(
                Berita.status == "aktif",
                Berita.sentimen == "Negatif",
                db.or_(
                    Berita.ai_last_checked.is_(None),
                    Berita.ai_last_checked < batas_negatif
                )
            )
            .order_by(
                db.asc(db.func.coalesce(Berita.ai_last_checked, datetime(1970, 1, 1))),
                Berita.id.asc()
            )
            .limit(20)
            .all()
        )

        antrian_jabar = []
        antrian_baru = []
        antrian_lama = []
        is_reanalysis = False

        if antrian_negatif:
            antrian = antrian_negatif
            is_reanalysis = True
            logger.info(f"[AIReview] PRIORITAS UTAMA: Memproses {len(antrian_negatif)} berita bertag Negatif untuk verifikasi sentimen...")
        else:
            # PRIORITAS 2: Re-analisis berita lama yang wilayah-nya masih generic 'Jawa Barat'
            batas_jabar = datetime.utcnow() - timedelta(hours=2)
            antrian_jabar = (
                Berita.query.filter(
                    Berita.status == "aktif",
                    Berita.wilayah == "Jawa Barat",
                    db.or_(
                        Berita.ai_last_checked.is_(None),
                        Berita.ai_last_checked < batas_jabar
                    )
                )
                .order_by(
                    db.asc(db.func.coalesce(Berita.ai_last_checked, datetime(1970, 1, 1))),
                    Berita.id.asc()
                )
                .limit(BATCH_SIZE)
                .all()
            )

            if antrian_jabar:
                antrian = antrian_jabar
                is_reanalysis = True
            else:
                # PRIORITAS 3: Berita baru yang belum dicek AI
                antrian_baru = (
                    Berita.query.filter(
                        Berita.status == "aktif",
                        db.or_(
                            Berita.ai_checked == False,  # noqa: E712
                            Berita.ai_checked.is_(None),  # noqa: E711
                        ),
                    )
                    .order_by(
                        db.asc(db.func.coalesce(Berita.ai_last_checked, datetime(1970, 1, 1))),
                        Berita.id.asc()
                    )
                    .limit(BATCH_SIZE)
                    .all()
                )

                if not antrian_baru:
                    # PRIORITAS 4: Re-analisis berita lama umum
                    batas_re_analisis = datetime.utcnow() - timedelta(hours=12)
                    antrian_lama = (
                        Berita.query.filter(
                            Berita.status == "aktif",
                            Berita.ai_checked == True,  # noqa: E712
                            db.or_(
                                Berita.ai_last_checked.is_(None),
                                Berita.ai_last_checked < batas_re_analisis
                            )
                        )
                        .order_by(db.asc(db.func.coalesce(Berita.ai_last_checked, datetime(1970, 1, 1))))
                        .limit(5)
                        .all()
                    )
                    if antrian_lama:
                        is_reanalysis = True

                antrian = antrian_baru + antrian_lama

        if not antrian:
            logger.debug(
                "[AIReview] Tidak ada berita baru maupun berita lama yang perlu disinkronkan. Menunggu..."
            )
            return

        if is_reanalysis:
            logger.info(f"[AIReview] Memproses sinkronisasi ulang {len(antrian)} berita lama secara berkala...")
        else:
            logger.info(f"[AIReview] Memproses {len(antrian)} berita belum dicek AI...")

        dihapus = 0
        diupdate = 0
        gagal = 0

        for berita in antrian:
            judul = berita.judul or ""
            isi = berita.isi or berita.ringkasan or ""
            teks = f"{judul} {isi}".lower()

            # ── Filter Tanggal: Hapus berita lebih dari 5 tahun ───────────────
            from datetime import datetime, timedelta

            if berita.tanggal:
                batas_lama = datetime.utcnow() - timedelta(days=5 * 365)
                if berita.tanggal < batas_lama:
                    try:
                        db.session.delete(berita)
                        db.session.commit()
                        dihapus += 1
                        logger.debug(
                            f"[AIReview] TERLALU LAMA ({berita.tanggal.strftime('%Y-%m-%d')}), hapus | {judul[:50]}"
                        )
                    except Exception:
                        db.session.rollback()
                    continue

            # ── Step 0: Resolve link + fetch gambar + validasi aksesibilitas ──
            link_diupdate = False
            try:
                from crawler.image_resolver import resolve_and_fetch_image

                if berita.link:
                    hasil_resolve = resolve_and_fetch_image(berita.link)

                    # Update link ke URL asli (bukan Google redirect)
                    if (
                        hasil_resolve.get("actual_url")
                        and berita.link != hasil_resolve["actual_url"]
                    ):
                        berita.link = hasil_resolve["actual_url"]
                        link_diupdate = True

                    # Ambil gambar jika belum ada
                    if hasil_resolve.get("gambar_url") and not berita.gambar_url:
                        berita.gambar_url = hasil_resolve["gambar_url"]
                        link_diupdate = True

                    # Ambil isi artikel jika belum ada
                    if hasil_resolve.get("isi") and not berita.isi:
                        berita.isi = hasil_resolve["isi"]
                        isi = berita.isi
                        teks = f"{judul} {isi}".lower()
                        link_diupdate = True

                    # Hapus jika artikel benar-benar tidak bisa diakses (404, domain mati)
                    if not hasil_resolve.get("dapat_diakses", True):
                        logger.debug(
                            f"[AIReview] Tidak bisa diakses, hapus | {judul[:55]}"
                        )
                        db.session.delete(berita)
                        db.session.commit()
                        dihapus += 1
                        continue

                if link_diupdate:
                    db.session.commit()

            except Exception as e:
                logger.debug(f"[AIReview] Gagal resolve link ID={berita.id}: {e}")

            # ── Lapis 1: Pre-filter kata kunci kota Jabar ─────────────────────
            if not any(k in teks for k in JABAR_KEYWORDS):
                try:
                    db.session.delete(berita)
                    db.session.commit()
                    dihapus += 1
                    logger.debug(f"[AIReview] L1-HAPUS | {judul[:60]}")
                except Exception as e:
                    db.session.rollback()
                    logger.warning(f"[AIReview] Gagal hapus ID={berita.id}: {e}")
                continue

            # ── Lapis 2: Analisis AI ──────────────────────────────────────────
            try:
                ai_result = gemini.analisis_berita(judul, berita.isi, berita.ringkasan, berita.media)
                time.sleep(DELAY_PER_REQ)

                if ai_result is None:
                    gagal += 1
                    logger.warning(f"[AIReview] AI gagal ID={berita.id} | {judul[:50]}")
                    try:
                        berita.ai_last_checked = datetime.utcnow()
                        db.session.commit()
                    except Exception:
                        db.session.rollback()
                    continue

                sentimen = ai_result.get("sentimen", "Netral")

                if sentimen == "Tidak Relevan":
                    db.session.delete(berita)
                    db.session.commit()
                    dihapus += 1
                    logger.debug(f"[AIReview] L2-HAPUS (tidak relevan) | {judul[:60]}")
                else:
                    # ── Validasi Pasca-AI: Hapus jika wilayah bukan Jawa Barat ──────
                    wilayah_ai = ai_result.get("wilayah")
                    WILAYAH_LUAR_JABAR = [
                        "Jakarta", "Surabaya", "Medan", "Bali", "Makassar",
                        "Semarang", "Yogyakarta", "Palembang", "Pekanbaru",
                        "Batam", "Banjarmasin", "Manado", "Padang", "Aceh",
                        "Lampung", "Kalimantan", "Sulawesi", "Papua", "Maluku",
                        "Sumatra", "Sumatera", "Lombok", "Nusa Tenggara",
                    ]
                    if wilayah_ai and any(
                        luar.lower() in str(wilayah_ai).lower()
                        for luar in WILAYAH_LUAR_JABAR
                    ):
                        try:
                            db.session.delete(berita)
                            db.session.commit()
                            dihapus += 1
                            logger.debug(
                                f"[AIReview] L2-HAPUS (wilayah luar Jabar: {wilayah_ai}) | {judul[:55]}"
                            )
                        except Exception as e:
                            db.session.rollback()
                            logger.warning(f"[AIReview] Gagal hapus (wilayah luar) ID={berita.id}: {e}")
                        continue

                    old_sentimen = berita.sentimen
                    berita.sentimen = sentimen
                    berita.topik = ai_result.get("topik", berita.topik)
                    berita.ai_checked = True
                    berita.ai_last_checked = datetime.utcnow()

                    if wilayah_ai:
                        berita.wilayah = wilayah_ai
                    elif not berita.wilayah:
                        berita.wilayah = "Jawa Barat"

                    if ai_result.get("ringkasan"):
                        berita.ringkasan = ai_result["ringkasan"]
                    if ai_result.get("narasumber"):
                        berita.narasumber = ai_result["narasumber"]

                    db.session.commit()
                    diupdate += 1
                    logger.debug(
                        f"[AIReview] OK | {sentimen:7} | {berita.wilayah or '?':20} | {judul[:45]}"
                    )

                    # Kirim notifikasi jika terdeteksi sentimen negatif baru
                    if sentimen == "Negatif" and old_sentimen != "Negatif":
                        try:
                            from services.notifikasi_service import NotifikasiService
                            NotifikasiService.tambah_notifikasi(
                                tipe="danger",
                                judul="⚠️ Berita Sentimen Negatif",
                                pesan=f"Terdeteksi berita negatif dari review AI: '{judul[:80]}...'",
                                link=f"/pemberitaan/{berita.id}",
                            )
                        except Exception as ne:
                            logger.error(f"[AIReview] Gagal kirim notif negatif: {ne}")

            except Exception as e:
                db.session.rollback()
                gagal += 1
                logger.error(f"[AIReview] Error analisis ID={berita.id}: {e}")
                try:
                    berita.ai_last_checked = datetime.utcnow()
                    db.session.commit()
                except Exception:
                    db.session.rollback()

        if dihapus or diupdate:
            logger.info(
                f"[AIReview] Siklus selesai → "
                f"Dihapus: {dihapus} | Diupdate: {diupdate} | Gagal: {gagal}"
            )

    # ── Kontrol Publik ────────────────────────────────────────────────────────
    @classmethod
    def start(cls, app):
        """Mulai background worker (dipanggil dari app.py)."""
        if cls._running:
            logger.debug("[AIReview] Worker sudah berjalan.")
            return

        cls.ensure_ai_checked_column(app)
        cls._running = True
        cls._thread = threading.Thread(
            target=cls._worker,
            args=(app,),
            name="AIReviewWorker",
            daemon=True,
        )
        cls._thread.start()
        logger.info("[AIReview] Background AI Review Service AKTIF.")

    @classmethod
    def stop(cls):
        """Hentikan background worker."""
        cls._running = False
        logger.info("[AIReview] Background AI Review Service DIHENTIKAN.")
