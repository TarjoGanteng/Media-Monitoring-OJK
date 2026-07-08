"""
database/extensions.py - Inisialisasi ekstensi Flask
"""

from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager

# Instance SQLAlchemy - diinisialisasi di sini, didaftarkan di app factory
db = SQLAlchemy()

# Instance LoginManager
login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message = "Silakan login untuk mengakses halaman ini."
login_manager.login_message_category = "error"
