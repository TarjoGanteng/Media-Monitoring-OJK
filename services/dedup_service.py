"""
services/dedup_service.py - Layanan deduplikasi berita OJK

Mendeteksi dan menghapus berita duplikat dalam 3 lapis:
1. Duplikat URL (link persis sama)
2. Duplikat judul (teks persis sama)
3. Duplikat mirip (judul sangat mirip, threshold >= 88%)
"""

import re
import logging
from difflib import SequenceMatcher
from collections import defaultdict
from datetime import timedelta

logger = logging.getLogger(__name__)


# ─── Utilitas ─────────────────────────────────────────────────────────────────

def _normalize(teks: str) -> str:
    """Normalisasi teks: lowercase, hapus tanda baca, whitespace tunggal."""
    teks = teks.lower().strip()
    teks = re.sub(r"[^\w\s]", "", teks)
    teks = re.sub(r"\s+", " ", teks)
    return teks


def _similarity(a: str, b: str) -> float:
    """Hitung kemiripan dua string (0.0 – 1.0)."""
    return SequenceMatcher(None, _normalize(a), _normalize(b)).ratio()


def _skor_kelengkapan(b) -> int:
    """Beri skor kelengkapan data sebuah berita. Makin tinggi = makin baik."""
    s = 0
    if b.gambar_url:                      s += 4
    if b.isi and len(b.isi) > 100:        s += 4
    if b.ringkasan and len(b.ringkasan) > 30: s += 3
    if b.narasumber:                      s += 2
    if b.wilayah:                         s += 1
    if b.sentimen in ("Positif", "Negatif"): s += 1
    return s


def _pilih_terbaik(berita_list: list):
    """Dari sekelompok duplikat, pilih satu berita yang paling lengkap datanya."""
    return max(berita_list, key=_skor_kelengkapan)


# ─── Service Utama ────────────────────────────────────────────────────────────

