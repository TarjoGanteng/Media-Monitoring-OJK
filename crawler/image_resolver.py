"""
crawler/image_resolver.py
Menggunakan requests + BeautifulSoup untuk:
1. Resolve Google News redirect URL ke URL artikel asli
2. Mengambil og:image dari halaman artikel asli
3. Validasi aksesibilitas URL dengan rotasi User-Agent
"""

import logging
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# User-Agent pool untuk rotasi saat diblokir
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Googlebot/2.1 (+http://www.google.com/bot.html)",
]


def _make_session(ua_index: int = 0) -> requests.Session:
    """Buat requests.Session baru per-panggilan agar thread-safe."""
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENTS[ua_index % len(USER_AGENTS)],
            "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer": "https://www.google.com/",
        }
    )
    return session


def cek_aksesibilitas_url(url: str) -> dict:
    """
    Cek apakah URL dapat diakses dengan strategi multi-UA.

    Returns:
        dict: 'dapat_diakses' (bool), 'status_code', 'alasan'
    """
    if not url or "google.com" in url:
        return {
            "dapat_diakses": False,
            "status_code": None,
            "alasan": "URL masih Google News",
        }

    for i in range(len(USER_AGENTS)):
        try:
            session = _make_session(i)
            resp = session.get(url, timeout=10, allow_redirects=True)
            status = resp.status_code

            if status == 200:
                return {"dapat_diakses": True, "status_code": 200, "alasan": "OK"}
            elif status == 404:
                return {
                    "dapat_diakses": False,
                    "status_code": 404,
                    "alasan": "Halaman tidak ditemukan (404)",
                }
            elif status == 410:
                return {
                    "dapat_diakses": False,
                    "status_code": 410,
                    "alasan": "Artikel dihapus permanen (410)",
                }
            elif status in [401, 403]:
                logger.debug(
                    f"[Resolver] UA-{i} diblokir ({status}), coba UA berikutnya..."
                )
                continue
            elif status >= 500:
                return {
                    "dapat_diakses": False,
                    "status_code": status,
                    "alasan": f"Server error ({status})",
                }
            else:
                continue

        except requests.exceptions.ConnectionError:
            return {
                "dapat_diakses": False,
                "status_code": None,
                "alasan": "Domain tidak bisa diakses",
            }
        except requests.exceptions.Timeout:
            logger.debug(f"[Resolver] Timeout UA-{i}")
            continue
        except Exception as e:
            logger.debug(f"[Resolver] Error UA-{i}: {e}")
            continue

    return {
        "dapat_diakses": False,
        "status_code": None,
        "alasan": "Semua User-Agent gagal (paywall/firewall)",
    }


def decode_google_news_url(google_url: str) -> str | None:
    """Ekstrak URL asli langsung dari Base64 Protobuf Google News tanpa HTTP request."""
    import base64
    import re

    try:
        if "/articles/" in google_url:
            encoded = google_url.split("/articles/")[1].split("?")[0]
            padded = encoded + "=" * (-len(encoded) % 4)
            decoded = base64.urlsafe_b64decode(padded)
            match = re.search(b"(https?://[^\x00-\x1f\x7f\x80-\xff]+)", decoded)
            if match:
                return match.group(1).decode("utf-8")
    except Exception as e:
        logger.debug(f"Base64 decode failed: {e}")
    return None


def resolve_url_with_playwright(
    google_news_url: str, timeout_ms: int = 15000
) -> str | None:
    """Resolve URL Google News ke URL artikel asli menggunakan Playwright (headless browser)."""
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(user_agent=USER_AGENTS[0], locale="id-ID")
            page = context.new_page()
            try:
                page.goto(
                    google_news_url, timeout=timeout_ms, wait_until="domcontentloaded"
                )
                page.wait_for_timeout(3000)
                final_url = page.url
            except Exception as e:
                logger.debug(f"Playwright navigation error: {e}")
                final_url = None
            context.close()
            browser.close()

        if final_url and "google.com" not in final_url:
            return final_url
        return None

    except ImportError:
        logger.debug("Playwright tidak terinstall.")
        return None
    except Exception as e:
        logger.debug(f"Error Playwright: {e}")
        return None


