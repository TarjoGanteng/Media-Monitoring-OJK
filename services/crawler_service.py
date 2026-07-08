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

    def cek_duplikat(self, link: str) -> bool:
        """
        Mengecek apakah link berita sudah ada di database.

        Args:
            link: URL artikel yang akan dicek

        Returns:
            True jika sudah ada (duplikat), False jika belum ada
        """
        return Berita.query.filter_by(link=link).first() is not None

    def simpan_berita(self, article_data: dict) -> tuple[bool, str]:
        """
        Menyimpan satu artikel ke database setelah melewati pengecekan duplikat.

        Args:
            article_data: Dictionary data artikel dari crawler

        Returns:
            Tuple (berhasil_disimpan, alasan)
        """
        link = article_data.get("link", "").strip()

        if not link:
            return False, "Link kosong, artikel dilewat."

        # Cek duplikat berdasarkan link
        if self.cek_duplikat(link):
            return False, f"Duplikat: {link}"

        judul = article_data.get("judul", "Tanpa Judul")
        isi = article_data.get("isi")

        # Analisis sentimen otomatis berbasis keyword
        hasil_sentimen = SentimentAnalyzer.analisis(judul, isi)
        topik_auto = SentimentAnalyzer.analisis_topik(judul, isi)
        wilayah_auto = SentimentAnalyzer.analisis_wilayah(judul, isi)

        berita = Berita(
            judul=judul,
            link=link,
            media=article_data.get("media"),
            tanggal=article_data.get("tanggal"),
            isi=isi,
            ringkasan=article_data.get("ringkasan"),
            gambar_url=article_data.get("gambar_url"),
            sentimen=hasil_sentimen["sentimen"],
            topik=article_data.get("topik") or topik_auto,
            wilayah=article_data.get("wilayah") or wilayah_auto,
            narasumber=article_data.get("narasumber"),
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
        for keyword in keywords:
            hasil = self.crawl_satu_keyword(keyword)
            semua_hasil.append(hasil)

        # Jalankan pembersihan otomatis untuk berita lama (lebih dari 5 tahun)
        self.cleanup_berita_lama(tahun=5)

        return semua_hasil

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
