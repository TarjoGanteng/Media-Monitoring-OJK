"""
services/ai_service.py - Integrasi AI untuk analisis berita OJK

Mendukung dua provider AI:
  1. OpenRouter (DIUTAMAKAN) - Gratis, tanpa batas wilayah, model Llama/Gemma
  2. Google Gemini (Fallback) - Jika GEMINI_API_KEY tersedia dan aktif

Mampu menganalisis: sentimen, topik, wilayah, ringkasan, dan narasumber.
"""

import json
import logging
import time

logger = logging.getLogger(__name__)

# Topik valid sesuai sistem (konsisten dengan config.py)
TOPIK_VALID = [
    "Pinjaman Online",
    "Literasi Keuangan",
    "Investasi",
    "Perbankan",
    "Asuransi",
    "Pasar Modal",
    "Fintech",
    "Perlindungan Konsumen",
    "Pengawasan",
    "Regulasi",
    "Investasi Ilegal",
]

# Wilayah valid (kota/kabupaten di Jawa Barat)
WILAYAH_VALID = [
    "Bandung",
    "Bekasi",
    "Bogor",
    "Cirebon",
    "Depok",
    "Sukabumi",
    "Karawang",
    "Tasikmalaya",
    "Garut",
    "Cianjur",
    "Subang",
    "Purwakarta",
    "Indramayu",
    "Majalengka",
    "Sumedang",
    "Kuningan",
    "Ciamis",
    "Banjar",
    "Pangandaran",
    "Jawa Barat",
]


# ─── Prompt Analisis (dipakai oleh semua provider) ────────────────────────────
def _build_prompt(judul: str, konten: str, nama_media: str = None) -> str:
    return f"""Anda adalah analis media profesional untuk Otoritas Jasa Keuangan (OJK) Republik Indonesia.
Tugas Anda: analisis berita berikut dan kembalikan HANYA JSON yang valid, tanpa teks lain.

=== DATA BERITA ===
Judul: {judul}
Media: {nama_media}
Konten: {konten}

=== FORMAT JSON WAJIB ===
{{
  "analisis_konteks": "<1-2 kalimat analisis inti berita dan dampaknya terhadap reputasi OJK>",
  "sentimen": "<PILIH SATU: Positif | Negatif | Netral>",
  "topik": "<PILIH SATU: {" | ".join(TOPIK_VALID)}>",
  "wilayah": "<nama kota/kabupaten/provinsi lokasi utama berita jika ada (misal: Bandung, Jakarta, Bogor, dsb), atau null>",
  "ringkasan": "<ringkasan 1-2 kalimat bahasa Indonesia>",
  "narasumber": "<nama dan jabatan narasumber yang dikutip, atau null>",
  "jenis_media": "<PILIH SATU: Lokal | Non-Lokal>"
}}

=== PANDUAN SENTIMEN (SUDUT PANDANG INSTITUSI OJK) ===
- POSITIF : Tindakan tegas OJK, prestasi OJK, apresiasi, literasi sukses, perlindungan konsumen dari OJK.
- NETRAL  : Kasus pinjol/penipuan di masyarakat (OJK TIDAK disalahkan), regulasi, edukasi, peringatan.
- NEGATIF : HANYA JIKA berita secara EKSPLISIT menyudutkan/mengkritik OJK, protes terhadap OJK.
- TIDAK RELEVAN : Jika berita SAMA SEKALI tidak membahas OJK atau industri jasa keuangan secara umum.
Jika ragu sentimennya → pilih NETRAL.

- LOKAL     : Jika nama media merupakan media daerah Jawa Barat (misal: Tribun Jabar, Radar Bandung, Pikiran Rakyat, dsb).
- NON-LOKAL : Jika media nasional (Kompas, Detik, CNBC) atau dari provinsi lain."""


