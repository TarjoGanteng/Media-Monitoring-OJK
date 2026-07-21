"""
services/dashboard_service.py - Service untuk data dashboard dan statistik
"""

import logging
from datetime import datetime, timedelta
from sqlalchemy import func, desc, case
from database.extensions import db
from database.models import Berita

logger = logging.getLogger(__name__)


def _date_str_expr(field):
    """Helper ekspresi tanggal yang kompatibel dengan SQLite & PostgreSQL."""
    try:
        bind = db.session.get_bind()
        if bind and bind.dialect.name == "postgresql":
            return func.to_char(field, "YYYY-MM-DD")
    except Exception:
        pass
    return func.strftime("%Y-%m-%d", field)


class DashboardService:
    """Service untuk mengumpulkan data statistik yang ditampilkan di dashboard."""

    @staticmethod
    def _apply_media_filter(query, tipe_media: str = "semua"):
        if tipe_media == "lokal":
            return query.filter(Berita.jenis_media == "Lokal")
        elif tipe_media == "non-lokal":
            return query.filter(Berita.jenis_media == "Non-Lokal")
        return query

    @staticmethod
    def get_statistik_utama(tipe_media: str = "semua") -> dict:
        """
        Mengambil statistik utama: total berita, positif, negatif, netral.

        Returns:
            Dictionary statistik utama
        """
        base_query = DashboardService._apply_media_filter(Berita.query.filter_by(status="aktif"), tipe_media)

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
    def get_topik_terbanyak(limit: int = 5, tipe_media: str = "semua") -> list[dict]:
        """
        Mengambil topik yang paling banyak muncul dalam berita.

        Args:
            limit: Jumlah topik yang ditampilkan

        Returns:
            List dictionary {topik, jumlah}
        """
        query = (
            db.session.query(Berita.topik, func.count(Berita.id).label("jumlah"))
            .filter(Berita.topik.isnot(None), Berita.status == "aktif")
        )
        query = DashboardService._apply_media_filter(query, tipe_media)
        result = query.group_by(Berita.topik).order_by(desc("jumlah")).limit(limit).all()

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
    def get_media_teraktif(limit: int = 5, tipe_media: str = "semua") -> list[dict]:
        """
        Mengambil media yang paling banyak memberitakan OJK.

        Args:
            limit: Jumlah media yang ditampilkan

        Returns:
            List dictionary {media, jumlah}
        """
        query = (
            db.session.query(Berita.media, func.count(Berita.id).label("jumlah"))
            .filter(Berita.media.isnot(None), Berita.status == "aktif")
        )
        query = DashboardService._apply_media_filter(query, tipe_media)
        result = query.group_by(Berita.media).order_by(desc("jumlah")).limit(limit).all()

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
    def get_trend_harian(hari: int = 7, tipe_media: str = "semua") -> dict:
        """
        Mengambil data trend berita harian untuk chart.
        Dioptimasi: menggunakan 1 query GROUP BY, bukan N×4 query.

        Args:
            hari: Jumlah hari ke belakang

        Returns:
            Dictionary dengan labels (tanggal) dan data (jumlah berita)
        """
        today = datetime.now().date()
        start_date = today - timedelta(days=hari - 1)
        start_dt = datetime.combine(start_date, datetime.min.time())
        end_dt = datetime.combine(today, datetime.max.time())

        tgl_expr = _date_str_expr(Berita.tanggal)

        # Satu query dengan GROUP BY tanggal dan agregasi sentimen
        query = (
            db.session.query(
                tgl_expr.label("tgl"),
                func.count(Berita.id).label("total"),
                func.sum(case((Berita.sentimen == "Positif", 1), else_=0)).label(
                    "positif"
                ),
                func.sum(case((Berita.sentimen == "Negatif", 1), else_=0)).label(
                    "negatif"
                ),
                func.sum(case((Berita.sentimen == "Netral", 1), else_=0)).label(
                    "netral"
                ),
            )
            .filter(
                Berita.status == "aktif",
                Berita.tanggal >= start_dt,
                Berita.tanggal <= end_dt,
            )
        )
        query = DashboardService._apply_media_filter(query, tipe_media)
        rows = query.group_by(tgl_expr).all()

        # Buat mapping tanggal -> data row
        data_map = {r.tgl: r for r in rows}

        date_range = [(today - timedelta(days=i)) for i in range(hari - 1, -1, -1)]
        labels = [d.strftime("%d %b") for d in date_range]
        data_total, data_positif, data_negatif, data_netral = [], [], [], []

        for d in date_range:
            r = data_map.get(d.strftime("%Y-%m-%d"))
            data_total.append(int(r.total) if r else 0)
            data_positif.append(int(r.positif) if r else 0)
            data_negatif.append(int(r.negatif) if r else 0)
            data_netral.append(int(r.netral) if r else 0)

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
    def get_trend_bulanan(bulan: int = 6, tipe_media: str = "semua") -> dict:
        from dateutil.relativedelta import relativedelta

        today = datetime.now()
        labels = []
        data_total = []
        data_positif = []
        data_negatif = []
        data_netral = []

        nama_bulan = [
            "",
            "Jan",
            "Feb",
            "Mar",
            "Apr",
            "Mei",
            "Jun",
            "Jul",
            "Agt",
            "Sep",
            "Okt",
            "Nov",
            "Des",
        ]

        for i in range(bulan - 1, -1, -1):
            target = today - relativedelta(months=i)
            base_query = Berita.query.filter(
                Berita.status == "aktif",
                Berita.bulan == target.month,
                Berita.tahun == target.year,
            )
            base_query = DashboardService._apply_media_filter(base_query, tipe_media)

            total = base_query.count()
            positif = base_query.filter(Berita.sentimen == "Positif").count()
            negatif = base_query.filter(Berita.sentimen == "Negatif").count()
            netral = base_query.filter(Berita.sentimen == "Netral").count()

            labels.append(f"{nama_bulan[target.month]} {target.year}")
            data_total.append(total)
            data_positif.append(positif)
            data_negatif.append(negatif)
            data_netral.append(netral)

        if all(v == 0 for v in data_total):
            data_total = DashboardService._generate_dummy_trend(bulan)
            data_positif = [max(0, v - 10) for v in data_total]
            data_negatif = [max(0, v // 3) for v in data_total]
            data_netral = [
                data_total[i] - data_positif[i] - data_negatif[i] for i in range(bulan)
            ]

        return {
            "labels": labels,
            "total": data_total,
            "positif": data_positif,
            "negatif": data_negatif,
            "netral": data_netral,
        }

    @staticmethod
    def get_trend_mingguan(minggu: int = 4, tipe_media: str = "semua") -> dict:
        labels = []
        data_total = []
        data_positif = []
        data_negatif = []
        data_netral = []

        today = datetime.now().date()

        for i in range(minggu - 1, -1, -1):
            start_date = today - timedelta(days=today.weekday() + (i * 7))
            end_date = start_date + timedelta(days=6)

            start_dt = datetime.combine(start_date, datetime.min.time())
            end_dt = datetime.combine(end_date, datetime.max.time())

            base_query = Berita.query.filter(
                Berita.status == "aktif",
                Berita.tanggal >= start_dt,
                Berita.tanggal <= end_dt,
            )
            base_query = DashboardService._apply_media_filter(base_query, tipe_media)

            total = base_query.count()
            positif = base_query.filter(Berita.sentimen == "Positif").count()
            negatif = base_query.filter(Berita.sentimen == "Negatif").count()
            netral = base_query.filter(Berita.sentimen == "Netral").count()

            labels.append(f"M{minggu - i} {start_date.strftime('%b')}")
            data_total.append(total)
            data_positif.append(positif)
            data_negatif.append(negatif)
            data_netral.append(netral)

        if all(v == 0 for v in data_total):
            data_total = DashboardService._generate_dummy_trend(minggu)
            data_positif = [max(0, v - 5) for v in data_total]
            data_negatif = [max(0, v // 4) for v in data_total]
            data_netral = [
                data_total[i] - data_positif[i] - data_negatif[i] for i in range(minggu)
            ]

        return {
            "labels": labels,
            "total": data_total,
            "positif": data_positif,
            "negatif": data_negatif,
            "netral": data_netral,
        }

    @staticmethod
    def get_sebaran_media(tipe_media: str = "semua") -> list[dict]:
        """
        Mengambil semua media beserta jumlah beritanya.

        Returns:
            List dictionary {media, jumlah, pct}
        """
        query = (
            db.session.query(Berita.media, func.count(Berita.id).label("jumlah"))
            .filter(Berita.media.isnot(None), Berita.status == "aktif")
        )
        query = DashboardService._apply_media_filter(query, tipe_media)
        result = query.group_by(Berita.media).order_by(desc("jumlah")).all()

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
            db.session.query(
                Berita.wilayah,
                func.count(Berita.id).label("jumlah"),
                func.sum(case((Berita.sentimen == "Positif", 1), else_=0)).label(
                    "positif"
                ),
                func.sum(case((Berita.sentimen == "Negatif", 1), else_=0)).label(
                    "negatif"
                ),
                func.sum(case((Berita.sentimen == "Netral", 1), else_=0)).label(
                    "netral"
                ),
            )
            .filter(Berita.wilayah.isnot(None), Berita.status == "aktif")
            .group_by(Berita.wilayah)
            .order_by(desc("jumlah"))
            .all()
        )

        if not result:
            return DashboardService._get_dummy_wilayah()

        return [
            {
                "wilayah": r.wilayah,
                "jumlah": r.jumlah,
                "positif": int(r.positif) if r.positif else 0,
                "negatif": int(r.negatif) if r.negatif else 0,
                "netral": int(r.netral) if r.netral else 0,
            }
            for r in result
        ]

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
            {
                "wilayah": "Bandung",
                "jumlah": 45,
                "positif": 20,
                "netral": 15,
                "negatif": 10,
            },
            {
                "wilayah": "Bogor",
                "jumlah": 28,
                "positif": 10,
                "netral": 10,
                "negatif": 8,
            },
            {
                "wilayah": "Bekasi",
                "jumlah": 24,
                "positif": 12,
                "netral": 8,
                "negatif": 4,
            },
            {"wilayah": "Depok", "jumlah": 18, "positif": 8, "netral": 6, "negatif": 4},
            {
                "wilayah": "Cirebon",
                "jumlah": 12,
                "positif": 6,
                "netral": 4,
                "negatif": 2,
            },
            {
                "wilayah": "Karawang",
                "jumlah": 8,
                "positif": 4,
                "netral": 3,
                "negatif": 1,
            },
            {
                "wilayah": "Tasikmalaya",
                "jumlah": 6,
                "positif": 3,
                "netral": 2,
                "negatif": 1,
            },
            {"wilayah": "Garut", "jumlah": 5, "positif": 2, "netral": 2, "negatif": 1},
            {
                "wilayah": "Sukabumi",
                "jumlah": 4,
                "positif": 2,
                "netral": 1,
                "negatif": 1,
            },
            {
                "wilayah": "Cianjur",
                "jumlah": 3,
                "positif": 1,
                "netral": 1,
                "negatif": 1,
            },
        ]

    # ======= AI DASHBOARD SUMMARY =======

    @staticmethod
    def get_ringkasan_ai_dashboard() -> dict:
        """
        Membuat ringkasan/analisis harian berbasis AI (Gemini) untuk ditampilkan
        di card 'RINGKASAN AI' pada dashboard.

        Mengambil berita 24 jam terakhir, menyusun konteks lengkap, lalu
        meminta Gemini membuat analisis naratif singkat dalam Bahasa Indonesia.

        Returns:
            Dict {
                tersedia: bool,
                ringkasan: str,        # Narasi utama 2-3 kalimat
                topik_utama: str,      # Topik yang paling banyak dibahas
                sentimen_dominan: str, # Positif/Negatif/Netral
                total_hari_ini: int,   # Jumlah berita hari ini
                kota_terbanyak: str,   # Kota paling banyak disebut hari ini
                media_terbanyak: str,  # Media paling aktif hari ini
                waktu_generate: str,   # Waktu analisis dibuat
            }
        """
        from datetime import datetime, timedelta

        # --- Kumpulkan data berita hari ini ---
        now = datetime.now()
        sejak = now - timedelta(hours=24)

        berita_hari_ini = (
            Berita.query.filter(
                Berita.status == "aktif",
                Berita.tanggal >= sejak,
            )
            .order_by(Berita.tanggal.desc())
            .limit(30)  # Maks 30 berita terbaru sebagai konteks
            .all()
        )

        # Statistik sentimen hari ini
        total = len(berita_hari_ini)
        positif = sum(1 for b in berita_hari_ini if b.sentimen == "Positif")
        negatif = sum(1 for b in berita_hari_ini if b.sentimen == "Negatif")
        netral = sum(1 for b in berita_hari_ini if b.sentimen == "Netral")

        # Topik terbanyak
        from collections import Counter

        topik_counter = Counter(b.topik for b in berita_hari_ini if b.topik)
        wilayah_counter = Counter(b.wilayah for b in berita_hari_ini if b.wilayah)
        media_counter = Counter(b.media for b in berita_hari_ini if b.media)

        topik_utama = (
            topik_counter.most_common(1)[0][0] if topik_counter else "Regulasi"
        )
        kota_terbanyak = (
            wilayah_counter.most_common(1)[0][0] if wilayah_counter else "-"
        )
        media_terbanyak = media_counter.most_common(1)[0][0] if media_counter else "-"

        sentimen_dominan = (
            "Positif"
            if positif >= negatif and positif >= netral
            else "Negatif"
            if negatif >= positif and negatif >= netral
            else "Netral"
        )

        # Jika tidak ada berita hari ini, kembalikan kosong
        if total == 0:
            return {
                "tersedia": False,
                "ringkasan": "Belum ada berita yang dikumpulkan hari ini.",
                "topik_utama": "-",
                "sentimen_dominan": "Netral",
                "total_hari_ini": 0,
                "kota_terbanyak": "-",
                "media_terbanyak": "-",
                "waktu_generate": now.strftime("%H:%M WIB"),
            }

        # --- Susun konteks untuk Gemini ---
        judul_list = "\n".join(
            f"- [{b.sentimen or 'Netral'}] {b.judul}" for b in berita_hari_ini[:15]
        )
        topik_str = ", ".join(f"{t}({c})" for t, c in topik_counter.most_common(5))
        kota_str = ", ".join(f"{k}({c})" for k, c in wilayah_counter.most_common(5))

        prompt = f"""Anda adalah analis media senior OJK (Otoritas Jasa Keuangan) Indonesia.
Berdasarkan data pemberitaan 24 jam terakhir, buat ringkasan analisis singkat dalam Bahasa Indonesia.

=== DATA PEMBERITAAN HARI INI ===
Tanggal: {now.strftime("%d %B %Y")}
Total berita: {total} artikel
Positif: {positif} | Negatif: {negatif} | Netral: {netral}
Topik terbanyak: {topik_str}
Kota paling banyak disebut: {kota_str}

Judul-judul berita terbaru:
{judul_list}

=== TUGAS ===
Buat ringkasan analisis naratif dalam 2-3 kalimat yang:
1. Menjelaskan isu/topik utama yang sedang banyak dibahas
2. Menyebutkan sentimen dominan dan apa maknanya bagi OJK
3. Menyebutkan kota atau wilayah yang paling aktif (jika relevan)

Gunakan bahasa formal, padat, dan profesional. Jangan gunakan bullet point.
Balas HANYA dengan paragraf narasi, tanpa judul atau penjelasan tambahan."""

        try:
            from services.ai_service import gemini
            from config import Config

            if not gemini.is_available():
                raise ValueError("AI tidak tersedia")

            res_text = None
            # Fallback 1: Cohere
            if hasattr(gemini, "_cohere") and gemini._cohere.is_available():
                try:
                    import requests
                    headers = {
                        "Authorization": f"Bearer {gemini._cohere._api_key}",
                        "Content-Type": "application/json"
                    }
                    payload = {
                        "model": "command-r-plus-08-2024",
                        "message": prompt
                    }
                    resp = requests.post("https://api.cohere.ai/v1/chat", headers=headers, json=payload, timeout=15)
                    if resp.status_code == 200:
                        res_text = resp.json().get("text", "").strip()
                except Exception:
                    pass

            # Fallback 2: Groq
            if not res_text and hasattr(gemini, "_groq") and gemini._groq.is_available():
                try:
                    import requests
                    headers = {
                        "Authorization": f"Bearer {gemini._groq._api_key}",
                        "Content-Type": "application/json"
                    }
                    payload = {
                        "model": "llama-3.3-70b-versatile",
                        "messages": [{"role": "user", "content": prompt}]
                    }
                    resp = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=15)
                    if resp.status_code == 200:
                        res_text = resp.json()["choices"][0]["message"]["content"].strip()
                except Exception:
                    pass

            # Fallback 3: Gemini 2.0 Flash Lite (New SDK)
            if not res_text and Config.GEMINI_API_KEY:
                try:
                    from google import genai
                    client = genai.Client(api_key=Config.GEMINI_API_KEY)
                    response = client.models.generate_content(
                        model="gemini-2.0-flash-lite",
                        contents=prompt
                    )
                    res_text = response.text.strip()
                except Exception:
                    import google.generativeai as genai_old
                    genai_old.configure(api_key=Config.GEMINI_API_KEY)
                    m = genai_old.GenerativeModel("models/gemini-2.0-flash-lite")
                    response = m.generate_content(prompt)
                    res_text = response.text.strip()

            if res_text:
                ringkasan_ai = res_text
            else:
                raise ValueError("Gagal mendapatkan respons dari provider AI")

        except Exception as e:
            logger.warning(f"[AI Dashboard] Gagal generate ringkasan: {e}")
            ringkasan_ai = (
                f"Hari ini terdapat {total} berita terkait OJK Jawa Barat "
                f"dengan sentimen {sentimen_dominan.lower()} mendominasi ({positif}P/{negatif}N/{netral}Ntrl). "
                f"Topik yang paling banyak dibahas adalah {topik_utama}."
            )

        return {
            "tersedia": True,
            "ringkasan": ringkasan_ai,
            "topik_utama": topik_utama,
            "sentimen_dominan": sentimen_dominan,
            "total_hari_ini": total,
            "kota_terbanyak": kota_terbanyak,
            "media_terbanyak": media_terbanyak,
            "waktu_generate": now.strftime("%H:%M WIB"),
        }
