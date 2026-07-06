"""
services/dashboard_service.py - Service untuk data dashboard dan statistik
"""

import logging
from datetime import datetime, timedelta
from sqlalchemy import func, desc, case
from database.extensions import db
from database.models import Berita

logger = logging.getLogger(__name__)


class DashboardService:
    """Service untuk mengumpulkan data statistik yang ditampilkan di dashboard."""

    @staticmethod
    def get_statistik_utama() -> dict:
        """
        Mengambil statistik utama: total berita, positif, negatif, netral.

        Returns:
            Dictionary statistik utama
        """
        base_query = Berita.query.filter_by(status="aktif")

        total = base_query.count()
        positif = base_query.filter_by(sentimen="Positif").count()
        negatif = base_query.filter_by(sentimen="Negatif").count()
        netral = base_query.filter_by(sentimen="Netral").count()

        # Hitung persentase
        pct_positif = round((positif / total * 100), 1) if total > 0 else 0
        pct_negatif = round((negatif / total * 100), 1) if total > 0 else 0
        pct_netral = round((netral / total * 100), 1) if total > 0 else 0

        return {
            "total": total,
            "positif": positif,
            "negatif": negatif,
            "netral": netral,
            "pct_positif": pct_positif,
            "pct_negatif": pct_negatif,
            "pct_netral": pct_netral,
        }

    @staticmethod
    def get_berita_terbaru(limit: int = 5) -> list[Berita]:
        """
        Mengambil 5 berita paling terbaru untuk ditampilkan di dashboard.

        Args:
            limit: Jumlah berita yang ditampilkan

        Returns:
            List objek Berita
        """
        return (
            Berita.query.filter_by(status="aktif")
            .order_by(desc(Berita.tanggal), desc(Berita.created_at))
            .limit(limit)
            .all()
        )

    @staticmethod
    def get_topik_terbanyak(limit: int = 5) -> list[dict]:
        """
        Mengambil topik yang paling banyak muncul dalam berita.

        Args:
            limit: Jumlah topik yang ditampilkan

        Returns:
            List dictionary {topik, jumlah}
        """
        result = (
            db.session.query(Berita.topik, func.count(Berita.id).label("jumlah"))
            .filter(Berita.topik.isnot(None), Berita.status == "aktif")
            .group_by(Berita.topik)
            .order_by(desc("jumlah"))
            .limit(limit)
            .all()
        )

        # Jika tidak ada data, kembalikan data dummy
        if not result:
            return DashboardService._get_dummy_topik()

        total = sum(r.jumlah for r in result)
        return [
            {
                "topik": r.topik,
                "jumlah": r.jumlah,
                "pct": round(r.jumlah / total * 100, 1) if total > 0 else 0,
            }
            for r in result
        ]

    @staticmethod
    def get_media_teraktif(limit: int = 5) -> list[dict]:
        """
        Mengambil media yang paling banyak memberitakan OJK.

        Args:
            limit: Jumlah media yang ditampilkan

        Returns:
            List dictionary {media, jumlah}
        """
        result = (
            db.session.query(Berita.media, func.count(Berita.id).label("jumlah"))
            .filter(Berita.media.isnot(None), Berita.status == "aktif")
            .group_by(Berita.media)
            .order_by(desc("jumlah"))
            .limit(limit)
            .all()
        )

        if not result:
            return DashboardService._get_dummy_media()

        return [{"media": r.media, "jumlah": r.jumlah} for r in result]

    @staticmethod
    def get_kota_terbanyak(limit: int = 5) -> list[dict]:
        """
        Mengambil kota yang paling banyak disebut dalam berita.

        Args:
            limit: Jumlah kota yang ditampilkan

        Returns:
            List dictionary {kota, jumlah}
        """
        result = (
            db.session.query(Berita.wilayah, func.count(Berita.id).label("jumlah"))
            .filter(Berita.wilayah.isnot(None), Berita.status == "aktif")
            .group_by(Berita.wilayah)
            .order_by(desc("jumlah"))
            .limit(limit)
            .all()
        )

        if not result:
            return DashboardService._get_dummy_kota()

        return [{"kota": r.wilayah, "jumlah": r.jumlah} for r in result]

    @staticmethod
    def get_trend_harian(hari: int = 7) -> dict:
        """
        Mengambil data trend berita harian untuk chart.

        Args:
            hari: Jumlah hari ke belakang

        Returns:
            Dictionary dengan labels (tanggal) dan data (jumlah berita)
        """
        today = datetime.now().date()
        labels = []
        data_total = []
        data_positif = []
        data_negatif = []
        data_netral = []

        for i in range(hari - 1, -1, -1):
            tanggal = today - timedelta(days=i)
            tanggal_dt = datetime.combine(tanggal, datetime.min.time())
            tanggal_dt_end = tanggal_dt + timedelta(days=1)

            berita_hari = Berita.query.filter(
                Berita.status == "aktif",
                Berita.tanggal >= tanggal_dt,
                Berita.tanggal < tanggal_dt_end,
            )

            total = berita_hari.count()
            positif = berita_hari.filter(Berita.sentimen == "Positif").count()
            negatif = berita_hari.filter(Berita.sentimen == "Negatif").count()
            netral = berita_hari.filter(Berita.sentimen == "Netral").count()

            labels.append(tanggal.strftime("%d %b"))
            data_total.append(total)
            data_positif.append(positif)
            data_negatif.append(negatif)
            data_netral.append(netral)

        # Jika semua data 0, tambahkan dummy data agar chart terlihat
        if all(v == 0 for v in data_total):
            data_total = DashboardService._generate_dummy_trend(hari)
            data_positif = [max(0, v - 5) for v in data_total]
            data_negatif = [max(0, v // 5) for v in data_total]
            data_netral = [
                data_total[i] - data_positif[i] - data_negatif[i]
                for i in range(len(data_total))
            ]

        return {
            "labels": labels,
            "total": data_total,
            "positif": data_positif,
            "negatif": data_negatif,
            "netral": data_netral,
        }

    @staticmethod
    def get_trend_bulanan(bulan: int = 6) -> dict:
        """
        Mengambil data trend berita bulanan untuk chart.

        Args:
            bulan: Jumlah bulan ke belakang

        Returns:
            Dictionary dengan labels dan data
        """
        from dateutil.relativedelta import relativedelta

        today = datetime.now()
        labels = []
        data = []

        nama_bulan = ["", "Jan", "Feb", "Mar", "Apr", "Mei", "Jun",
                       "Jul", "Agt", "Sep", "Okt", "Nov", "Des"]

        for i in range(bulan - 1, -1, -1):
            target = today - relativedelta(months=i)
            jumlah = Berita.query.filter(
                Berita.status == "aktif",
                Berita.bulan == target.month,
                Berita.tahun == target.year,
            ).count()

            labels.append(f"{nama_bulan[target.month]} {target.year}")
            data.append(jumlah)

        return {"labels": labels, "data": data}

    @staticmethod
    def get_sebaran_media() -> list[dict]:
        """
        Mengambil semua media beserta jumlah beritanya.

        Returns:
            List dictionary {media, jumlah, pct}
        """
        result = (
            db.session.query(Berita.media, func.count(Berita.id).label("jumlah"))
            .filter(Berita.media.isnot(None), Berita.status == "aktif")
            .group_by(Berita.media)
            .order_by(desc("jumlah"))
            .all()
        )

        if not result:
            return DashboardService._get_dummy_media_full()

        total = sum(r.jumlah for r in result)
        return [
            {
                "media": r.media,
                "jumlah": r.jumlah,
                "pct": round(r.jumlah / total * 100, 1) if total > 0 else 0,
            }
            for r in result
        ]

    @staticmethod
    def get_sebaran_wilayah() -> list[dict]:
        """
        Mengambil sebaran berita per wilayah untuk peta.

        Returns:
            List dictionary {wilayah, jumlah}
        """
        result = (
            db.session.query(Berita.wilayah, func.count(Berita.id).label("jumlah"))
            .filter(Berita.wilayah.isnot(None), Berita.status == "aktif")
            .group_by(Berita.wilayah)
            .order_by(desc("jumlah"))
            .all()
        )

        if not result:
            return DashboardService._get_dummy_wilayah()

        return [{"wilayah": r.wilayah, "jumlah": r.jumlah} for r in result]

    # ======= DUMMY DATA HELPERS =======

    @staticmethod
    def _generate_dummy_trend(hari: int) -> list[int]:
        """Menghasilkan data trend dummy yang terlihat realistis."""
        import random
        random.seed(42)
        base = [random.randint(15, 45) for _ in range(hari)]
        return base

    @staticmethod
    def _get_dummy_topik() -> list[dict]:
        """Data dummy topik untuk dashboard saat database kosong."""
        return [
            {"topik": "Pinjaman Online", "jumlah": 38, "pct": 30.4},
            {"topik": "Literasi Keuangan", "jumlah": 27, "pct": 21.6},
            {"topik": "Investasi", "jumlah": 22, "pct": 17.6},
            {"topik": "Perbankan", "jumlah": 18, "pct": 14.4},
            {"topik": "Fintech", "jumlah": 20, "pct": 16.0},
        ]

    @staticmethod
    def _get_dummy_media() -> list[dict]:
        """Data dummy media untuk dashboard saat database kosong."""
        return [
            {"media": "Kompas.com", "jumlah": 28},
            {"media": "Detik.com", "jumlah": 22},
            {"media": "CNBC Indonesia", "jumlah": 16},
            {"media": "Tribun Jabar", "jumlah": 14},
            {"media": "Bisnis Indonesia", "jumlah": 11},
        ]

    @staticmethod
    def _get_dummy_media_full() -> list[dict]:
        """Data dummy media lengkap."""
        return [
            {"media": "Kompas.com", "jumlah": 28, "pct": 30.4},
            {"media": "Detik.com", "jumlah": 22, "pct": 23.9},
            {"media": "CNBC Indonesia", "jumlah": 16, "pct": 17.4},
            {"media": "Tribun Jabar", "jumlah": 14, "pct": 15.2},
            {"media": "Bisnis Indonesia", "jumlah": 11, "pct": 12.0},
            {"media": "Pikiran Rakyat", "jumlah": 1, "pct": 1.1},
        ]

    @staticmethod
    def _get_dummy_kota() -> list[dict]:
        """Data dummy kota untuk dashboard saat database kosong."""
        return [
            {"kota": "Bandung", "jumlah": 45},
            {"kota": "Bogor", "jumlah": 28},
            {"kota": "Bekasi", "jumlah": 24},
            {"kota": "Cirebon", "jumlah": 12},
            {"kota": "Karawang", "jumlah": 8},
        ]

    @staticmethod
    def _get_dummy_wilayah() -> list[dict]:
        """Data dummy wilayah untuk peta."""
        return [
            {"wilayah": "Bandung", "jumlah": 45},
            {"wilayah": "Bogor", "jumlah": 28},
            {"wilayah": "Bekasi", "jumlah": 24},
            {"wilayah": "Depok", "jumlah": 18},
            {"wilayah": "Cirebon", "jumlah": 12},
            {"wilayah": "Karawang", "jumlah": 8},
            {"wilayah": "Tasikmalaya", "jumlah": 6},
            {"wilayah": "Garut", "jumlah": 5},
            {"wilayah": "Sukabumi", "jumlah": 4},
            {"wilayah": "Cianjur", "jumlah": 3},
        ]
