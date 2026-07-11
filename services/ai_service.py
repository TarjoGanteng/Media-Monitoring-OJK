"""
services/ai_service.py - Integrasi Google Gemini AI untuk analisis berita OJK

Menggantikan rule-based SentimentAnalyzer dengan AI yang lebih akurat.
Mampu menganalisis: sentimen, topik, wilayah, ringkasan, dan narasumber.
"""

import json
import logging
import time

logger = logging.getLogger(__name__)

# Topik valid sesuai sistem (konsisten dengan config.py)
TOPIK_VALID = [
    "Pinjaman Online", "Literasi Keuangan", "Investasi", "Perbankan",
    "Asuransi", "Pasar Modal", "Fintech", "Perlindungan Konsumen",
    "Pengawasan", "Regulasi", "Investasi Ilegal",
]

# Wilayah valid (kota/kabupaten di Jawa Barat)
WILAYAH_VALID = [
    "Bandung", "Bekasi", "Bogor", "Cirebon", "Depok", "Sukabumi",
    "Karawang", "Tasikmalaya", "Garut", "Cianjur", "Subang",
    "Purwakarta", "Indramayu", "Majalengka", "Sumedang", "Kuningan",
    "Ciamis", "Banjar", "Pangandaran", "Jawa Barat",
]


