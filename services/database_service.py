"""
services/database_service.py - Service untuk operasi database umum
"""

import logging
from database.extensions import db
from database.models import Berita, CrawlLog, Keyword
from config import Config

logger = logging.getLogger(__name__)


class DatabaseService:
    """Service untuk operasi-operasi umum pada database."""

    @staticmethod
    def inisialisasi_keyword_default():
        """
        Mengisi tabel keyword dengan keyword default jika masih kosong.
        Dipanggil saat pertama kali aplikasi dijalankan.
        """
        if Keyword.query.count() == 0:
            keywords_default = Config.CRAWLER_KEYWORDS
            for kata in keywords_default:
                kw = Keyword(kata=kata, aktif=True)
                db.session.add(kw)
            try:
                db.session.commit()
                logger.info(
                    f"Berhasil menambahkan {len(keywords_default)} keyword default."
                )
            except Exception as e:
                db.session.rollback()
                logger.error(f"Gagal inisialisasi keyword: {e}")

    @staticmethod
    def get_semua_keyword(hanya_aktif: bool = True) -> list[Keyword]:
        """
        Mengambil semua keyword dari database.

        Args:
            hanya_aktif: Jika True, hanya mengembalikan keyword yang aktif

        Returns:
            List objek Keyword
        """
        query = Keyword.query
        if hanya_aktif:
            query = query.filter_by(aktif=True)
        return query.order_by(Keyword.id).all()

    @staticmethod
    def tambah_keyword(kata: str) -> tuple[bool, str]:
        """
        Menambahkan keyword baru ke database.

        Args:
            kata: Kata kunci baru

        Returns:
            Tuple (berhasil, pesan)
        """
        existing = Keyword.query.filter_by(kata=kata).first()
        if existing:
            return False, f"Keyword '{kata}' sudah ada."

        kw = Keyword(kata=kata, aktif=True)
        db.session.add(kw)
        try:
            db.session.commit()
            return True, f"Keyword '{kata}' berhasil ditambahkan."
        except Exception as e:
            db.session.rollback()
            logger.error(f"Gagal tambah keyword: {e}")
            return False, f"Gagal menambahkan keyword: {str(e)}"

    @staticmethod
    def cleanup_old_data():
        """
        Menghapus data berita yang lebih lama dari rentang waktu konfigurasi (1, 3, atau 5 tahun).
        """
        from services.config_service import ConfigService
        from datetime import datetime, timedelta

        config = ConfigService.get_config()

        if not config.get("auto_hapus"):
            return 0

        rentang = str(config.get("rentang_data", "5"))
        if rentang == "all":
            return 0

        try:
            years = int(rentang)
            cutoff_date = datetime.now() - timedelta(days=years * 365)

            # Delete old records
            deleted_count = Berita.query.filter(Berita.tanggal < cutoff_date).delete()
            db.session.commit()
            if deleted_count > 0:
                logger.info(
                    f"Berhasil menghapus {deleted_count} berita yang lebih lama dari {years} tahun."
                )
            return deleted_count
        except Exception as e:
            db.session.rollback()
            logger.error(f"Gagal saat membersihkan data lama: {e}")
            return 0

    @staticmethod
    def simpan_crawl_log(
        keyword: str,
        jumlah_ditemukan: int,
        jumlah_disimpan: int,
        jumlah_duplikat: int,
        status: str = "sukses",
        pesan: str = None,
    ) -> CrawlLog:
        """
        Menyimpan log hasil crawling ke database.

        Args:
            keyword: Keyword yang di-crawl
            jumlah_ditemukan: Total artikel ditemukan dari RSS
            jumlah_disimpan: Artikel yang berhasil disimpan
            jumlah_duplikat: Artikel yang dilewat karena duplikat
            status: Status crawling (sukses/gagal)
            pesan: Pesan tambahan (opsional)

        Returns:
            Objek CrawlLog yang disimpan
        """
        log = CrawlLog(
            keyword=keyword,
            jumlah_ditemukan=jumlah_ditemukan,
            jumlah_disimpan=jumlah_disimpan,
            jumlah_duplikat=jumlah_duplikat,
            status=status,
            pesan=pesan,
        )
        db.session.add(log)
        try:
            db.session.commit()
            return log
        except Exception as e:
            db.session.rollback()
            logger.error(f"Gagal simpan crawl log: {e}")
            return None

    @staticmethod
    def get_crawl_log_terbaru(limit: int = 20) -> list[CrawlLog]:
        """
        Mengambil log crawling terbaru.

        Args:
            limit: Jumlah log yang diambil

        Returns:
            List CrawlLog terbaru
        """
        return CrawlLog.query.order_by(CrawlLog.created_at.desc()).limit(limit).all()
