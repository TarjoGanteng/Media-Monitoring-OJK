"""
services/berita_service.py - Service untuk operasi CRUD dan query berita
"""

import logging
from datetime import datetime, timedelta
from sqlalchemy import func, desc
from database.extensions import db
from database.models import Berita
from config import Config

logger = logging.getLogger(__name__)


class BeritaService:
    """Service untuk mengelola operasi berita: read, filter, pagination, detail."""

    @staticmethod
    def get_berita_paginated(
        page: int = 1,
        per_page: int = None,
        tanggal_dari: str = None,
        tanggal_sampai: str = None,
        media: str = None,
        topik: str = None,
        sentimen: str = None,
        keyword: str = None,
        wilayah: str = None,
    ):
        """
        Mengambil berita dengan filter dan pagination.

        Args:
            page: Nomor halaman (mulai dari 1)
            per_page: Jumlah berita per halaman
            tanggal_dari: Filter tanggal mulai (format YYYY-MM-DD)
            tanggal_sampai: Filter tanggal akhir (format YYYY-MM-DD)
            media: Filter nama media
            topik: Filter topik
            sentimen: Filter sentimen
            keyword: Filter teks di judul
            wilayah: Filter wilayah

        Returns:
            Objek Pagination dari SQLAlchemy
        """
        if per_page is None:
            per_page = Config.ARTICLES_PER_PAGE

        query = Berita.query.filter_by(status="aktif")

        # Filter tanggal dari
        if tanggal_dari:
            try:
                dt_dari = datetime.strptime(tanggal_dari, "%Y-%m-%d")
                query = query.filter(Berita.tanggal >= dt_dari)
            except ValueError:
                logger.warning(f"Format tanggal_dari tidak valid: {tanggal_dari}")

        # Filter tanggal sampai
        if tanggal_sampai:
            try:
                dt_sampai = datetime.strptime(tanggal_sampai, "%Y-%m-%d")
                dt_sampai = dt_sampai.replace(hour=23, minute=59, second=59)
                query = query.filter(Berita.tanggal <= dt_sampai)
            except ValueError:
                logger.warning(f"Format tanggal_sampai tidak valid: {tanggal_sampai}")

        # Filter media (case-insensitive)
        if media:
            query = query.filter(Berita.media.ilike(f"%{media}%"))

        # Filter topik
        if topik:
            query = query.filter(Berita.topik.ilike(f"%{topik}%"))

        # Filter sentimen
        if sentimen and sentimen in ["Positif", "Netral", "Negatif"]:
            query = query.filter(Berita.sentimen == sentimen)

        # Filter keyword di judul
        if keyword:
            query = query.filter(Berita.judul.ilike(f"%{keyword}%"))

        # Filter wilayah
        if wilayah:
            query = query.filter(Berita.wilayah.ilike(f"%{wilayah}%"))

        # Urutkan berdasarkan tanggal terbaru
        query = query.order_by(desc(Berita.tanggal), desc(Berita.created_at))

        return query.paginate(page=page, per_page=per_page, error_out=False)

    @staticmethod
    def get_berita_by_id(berita_id: int) -> Berita | None:
        """
        Mengambil satu berita berdasarkan ID.

        Args:
            berita_id: ID berita

        Returns:
            Objek Berita atau None jika tidak ditemukan
        """
        return db.session.get(Berita, berita_id)

    @staticmethod
    def get_berita_terbaru(limit: int = 5) -> list[Berita]:
        """
        Mengambil berita paling terbaru.

        Args:
            limit: Jumlah berita yang diambil

        Returns:
            List berita terbaru
        """
        return (
            Berita.query.filter_by(status="aktif")
            .order_by(desc(Berita.tanggal), desc(Berita.created_at))
            .limit(limit)
            .all()
        )

    @staticmethod
    def get_daftar_media() -> list[str]:
        """
        Mengambil daftar media unik yang ada di database.

        Returns:
            List nama media yang sudah diurutkan
        """
        result = (
            db.session.query(Berita.media)
            .filter(Berita.media.isnot(None), Berita.status == "aktif")
            .distinct()
            .order_by(Berita.media)
            .all()
        )
        return [r[0] for r in result if r[0]]

    @staticmethod
    def get_daftar_topik() -> list[str]:
        """
        Mengambil daftar topik unik yang ada di database.

        Returns:
            List topik yang sudah diurutkan
        """
        result = (
            db.session.query(Berita.topik)
            .filter(Berita.topik.isnot(None), Berita.status == "aktif")
            .distinct()
            .order_by(Berita.topik)
            .all()
        )
        return [r[0] for r in result if r[0]]

    @staticmethod
    def get_daftar_wilayah() -> list[str]:
        """
        Mengambil daftar wilayah unik yang ada di database.

        Returns:
            List wilayah yang sudah diurutkan
        """
        result = (
            db.session.query(Berita.wilayah)
            .filter(Berita.wilayah.isnot(None), Berita.status == "aktif")
            .distinct()
            .order_by(Berita.wilayah)
            .all()
        )
        return [r[0] for r in result if r[0]]

    @staticmethod
    def cari_berita(
        query_text: str,
        sentimen: str = None,
        media: str = None,
        topik: str = None,
        tanggal_dari: str = None,
        tanggal_sampai: str = None,
        wilayah: str = None,
        page: int = 1,
        per_page: int = None,
    ):
        """
        Pencarian berita berdasarkan teks di judul dan isi.

        Args:
            query_text: Teks pencarian
            sentimen: Filter sentimen opsional
            media: Filter media opsional
            topik: Filter topik opsional
            tanggal_dari: Filter tanggal mulai
            tanggal_sampai: Filter tanggal akhir
            wilayah: Filter wilayah
            page: Nomor halaman
            per_page: Berita per halaman

        Returns:
            Objek Pagination
        """
        if per_page is None:
            per_page = Config.ARTICLES_PER_PAGE

        query = Berita.query.filter_by(status="aktif")

        # Filter teks pencarian di judul atau isi
        if query_text:
            query = query.filter(
                (Berita.judul.ilike(f"%{query_text}%"))
                | (Berita.isi.ilike(f"%{query_text}%"))
                | (Berita.ringkasan.ilike(f"%{query_text}%"))
            )

        # Filter tambahan
        if sentimen:
            query = query.filter(Berita.sentimen == sentimen)
        if media:
            query = query.filter(Berita.media.ilike(f"%{media}%"))
        if topik:
            query = query.filter(Berita.topik.ilike(f"%{topik}%"))
        if wilayah:
            query = query.filter(Berita.wilayah.ilike(f"%{wilayah}%"))

        if tanggal_dari:
            try:
                dt = datetime.strptime(tanggal_dari, "%Y-%m-%d")
                query = query.filter(Berita.tanggal >= dt)
            except ValueError:
                pass

        if tanggal_sampai:
            try:
                dt = datetime.strptime(tanggal_sampai, "%Y-%m-%d")
                dt = dt.replace(hour=23, minute=59, second=59)
                query = query.filter(Berita.tanggal <= dt)
            except ValueError:
                pass

        query = query.order_by(desc(Berita.tanggal), desc(Berita.created_at))
        return query.paginate(page=page, per_page=per_page, error_out=False)

    @staticmethod
    def hapus_berita(berita_id: int) -> tuple[bool, str]:
        """
        Soft delete berita (ubah status menjadi 'hapus').

        Args:
            berita_id: ID berita

        Returns:
            Tuple (berhasil, pesan)
        """
        berita = db.session.get(Berita, berita_id)
        if not berita:
            return False, "Berita tidak ditemukan."

        berita.status = "hapus"
        try:
            db.session.commit()
            return True, "Berita berhasil dihapus."
        except Exception as e:
            db.session.rollback()
            return False, f"Gagal menghapus: {str(e)}"
