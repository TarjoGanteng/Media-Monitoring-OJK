"""
services/ai_service.py - Integrasi AI untuk analisis berita OJK

Mendukung multi-provider AI (semua GRATIS):
  1. Cohere (UTAMA)      - command-r-plus, sangat baik untuk NLP & JSON
  2. Groq   (KEDUA)      - llama-3.3-70b, sangat cepat (inference terkencang)
  3. OpenRouter (KETIGA) - llama-3.3-70b via aggregator, fallback stabil
  4. Gemini (TERAKHIR)   - gemini-2.0-flash-lite, limit reset harian

Urutan fallback: Cohere → Groq → OpenRouter → Gemini
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
  "wilayah": "<nama kota/kabupaten lokasi utama berita di Jawa Barat jika ada (PILIH DARI: Bandung, Bekasi, Bogor, Cirebon, Depok, Sukabumi, Karawang, Tasikmalaya, Garut, Cianjur, Subang, Purwakarta, Indramayu, Majalengka, Sumedang, Kuningan, Ciamis, Banjar, Pangandaran). Jika tidak disebutkan secara eksplisit di dalam konten, analisislah asal media tersebut (misal: 'Radar Bogor' -> Bogor, 'Radar Cirebon' -> Cirebon, 'Pikiran Rakyat' -> Bandung, 'Tribun Jabar' -> Bandung). Jika benar-benar tidak terdeteksi, berikan null>",
  "ringkasan": "<ringkasan 1-2 kalimat bahasa Indonesia>",
  "narasumber": "<nama dan jabatan narasumber yang dikutip, atau null>",
  "jenis_media": "<PILIH SATU: Lokal | Non-Lokal>"
}}

=== KONTEKS SISTEM ===
Sistem ini adalah MEDIA MONITORING KHUSUS OJK JAWA BARAT. Hanya berita yang relevan dengan OJK dan/atau wilayah Provinsi Jawa Barat yang boleh masuk.

=== PANDUAN SENTIMEN (SUDUT PANDANG INSTITUSI OJK) ===
- POSITIF : Tindakan tegas OJK, prestasi OJK, apresiasi, literasi sukses, perlindungan konsumen dari OJK.
- NETRAL  : Kasus pinjol/penipuan di masyarakat (OJK TIDAK disalahkan), regulasi, edukasi, peringatan.
- NEGATIF : HANYA JIKA berita secara EKSPLISIT menyudutkan/mengkritik OJK, protes terhadap OJK.
- TIDAK RELEVAN : Gunakan ini jika SALAH SATU dari kondisi berikut terpenuhi:
    (a) Berita sama sekali tidak membahas OJK atau industri jasa keuangan.
    (b) Berita membahas OJK PUSAT / OJK NASIONAL tanpa keterkaitan apapun dengan Jawa Barat (tidak ada nama kota/kabupaten Jawa Barat, tidak ada kegiatan OJK di Jawa Barat, narasumber bukan dari OJK Jawa Barat).
    (c) Berita membahas OJK atau keuangan di provinsi LAIN (misalnya Jakarta, Surabaya, Medan, Bali, dll.) bukan di Jawa Barat.
Jika ragu apakah terkait Jawa Barat atau tidak → pilih TIDAK RELEVAN.
Jika ragu sentimennya (tapi jelas relevan dengan Jawa Barat) → pilih NETRAL.

- LOKAL     : Jika nama media merupakan media daerah Jawa Barat (misal: Tribun Jabar, Radar Bandung, Pikiran Rakyat, dsb).
- NON-LOKAL : Jika media nasional (Kompas, Detik, CNBC) atau dari provinsi lain."""


