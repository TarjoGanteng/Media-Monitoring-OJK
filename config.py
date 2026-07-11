"""
config.py - Konfigurasi aplikasi Media Monitoring OJK
"""

import os

# Direktori root project
BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    """Konfigurasi dasar aplikasi."""

    # Keamanan aplikasi
    SECRET_KEY = os.environ.get("SECRET_KEY", "ojk-jabar-monitoring-secret-2024")

    # Google Gemini AI
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

    # Konfigurasi Database SQLite
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        f"sqlite:///{os.path.join(BASE_DIR, 'instance', 'media_monitoring.db')}",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = False  # Set True untuk debug query SQL

    # Konfigurasi Crawler
    CRAWLER_BASE_URL = "https://news.google.com/rss/search?q={keyword}&hl=id&gl=ID&ceid=ID:id"
    CRAWLER_KEYWORDS = [
        "OJK",
        "OJK Jawa Barat",
        "OJK Bandung",
        "Pinjaman Online OJK",
        "Literasi Keuangan OJK",
        "Investasi Ilegal OJK",
        "OJK Jabar",
    ]
    CRAWLER_MAX_ARTICLES = 50  # Batas artikel per keyword per crawl
    CRAWLER_TIMEOUT = 30  # Timeout request dalam detik

    # Konfigurasi Pagination
    ARTICLES_PER_PAGE = 10

    # Konfigurasi Aplikasi
    APP_NAME = "Media Monitoring OJK"
    APP_SUBTITLE = "OJK Provinsi Jawa Barat"
    APP_VERSION = "1.0.0"

    # Wilayah yang dipantau
    WILAYAH_JABAR = [
        "Bandung",
        "Bekasi",
        "Bogor",
        "Cirebon",
        "Depok",
        "Sukabumi",
        "Karawang",
        "Tasikmalaya",
        "Garut",
        "Cianjur",
        "Subang",
        "Purwakarta",
        "Indramayu",
        "Majalengka",
        "Sumedang",
        "Kuningan",
        "Ciamis",
        "Banjar",
        "Pangandaran",
    ]

    # Topik yang dipantau
    TOPIK_LIST = [
        "Pinjaman Online",
        "Literasi Keuangan",
        "Investasi",
        "Perbankan",
        "Asuransi",
        "Pasar Modal",
        "Fintech",
        "Perlindungan Konsumen",
        "Regulasi",
        "Pengawasan",
    ]


class DevelopmentConfig(Config):
    """Konfigurasi untuk development."""

    DEBUG = True
    SQLALCHEMY_ECHO = True


class ProductionConfig(Config):
    """Konfigurasi untuk production."""

    DEBUG = False
    SQLALCHEMY_ECHO = False


class TestingConfig(Config):
    """Konfigurasi untuk testing."""

    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"


# Mapping konfigurasi
config_map = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
    "default": DevelopmentConfig,
}


def get_config(env: str = "default") -> Config:
    """Mengembalikan konfigurasi berdasarkan environment."""
    return config_map.get(env, config_map["default"])