def normalize_wilayah_name(w: str) -> str:
    if not w:
        return None
    w = str(w).strip()
    w_lower = w.lower()
    
    # Pencocokan khusus
    if "bandung barat" in w_lower:
        return "Bandung Barat"
    if "bandung" in w_lower:
        return "Bandung"
    if "jakarta" in w_lower:
        return "Jakarta"
    if "jawa barat" in w_lower or "jabar" in w_lower:
        return "Jawa Barat"
        
    # Bersihkan awalan Kota / Kabupaten / Kab.
    import re
    cleaned = re.sub(r'^(kab\.|kabupaten|kota)\s+', '', w, flags=re.IGNORECASE)
    cleaned = cleaned.strip()
    
    # Format Title Case (Huruf Kapital di Awal Kata)
    return cleaned.title()


def _parse_result(result: dict, media: str = None) -> dict:
    """Validasi dan normalisasi output JSON dari AI."""
    sentimen = result.get("sentimen", "Netral")
    if sentimen not in ["Positif", "Negatif", "Netral", "Tidak Relevan"]:
        sentimen = "Netral"

    topik = result.get("topik", "Regulasi")
    if topik not in TOPIK_VALID:
        topik = "Regulasi"

    # Penentuan wilayah
    wilayah = result.get("wilayah")
    if wilayah and str(wilayah).lower() not in ["null", "none", ""]:
        wilayah = normalize_wilayah_name(wilayah)
    else:
        wilayah = None

    jenis_media = result.get("jenis_media", "Non-Lokal")
    if jenis_media not in ["Lokal", "Non-Lokal"]:
        jenis_media = "Non-Lokal"

    # Logika fallback lokasi jika tidak terindikasi di isi berita
    if not wilayah:
        media_lower = str(media or "").lower()
        # Jika nama media adalah media lokal Jabar
        is_local_media = any(k in media_lower for k in ["jabar", "bandung", "ciamik", "bogor", "depok", "bekasi", "cirebon", "pikiran rakyat", "radar"])
        
        if is_local_media or jenis_media == "Lokal":
            wilayah = "Jawa Barat"
        else:
            # Default media nasional ke Jakarta
            wilayah = "Jakarta"

    return {
        "sentimen": sentimen,
        "topik": topik,
        "wilayah": wilayah,
        "ringkasan": (result.get("ringkasan") or "").strip() or None,
        "narasumber": result.get("narasumber") or None,
        "jenis_media": jenis_media,
    }


# =============================================================================
# Provider 0: Cohere AI (UTAMA - Sangat Cerdas, Gratis, Anti Cloudflare)
# =============================================================================


class CohereService:
    """
    Analisis berita menggunakan Cohere API (Model Command-R).
    Sangat stabil untuk NLP dan parsing JSON.
    """

    MODEL_NAME = "command-r-plus-08-2024"
    API_BASE = "https://api.cohere.ai/v1/chat"

    def __init__(self, api_key: str = None):
        self._api_key = api_key
        self._initialized = False
        self._available = False

    def _init(self) -> bool:
        if self._initialized:
            return self._available
        self._initialized = True

        if not self._api_key:
            try:
                import os
                from dotenv import load_dotenv

                load_dotenv(override=True)
                self._api_key = os.environ.get("COHERE_API_KEY", "")
                if not self._api_key:
                    from config import Config

                    self._api_key = getattr(Config, "COHERE_API_KEY", "")
            except Exception:
                pass

        if not self._api_key:
            logger.debug("[Cohere] API Key tidak ditemukan. Dilewat.")
            return False

        self._available = True
        logger.info(f"[Cohere] Siap digunakan dengan model {self.MODEL_NAME}")
        return True

    def is_available(self) -> bool:
        return self._init()

    def analisis_berita(
        self, judul: str, isi: str = None, ringkasan: str = None, media: str = None
    ) -> dict | None:
        if not self._init():
            return None

        konten = isi or ringkasan or ""
        konten_pendek = konten[:2500] if konten else "Konten tidak tersedia."
        prompt = _build_prompt(judul, konten_pendek, media)

        try:
            import requests

            headers = {
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": self.MODEL_NAME,
                "message": prompt,
                "temperature": 0.1,
                "response_format": {"type": "json_object"},
            }
            resp = requests.post(
                self.API_BASE, headers=headers, json=payload, timeout=45
            )
            resp.raise_for_status()

            data = resp.json()
            content = data["text"].strip()

            # Ekstrak json jika ada teks lain
            if not content.startswith("{"):
                start = content.find("{")
                end = content.rfind("}") + 1
                if start != -1:
                    content = content[start:end]

            result = json.loads(content)
            alasan = result.get("analisis_konteks", "")
            if alasan:
                logger.debug(f"[Cohere] Reasoning: {alasan[:80]}")
            return _parse_result(result, media)

        except json.JSONDecodeError as e:
            logger.warning(f"[Cohere] Gagal parse JSON: {e}")
            return None
        except Exception as e:
            logger.error(f"[Cohere] Error API: {e}")
            return None

    def cek_koneksi(self) -> dict:
        if not self._init():
            return {
                "ok": False,
                "pesan": "COHERE_API_KEY tidak ditemukan di .env",
                "model": None,
            }
        try:
            import requests

            headers = {
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": self.MODEL_NAME,
                "message": 'Balas persis seperti ini: {"status": "ok"}',
                "temperature": 0.1,
                "response_format": {"type": "json_object"},
            }
            resp = requests.post(
                self.API_BASE, headers=headers, json=payload, timeout=20
            )
            resp.raise_for_status()
            content = resp.json()["text"]
            return {
                "ok": True,
                "pesan": f"Koneksi ke Cohere berhasil. Response: {content[:30]}",
                "model": self.MODEL_NAME,
            }
        except Exception as e:
            return {
                "ok": False,
                "pesan": f"Gagal terhubung ke Cohere: {e}",
                "model": self.MODEL_NAME,
            }


