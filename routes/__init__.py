"""
routes/__init__.py - Package routes
"""

from routes.dashboard import bp as dashboard_bp
from routes.pemberitaan import bp as pemberitaan_bp
from routes.crawler_api import bp as crawler_api_bp
from routes.halaman import bp as halaman_bp
from routes.auth import bp as auth_bp


def register_blueprints(app):
    """
    Mendaftarkan semua Blueprint ke Flask app.

    Args:
        app: Instance Flask application
    """
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(pemberitaan_bp)
    app.register_blueprint(crawler_api_bp)
    app.register_blueprint(halaman_bp)
