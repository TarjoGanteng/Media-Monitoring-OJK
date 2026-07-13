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

# ─── Prompt Analisis (dipakai oleh semua provider) ────────────────────────────
def _build_prompt(judul: str, konten: str) -> str:
    return f"""Anda adalah analis media profesional untuk Otoritas Jasa Keuangan (OJK) Republik Indonesia.
Tugas Anda: analisis berita berikut dan kembalikan HANYA JSON yang valid, tanpa teks lain.

=== DATA BERITA ===
Judul: {judul}
Konten: {konten}

=== FORMAT JSON WAJIB ===
{{
  "analisis_konteks": "<1-2 kalimat analisis inti berita dan dampaknya terhadap reputasi OJK>",
  "sentimen": "<PILIH SATU: Positif | Negatif | Netral>",
  "topik": "<PILIH SATU: {' | '.join(TOPIK_VALID)}>",
  "wilayah": "<nama kota/wilayah Jawa Barat jika ada, atau null>",
  "ringkasan": "<ringkasan 1-2 kalimat bahasa Indonesia>",
  "narasumber": "<nama dan jabatan narasumber yang dikutip, atau null>"
}}

=== PANDUAN SENTIMEN (SUDUT PANDANG INSTITUSI OJK) ===
- POSITIF : Tindakan tegas OJK, prestasi OJK, apresiasi, literasi sukses, perlindungan konsumen dari OJK.
- NETRAL  : Kasus pinjol/penipuan di masyarakat (OJK TIDAK disalahkan), regulasi, edukasi, peringatan.
- NEGATIF : HANYA JIKA berita secara EKSPLISIT menyudutkan/mengkritik OJK, protes terhadap OJK.
Jika ragu → pilih NETRAL."""


def _parse_result(result: dict) -> dict:
    """Validasi dan normalisasi output JSON dari AI."""
    sentimen = result.get("sentimen", "Netral")
    if sentimen not in ["Positif", "Negatif", "Netral"]:
        sentimen = "Netral"

    topik = result.get("topik", "Regulasi")
    if topik not in TOPIK_VALID:
        topik = "Regulasi"

    wilayah = result.get("wilayah")
    if wilayah and wilayah not in WILAYAH_VALID:
        wilayah = next(
            (w for w in WILAYAH_VALID if w.lower() in str(wilayah).lower()), None
        )

    return {
        "sentimen": sentimen,
        "topik": topik,
        "wilayah": wilayah,
        "ringkasan": (result.get("ringkasan") or "").strip() or None,
        "narasumber": result.get("narasumber") or None,
    }


# =============================================================================
# Provider 0: Hugging Face (UTAMA - Gratis Selamanya)
# =============================================================================

