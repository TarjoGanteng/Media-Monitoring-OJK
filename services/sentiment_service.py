"""
services/sentiment_service.py - Analisis sentimen berbasis keyword (rule-based)
Tidak menggunakan AI - menggunakan kamus kata positif/negatif bahasa Indonesia.
Akan digantikan AI pada tahap berikutnya.
"""

import re
import logging

logger = logging.getLogger(__name__)


class SentimentAnalyzer:
    """
    Pengklasifikasi sentimen berbasis keyword untuk berita keuangan/OJK.
    Menggunakan pendekatan lexicon-based dengan bobot kata.
    """

    # Kata-kata bersentimen POSITIF (konteks keuangan/OJK)
    KATA_POSITIF = {
        # Kinerja & Pertumbuhan
        "meningkat": 2, "tumbuh": 2, "bertumbuh": 2, "naik": 1, "menguat": 2,
        "berkembang": 2, "maju": 1, "peningkatan": 2, "pertumbuhan": 2,
        "rekor": 2, "tertinggi": 1, "surplus": 2, "positif": 1,
        # Keberhasilan & Pencapaian
        "berhasil": 3, "sukses": 3, "berhasil": 3, "prestasi": 2, "capaian": 2,
        "pencapaian": 2, "capai": 2, "raih": 2, "meraih": 2, "memenangkan": 2,
        "juara": 2, "terbaik": 2, "unggul": 2, "unggulan": 2,
        # Perlindungan & Keamanan
        "perlindungan": 2, "lindungi": 2, "aman": 2, "keamanan": 2, "terlindungi": 2,
        "selamat": 1, "terjamin": 2, "jaminan": 1, "penjaminan": 2,
        # Pendidikan & Literasi
        "literasi": 2, "edukasi": 2, "sosialisasi": 1, "seminar": 1, "workshop": 1,
        "pelatihan": 1, "bimbingan": 1, "pendampingan": 2, "pemahaman": 1,
        "meningkatkan literasi": 3, "literasi keuangan": 2,
        # Inovasi & Digital
        "inovasi": 2, "inovatif": 2, "digital": 1, "transformasi": 1,
        "modernisasi": 2, "teknologi": 1, "fintech": 1, "kolaborasi": 2,
        "sinergi": 2, "kerjasama": 1, "kemitraan": 2,
        # Stabilitas & Kepercayaan
        "stabil": 2, "stabilitas": 2, "kepercayaan": 2, "terpercaya": 2,
        "transparan": 2, "transparansi": 2, "akuntabel": 2, "kredibel": 2,
        # Ekonomi positif
        "pemulihan": 2, "pulih": 2, "bangkit": 2, "investasi": 1,
        "inklusi": 2, "inklusi keuangan": 3, "akses": 1, "kemudahan": 2,
        # OJK konteks positif
        "pengawasan ketat": 2, "tertib": 1, "patuh": 1, "kepatuhan": 2,
        "regulasi": 1, "terdaftar": 2, "berizin": 3, "legal": 2,
        "resmi": 2, "sah": 1, "mendukung": 1, "dukungan": 1,
        # Sosial
        "kesejahteraan": 2, "sejahtera": 2, "manfaat": 1, "bermanfaat": 2,
        "membantu": 1, "meringankan": 1, "pemberdayaan": 2,
    }

    # Kata-kata bersentimen NEGATIF (konteks keuangan/OJK)
    KATA_NEGATIF = {
        # Penipuan & Ilegalitas
        "ilegal": 4, "penipuan": 4, "penipu": 4, "modus": 3, "curang": 3,
        "manipulasi": 3, "penggelapan": 4, "korupsi": 4, "suap": 3,
        "kejahatan": 3, "kriminal": 3, "pidana": 3, "melanggar": 2,
        "pelanggaran": 2, "tidak berizin": 4, "bodong": 4, "palsu": 3,
        "fiktif": 3, "rekayasa": 2,
        # Pinjol & Investasi Bodong
        "pinjol": 2, "rentenir": 3, "lintah darat": 4, "bunga tinggi": 2,
        "bunga mencekik": 3, "jeratan": 3, "terjerat": 3, "terlilit": 3,
        "investasi bodong": 4, "investasi ilegal": 4, "skema ponzi": 4,
        "money game": 3, "robot trading": 2, "binary option": 3,
        # Kerugian
        "rugi": 3, "kerugian": 3, "menderita kerugian": 4, "bangkrut": 3,
        "pailit": 3, "gagal bayar": 3, "kredit macet": 3, "tunggakan": 2,
        "hutang": 1, "lilitan hutang": 3, "terjerat hutang": 3,
        # Penurunan
        "turun": 1, "menurun": 1, "melemah": 1, "anjlok": 3, "ambruk": 3,
        "terpuruk": 3, "runtuh": 3, "kolaps": 3, "jatuh": 1,
        # Korban
        "korban": 3, "dirugikan": 3, "tertipu": 3, "ditipu": 3,
        "masyarakat dirugikan": 4, "nasabah dirugikan": 4,
        # Masalah & Konflik
        "masalah": 1, "permasalahan": 1, "sengketa": 2, "gugatan": 2,
        "tuntutan": 2, "somasi": 2, "sanksi": 2, "denda": 1,
        "pembekuan": 3, "pencabutan izin": 4, "ditutup": 2, "diblokir": 2,
        # Risiko
        "risiko": 1, "berbahaya": 2, "mengancam": 2, "ancaman": 2,
        "waspada": 1, "hati-hati": 1, "bahaya": 2, "marak": 1,
        # Pengaduan
        "pengaduan": 1, "laporan": 1, "aduan": 1, "keluhan": 2,
        "komplain": 1,
    }

    # Kata penguat (amplifier)
    AMPLIFIER = {
        "sangat": 1.5, "amat": 1.5, "sekali": 1.3, "paling": 1.5,
        "semakin": 1.2, "makin": 1.2, "terus": 1.1, "kian": 1.2,
        "jauh lebih": 1.5, "jauh": 1.2,
    }

    # Kata pembalik (negasi)
    NEGASI = {"tidak", "bukan", "belum", "tanpa", "tak", "jangan", "tiada"}

    @classmethod
    def analisis(cls, judul: str, isi: str = None) -> dict:
        """
        Menganalisis sentimen dari judul dan isi berita.

        Args:
            judul: Judul berita
            isi: Isi berita (opsional)

        Returns:
            Dictionary {sentimen, skor, detail}
        """
        # Gabungkan teks - judul diberi bobot lebih tinggi
        teks_judul = (judul or "").lower()
        teks_isi = (isi or "").lower()

        # Judul memiliki bobot 2x
        skor_positif = cls._hitung_skor(teks_judul, cls.KATA_POSITIF) * 2
        skor_negatif = cls._hitung_skor(teks_judul, cls.KATA_NEGATIF) * 2

        if teks_isi:
            skor_positif += cls._hitung_skor(teks_isi, cls.KATA_POSITIF)
            skor_negatif += cls._hitung_skor(teks_isi, cls.KATA_NEGATIF)

        skor_bersih = skor_positif - skor_negatif

        # Threshold klasifikasi
        if skor_bersih >= 3:
            sentimen = "Positif"
        elif skor_bersih <= -2:
            sentimen = "Negatif"
        else:
            sentimen = "Netral"

        return {
            "sentimen": sentimen,
            "skor": round(skor_bersih, 2),
            "skor_positif": round(skor_positif, 2),
            "skor_negatif": round(skor_negatif, 2),
        }

    @classmethod
    def _hitung_skor(cls, teks: str, kamus: dict) -> float:
        """
        Menghitung skor sentimen dari teks menggunakan kamus kata.

        Args:
            teks: Teks yang akan dianalisis (sudah lowercase)
            kamus: Dictionary kata -> bobot

        Returns:
            Total skor sentimen
        """
        skor = 0.0
        kata_list = teks.split()

        for i, kata in enumerate(kata_list):
            # Cek kata tunggal
            if kata in kamus:
                bobot = kamus[kata]
                # Cek negasi (2 kata sebelumnya)
                if i > 0 and kata_list[i-1] in cls.NEGASI:
                    bobot *= -0.5  # Balik makna sebagian
                # Cek amplifier (kata sebelumnya)
                if i > 0 and kata_list[i-1] in cls.AMPLIFIER:
                    bobot *= cls.AMPLIFIER[kata_list[i-1]]
                skor += bobot

            # Cek frasa 2 kata
            if i < len(kata_list) - 1:
                frasa = f"{kata} {kata_list[i+1]}"
                if frasa in kamus:
                    skor += kamus[frasa]

            # Cek frasa 3 kata
            if i < len(kata_list) - 2:
                frasa3 = f"{kata} {kata_list[i+1]} {kata_list[i+2]}"
                if frasa3 in kamus:
                    skor += kamus[frasa3]

        return skor

    @classmethod
    def analisis_topik(cls, judul: str, isi: str = None) -> str | None:
        """
        Mengklasifikasikan topik berita berdasarkan keyword.

        Args:
            judul: Judul berita
            isi: Isi berita

        Returns:
            Nama topik atau None
        """
        teks = ((judul or "") + " " + (isi or "")).lower()

        topik_keywords = {
            "Pinjaman Online": ["pinjaman online", "pinjol", "p2p lending", "fintech lending",
                                "kredit online", "pinjam online", "bunga pinjaman"],
            "Literasi Keuangan": ["literasi keuangan", "edukasi keuangan", "melek keuangan",
                                  "pengelolaan keuangan", "literasi", "inklusi keuangan"],
            "Investasi": ["investasi", "saham", "obligasi", "reksa dana", "portofolio",
                          "return", "dividen", "emiten", "bursa", "ihsg"],
            "Perbankan": ["bank", "perbankan", "tabungan", "deposito", "kredit", "kpr",
                          "atm", "mobile banking", "internet banking", "nasabah bank"],
            "Asuransi": ["asuransi", "premi", "klaim asuransi", "polis", "jiwa", "kesehatan"],
            "Pasar Modal": ["pasar modal", "bursa efek", "saham", "idx", "bei",
                            "penawaran umum", "ipo", "obligasi"],
            "Fintech": ["fintech", "teknologi keuangan", "digital payment", "dompet digital",
                        "qris", "e-wallet", "gopay", "ovo", "dana", "uang elektronik"],
            "Perlindungan Konsumen": ["perlindungan konsumen", "pengaduan", "sengketa",
                                      "korban", "dirugikan", "aduan nasabah"],
            "Pengawasan": ["pengawasan", "pemeriksaan", "audit", "inspeksi", "sanksi",
                           "denda", "pencabutan izin", "pembekuan"],
            "Investasi Ilegal": ["investasi ilegal", "investasi bodong", "penipuan investasi",
                                 "skema ponzi", "money game", "robot trading ilegal"],
        }

        skor_topik = {}
        for topik, keywords in topik_keywords.items():
            skor = sum(1 for kw in keywords if kw in teks)
            if skor > 0:
                skor_topik[topik] = skor

        if not skor_topik:
            return "Regulasi"  # default

        return max(skor_topik, key=skor_topik.get)

    @classmethod
    def analisis_wilayah(cls, judul: str, isi: str = None) -> str | None:
        """
        Mendeteksi wilayah yang disebut dalam berita (fokus Jawa Barat).

        Args:
            judul: Judul berita
            isi: Isi berita

        Returns:
            Nama kota/wilayah atau None
        """
        teks = ((judul or "") + " " + (isi or "")).lower()

        wilayah_list = [
            "bandung", "bekasi", "bogor", "cirebon", "depok",
            "sukabumi", "karawang", "tasikmalaya", "garut", "cianjur",
            "subang", "purwakarta", "indramayu", "majalengka", "sumedang",
            "kuningan", "ciamis", "banjar", "pangandaran"
        ]

        for wilayah in wilayah_list:
            if wilayah in teks:
                # Normalisasi nama
                if wilayah == "jabar":
                    return "Jawa Barat"
                return wilayah.title()

        return None
