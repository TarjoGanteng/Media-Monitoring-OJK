import os
import sys

# Tambahkan direktori root ke path agar import berfungsi
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app
from database.extensions import db
from database.models import Berita

app = create_app()
with app.app_context():
    # Hapus "Jawa Barat" dari wilayah agar tidak tampil di grafik kota
    count = Berita.query.filter(
        Berita.wilayah.in_(["Jawa Barat", "jawa barat", "Jabar", "jabar"])
    ).update({"wilayah": None})
    db.session.commit()
    print(
        f"Berhasil mengosongkan field wilayah untuk {count} berita yang tadinya berisi 'Jawa Barat'."
    )
