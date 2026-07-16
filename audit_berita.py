"""
audit_berita.py
==============
Skrip audit menyeluruh untuk seluruh berita di database:
1. Pre-filter Lapis 1: Cek kata kunci kota Jabar secara cepat di teks berita
2. Filter Lapis 2 (AI): Kirim ke Cohere untuk penilaian relevansi Jawa Barat
3. Hapus berita yang tidak relevan
4. Update sentimen berita yang relevan

Jalankan: python audit_berita.py
"""

import time
from app import create_app
from database.extensions import db
from database.models import Berita
from services.ai_service import gemini

# ─── Konfigurasi ──────────────────────────────────────────────────────────────
DELAY_PER_REQUEST = 1.5  # Jeda antar request ke Cohere (detik)
BATCH_COMMIT = 10  # Simpan ke DB setiap N artikel
DRY_RUN = False  # True = hanya simulasi, tidak hapus/ubah data

# ─── Kata Kunci Kota/Wilayah Jawa Barat ───────────────────────────────────────
JABAR_KEYWORDS = [
    "jawa barat",
    "jabar",
    "bandung",
    "bogor",
    "depok",
    "bekasi",
    "cimahi",
    "cirebon",
    "sukabumi",
    "tasikmalaya",
    "banjar",
    "garut",
    "cianjur",
    "ciamis",
    "kuningan",
    "majalengka",
    "pangandaran",
    "purwakarta",
    "subang",
    "sumedang",
    "indramayu",
    "karawang",
    "ojk jabar",
    "ojk jawa barat",
    "ojk bandung",
]


def audit_berita():
    app = create_app("development")
    with app.app_context():
        semua_berita = (
            Berita.query.filter_by(status="aktif").order_by(Berita.id.asc()).all()
        )
        total = len(semua_berita)

        print(f"{'=' * 55}")
        print(f"  AUDIT BERITA — Total: {total} | DRY_RUN: {DRY_RUN}")
        print(f"{'=' * 55}\n")

        stat = {
            "lolos_l1": 0,  # Lolos pre-filter kata kunci
            "tolak_l1": 0,  # Ditolak pre-filter (tidak ada kata kota Jabar)
            "lolos_l2": 0,  # AI: relevan Jabar
            "tolak_l2": 0,  # AI: tidak relevan / "Tidak Relevan"
            "ai_gagal": 0,  # AI error / timeout
            "dihapus": 0,
            "diupdate": 0,
        }

        dihapus_ids = []
        to_commit = 0

        for idx, berita in enumerate(semua_berita, start=1):
            judul = berita.judul or ""
            isi = berita.isi or berita.ringkasan or ""
            teks = f"{judul} {isi}".lower()

            prefix = f"[{idx:4}/{total}] ID={berita.id}"

            # ── Lapis 1: Pre-filter kata kunci kota (sangat cepat) ────────────
            if not any(k in teks for k in JABAR_KEYWORDS):
                stat["tolak_l1"] += 1
                print(f"{prefix} | L1-TOLAK  | {judul[:55]}")
                if not DRY_RUN:
                    db.session.delete(berita)
                    dihapus_ids.append(berita.id)
                    stat["dihapus"] += 1
                    to_commit += 1
                else:
                    print("         ⚠ (DRY RUN - tidak dihapus)")
            else:
                stat["lolos_l1"] += 1
                # ── Lapis 2: AI Cohere ─────────────────────────────────────────
                try:
                    ai_result = gemini.analisis_berita(
                        judul, berita.isi, berita.ringkasan, berita.media
                    )

                    if ai_result is None:
                        # AI gagal (error/timeout), pertahankan berita
                        stat["ai_gagal"] += 1
                        print(f"{prefix} | AI-GAGAL  | {judul[:55]}")
                    elif ai_result.get("sentimen") == "Tidak Relevan":
                        stat["tolak_l2"] += 1
                        print(f"{prefix} | L2-TOLAK  | {judul[:55]}")
                        if not DRY_RUN:
                            db.session.delete(berita)
                            dihapus_ids.append(berita.id)
                            stat["dihapus"] += 1
                            to_commit += 1
                    else:
                        # Relevan → update sentimen & topik
                        stat["lolos_l2"] += 1
                        if not DRY_RUN:
                            berita.sentimen = ai_result["sentimen"]
                            berita.topik = ai_result.get("topik", berita.topik)
                            if ai_result.get("wilayah"):
                                berita.wilayah = ai_result["wilayah"]
                            if ai_result.get("ringkasan"):
                                berita.ringkasan = ai_result["ringkasan"]
                            if ai_result.get("narasumber"):
                                berita.narasumber = ai_result["narasumber"]
                            stat["diupdate"] += 1
                            to_commit += 1
                        print(
                            f"{prefix} | RELEVAN   | {ai_result.get('sentimen', '?'):7} | {judul[:45]}"
                        )

                    time.sleep(DELAY_PER_REQUEST)

                except Exception as e:
                    stat["ai_gagal"] += 1
                    print(f"{prefix} | AI-ERROR  | {e} | {judul[:40]}")

            # Commit setiap BATCH_COMMIT artikel
            if to_commit >= BATCH_COMMIT and not DRY_RUN:
                db.session.commit()
                to_commit = 0
                # Tampilkan progress ringkas
                sisa_neg = Berita.query.filter_by(sentimen="Negatif").count()
                print(
                    f"  >>> COMMIT | Diproses: {idx}/{total} | Dihapus: {stat['dihapus']} | Sisa Negatif DB: {sisa_neg}"
                )

        # Commit sisa
        if to_commit > 0 and not DRY_RUN:
            db.session.commit()

        # ── Laporan Akhir ─────────────────────────────────────────────────────
        pos = Berita.query.filter_by(sentimen="Positif").count()
        net = Berita.query.filter_by(sentimen="Netral").count()
        neg = Berita.query.filter_by(sentimen="Negatif").count()
        tot = Berita.query.filter_by(status="aktif").count()

        print(f"\n{'=' * 55}")
        print(f"  AUDIT SELESAI — {'(DRY RUN)' if DRY_RUN else '(LIVE)'}")
        print(f"{'=' * 55}")
        print(f"  Total diproses    : {total}")
        print(f"  Ditolak L1 (teks) : {stat['tolak_l1']}")
        print(f"  Ditolak L2 (AI)   : {stat['tolak_l2']}")
        print(f"  AI gagal          : {stat['ai_gagal']}")
        print(f"  Dihapus total     : {stat['dihapus']}")
        print(f"  Diupdate sentimen : {stat['diupdate']}")
        print(f"  Lolos (relevan)   : {stat['lolos_l2']}")
        print(f"{'─' * 55}")
        print(f"  Sisa Berita DB    : {tot}")
        print(f"  Positif           : {pos}")
        print(f"  Netral            : {net}")
        print(f"  Negatif           : {neg}")
        print(f"{'=' * 55}")


if __name__ == "__main__":
    audit_berita()