def fetch_article_data(url: str) -> dict:
    """
    Ambil URL gambar og:image dan isi paragraf teks dari halaman artikel.
    Mencoba rotasi User-Agent agar tidak mudah diblokir.
    """
    result = {"gambar_url": None, "isi": None}
    if not url or "google.com" in url:
        return result

    for i in range(len(USER_AGENTS)):
        session = _make_session(i)
        try:
            resp = session.get(url, timeout=10, allow_redirects=True)
            if resp.status_code != 200:
                continue
            soup = BeautifulSoup(resp.text, "html.parser")

            # Fetch Image (og:image prioritas pertama)
            for attr in [
                {"property": "og:image"},
                {"name": "twitter:image"},
                {"name": "twitter:image:src"},
                {"property": "og:image:url"},
            ]:
                tag = soup.find("meta", attr)
                if tag:
                    content = tag.get("content", "").strip()
                    if content.startswith("http"):
                        result["gambar_url"] = content
                        break

            if not result["gambar_url"]:
                link_tag = soup.find("link", rel="image_src")
                if link_tag and link_tag.get("href", "").startswith("http"):
                    result["gambar_url"] = link_tag["href"].strip()

            # Fetch Content
            article_body = soup.find("article") or soup.find(
                class_=lambda c: (
                    c
                    and any(
                        w in c.lower()
                        for w in ["content", "detail", "read", "body", "article"]
                    )
                )
            )
            paragraphs = (
                article_body.find_all("p") if article_body else soup.find_all("p")
            )

            teks_list = []
            for p in paragraphs:
                text = p.get_text(strip=True)
                if (
                    len(text) > 60
                    and "baca juga" not in text.lower()
                    and "copyright" not in text.lower()
                ):
                    teks_list.append(f"<p style='margin-bottom: 1rem;'>{text}</p>")

            if teks_list:
                result["isi"] = "\n".join(teks_list)

            if result["gambar_url"] or result["isi"]:
                return result

        except Exception as e:
            logger.debug(f"Gagal fetch artikel (UA-{i}) dari {url}: {e}")
            continue

    return result


def resolve_and_fetch_image(google_news_url: str) -> dict:
    """
    Resolve Google News URL dan ambil gambar serta teks artikel.

    Strategi resolusi (urutan):
      1. Base64 decode instan (tanpa HTTP request)
      2. HTTP follow redirect biasa
      3. Playwright headless browser (jika terinstall)

    Jika URL bukan Google News, langsung fetch data dari URL tersebut.

    Returns:
        Dict: 'actual_url', 'gambar_url', 'isi', 'dapat_diakses'
    """
    result = {
        "actual_url": None,
        "gambar_url": None,
        "isi": None,
        "dapat_diakses": True,
    }

    # Bukan Google News → langsung fetch
    if not google_news_url or "news.google.com" not in google_news_url:
        result["actual_url"] = google_news_url
        if google_news_url:
            # Validasi dulu apakah bisa diakses
            cek = cek_aksesibilitas_url(google_news_url)
            if cek["dapat_diakses"]:
                data = fetch_article_data(google_news_url)
                result.update(data)
            else:
                result["dapat_diakses"] = False
        return result

    logger.debug(f"[Resolver] Resolving: {google_news_url[:70]}...")

    # Strategi 1: Base64 decode instan
    actual_url = decode_google_news_url(google_news_url)

    # Strategi 2: HTTP follow redirect
    if not actual_url:
        try:
            session = _make_session()
            resp = session.get(google_news_url, timeout=10, allow_redirects=True)
            if resp.status_code == 200 and "google.com" not in resp.url:
                actual_url = resp.url
        except Exception as e:
            logger.debug(f"[Resolver] HTTP redirect failed: {e}")

    # Strategi 3: Playwright (jika ada)
    if not actual_url:
        actual_url = resolve_url_with_playwright(google_news_url)

    if actual_url:
        result["actual_url"] = actual_url
        # Cek aksesibilitas URL hasil resolve
        cek = cek_aksesibilitas_url(actual_url)
        if cek["dapat_diakses"]:
            data = fetch_article_data(actual_url)
            result.update(data)
        else:
            # URL resolve tapi tidak bisa dibuka (404, domain mati, dsb)
            logger.debug(
                f"[Resolver] URL resolve tapi tidak bisa diakses: {cek['alasan']}"
            )
            # Tetap simpan actual_url agar link di-update, tapi tandai tidak bisa diakses
            # KECUALI artikel yang memang permanen hilang (404/410)
            if cek.get("status_code") in [404, 410]:
                result["dapat_diakses"] = False
    else:
        result["dapat_diakses"] = False
        logger.debug(f"[Resolver] Gagal resolve: {google_news_url[:70]}")

    return result
