"""
services/crawler_service.py - Service untuk mengelola proses crawling berita
"""

import logging
from datetime import datetime
from database.extensions import db
from database.models import Berita
from crawler.rss_crawler import RSSCrawler
from services.database_service import DatabaseService
from services.sentiment_service import SentimentAnalyzer

logger = logging.getLogger(__name__)


class CrawlerService:
    """
    Service yang mengorkestrasi proses crawling:
    1. Ambil keyword dari database
    2. Panggil RSSCrawler untuk setiap keyword
    3. Filter duplikat berdasarkan link
    4. Simpan berita baru ke database
    5. Catat log crawling
    """

    def __init__(self):
        """Inisialisasi crawler service."""
        self.crawler = RSSCrawler()

    def cek_duplikat(self, link: str, judul: str = None) -> bool:
        """
        Mengecek duplikat berdasarkan link URL dan judul berita.
        Mencegah berita sama masuk lewat keyword berbeda.

        Args:
            link: URL artikel
            judul: Judul artikel (opsional, cek exact match)

        Returns:
            True jika duplikat, False jika baru
        """
        # Lapis 1: Cek URL persis
        if link and Berita.query.filter_by(link=link).first():
            return True
        # Lapis 2: Cek judul persis (tangkap duplikat dari keyword berbeda)
        if judul and Berita.query.filter_by(judul=judul).first():
            return True
        return False

    def simpan_berita(self, article_data: dict) -> tuple[bool, str]:
        """
        Menyimpan satu artikel ke database setelah melewati pengecekan duplikat.
        Analisis dilakukan oleh Gemini AI (jika tersedia) atau rule-based (fallback).

        Args:
            article_data: Dictionary data artikel dari crawler

        Returns:
            Tuple (berhasil_disimpan, alasan)
        """
        link = article_data.get("link", "").strip()

        if not link:
            return False, "Link kosong, artikel dilewat."

        # Cek duplikat berdasarkan link
        if self.cek_duplikat(link, judul):
            return False, f"Duplikat: {link or judul}"

        judul = article_data.get("judul", "Tanpa Judul")
        isi   = article_data.get("isi")
        ringkasan = article_data.get("ringkasan")

        # ── Analisis AI (Gemini) — prioritas utama ────────────────────────────
        sentimen_final  = None
        topik_final     = None
        wilayah_final   = None
        ringkasan_final = ringkasan
        narasumber_final = article_data.get("narasumber")

        try:
            from services.ai_service import gemini
            if gemini.is_available():
                ai_result = gemini.analisis_berita(judul, isi, ringkasan)
                if ai_result:
                    sentimen_final   = ai_result["sentimen"]
                    topik_final      = ai_result["topik"]
                    wilayah_final    = ai_result.get("wilayah")
                    if ai_result.get("ringkasan"):
                        ringkasan_final = ai_result["ringkasan"]
                    if ai_result.get("narasumber"):
                        narasumber_final = ai_result["narasumber"]
                    logger.debug(f"[AI] Analisis OK: '{judul[:50]}' → {sentimen_final}, {topik_final}")
        except Exception as e:
            logger.warning(f"[AI] Gagal analisis, fallback ke rule-based: {e}")

        # ── Fallback rule-based jika AI tidak menghasilkan data ───────────────
        if not sentimen_final:
            hasil_sentimen  = SentimentAnalyzer.analisis(judul, isi)
            sentimen_final  = hasil_sentimen["sentimen"]
        if not topik_final:
            topik_final     = SentimentAnalyzer.analisis_topik(judul, isi)
        if not wilayah_final:
            wilayah_final   = SentimentAnalyzer.analisis_wilayah(judul, isi)

        berita = Berita(
            judul=judul,
            link=link,
            media=article_data.get("media"),
            tanggal=article_data.get("tanggal"),
            isi=isi,
            ringkasan=ringkasan_final,
            gambar_url=article_data.get("gambar_url"),
            sentimen=sentimen_final,
            topik=article_data.get("topik") or topik_final,
            wilayah=article_data.get("wilayah") or wilayah_final,
            narasumber=narasumber_final,
            bulan=article_data.get("bulan"),
            tahun=article_data.get("tahun"),
            triwulan=article_data.get("triwulan"),
            keyword=article_data.get("keyword"),
            status="aktif",
        )

        db.session.add(berita)
        try:
            db.session.commit()
            return True, f"Berhasil simpan: {berita.judul[:60]}"
        except Exception as e:
            db.session.rollback()
            logger.error(f"Gagal simpan berita: {e}")
            return False, f"Error database: {str(e)}"


    def crawl_satu_keyword(self, keyword: str) -> dict:
        """
        Menjalankan crawling untuk satu keyword lengkap dengan penyimpanan.

        Args:
            keyword: Kata kunci yang akan di-crawl

        Returns:
            Dictionary dengan statistik hasil crawling
        """
        logger.info(f"=== Mulai crawl keyword: '{keyword}' ===")
        hasil = {
            "keyword": keyword,
            "jumlah_ditemukan": 0,
            "jumlah_disimpan": 0,
            "jumlah_duplikat": 0,
            "jumlah_error": 0,
            "status": "sukses",
            "pesan": None,
            "waktu": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        try:
            # Ambil artikel dari RSS
            articles = self.crawler.crawl_keyword(keyword)
            hasil["jumlah_ditemukan"] = len(articles)

            # Proses setiap artikel
            for article in articles:
                simpan_ok, pesan = self.simpan_berita(article)
                if simpan_ok:
                    hasil["jumlah_disimpan"] += 1
                elif "Duplikat" in pesan:
                    hasil["jumlah_duplikat"] += 1
                else:
                    hasil["jumlah_error"] += 1
                    logger.warning(pesan)

        except Exception as e:
            hasil["status"] = "gagal"
            hasil["pesan"] = str(e)
            logger.error(f"Error crawl keyword '{keyword}': {e}")

        # Simpan log ke database
        DatabaseService.simpan_crawl_log(
            keyword=keyword,
            jumlah_ditemukan=hasil["jumlah_ditemukan"],
            jumlah_disimpan=hasil["jumlah_disimpan"],
            jumlah_duplikat=hasil["jumlah_duplikat"],
            status=hasil["status"],
            pesan=hasil["pesan"],
        )

        logger.info(
            f"=== Selesai crawl '{keyword}': "
            f"Ditemukan={hasil['jumlah_ditemukan']}, "
            f"Disimpan={hasil['jumlah_disimpan']}, "
            f"Duplikat={hasil['jumlah_duplikat']} ==="
        )
        return hasil

    def crawl_semua_keyword(self, keywords: list[str] = None) -> list[dict]:
        """
        Menjalankan crawling untuk semua keyword aktif.

        Args:
            keywords: List keyword opsional, jika None ambil dari database

        Returns:
            List hasil crawling per keyword
        """
        if keywords is None:
            kw_objects = DatabaseService.get_semua_keyword(hanya_aktif=True)
            keywords = [kw.kata for kw in kw_objects]

        if not keywords:
            logger.warning("Tidak ada keyword aktif untuk di-crawl.")
            return []

        semua_hasil = []
        max_workers = min(len(keywords), 4)  # Maks 4 thread paralel
        logger.info(f"Crawling {len(keywords)} keyword dengan {max_workers} thread paralel...")

        from concurrent.futures import ThreadPoolExecutor, as_completed
        from flask import current_app

        app = current_app._get_current_object()

        def crawl_dalam_context(kw):
            with app.app_context():
                return self.crawl_satu_keyword(kw)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(crawl_dalam_context, kw): kw for kw in keywords}
            for future in as_completed(futures):
                try:
                    hasil = future.result()
                    semua_hasil.append(hasil)
                except Exception as e:
                    kw = futures[future]
                    logger.error(f"Thread error crawl '{kw}': {e}")
                    semua_hasil.append({
                        "keyword": kw, "jumlah_ditemukan": 0,
                        "jumlah_disimpan": 0, "jumlah_duplikat": 0,
                        "jumlah_error": 1, "status": "gagal", "pesan": str(e),
                    })

        # Jalankan pembersihan otomatis berita lama (lebih dari 5 tahun)
        self.cleanup_berita_lama(tahun=5)

        # Jalankan deduplikasi otomatis setelah crawl selesai
        try:
            from services.dedup_service import DeduplicateService
            hasil_dedup = DeduplicateService.jalankan_semua(threshold_mirip=0.88)
            if hasil_dedup["total_dihapus"] > 0:
                logger.info(
                    f"[Dedup Auto] {hasil_dedup['total_dihapus']} berita duplikat dihapus: "
                    f"URL={hasil_dedup['lapis_1_url']['dihapus']}, "
                    f"Judul={hasil_dedup['lapis_2_judul']['dihapus']}, "
                    f"Mirip={hasil_dedup['lapis_3_mirip']['dihapus']}"
                )
        except Exception as e:
            logger.warning(f"[Dedup Auto] Gagal: {e}")

        # Jalankan pengambilan gambar di background (tidak memblokir response)
        import threading
        t = threading.Thread(
            target=self._fetch_gambar_background,
            args=(app,),
            daemon=True
        )
        t.start()
        logger.info("Thread pengambilan gambar dimulai di background.")

        return semua_hasil

    def _fetch_gambar_background(self, app):
        """
        Mengambil gambar untuk berita yang belum memiliki gambar_url.
        Dijalankan di background thread setelah crawl utama selesai.
        Menggunakan requests biasa (bukan Playwright) agar ringan.
        """
        import time
        time.sleep(2)  # Beri jeda singkat agar crawl utama commit dulu

        with app.app_context():
            from database.extensions import db
            from database.models import Berita

            berita_list = (
                Berita.query.filter(
                    (Berita.gambar_url == None) | (Berita.gambar_url == "")
                )
                .order_by(Berita.tanggal.desc())
                .limit(30)
                .all()
            )

            logger.info(f"[BG] Mulai ambil gambar untuk {len(berita_list)} berita...")
            diupdate = 0

            for berita in berita_list:
                try:
                    link = berita.link or ""
                    if not link:
                        continue

                    # ekstrak_gambar sudah handle resolve Google News otomatis
                    gambar = self.crawler.ekstrak_gambar(link)
                    if gambar:
                        berita.gambar_url = gambar
                        diupdate += 1
                except Exception as e:
                    logger.debug(f"[BG] Gagal ambil gambar untuk '{berita.judul[:40]}': {e}")
                    continue

            try:
                db.session.commit()
                logger.info(f"[BG] Selesai: {diupdate} gambar berhasil diperbarui.")
            except Exception as e:
                db.session.rollback()
                logger.error(f"[BG] Gagal commit gambar: {e}")

    def cleanup_berita_lama(self, tahun: int = 5) -> int:
        """
        Menghapus berita yang usianya lebih dari batas tahun yang ditentukan.
        Ini menjaga efisiensi database untuk monitoring OJK Jabar.

        Args:
            tahun: Batas usia berita dalam tahun

        Returns:
            Jumlah berita yang dihapus
        """
        from datetime import timedelta
        
        batas_waktu = datetime.now() - timedelta(days=tahun * 365)
        
        try:
            # Cari dan hapus berita yang lebih tua dari batas_waktu
            berita_lama = Berita.query.filter(Berita.tanggal < batas_waktu).all()
            jumlah_dihapus = len(berita_lama)
            
            if jumlah_dihapus > 0:
                for berita in berita_lama:
                    db.session.delete(berita)
                db.session.commit()
                logger.info(f"Berhasil menghapus otomatis {jumlah_dihapus} berita yang lebih dari {tahun} tahun.")
            else:
                logger.info(f"Tidak ada berita yang usianya lebih dari {tahun} tahun.")
                
            return jumlah_dihapus
        except Exception as e:
            db.session.rollback()
            logger.error(f"Gagal saat pembersihan otomatis berita lama: {e}")
            return 0

    def get_statistik_crawl(self) -> dict:
        """
        Mengambil statistik keseluruhan proses crawling.

        Returns:
            Dictionary statistik crawling
        """
        from database.models import CrawlLog

        total_log = CrawlLog.query.count()
        total_berhasil = CrawlLog.query.filter_by(status="sukses").count()
        total_gagal = CrawlLog.query.filter_by(status="gagal").count()
        log_terbaru = CrawlLog.query.order_by(CrawlLog.created_at.desc()).first()

        return {
            "total_log": total_log,
            "total_berhasil": total_berhasil,
            "total_gagal": total_gagal,
            "crawl_terakhir": log_terbaru.created_at if log_terbaru else None,
        }