def normalize_wilayah_name(w: str) -> str:
    if not w:
        return None
    w = str(w).strip()
    w_lower = w.lower()
    
    # Pencocokan khusus
    if "bandung barat" in w_lower:
        return "Bandung"
    if "bandung" in w_lower:
        return "Bandung"
    if "jakarta" in w_lower:
        return "Jakarta"
    if "jawa barat" in w_lower or "jabar" in w_lower:
        return "Bandung"  # Map general Jawa Barat to Bandung
        
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
    if wilayah and str(wilayah).lower() not in ["null", "none", "", "jawa barat"]:
        wilayah = normalize_wilayah_name(wilayah)
    else:
        wilayah = None

    media_lower = str(media or "").lower()
    # Jika nama media adalah media lokal Jabar
    is_local_media = any(k in media_lower for k in [
        "jabar", "jawa barat", "bjb", "bandung", "ciamik", "bogor", "depok", "bekasi", "cirebon", 
        "pikiran rakyat", "radar", "cianjur", "tasikmalaya", "garut", "subang", 
        "purwakarta", "indramayu", "majalengka", "sumedang", "kuningan", "ciamis", 
        "banjar", "pangandaran", "sukabumi", "karawang", "pasundan"
    ])

    jenis_media = result.get("jenis_media", "Non-Lokal")
    if is_local_media:
        jenis_media = "Lokal"
    elif jenis_media not in ["Lokal", "Non-Lokal"]:
        jenis_media = "Non-Lokal"

    # Logika fallback lokasi berdasarkan nama media
    if not wilayah or wilayah == "Jawa Barat":
        if "cirebon" in media_lower:
            wilayah = "Cirebon"
        elif "bogor" in media_lower:
            wilayah = "Bogor"
        elif "sukabumi" in media_lower:
            wilayah = "Sukabumi"
        elif "karawang" in media_lower:
            wilayah = "Karawang"
        elif "tasikmalaya" in media_lower or "priangan" in media_lower:
            wilayah = "Tasikmalaya"
        elif "garut" in media_lower:
            wilayah = "Garut"
        elif "cianjur" in media_lower:
            wilayah = "Cianjur"
        elif "subang" in media_lower or "pasundan" in media_lower:
            wilayah = "Subang"
        elif "purwakarta" in media_lower:
            wilayah = "Purwakarta"
        elif "indramayu" in media_lower:
            wilayah = "Indramayu"
        elif "majalengka" in media_lower:
            wilayah = "Majalengka"
        elif "sumedang" in media_lower:
            wilayah = "Sumedang"
        elif "kuningan" in media_lower:
            wilayah = "Kuningan"
        elif "ciamis" in media_lower:
            wilayah = "Ciamis"
        elif "banjar" in media_lower:
            wilayah = "Banjar"
        elif "pangandaran" in media_lower:
            wilayah = "Pangandaran"
        elif "depok" in media_lower:
            wilayah = "Depok"
        elif "bekasi" in media_lower:
            wilayah = "Bekasi"
        elif is_local_media or jenis_media == "Lokal":
            wilayah = "Bandung"
        else:
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


# =============================================================================
# Provider 1b: Groq AI (KEDUA - Sangat Cepat, Gratis, Model Llama)
# Daftar di: https://console.groq.com → API Keys → Create API Key
# =============================================================================


class GroqService:
    """
    Analisis berita menggunakan Groq API.
    Groq adalah provider LLM GRATIS dengan kecepatan inferensi tertinggi.
    Model: llama-3.3-70b-versatile (gratis, akurasi tinggi untuk bahasa Indonesia)
    Limit: 14.400 request/hari (cukup untuk monitoring rutin).
    """

    MODEL_NAME = "llama-3.3-70b-versatile"
    API_BASE = "https://api.groq.com/openai/v1/chat/completions"

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
                self._api_key = os.environ.get("GROQ_API_KEY", "")
                if not self._api_key:
                    from config import Config
                    self._api_key = getattr(Config, "GROQ_API_KEY", "")
            except Exception:
                pass

        if not self._api_key:
            logger.debug("[Groq] API Key tidak ditemukan. Dilewat.")
            return False

        self._available = True
        logger.info(f"[Groq] Siap digunakan dengan model {self.MODEL_NAME}")
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
                logger.debug(f"[Groq] Reasoning: {alasan[:80]}")

            return _parse_result(result, media)

        except json.JSONDecodeError as e:
            logger.warning(f"[Groq] Gagal parse JSON: {e}")
            return None
        except Exception as e:
            err_str = str(e).lower()
            if "429" in err_str or "rate" in err_str or "quota" in err_str:
                logger.warning(f"[Groq] Rate limit: {e}")
            else:
                logger.error(f"[Groq] Error API: {e}")
            return None

    def cek_koneksi(self) -> dict:
        if not self._init():
            return {
                "ok": False,
                "pesan": "GROQ_API_KEY tidak ditemukan di .env",
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
                "pesan": f"Koneksi ke Groq berhasil. Model: {self.MODEL_NAME}",
                "model": self.MODEL_NAME,
            }
        except Exception as e:
            return {
                "ok": False,
                "pesan": f"Gagal terhubung ke Groq: {str(e)}",
                "model": self.MODEL_NAME,
            }


