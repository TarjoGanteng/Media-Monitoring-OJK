"""
reset_ai_check.py
=================
Script satu kali untuk me-reset flag ai_checked pada semua berita aktif,
sehingga AIReviewService akan menganalisis ulang semua berita dengan
prompt yang sudah diperketat (harus relevan dengan Jawa Barat).

Cara menjalankan:
    python reset_ai_check.py

Jalankan SEKALI, lalu restart app.py. Background AI service akan
secara bertahap menganalisis ulang dan menghapus berita yang tidak relevan.
"""

from dotenv import load_dotenv
load_dotenv()

from app import create_app
from database.extensions import db
from database.models import Berita
from sqlalchemy import update

app = create_app("development")

with app.app_context():
    # Hitung dulu berapa berita yang akan direset
    total = Berita.query.filter(Berita.status == "aktif").count()
    print(f"Total berita aktif: {total}")

    # Reset ai_checked = False dan ai_last_checked = NULL pada semua berita aktif
    result = db.session.execute(
        update(Berita)
        .where(Berita.status == "aktif")
        .values(ai_checked=False, ai_last_checked=None)
    )
    db.session.commit()

    print(f"[OK] Berhasil reset {result.rowcount} berita untuk dianalisis ulang.")
    print()
    print("Sekarang restart app.py, lalu background AI service akan")
    print("secara otomatis menganalisis ulang semua berita dengan filter yang lebih ketat.")
