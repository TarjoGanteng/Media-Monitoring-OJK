"""
database/extensions.py - Inisialisasi ekstensi Flask
"""

from flask_sqlalchemy import SQLAlchemy

# Instance SQLAlchemy - diinisialisasi di sini, didaftarkan di app factory
db = SQLAlchemy()
