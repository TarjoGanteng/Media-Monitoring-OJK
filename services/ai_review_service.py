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
INTERVAL_DETIK = 30  # Cek ulang berita setiap 30 detik (24/7 continuous loop)
BATCH_SIZE = 10      # Jumlah berita yang diproses per batch
DELAY_PER_REQ = 2.0   # Jeda antar request ke AI (detik)

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
        Ambil BATCH_SIZE berita (gabungan Negatif, Jabar generic, belum dicek, dan berita lama),
        analisis, dan update/hapus sesuai hasil secara berkelanjutan 24/7.
        """
        from database.extensions import db
        from database.models import Berita
        from services.ai_service import gemini
        from datetime import datetime, timedelta

        # 1. Antrian Prioritas 1: Berita bertag 'Negatif' (untuk re-verifikasi sentimen)
        batas_negatif = datetime.utcnow() - timedelta(minutes=2)
        antrian_negatif = (
            Berita.query.filter(
                Berita.status == "aktif",
                Berita.sentimen == "Negatif",
                db.or_(
                    Berita.ai_last_checked.is_(None),
                    Berita.ai_last_checked < batas_negatif
                )
            )
            .order_by(db.asc(db.func.coalesce(Berita.ai_last_checked, datetime(1970, 1, 1))))
            .limit(5)
            .all()
        )

        # 2. Antrian Prioritas 2: Berita yang belum dicek AI sama sekali
        antrian_baru = (
            Berita.query.filter(
                Berita.status == "aktif",
                db.or_(
                    Berita.ai_checked == False,  # noqa: E712
                    Berita.ai_checked.is_(None),  # noqa: E711
                ),
            )
            .order_by(db.asc(db.func.coalesce(Berita.ai_last_checked, datetime(1970, 1, 1))))
            .limit(5)
            .all()
        )

        # 3. Antrian Prioritas 3: Berita yang wilayahnya masih generic 'Jawa Barat' (untuk penajaman kota)
        batas_jabar = datetime.utcnow() - timedelta(minutes=15)
        antrian_jabar = (
            Berita.query.filter(
                Berita.status == "aktif",
                Berita.wilayah == "Jawa Barat",
                db.or_(
                    Berita.ai_last_checked.is_(None),
                    Berita.ai_last_checked < batas_jabar
                )
            )
            .order_by(db.asc(db.func.coalesce(Berita.ai_last_checked, datetime(1970, 1, 1))))
            .limit(5)
            .all()
        )

        # 4. Antrian Prioritas 4: Re-analisis berita lama secara berputar
        batas_lama = datetime.utcnow() - timedelta(hours=1)
        antrian_lama = (
            Berita.query.filter(
                Berita.status == "aktif",
                db.or_(
                    Berita.ai_last_checked.is_(None),
                    Berita.ai_last_checked < batas_lama
                )
            )
            .order_by(db.asc(db.func.coalesce(Berita.ai_last_checked, datetime(1970, 1, 1))))
            .limit(5)
            .all()
        )

        # Gabungkan semua antrian tanpa duplikat
        seen_ids = set()
        antrian = []
        for b in (antrian_negatif + antrian_baru + antrian_jabar + antrian_lama):
            if b.id not in seen_ids:
                seen_ids.add(b.id)
                antrian.append(b)

        if not antrian:
            logger.debug("[AIReview] Tidak ada berita yang perlu diproses siklus ini.")
            return

        logger.info(f"[AIReview] Memproses batch {len(antrian)} berita untuk verifikasi 24/7...")

        dihapus = 0
        diupdate = 0
        gagal = 0

        # Peta Ekstraksi Kota Jabar untuk Fast Rule-Based Verification
        KOTA_JABAR_MAP = {
            "bandung": "Bandung", "bekasi": "Bekasi", "bogor": "Bogor",
            "cirebon": "Cirebon", "depok": "Depok", "sukabumi": "Sukabumi",
            "karawang": "Karawang", "tasikmalaya": "Tasikmalaya", "garut": "Garut",
            "cianjur": "Cianjur", "subang": "Subang", "purwakarta": "Purwakarta",
            "indramayu": "Indramayu", "majalengka": "Majalengka", "sumedang": "Sumedang",
            "kuningan": "Kuningan", "ciamis": "Ciamis", "banjar": "Banjar",
            "pangandaran": "Pangandaran", "cimahi": "Cimahi"
        }

        for berita in antrian:
            judul = berita.judul or ""
            isi = berita.isi or berita.ringkasan or ""
            teks = f"{judul} {isi}".lower()

            # ── Fast Pre-Check A: Auto-correct Fake Negatives (OJK Actions/Imbauan) ─────
            if berita.sentimen == "Negatif":
                judul_txt = judul.lower()
                ringkasan_txt = (berita.ringkasan or "").lower()
                gabung_txt = f"{judul_txt} {ringkasan_txt}"
                kata_tindakan = ["ungkap", "imbau", "edukasi", "dorong", "ingatkan", "sosialisasi", "tindak", "gandeng", "gelar", "beberkan", "buka suara", "sebut", "pastikan", "cabut izin", "tutup"]
                kata_kritikan = ["kritik", "protes", "didemo", "disorot", "gagal", "lalai", "bobrok", "kecam", "tuding"]
                if any(w in gabung_txt for w in kata_tindakan) and not any(w in gabung_txt for w in kata_kritikan):
                    berita.sentimen = "Netral"
                    berita.ai_checked = True
                    berita.ai_last_checked = datetime.utcnow()
                    db.session.commit()
                    diupdate += 1
                    logger.info(f"[AIReview] Fast Guardrail: Koreksi Negatif -> Netral ID={berita.id} | {judul[:50]}")

            # ── Fast Pre-Check B: Penajaman Wilayah Kota/Kabupaten Jabar ────────────────
            if berita.wilayah in ["Jawa Barat", "Lokal", None, ""]:
                found_city = None
                for k_lower, k_name in KOTA_JABAR_MAP.items():
                    if k_lower in teks:
                        found_city = k_name
                        break
                if found_city:
                    berita.wilayah = found_city
                    berita.ai_checked = True
                    berita.ai_last_checked = datetime.utcnow()
                    db.session.commit()
                    diupdate += 1
                    logger.info(f"[AIReview] Fast Wilayah: Set ID={berita.id} -> Kota {found_city}")

            # ── Filter Tanggal: Hapus berita lebih dari 5 tahun ───────────────
            if berita.tanggal:
                batas_expired = datetime.utcnow() - timedelta(days=5 * 365)
                if berita.tanggal < batas_expired:
                    try:
                        db.session.delete(berita)
                        db.session.commit()
                        dihapus += 1
                        logger.info(f"[AIReview] TERLALU LAMA ({berita.tanggal.strftime('%Y-%m-%d')}), hapus | {judul[:50]}")
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
                        logger.info(f"[AIReview] Tidak bisa diakses, hapus | {judul[:55]}")
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
                    logger.info(f"[AIReview] L1-HAPUS (bukan OJK/Jabar) | {judul[:60]}")
                except Exception as e:
                    db.session.rollback()
                    logger.warning(f"[AIReview] Gagal hapus ID={berita.id}: {e}")
                continue

            # ── Lapis 2: Analisis AI Multi-Provider ───────────────────────────
            try:
                ai_result = gemini.analisis_berita(judul, berita.isi, berita.ringkasan, berita.media)
                time.sleep(DELAY_PER_REQ)

                if ai_result is None:
                    # JANGAN update ai_last_checked ke utcnow() agar AI mencoba lagi saat quota API reset!
                    gagal += 1
                    logger.warning(f"[AIReview] AI API Rate Limited (429) ID={berita.id} | {judul[:50]}. Menunggu retry...")
                    continue

                sentimen = ai_result.get("sentimen", "Netral")

                if sentimen == "Tidak Relevan":
                    db.session.delete(berita)
                    db.session.commit()
                    dihapus += 1
                    logger.info(f"[AIReview] L2-HAPUS (tidak relevan) | {judul[:60]}")
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
                            logger.info(f"[AIReview] L2-HAPUS (wilayah luar Jabar: {wilayah_ai}) | {judul[:55]}")
                        except Exception as e:
                            db.session.rollback()
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
                    logger.info(f"[AIReview] OK | {sentimen:7} | {berita.wilayah or '?':15} | {judul[:45]}")

                    if sentimen == "Negatif" and old_sentimen != "Negatif":
                        try:
                            from services.notifikasi_service import NotifikasiService
                            NotifikasiService.tambah_notifikasi(
                                judul=f"Sentimen Negatif Terdeteksi: {judul[:50]}...",
                                pesan=f"Berita dari {berita.media} dikategorikan ber-sentimen Negatif.",
                                tipe="negatif",
                                link=berita.link,
                            )
                        except Exception as ex:
                            logger.warning(f"[AIReview] Gagal kirim notifikasi: {ex}")

            except Exception as e:
                db.session.rollback()
                gagal += 1
                logger.error(f"[AIReview] Error analisis ID={berita.id}: {e}")

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
