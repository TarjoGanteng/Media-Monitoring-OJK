"""
database/__init__.py - Package database
"""

from database.extensions import db
from database.models import Berita, CrawlLog, Keyword

__all__ = ["db", "Berita", "CrawlLog", "Keyword"]