class OpenRouterService:
    """
    Analisis berita menggunakan OpenRouter API.
    Mendukung model gratis: meta-llama/llama-3.1-8b-instruct:free, dll.
    Daftar gratis di: https://openrouter.ai/sign-up
    """

    # Model gratis terbaik di OpenRouter untuk analisis teks bahasa Indonesia
    MODEL_NAME = "meta-llama/llama-3.3-70b-instruct:free"
    API_BASE = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(self, api_key: str = None):
        self._api_key = api_key
        self._initialized = False
        self._available = False

    def _init(self) -> bool:
        if self._initialized:
            return self._available
        self._initialized = True

        if not self._api_key:
            try:
                import os
                from dotenv import load_dotenv

                load_dotenv(override=True)
                self._api_key = os.environ.get("OPENROUTER_API_KEY", "")
                if not self._api_key:
                    from config import Config

                    self._api_key = getattr(Config, "OPENROUTER_API_KEY", "")
            except Exception:
                pass

        if not self._api_key:
            logger.debug("[OpenRouter] API Key tidak ditemukan. Dilewat.")
            return False

        self._available = True
        logger.info(f"[OpenRouter] Siap digunakan dengan model {self.MODEL_NAME}")
        return True

    def is_available(self) -> bool:
        return self._init()

    def analisis_berita(
        self, judul: str, isi: str = None, ringkasan: str = None, media: str = None
    ) -> dict | None:
        if not self._init():
            return None

        konten = isi or ringkasan or ""
        konten_pendek = konten[:2500] if konten else "Konten tidak tersedia."
        prompt = _build_prompt(judul, konten_pendek, media)

        try:
            import requests

            headers = {
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://ojk-jabar-monitoring.app",
                "X-Title": "Media Monitoring OJK Jawa Barat",
            }
            payload = {
                "model": self.MODEL_NAME,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "response_format": {"type": "json_object"},
            }
            resp = requests.post(
                self.API_BASE, headers=headers, json=payload, timeout=30
            )
            resp.raise_for_status()

            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            result = json.loads(content)

            alasan = result.get("analisis_konteks", "")
            if alasan:
                logger.debug(f"[OpenRouter] Reasoning: {alasan[:80]}")

            return _parse_result(result, media)

        except json.JSONDecodeError as e:
            logger.warning(f"[OpenRouter] Gagal parse JSON: {e}")
            return None
        except Exception as e:
            err_str = str(e).lower()
            if "429" in err_str or "rate" in err_str or "quota" in err_str:
                logger.warning(f"[OpenRouter] Rate limit: {e}")
            else:
                logger.error(f"[OpenRouter] Error: {e}")
            return None

    def cek_koneksi(self) -> dict:
        if not self._init():
            return {
                "ok": False,
                "pesan": "OPENROUTER_API_KEY tidak ditemukan di .env",
                "model": None,
            }
        try:
            import requests

            headers = {
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": self.MODEL_NAME,
                "messages": [
                    {"role": "user", "content": 'Balas dengan JSON: {"status": "ok"}'}
                ],
                "response_format": {"type": "json_object"},
            }
            resp = requests.post(
                self.API_BASE, headers=headers, json=payload, timeout=15
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            json.loads(content)
            return {
                "ok": True,
                "pesan": "Koneksi ke OpenRouter berhasil.",
                "model": self.MODEL_NAME,
            }
        except Exception as e:
            return {
                "ok": False,
                "pesan": f"Gagal terhubung ke OpenRouter: {e}",
                "model": self.MODEL_NAME,
            }


# =============================================================================
# Provider 2: Google Gemini (Fallback)
# =============================================================================


class GeminiService:
    """
    Service analisis berita menggunakan Google Gemini AI (via google-genai SDK).
    Digunakan sebagai fallback jika OpenRouter tidak tersedia.
    """

    MODEL_NAME = "gemini-2.0-flash-lite"

    def __init__(self, api_key: str = None):
        self._api_key = api_key
        self._client = None
        self._initialized = False

    def _init_model(self) -> bool:
        if self._initialized:
            return self._client is not None
        self._initialized = True

        if not self._api_key:
            try:
                import os
                from dotenv import load_dotenv

                load_dotenv(override=True)
                self._api_key = os.environ.get("GEMINI_API_KEY", "")
                if not self._api_key:
                    from config import Config

                    self._api_key = getattr(Config, "GEMINI_API_KEY", "")
            except Exception:
                pass

        if not self._api_key:
            logger.warning("[Gemini] GEMINI_API_KEY tidak ditemukan. AI tidak aktif.")
            return False

        try:
            from google import genai

            self._client = genai.Client(api_key=self._api_key)
            logger.info(f"[Gemini] Berhasil diinisialisasi ({self.MODEL_NAME}).")
            return True
        except ImportError:
            logger.error("[Gemini] Library 'google-genai' tidak terinstall.")
            return False
        except Exception as e:
            logger.error(f"[Gemini] Gagal inisialisasi: {e}")
            return False

    def is_available(self) -> bool:
        return self._init_model()

    def analisis_berita(
        self, judul: str, isi: str = None, ringkasan: str = None, media: str = None
    ) -> dict | None:
        if not self._init_model():
            return None

        konten = isi or ringkasan or ""
        konten_pendek = konten[:2500] if konten else "Konten tidak tersedia."
        prompt = _build_prompt(judul, konten_pendek, media)

        try:
            from google.genai import types

            response = self._client.models.generate_content(
                model=self.MODEL_NAME,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    response_mime_type="application/json",
                ),
            )
            result = json.loads(response.text)
            alasan = result.get("analisis_konteks", "")
            if alasan:
                logger.debug(f"[Gemini] Reasoning: {alasan[:80]}")
            return _parse_result(result, media)

        except json.JSONDecodeError as e:
            logger.warning(f"[Gemini] Gagal parse JSON: {e}")
            return None
        except Exception as e:
            err_str = str(e).lower()
            if "quota" in err_str or "rate" in err_str or "429" in err_str:
                logger.warning(f"[Gemini] Rate limit/quota habis: {e}")
            else:
                logger.error(f"[Gemini] Error API: {e}")
            return None

    def cek_koneksi(self) -> dict:
        if not self._init_model():
            return {
                "ok": False,
                "pesan": "API Key tidak ditemukan atau library tidak terinstall.",
                "model": None,
            }
        try:
            from google.genai import types

            response = self._client.models.generate_content(
                model=self.MODEL_NAME,
                contents='Balas dengan JSON: {"status": "ok"}',
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                ),
            )
            json.loads(response.text)
            return {
                "ok": True,
                "pesan": "Koneksi ke Gemini berhasil.",
                "model": self.MODEL_NAME,
            }
        except Exception as e:
            return {
                "ok": False,
                "pesan": f"Gagal terhubung ke Gemini: {str(e)}",
                "model": self.MODEL_NAME,
            }