class DeduplicateService:
    """Layanan deduplikasi berita OJK di database."""

    # ── Preview (tanpa hapus) ─────────────────────────────────────────────────

    @staticmethod
    def preview() -> dict:
        """
        Cek jumlah duplikat yang ada tanpa menghapus apapun.
        Gunakan endpoint ini sebelum menjalankan penghapusan.
        """
        from database.extensions import db
        from database.models import Berita
        from sqlalchemy import func

        total_aktif = Berita.query.filter_by(status="aktif").count()

        dup_link = db.session.query(
            func.count(Berita.id).label("jml")
        ).filter(
            Berita.status == "aktif",
            Berita.link.isnot(None), Berita.link != "",
        ).group_by(Berita.link).having(func.count(Berita.id) > 1).count()

        dup_judul = db.session.query(
            func.count(Berita.id).label("jml")
        ).filter(
            Berita.status == "aktif",
            Berita.judul.isnot(None), Berita.judul != "",
        ).group_by(Berita.judul).having(func.count(Berita.id) > 1).count()

        # Estimasi near-duplicate: batasi 200 terbaru untuk preview cepat
        sample = (
            Berita.query.filter_by(status="aktif")
            .order_by(Berita.tanggal.desc())
            .limit(200).all()
        )
        near_dup_count = DeduplicateService._hitung_near_dup(sample, threshold=0.88)

        return {
            "total_berita": total_aktif,
            "grup_duplikat_url": dup_link,
            "grup_duplikat_judul": dup_judul,
            "estimasi_near_duplicate": near_dup_count,
        }

    @staticmethod
    def _hitung_near_dup(berita_list: list, threshold: float) -> int:
        """Hitung jumlah grup near-duplicate tanpa menghapus."""
        sudah = set()
        count = 0
        for i, b1 in enumerate(berita_list):
            if b1.id in sudah:
                continue
            for b2 in berita_list[i + 1:]:
                if b2.id in sudah:
                    continue
                if _similarity(b1.judul or "", b2.judul or "") >= threshold:
                    sudah.add(b2.id)
                    count += 1
        return count

    # ── Lapis 1: Duplikat URL ─────────────────────────────────────────────────

    @staticmethod
    def hapus_duplikat_link() -> dict:
        """Hapus berita dengan URL (link) yang 100% sama. Pertahankan yang paling lengkap."""
        from database.extensions import db
        from database.models import Berita
        from sqlalchemy import func

        grup_list = db.session.query(
            Berita.link, func.count(Berita.id).label("jml")
        ).filter(
            Berita.status == "aktif",
            Berita.link.isnot(None), Berita.link != "",
        ).group_by(Berita.link).having(func.count(Berita.id) > 1).all()

        dihapus = 0
        for row in grup_list:
            berita_list = Berita.query.filter_by(link=row.link).all()
            if len(berita_list) <= 1:
                continue
            terbaik = _pilih_terbaik(berita_list)
            for b in berita_list:
                if b.id != terbaik.id:
                    db.session.delete(b)
                    dihapus += 1

        db.session.commit()
        logger.info(f"[Dedup] Lapis 1 selesai: {dihapus} berita dihapus dari {len(grup_list)} grup URL duplikat.")
        return {"grup": len(grup_list), "dihapus": dihapus}

    # ── Lapis 2: Duplikat Judul Persis ───────────────────────────────────────

    @staticmethod
    def hapus_duplikat_judul_exact() -> dict:
        """Hapus berita dengan judul yang 100% sama persis. Pertahankan yang paling lengkap."""
        from database.extensions import db
        from database.models import Berita
        from sqlalchemy import func

        grup_list = db.session.query(
            Berita.judul, func.count(Berita.id).label("jml")
        ).filter(
            Berita.status == "aktif",
            Berita.judul.isnot(None), Berita.judul != "",
        ).group_by(Berita.judul).having(func.count(Berita.id) > 1).all()

        dihapus = 0
        for row in grup_list:
            berita_list = Berita.query.filter_by(judul=row.judul).all()
            if len(berita_list) <= 1:
                continue
            terbaik = _pilih_terbaik(berita_list)
            for b in berita_list:
                if b.id != terbaik.id:
                    db.session.delete(b)
                    dihapus += 1

        db.session.commit()
        logger.info(f"[Dedup] Lapis 2 selesai: {dihapus} berita dihapus dari {len(grup_list)} grup judul duplikat.")
        return {"grup": len(grup_list), "dihapus": dihapus}

    # ── Lapis 3: Near-Duplicate (judul sangat mirip) ──────────────────────────

    @staticmethod
    def hapus_duplikat_mirip(threshold: float = 0.88, max_berita: int = 2000) -> dict:
        """
        Hapus berita dengan judul yang sangat mirip (near-duplicate).
        Menggunakan algoritma perbandingan per-hari untuk efisiensi O(n * k²)
        di mana k = berita per hari (~50-100), bukan O(n²).

        Args:
            threshold: Ambang kemiripan (0.88 = 88% mirip dianggap duplikat)
            max_berita: Maks berita yang diproses (hindari timeout)
        """
        from database.extensions import db
        from database.models import Berita

        # Ambil berita terbaru sebagai kandidat
        semua = (
            Berita.query.filter_by(status="aktif")
            .order_by(Berita.tanggal.desc())
            .limit(max_berita).all()
        )

        # Kelompokkan per hari untuk efisiensi
        by_date = defaultdict(list)
        tanpa_tanggal = []
        for b in semua:
            if b.tanggal:
                by_date[b.tanggal.date()].append(b)
            else:
                tanpa_tanggal.append(b)

        sudah_hapus = set()
        total_dihapus = 0
        total_grup = 0
        batch = []  # Kumpulkan hapus dulu, commit di akhir

        for tgl, berita_hari in by_date.items():
            # Kandidat: hari ini + hari sebelumnya + hari sesudahnya
            kandidat = (
                berita_hari
                + by_date.get(tgl - timedelta(days=1), [])
                + by_date.get(tgl + timedelta(days=1), [])
            )
            kandidat_ids = set(b.id for b in kandidat)

            for b1 in berita_hari:
                if b1.id in sudah_hapus:
                    continue
                grup = [b1]

                for b2 in kandidat:
                    if b2.id == b1.id or b2.id in sudah_hapus:
                        continue
                    if _similarity(b1.judul or "", b2.judul or "") >= threshold:
                        grup.append(b2)

                if len(grup) > 1:
                    total_grup += 1
                    terbaik = _pilih_terbaik(grup)
                    for b in grup:
                        if b.id != terbaik.id and b.id not in sudah_hapus:
                            sudah_hapus.add(b.id)
                            batch.append(b.id)
                            total_dihapus += 1

        # Hapus dalam satu batch
        if batch:
            Berita.query.filter(Berita.id.in_(batch)).delete(synchronize_session=False)
            db.session.commit()

        logger.info(f"[Dedup] Lapis 3 selesai: {total_dihapus} berita dihapus dari {total_grup} grup near-duplicate.")
        return {"threshold": threshold, "grup": total_grup, "dihapus": total_dihapus}

    # ── Jalankan Semua ────────────────────────────────────────────────────────

    @staticmethod
    def jalankan_semua(threshold_mirip: float = 0.88) -> dict:
        """
        Jalankan 3 lapis deduplikasi secara berurutan.
        Urutan penting: URL → judul exact → near-duplicate.
        """
        logger.info("[Dedup] Memulai deduplikasi lengkap 3 lapis...")
        hasil_link  = DeduplicateService.hapus_duplikat_link()
        hasil_judul = DeduplicateService.hapus_duplikat_judul_exact()
        hasil_mirip = DeduplicateService.hapus_duplikat_mirip(threshold=threshold_mirip)

        total = hasil_link["dihapus"] + hasil_judul["dihapus"] + hasil_mirip["dihapus"]
        logger.info(f"[Dedup] Selesai: total {total} berita duplikat dihapus.")

        return {
            "total_dihapus": total,
            "lapis_1_url":   hasil_link,
            "lapis_2_judul": hasil_judul,
            "lapis_3_mirip": hasil_mirip,
        }