class HuggingFaceService:
    """
    Analisis berita menggunakan Hugging Face Inference API.
    Menggunakan endpoint OpenAI-compatible dengan model Mistral gratis.
    Daftar gratis di: https://huggingface.co/settings/tokens
    """

    MODEL_NAME = "mistralai/Mistral-7B-Instruct-v0.3"
    API_BASE   = "https://api-inference.huggingface.co/v1/chat/completions"

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
                self._api_key = os.environ.get("HUGGINGFACE_API_KEY", "")
                if not self._api_key:
                    from config import Config
                    self._api_key = getattr(Config, "HUGGINGFACE_API_KEY", "")
            except Exception:
                pass

        if not self._api_key:
            logger.debug("[HuggingFace] API Key tidak ditemukan. Dilewat.")
            return False

        self._available = True
        logger.info(f"[HuggingFace] Siap digunakan dengan model {self.MODEL_NAME}")
        return True

    def is_available(self) -> bool:
        return self._init()

    def analisis_berita(self, judul: str, isi: str = None, ringkasan: str = None) -> dict | None:
        if not self._init():
            return None

        konten = isi or ringkasan or ""
        konten_pendek = konten[:2000] if konten else "Konten tidak tersedia."
        prompt = _build_prompt(judul, konten_pendek)

        try:
            import requests
            headers = {
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": self.MODEL_NAME,
                "messages": [
                    {"role": "system", "content": "You are a JSON-only assistant. Always respond with valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.1,
                "max_tokens": 500,
                "stream": False,
            }
            resp = requests.post(self.API_BASE, headers=headers, json=payload, timeout=45)
            resp.raise_for_status()

            data = resp.json()
            content = data["choices"][0]["message"]["content"].strip()

            # Coba parse JSON - kadang ada teks sebelum/sesudah JSON
            if not content.startswith("{"):
                start = content.find("{")
                end = content.rfind("}") + 1
                if start != -1:
                    content = content[start:end]

            result = json.loads(content)
            alasan = result.get("analisis_konteks", "")
            if alasan:
                logger.debug(f"[HuggingFace] Reasoning: {alasan[:80]}")
            return _parse_result(result)

        except json.JSONDecodeError as e:
            logger.warning(f"[HuggingFace] Gagal parse JSON: {e}")
            return None
        except Exception as e:
            err_str = str(e).lower()
            if "429" in err_str or "rate" in err_str:
                logger.warning(f"[HuggingFace] Rate limit: {e}")
            else:
                logger.error(f"[HuggingFace] Error: {e}")
            return None

    def cek_koneksi(self) -> dict:
        if not self._init():
            return {"ok": False, "pesan": "HUGGINGFACE_API_KEY tidak ditemukan di .env", "model": None}
        try:
            import requests
            headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
            payload = {
                "model": self.MODEL_NAME,
                "messages": [{"role": "user", "content": 'Balas hanya dengan JSON valid: {"status": "ok"}'}],
                "max_tokens": 20,
                "stream": False,
            }
            resp = requests.post(self.API_BASE, headers=headers, json=payload, timeout=20)
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            return {"ok": True, "pesan": f"Koneksi ke Hugging Face berhasil. Response: {content[:30]}", "model": self.MODEL_NAME}
        except Exception as e:
            return {"ok": False, "pesan": f"Gagal terhubung ke Hugging Face: {e}", "model": self.MODEL_NAME}



class OpenRouterService:
    """
    Analisis berita menggunakan OpenRouter API.
    Mendukung model gratis: meta-llama/llama-3.1-8b-instruct:free, dll.
    Daftar gratis di: https://openrouter.ai/sign-up
    """

    # Model gratis terbaik di OpenRouter untuk analisis teks bahasa Indonesia
    MODEL_NAME = "meta-llama/llama-3.3-70b-instruct:free"
    API_BASE   = "https://openrouter.ai/api/v1/chat/completions"

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

    def analisis_berita(self, judul: str, isi: str = None, ringkasan: str = None) -> dict | None:
        if not self._init():
            return None

        konten = isi or ringkasan or ""
        konten_pendek = konten[:2500] if konten else "Konten tidak tersedia."
        prompt = _build_prompt(judul, konten_pendek)

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
            resp = requests.post(self.API_BASE, headers=headers, json=payload, timeout=30)
            resp.raise_for_status()

            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            result = json.loads(content)

            alasan = result.get("analisis_konteks", "")
            if alasan:
                logger.debug(f"[OpenRouter] Reasoning: {alasan[:80]}")

            return _parse_result(result)

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
            return {"ok": False, "pesan": "OPENROUTER_API_KEY tidak ditemukan di .env", "model": None}
        try:
            import requests
            headers = {
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": self.MODEL_NAME,
                "messages": [{"role": "user", "content": "Balas dengan JSON: {\"status\": \"ok\"}"}],
                "response_format": {"type": "json_object"},
            }
            resp = requests.post(self.API_BASE, headers=headers, json=payload, timeout=15)
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            json.loads(content)
            return {"ok": True, "pesan": "Koneksi ke OpenRouter berhasil.", "model": self.MODEL_NAME}
        except Exception as e:
            return {"ok": False, "pesan": f"Gagal terhubung ke OpenRouter: {e}", "model": self.MODEL_NAME}


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

    def analisis_berita(self, judul: str, isi: str = None, ringkasan: str = None) -> dict | None:
        if not self._init_model():
            return None

        konten = isi or ringkasan or ""
        konten_pendek = konten[:2500] if konten else "Konten tidak tersedia."
        prompt = _build_prompt(judul, konten_pendek)

        try:
            from google.genai import types
            response = self._client.models.generate_content(
                model=self.MODEL_NAME,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    response_mime_type="application/json",
                )
            )
            result = json.loads(response.text)
            alasan = result.get("analisis_konteks", "")
            if alasan:
                logger.debug(f"[Gemini] Reasoning: {alasan[:80]}")
            return _parse_result(result)

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
            return {"ok": False, "pesan": "API Key tidak ditemukan atau library tidak terinstall.", "model": None}
        try:
            from google.genai import types
            response = self._client.models.generate_content(
                model=self.MODEL_NAME,
                contents='Balas dengan JSON: {"status": "ok"}',
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
            json.loads(response.text)
            return {"ok": True, "pesan": "Koneksi ke Gemini berhasil.", "model": self.MODEL_NAME}
        except Exception as e:
            return {"ok": False, "pesan": f"Gagal terhubung ke Gemini: {str(e)}", "model": self.MODEL_NAME}


# =============================================================================
# Unified AI Service — Otomatis memilih provider yang tersedia
# =============================================================================

class AIService:
    """
    Facade tunggal untuk seluruh aplikasi.
    Urutan prioritas: OpenRouter → Gemini → None (fallback rule-based)
    """

    def __init__(self):
        self._huggingface = HuggingFaceService()
        self._openrouter = OpenRouterService()
        self._gemini = GeminiService()
        self._active_provider = None

    def _get_provider(self):
        """Pilih provider yang aktif secara lazy. Prioritas: HuggingFace → OpenRouter → Gemini"""
        if self._active_provider:
            return self._active_provider
        if self._huggingface.is_available():
            self._active_provider = self._huggingface
            logger.info("[AI] Menggunakan provider: Hugging Face")
        elif self._openrouter.is_available():
            self._active_provider = self._openrouter
            logger.info("[AI] Menggunakan provider: OpenRouter")
        elif self._gemini.is_available():
            self._active_provider = self._gemini
            logger.info("[AI] Menggunakan provider: Gemini")
        return self._active_provider

    def is_available(self) -> bool:
        return self._get_provider() is not None

    def analisis_berita(self, judul: str, isi: str = None, ringkasan: str = None) -> dict | None:
        provider = self._get_provider()
        if not provider:
            return None
        return provider.analisis_berita(judul, isi, ringkasan)

    def analisis_batch(self, berita_list: list, delay_per_request: float = 2.0) -> dict:
        if not self.is_available():
            return {
                "diproses": 0, "berhasil": 0, "gagal": 0,
                "error": "Tidak ada provider AI yang tersedia. Cek OPENROUTER_API_KEY atau GEMINI_API_KEY di .env",
            }

        stats = {"diproses": 0, "berhasil": 0, "gagal": 0, "error": None}

        for berita in berita_list:
            stats["diproses"] += 1
            try:
                result = self.analisis_berita(berita.judul, berita.isi, berita.ringkasan)
                if result:
                    berita.sentimen  = result["sentimen"]
                    berita.topik     = result["topik"]
                    if result.get("wilayah"):
                        berita.wilayah = result["wilayah"]
                    if result.get("ringkasan"):
                        berita.ringkasan = result["ringkasan"]
                    if result.get("narasumber"):
                        berita.narasumber = result["narasumber"]
                    stats["berhasil"] += 1
                    logger.debug(f"[AI] Berita ID {berita.id}: {result['sentimen']}, {result['topik']}")
                else:
                    stats["gagal"] += 1
                time.sleep(delay_per_request)
            except Exception as e:
                logger.error(f"[AI] Error analisis berita ID {berita.id}: {e}")
                stats["gagal"] += 1

        return stats

    def cek_koneksi(self) -> dict:
        """Tes koneksi semua provider dan kembalikan status."""
        hf_status  = self._huggingface.cek_koneksi()
        or_status  = self._openrouter.cek_koneksi()
        gem_status = self._gemini.cek_koneksi()

        if hf_status["ok"]:
            return {**hf_status, "provider": "Hugging Face"}
        if or_status["ok"]:
            return {**or_status, "provider": "OpenRouter"}
        if gem_status["ok"]:
            return {**gem_status, "provider": "Gemini"}

        return {
            "ok": False,
            "provider": None,
            "model": None,
            "pesan": f"HF: {hf_status['pesan']} | OR: {or_status['pesan']} | Gemini: {gem_status['pesan']}",
        }


# ─── Singleton instance ───────────────────────────────────────────────────────
# Backward-compatible: kode lama yang memanggil `gemini.xxx` tetap bisa dipakai
gemini = AIService()