# =============================================================================
# Unified AI Service — Otomatis memilih provider yang tersedia
# =============================================================================


class AIService:
    """
    Facade tunggal untuk seluruh aplikasi.
    Urutan prioritas: OpenRouter → Gemini → None (fallback rule-based)
    """

    def __init__(self):
        self._cohere = CohereService()
        self._openrouter = OpenRouterService()
        self._gemini = GeminiService()
        self._active_provider = None

    def _get_provider(self):
        """Pilih provider yang aktif secara lazy. Prioritas: Cohere → OpenRouter → Gemini"""
        if self._active_provider:
            return self._active_provider
        if self._cohere.is_available():
            self._active_provider = self._cohere
            logger.info("[AI] Menggunakan provider: Cohere")
        elif self._openrouter.is_available():
            self._active_provider = self._openrouter
            logger.info("[AI] Menggunakan provider: OpenRouter")
        elif self._gemini.is_available():
            self._active_provider = self._gemini
            logger.info("[AI] Menggunakan provider: Gemini")
        return self._active_provider

    def is_available(self) -> bool:
        return self._get_provider() is not None

    def analisis_berita(
        self, judul: str, isi: str = None, ringkasan: str = None, media: str = None
    ) -> dict | None:
        provider = self._get_provider()
        if not provider:
            return None
        return provider.analisis_berita(judul, isi, ringkasan, media)

    def analisis_batch(self, berita_list: list, delay_per_request: float = 2.0) -> dict:
        if not self.is_available():
            return {
                "diproses": 0,
                "berhasil": 0,
                "gagal": 0,
                "error": "Tidak ada provider AI yang tersedia. Cek OPENROUTER_API_KEY atau GEMINI_API_KEY di .env",
            }

        stats = {"diproses": 0, "berhasil": 0, "gagal": 0, "error": None}

        for berita in berita_list:
            stats["diproses"] += 1
            try:
                result = self.analisis_berita(
                    berita.judul, berita.isi, berita.ringkasan, berita.media
                )
                if result:
                    berita.sentimen = result["sentimen"]
                    berita.topik = result["topik"]
                    if result.get("wilayah"):
                        berita.wilayah = result["wilayah"]
                    if result.get("ringkasan"):
                        berita.ringkasan = result["ringkasan"]
                    if result.get("narasumber"):
                        berita.narasumber = result["narasumber"]
                    stats["berhasil"] += 1
                    logger.debug(
                        f"[AI] Berita ID {berita.id}: {result['sentimen']}, {result['topik']}"
                    )
                else:
                    stats["gagal"] += 1
                time.sleep(delay_per_request)
            except Exception as e:
                logger.error(f"[AI] Error analisis berita ID {berita.id}: {e}")
                stats["gagal"] += 1

        return stats

    def cek_koneksi(self) -> dict:
        """Tes koneksi semua provider dan kembalikan status."""
        co_status = self._cohere.cek_koneksi()
        or_status = self._openrouter.cek_koneksi()
        gem_status = self._gemini.cek_koneksi()

        if co_status["ok"]:
            return {**co_status, "provider": "Cohere"}
        if or_status["ok"]:
            return {**or_status, "provider": "OpenRouter"}
        if gem_status["ok"]:
            return {**gem_status, "provider": "Gemini"}

        return {
            "ok": False,
            "provider": None,
            "model": None,
            "pesan": f"Cohere: {co_status['pesan']} | OR: {or_status['pesan']} | Gemini: {gem_status['pesan']}",
        }


# ─── Singleton instance ───────────────────────────────────────────────────────
# Backward-compatible: kode lama yang memanggil `gemini.xxx` tetap bisa dipakai
gemini = AIService()

"Bandung Barat",