class GeminiService:
    """
    Service analisis berita menggunakan Google Gemini AI.
    Mendukung analisis per-artikel maupun batch.
    """

    MODEL_NAME = "gemini-1.5-flash"  # Model gratis dengan kuota tinggi

    def __init__(self, api_key: str = None):
        """
        Args:
            api_key: Gemini API Key. Jika None, diambil dari config.
        """
        self._api_key = api_key
        self._model = None
        self._initialized = False

    def _init_model(self) -> bool:
        """Inisialisasi lazy model Gemini (hanya sekali)."""
        if self._initialized:
            return self._model is not None
        self._initialized = True

        # Ambil API key dari config jika tidak diberikan langsung
        if not self._api_key:
            try:
                from config import Config
                self._api_key = getattr(Config, "GEMINI_API_KEY", "")
            except Exception:
                pass

        if not self._api_key:
            logger.warning(
                "[AI] GEMINI_API_KEY tidak ditemukan di .env atau config. "
                "Analisis AI tidak aktif. Sistem akan menggunakan rule-based."
            )
            return False

        try:
            import google.generativeai as genai
            genai.configure(api_key=self._api_key)
            self._model = genai.GenerativeModel(
                model_name=self.MODEL_NAME,
                generation_config={
                    "temperature": 0.1,        # Rendah = output lebih konsisten
                    "response_mime_type": "application/json",
                },
            )
            logger.info(f"[AI] Gemini ({self.MODEL_NAME}) berhasil diinisialisasi.")
            return True

        except ImportError:
            logger.error(
                "[AI] Library 'google-generativeai' tidak terinstall. "
                "Jalankan: pip install google-generativeai"
            )
            return False
        except Exception as e:
            logger.error(f"[AI] Gagal inisialisasi Gemini: {e}")
            return False

    def is_available(self) -> bool:
        """Cek apakah layanan Gemini siap digunakan."""
        return self._init_model()

    # -------------------------------------------------------------------------
    # Analisis Tunggal
    # -------------------------------------------------------------------------

    def analisis_berita(self, judul: str, isi: str = None, ringkasan: str = None) -> dict | None:
        """
        Menganalisis satu berita OJK menggunakan Gemini AI.

        Args:
            judul: Judul berita
            isi: Isi lengkap berita (opsional)
            ringkasan: Ringkasan/deskripsi singkat (opsional, fallback jika isi kosong)

        Returns:
            Dict {sentimen, topik, wilayah, ringkasan, narasumber}
            atau None jika gagal (sistem akan fallback ke rule-based)
        """
        if not self._init_model():
            return None

        # Gunakan isi, fallback ke ringkasan, potong agar tidak melebihi token
        konten = isi or ringkasan or ""
        konten_pendek = konten[:2500] if konten else "Konten tidak tersedia."

        prompt = f"""Anda adalah analis media profesional untuk Otoritas Jasa Keuangan (OJK) Republik Indonesia.
Tugas Anda: analisis berita berikut dan kembalikan HANYA JSON, tanpa teks lain.

=== DATA BERITA ===
Judul: {judul}
Konten: {konten_pendek}

=== FORMAT JSON WAJIB (isi semua field) ===
{{
  "sentimen": "<PILIH SATU: Positif | Negatif | Netral>",
  "topik": "<PILIH SATU: {' | '.join(TOPIK_VALID)}>",
  "wilayah": "<nama kota/wilayah Jawa Barat jika ada, atau null>",
  "ringkasan": "<ringkasan 1-2 kalimat dalam bahasa Indonesia yang jelas dan informatif>",
  "narasumber": "<nama dan jabatan narasumber yang dikutip dalam berita, atau null>"
}}

=== PANDUAN SENTIMEN ===
- Positif  : prestasi OJK, keberhasilan perlindungan konsumen, program literasi, pertumbuhan positif, inovasi
- Negatif  : penipuan, pinjol ilegal, investasi bodong, kerugian nasabah, sanksi, kriminal, pengaduan
- Netral   : regulasi baru, informasi umum, berita tanpa konotasi jelas, siaran pers rutin"""

        try:
            response = self._model.generate_content(prompt)
            result = json.loads(response.text)

            # Validasi & normalisasi output AI
            sentimen = result.get("sentimen", "Netral")
            if sentimen not in ["Positif", "Negatif", "Netral"]:
                sentimen = "Netral"

            topik = result.get("topik", "Regulasi")
            if topik not in TOPIK_VALID:
                topik = "Regulasi"

            wilayah = result.get("wilayah")
            if wilayah and wilayah not in WILAYAH_VALID:
                # Coba cocokkan sebagian nama
                wilayah_cocok = next(
                    (w for w in WILAYAH_VALID if w.lower() in wilayah.lower()), None
                )
                wilayah = wilayah_cocok

            return {
                "sentimen": sentimen,
                "topik": topik,
                "wilayah": wilayah,
                "ringkasan": (result.get("ringkasan") or "").strip() or None,
                "narasumber": result.get("narasumber") or None,
            }

        except json.JSONDecodeError as e:
            logger.warning(f"[AI] Gagal parse JSON dari Gemini: {e}")
            return None
        except Exception as e:
            # Rate limit error dari Google
            err_str = str(e).lower()
            if "quota" in err_str or "rate" in err_str or "429" in err_str:
                logger.warning(f"[AI] Rate limit tercapai: {e}")
            else:
                logger.error(f"[AI] Error Gemini API: {e}")
            return None

    # -------------------------------------------------------------------------
    # Analisis Batch (untuk banyak artikel sekaligus)
    # -------------------------------------------------------------------------

    def analisis_batch(
        self,
        berita_list: list,
        delay_per_request: float = 1.5,
    ) -> dict:
        """
        Analisis banyak berita secara berurutan dengan jeda antar request.
        Hasil analisis langsung ditulis ke objek berita (perlu db.session.commit di luar).

        Args:
            berita_list: List objek Berita dari SQLAlchemy
            delay_per_request: Jeda antar request dalam detik (hindari rate limit)

        Returns:
            Dict statistik: {diproses, berhasil, gagal, error}
        """
        if not self._init_model():
            return {
                "diproses": 0, "berhasil": 0, "gagal": 0,
                "error": "Gemini AI tidak tersedia. Cek GEMINI_API_KEY di file .env.",
            }

        stats = {"diproses": 0, "berhasil": 0, "gagal": 0, "error": None}

        for berita in berita_list:
            stats["diproses"] += 1
            try:
                result = self.analisis_berita(berita.judul, berita.isi, berita.ringkasan)

                if result:
                    # Timpa field analisis dengan hasil AI
                    berita.sentimen  = result["sentimen"]
                    berita.topik     = result["topik"]
                    if result.get("wilayah"):
                        berita.wilayah = result["wilayah"]
                    if result.get("ringkasan"):
                        berita.ringkasan = result["ringkasan"]
                    if result.get("narasumber"):
                        berita.narasumber = result["narasumber"]
                    stats["berhasil"] += 1
                    logger.debug(
                        f"[AI] Berita ID {berita.id}: "
                        f"sentimen={result['sentimen']}, topik={result['topik']}"
                    )
                else:
                    stats["gagal"] += 1

                # Jeda wajib antar request untuk hindari rate limit (15 RPM di free tier)
                time.sleep(delay_per_request)

            except Exception as e:
                logger.error(f"[AI] Error analisis berita ID {berita.id}: {e}")
                stats["gagal"] += 1

        return stats

    # -------------------------------------------------------------------------
    # Utilitas
    # -------------------------------------------------------------------------

    def cek_koneksi(self) -> dict:
        """
        Tes koneksi ke Gemini API dengan prompt sederhana.

        Returns:
            Dict {ok: bool, pesan: str, model: str}
        """
        if not self._init_model():
            return {
                "ok": False,
                "pesan": "API Key tidak ditemukan atau library tidak terinstall.",
                "model": None,
            }
        try:
            # Prompt minimal untuk tes koneksi
            test_model = self._model
            response = test_model.generate_content(
                'Balas dengan JSON: {"status": "ok"}'
            )
            json.loads(response.text)  # Validasi response bisa di-parse
            return {
                "ok": True,
                "pesan": f"Koneksi ke Gemini berhasil.",
                "model": self.MODEL_NAME,
            }
        except Exception as e:
            return {
                "ok": False,
                "pesan": f"Gagal terhubung ke Gemini: {str(e)}",
                "model": self.MODEL_NAME,
            }


# ─── Singleton instance ───────────────────────────────────────────────────────
# Gunakan instance ini di seluruh aplikasi agar tidak inisialisasi berulang.
gemini = GeminiService()
