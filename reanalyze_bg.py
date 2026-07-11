import os
import time
import logging
from dotenv import load_dotenv

# Load env file first
load_dotenv()

from app import create_app
from database.extensions import db
from database.models import Berita
from services.ai_service import gemini

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Reanalyze")

app = create_app("development")

def jalankan():
    with app.app_context():
        from sqlalchemy import case
        order_case = case(
            (Berita.sentimen == 'Negatif', 1),
            (Berita.sentimen == 'Positif', 2),
            (Berita.sentimen == 'Netral', 3),
            else_=4
        )
        berita_all = Berita.query.filter_by(status='aktif').order_by(order_case, Berita.tanggal.desc()).all()
        logger.info(f"Mulai re-analisis sentimen {len(berita_all)} berita dengan panduan sentimen baru (OJK Perspective)...")
        
        sukses = 0
        gagal = 0
        for i, b in enumerate(berita_all):
            try:
                res = gemini.analisis_berita(b.judul, b.isi, b.ringkasan)
                if res:
                    b.sentimen = res["sentimen"]
                    b.topik = res["topik"]
                    if res.get("wilayah"): b.wilayah = res["wilayah"]
                    db.session.commit()
                    sukses += 1
                    logger.info(f"[{i+1}/{len(berita_all)}] '{b.judul[:40]}...' -> {b.sentimen}")
                else:
                    gagal += 1
                    logger.warning(f"[{i+1}/{len(berita_all)}] '{b.judul[:40]}...' -> Gagal Analisis")
                
                # Jeda 4.5 detik untuk hindari limit 15 RPM
                time.sleep(4.5)
            except Exception as e:
                logger.error(f"Error pada ID {b.id}: {e}")
                time.sleep(5)
                
        logger.info(f"SELESAI! Berhasil: {sukses}, Gagal: {gagal}")

if __name__ == "__main__":
    jalankan()
