import time
import logging
from app import create_app
from database.extensions import db
from database.models import Berita
from services.ai_service import gemini

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ReanalyzeNegatif")

app = create_app("development")


def jalankan():
    with app.app_context():
        # Hanya ambil yang berstatus Negatif agar proses cepat terlihat hasilnya oleh user
        berita_negatif = Berita.query.filter_by(
            status="aktif", sentimen="Negatif"
        ).all()
        logger.info(f"Mulai re-analisis khusus {len(berita_negatif)} berita NEGATIF...")

        sukses = 0
        gagal = 0
        berubah = 0

        for i, b in enumerate(berita_negatif):
            try:
                res = gemini.analisis_berita(b.judul, b.isi, b.ringkasan)
                if res:
                    sentimen_baru = res["sentimen"]
                    if sentimen_baru != "Negatif":
                        berubah += 1
                        logger.info(
                            f"[{i + 1}/{len(berita_negatif)}] '{b.judul[:40]}...' BERUBAH: Negatif -> {sentimen_baru}"
                        )
                    else:
                        logger.info(
                            f"[{i + 1}/{len(berita_negatif)}] '{b.judul[:40]}...' TETAP: Negatif"
                        )

                    b.sentimen = sentimen_baru
                    b.topik = res["topik"]
                    if res.get("wilayah"):
                        b.wilayah = res["wilayah"]
                    db.session.commit()
                    sukses += 1
                else:
                    gagal += 1
                    logger.warning(
                        f"[{i + 1}/{len(berita_negatif)}] '{b.judul[:40]}...' -> Gagal Analisis"
                    )

                # Jeda 4.5 detik untuk hindari limit 15 RPM
                time.sleep(4.5)
            except Exception as e:
                logger.error(f"Error pada ID {b.id}: {e}")
                time.sleep(5)

        logger.info(
            f"SELESAI! Berhasil: {sukses}, Gagal: {gagal}, Berubah dari Negatif: {berubah}"
        )


if __name__ == "__main__":
    jalankan()