class OpenRouterService:

    """
    Analisis berita menggunakan OpenRouter API.
    Mendukung model gratis: meta-llama/llama-3.1-8b-instruct:free, dll.
    Daftar gratis di: https://openrouter.ai/sign-up
    """

    # "openrouter/free" adalah router resmi OpenRouter yang otomatis memilih
    # model gratis terbaik yang tersedia saat ini — tidak perlu update manual.
    MODEL_NAME = "openrouter/auto"
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
    Urutan prioritas: Cohere → Groq → OpenRouter → Gemini
    Semua provider GRATIS. Jika satu kena rate limit, otomatis fallback ke berikutnya.
    """

    def __init__(self):
        self._cohere = CohereService()
        self._groq = GroqService()
        self._openrouter = OpenRouterService()
        self._gemini = GeminiService()

    def is_available(self) -> bool:
        return (
            self._cohere.is_available()
            or self._groq.is_available()
            or self._openrouter.is_available()
            or self._gemini.is_available()
        )

    def analisis_berita(
        self, judul: str, isi: str = None, ringkasan: str = None, media: str = None
    ) -> dict | None:
        # Kumpulkan provider yang API Key-nya tersedia di .env (urutan = prioritas)
        available_providers = []
        if self._cohere.is_available():
            available_providers.append(("Cohere", self._cohere))
        if self._groq.is_available():
            available_providers.append(("Groq", self._groq))
        if self._openrouter.is_available():
            available_providers.append(("OpenRouter", self._openrouter))
        if self._gemini.is_available():
            available_providers.append(("Gemini", self._gemini))

        if not available_providers:
            return None

        # Coba satu per satu sesuai prioritas, fallback otomatis jika gagal/limit
        for name, provider in available_providers:
            try:
                result = provider.analisis_berita(judul, isi, ringkasan, media)
                if result is not None:
                    logger.debug(f"[AI] Berhasil via {name}")
                    return result
                logger.warning(f"[AI] {name} mengembalikan None (limit/error). Mencoba fallback...")
            except Exception as e:
                logger.warning(f"[AI] {name} error: {e}. Mencoba fallback...")

        return None

    def analisis_batch(self, berita_list: list, delay_per_request: float = 2.0) -> dict:
        if not self.is_available():
            return {
                "diproses": 0,
                "berhasil": 0,
                "gagal": 0,
                "error": "Tidak ada provider AI yang tersedia. Tambahkan API key di .env",
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
        """Tes koneksi semua provider dan kembalikan status masing-masing."""
        co_status = self._cohere.cek_koneksi()
        gr_status = self._groq.cek_koneksi()
        or_status = self._openrouter.cek_koneksi()
        gem_status = self._gemini.cek_koneksi()

        # Kembalikan provider pertama yang OK sebagai 'aktif'
        if co_status["ok"]:
            return {**co_status, "provider": "Cohere"}
        if gr_status["ok"]:
            return {**gr_status, "provider": "Groq"}
        if or_status["ok"]:
            return {**or_status, "provider": "OpenRouter"}
        if gem_status["ok"]:
            return {**gem_status, "provider": "Gemini"}

        return {
            "ok": False,
            "provider": None,
            "model": None,
            "pesan": (
                f"Cohere: {co_status['pesan']} | "
                f"Groq: {gr_status['pesan']} | "
                f"OpenRouter: {or_status['pesan']} | "
                f"Gemini: {gem_status['pesan']}"
            ),
        }

    def generate_narasi(self, prompt: str, temperature: float = 0.5) -> str | None:
        """
        Helper method untuk men-generate teks narasi bebas (seperti ringkasan/penjelasan laporan).
        Mencoba provider secara berurutan: Cohere → Groq → OpenRouter → Gemini.
        """
        # Coba Cohere
        if self._cohere.is_available():
            try:
                import requests
                headers = {
                    "Authorization": f"Bearer {self._cohere._api_key}",
                    "Content-Type": "application/json",
                }
                payload = {
                    "message": prompt,
                    "model": self._cohere.MODEL_NAME,
                    "temperature": temperature,
                }
                resp = requests.post(self._cohere.API_BASE, headers=headers, json=payload, timeout=30)
                resp.raise_for_status()
                return resp.json()["text"].strip()
            except Exception as e:
                logger.warning(f"[AIService] generate_narasi Cohere gagal: {e}")

        # Fallback ke Groq
        if self._groq.is_available():
            try:
                import requests
                headers = {
                    "Authorization": f"Bearer {self._groq._api_key}",
                    "Content-Type": "application/json",
                }
                payload = {
                    "model": self._groq.MODEL_NAME,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": temperature,
                }
                resp = requests.post(self._groq.API_BASE, headers=headers, json=payload, timeout=30)
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"].strip()
            except Exception as e:
                logger.warning(f"[AIService] generate_narasi Groq gagal: {e}")

        # Fallback ke OpenRouter
        if self._openrouter.is_available():
            try:
                import requests
                headers = {
                    "Authorization": f"Bearer {self._openrouter._api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://ojk-jabar-monitoring.app",
                    "X-Title": "Media Monitoring OJK Jawa Barat",
                }
                payload = {
                    "model": self._openrouter.MODEL_NAME,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": temperature,
                }
                resp = requests.post(self._openrouter.API_BASE, headers=headers, json=payload, timeout=30)
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"].strip()
            except Exception as e:
                logger.warning(f"[AIService] generate_narasi OpenRouter gagal: {e}")

        # Fallback ke Gemini
        if self._gemini.is_available():
            try:
                from google.genai import types
                response = self._gemini._client.models.generate_content(
                    model=self._gemini.MODEL_NAME,
                    contents=prompt,
                )
                return response.text.strip()
            except Exception as e:
                logger.warning(f"[AIService] generate_narasi Gemini gagal: {e}")

        return None


# ─── Singleton instance ───────────────────────────────────────────────────────
# Backward-compatible: kode lama yang memanggil `gemini.xxx` tetap bisa dipakai
gemini = AIService()