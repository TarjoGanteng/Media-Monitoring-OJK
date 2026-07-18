"""
services/notifikasi_service.py - Service untuk mengelola Notifikasi sistem
"""

import logging
from datetime import datetime, timedelta
from sqlalchemy import desc
from database.extensions import db
from database.models import Notifikasi, Berita

logger = logging.getLogger(__name__)


class NotifikasiService:
    """Service untuk operasi modul Notifikasi"""

    @staticmethod
    def tambah_notifikasi(tipe: str, judul: str, pesan: str, link: str = None) -> bool:
        """
        Menambahkan notifikasi baru ke database.

        Args:
            tipe: info, warning, danger, success
            judul: Judul singkat notifikasi
            pesan: Detail isi notifikasi
            link: URL tujuan jika notifikasi diklik

        Returns:
            True jika berhasil, False jika gagal
        """
        try:
            notif = Notifikasi(tipe=tipe, judul=judul, pesan=pesan, link=link)
            db.session.add(notif)
            db.session.commit()
            return True
        except Exception as e:
            db.session.rollback()
            logger.error(f"Gagal menambahkan notifikasi: {e}")
            return False

    @staticmethod
    def get_semua_notifikasi(limit: int = 50) -> list[Notifikasi]:
        """Ambil notifikasi terbaru"""
        return Notifikasi.query.order_by(desc(Notifikasi.created_at)).limit(limit).all()

    @staticmethod
    def get_notifikasi_belum_dibaca() -> list[Notifikasi]:
        """Ambil notifikasi yang belum dibaca"""
        return (
            Notifikasi.query.filter_by(is_read=False)
            .order_by(desc(Notifikasi.created_at))
            .all()
        )

    @staticmethod
    def hitung_belum_dibaca() -> int:
        """Hitung jumlah notifikasi yang belum dibaca"""
        return Notifikasi.query.filter_by(is_read=False).count()

    @staticmethod
    def tandai_dibaca(notif_id: int) -> bool:
        """Tandai satu notifikasi sudah dibaca"""
        notif = db.session.get(Notifikasi, notif_id)
        if notif:
            notif.is_read = True
            try:
                db.session.commit()
                return True
            except Exception as e:
                db.session.rollback()
                logger.error(f"Gagal update notifikasi {notif_id}: {e}")
        return False

    @staticmethod
    def tandai_semua_dibaca() -> bool:
        """Tandai semua notifikasi sudah dibaca"""
        try:
            db.session.query(Notifikasi).filter_by(is_read=False).update(
                {"is_read": True}
            )
            db.session.commit()
            return True
        except Exception as e:
            db.session.rollback()
            logger.error(f"Gagal update semua notifikasi: {e}")
            return False

    @staticmethod
    def hapus_notifikasi(notif_id: int) -> bool:
        """Hapus satu notifikasi berdasarkan ID"""
        notif = db.session.get(Notifikasi, notif_id)
        if notif:
            try:
                db.session.delete(notif)
                db.session.commit()
                return True
            except Exception as e:
                db.session.rollback()
                logger.error(f"Gagal menghapus notifikasi {notif_id}: {e}")
        return False

    @staticmethod
    def hapus_semua_notifikasi() -> int:
        """Hapus semua notifikasi"""
        try:
            jml = Notifikasi.query.count()
            Notifikasi.query.delete()
            db.session.commit()
            return jml
        except Exception as e:
            db.session.rollback()
            logger.error(f"Gagal hapus semua notifikasi: {e}")
            return 0

    @staticmethod
    def hapus_notifikasi_lama() -> int:
        """
        Hapus notifikasi otomatis:
        - Belum dibaca (is_read=False) -> hapus jika > 30 hari
        - Sudah dibaca (is_read=True) -> hapus jika > 7 hari
        """
        now = datetime.utcnow()
        batas_belum_dibaca = now - timedelta(days=30)
        batas_sudah_dibaca = now - timedelta(days=7)
        try:
            # 1. Ambil yang belum dibaca > 30 hari
            belum_dibaca = Notifikasi.query.filter(
                Notifikasi.is_read == False,
                Notifikasi.created_at < batas_belum_dibaca
            ).all()
            
            # 2. Ambil yang sudah dibaca > 7 hari
            sudah_dibaca = Notifikasi.query.filter(
                Notifikasi.is_read == True,
                Notifikasi.created_at < batas_sudah_dibaca
            ).all()
            
            lama = belum_dibaca + sudah_dibaca
            jml = len(lama)
            for n in lama:
                db.session.delete(n)
            db.session.commit()
            return jml
        except Exception as e:
            db.session.rollback()
            logger.error(f"Gagal hapus notifikasi lama: {e}")
            return 0

    @staticmethod
    def cek_lonjakan_isu():
        """
        Mengecek apakah ada lonjakan berita dengan topik tertentu
        dalam 24 jam terakhir (misal: lebih dari 10 berita).
        """
        try:
            batas_waktu = datetime.utcnow() - timedelta(hours=24)
            # Dapatkan topik beserta jumlahnya dalam 24 jam terakhir
            from sqlalchemy import func

            hasil = (
                db.session.query(Berita.topik, func.count(Berita.id).label("jumlah"))
                .filter(
                    Berita.created_at >= batas_waktu,
                    Berita.status == "aktif",
                    Berita.topik.isnot(None),
                )
                .group_by(Berita.topik)
                .all()
            )

            # Ambang batas lonjakan (contoh: 10 berita)
            ambang_batas = 10

            for row in hasil:
                topik = row.topik
                jumlah = row.jumlah

                if jumlah >= ambang_batas:
                    # Cek apakah sudah ada notifikasi lonjakan untuk topik ini hari ini
                    hari_ini_awal = datetime.utcnow().replace(
                        hour=0, minute=0, second=0
                    )
                    sudah_ada = Notifikasi.query.filter(
                        Notifikasi.tipe == "warning",
                        Notifikasi.judul.like("%Lonjakan Isu%"),
                        Notifikasi.pesan.like(f"%'{topik}'%"),
                        Notifikasi.created_at >= hari_ini_awal,
                    ).first()

                    if not sudah_ada:
                        NotifikasiService.tambah_notifikasi(
                            tipe="warning",
                            judul="📈 Lonjakan Isu",
                            pesan=f"Terdapat lonjakan {jumlah} berita mengenai '{topik}' dalam 24 jam terakhir di Jawa Barat.",
                            link=f"/pemberitaan?topik={topik}",
                        )
        except Exception as e:
            logger.error(f"Gagal cek lonjakan isu: {e}")
