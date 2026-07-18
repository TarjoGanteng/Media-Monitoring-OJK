"""
database/models.py - Model database SQLAlchemy untuk Media Monitoring OJK
"""

from datetime import datetime
from database.extensions import db


class Berita(db.Model):
    """Model untuk menyimpan data berita hasil crawling."""

    __tablename__ = "berita"

    # --- Primary Key ---
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    # --- Konten Berita ---
    judul = db.Column(db.String(500), nullable=False)
    link = db.Column(db.String(1000), nullable=False, unique=True, index=True)
    media = db.Column(db.String(200), nullable=True)
    jenis_media = db.Column(db.String(20), nullable=True, default="Non-Lokal")
    tanggal = db.Column(db.DateTime, nullable=True)
    isi = db.Column(db.Text, nullable=True)
    ringkasan = db.Column(db.Text, nullable=True)
    gambar_url = db.Column(db.String(1000), nullable=True)  # URL thumbnail/og:image

    # --- Klasifikasi ---
    sentimen = db.Column(
        db.String(20), nullable=True, default="Netral"
    )  # Positif, Negatif, Netral
    topik = db.Column(db.String(200), nullable=True)
    wilayah = db.Column(db.String(200), nullable=True)
    narasumber = db.Column(db.String(500), nullable=True)

    # --- Waktu ---
    bulan = db.Column(db.Integer, nullable=True)
    tahun = db.Column(db.Integer, nullable=True)
    triwulan = db.Column(db.Integer, nullable=True)

    # --- Metadata ---
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    status = db.Column(
        db.String(20), default="aktif", nullable=False
    )  # aktif, arsip, hapus
    keyword = db.Column(db.String(200), nullable=True)  # keyword sumber crawl
    ai_checked = db.Column(
        db.Boolean, default=False, nullable=False
    )  # sudah dianalisis AI?
    ai_last_checked = db.Column(
        db.DateTime, nullable=True
    )  # waktu terakhir dianalisis/sinkronisasi AI

    def __repr__(self):
        return f"<Berita id={self.id} judul='{self.judul[:50]}...'>"

    def to_dict(self) -> dict:
        """Konversi model ke dictionary untuk JSON response."""
        return {
            "id": self.id,
            "judul": self.judul,
            "link": self.link,
            "media": self.media,
            "jenis_media": self.jenis_media,
            "tanggal": self.tanggal.isoformat() if self.tanggal else None,
            "isi": self.isi,
            "ringkasan": self.ringkasan,
            "gambar_url": self.gambar_url,
            "sentimen": self.sentimen,
            "topik": self.topik,
            "wilayah": self.wilayah,
            "narasumber": self.narasumber,
            "bulan": self.bulan,
            "tahun": self.tahun,
            "triwulan": self.triwulan,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "status": self.status,
            "keyword": self.keyword,
        }

    def get_sentimen_badge(self) -> str:
        """Mengembalikan class Bootstrap badge berdasarkan sentimen."""
        badges = {
            "Positif": "badge-positif",
            "Negatif": "badge-negatif",
            "Netral": "badge-netral",
        }
        return badges.get(self.sentimen, "badge-netral")

    def get_tanggal_formatted(self) -> str:
        """Mengembalikan tanggal dalam format Indonesia."""
        if not self.tanggal:
            return "-"
        bulan_id = [
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
        return f"{self.tanggal.day} {bulan_id[self.tanggal.month]} {self.tanggal.year} {self.tanggal.strftime('%H:%M')}"

    def get_media_favicon(self) -> str:
        """Mengembalikan URL favicon media via Google Favicon API."""
        MEDIA_DOMAIN_MAP = {
            "kompas.com": "kompas.com",
            "kompas": "kompas.com",
            "detik": "detik.com",
            "detik.com": "detik.com",
            "cnbc indonesia": "cnbcindonesia.com",
            "cnbc": "cnbcindonesia.com",
            "tribun": "tribunnews.com",
            "tribun jabar": "jabar.tribunnews.com",
            "tribunnews": "tribunnews.com",
            "bisnis indonesia": "bisnis.com",
            "bisnis": "bisnis.com",
            "antara": "antaranews.com",
            "antara news": "antaranews.com",
            "tempo": "tempo.co",
            "republika": "republika.co.id",
            "okezone": "okezone.com",
            "liputan6": "liputan6.com",
            "inews": "inews.id",
            "merdeka": "merdeka.com",
            "beritasatu": "beritasatu.com",
            "sindonews": "sindonews.com",
            "suara": "suara.com",
            "idntimes": "idntimes.com",
            "kumparan": "kumparan.com",
            "jpnn": "jpnn.com",
            "medcom": "medcom.id",
            "katadata": "katadata.co.id",
            "jabarprov": "jabarprov.go.id",
        }
        if not self.media:
            return "https://www.google.com/s2/favicons?domain=google.com&sz=64"
        media_lower = self.media.lower().strip()
        domain = MEDIA_DOMAIN_MAP.get(media_lower)
        if not domain:
            # Fallback: coba buat domain dari nama media
            domain = media_lower.replace(" ", "") + ".com"
        return f"https://www.google.com/s2/favicons?domain={domain}&sz=64"

    @staticmethod
    def hitung_triwulan(bulan: int) -> int:
        """Menghitung triwulan berdasarkan bulan."""
        if bulan in [1, 2, 3]:
            return 1
        elif bulan in [4, 5, 6]:
            return 2
        elif bulan in [7, 8, 9]:
            return 3
        else:
            return 4


class CrawlLog(db.Model):
    """Model untuk menyimpan log aktivitas crawling."""

    __tablename__ = "crawl_log"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    keyword = db.Column(db.String(200), nullable=False)
    jumlah_ditemukan = db.Column(db.Integer, default=0)
    jumlah_disimpan = db.Column(db.Integer, default=0)
    jumlah_duplikat = db.Column(db.Integer, default=0)
    status = db.Column(db.String(20), default="sukses")  # sukses, gagal
    pesan = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return (
            f"<CrawlLog id={self.id} keyword='{self.keyword}' status='{self.status}'>"
        )


class Keyword(db.Model):
    """Model untuk menyimpan daftar keyword crawling yang dapat dikelola."""

    __tablename__ = "keyword"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    kata = db.Column(db.String(200), nullable=False, unique=True)
    aktif = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<Keyword id={self.id} kata='{self.kata}'>"


class User(db.Model):
    """Model untuk menyimpan data pengguna dan role (RBAC)."""

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(100), unique=True, nullable=False, index=True)
    nama_lengkap = db.Column(db.String(150), nullable=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(
        db.String(20), nullable=False, default="staff"
    )  # super_admin, pemimpin, staff (karyawan)
    status = db.Column(
        db.String(20), nullable=False, default="aktif"
    )  # aktif, nonaktif
    last_login = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Implementasi properties wajib untuk Flask-Login (UserMixin fallback)
    @property
    def is_authenticated(self):
        return True

    @property
    def is_active(self):
        return self.status == "aktif"

    @property
    def is_anonymous(self):
        return False

    def get_id(self):
        return str(self.id)

    def __repr__(self):
        return f"<User id={self.id} username='{self.username}' role='{self.role}'>"


class Notifikasi(db.Model):
    """Model untuk menyimpan notifikasi/peringatan sistem."""

    __tablename__ = "notifikasi"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tipe = db.Column(
        db.String(20), nullable=False, default="info"
    )  # info, warning, danger, success
    judul = db.Column(db.String(255), nullable=False)
    pesan = db.Column(db.Text, nullable=False)
    link = db.Column(db.String(1000), nullable=True)
    is_read = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<Notifikasi id={self.id} tipe='{self.tipe}' is_read={self.is_read}>"


class Laporan(db.Model):
    """Model untuk menyimpan riwayat laporan yang digenerate."""

    __tablename__ = "laporan"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    nomor_laporan = db.Column(db.String(30), nullable=False, unique=True)  # LAP-MM-2026-001
    judul = db.Column(db.String(300), nullable=False)
    periode_label = db.Column(db.String(100), nullable=False)   # misal: "Triwulan II (Apr-Jun 2026)"
    jenis_periode = db.Column(db.String(20), nullable=False)    # harian/mingguan/bulanan/triwulan/tahunan/custom
    tanggal_dari = db.Column(db.Date, nullable=True)
    tanggal_sampai = db.Column(db.Date, nullable=True)
    wilayah = db.Column(db.String(100), nullable=True, default="Jawa Barat")
    topik = db.Column(db.String(200), nullable=True)            # null = semua topik
    jenis_media = db.Column(db.String(20), nullable=True)       # semua/lokal/non-lokal
    path_pdf = db.Column(db.String(500), nullable=True)         # path file PDF
    path_excel = db.Column(db.String(500), nullable=True)       # path file Excel
    dibuat_oleh = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Statistik snapshot saat laporan dibuat
    total_berita = db.Column(db.Integer, default=0)
    total_positif = db.Column(db.Integer, default=0)
    total_negatif = db.Column(db.Integer, default=0)
    total_netral = db.Column(db.Integer, default=0)

    # Relationship
    pembuat = db.relationship("User", foreign_keys=[dibuat_oleh], lazy="joined")

    def __repr__(self):
        return f"<Laporan id={self.id} nomor='{self.nomor_laporan}' periode='{self.periode_label}'>"

    def get_status(self) -> str:
        """Cek status file PDF — ada atau tidak."""
        import os
        if self.path_pdf and os.path.exists(self.path_pdf):
            return "selesai"
        return "tidak ada"
