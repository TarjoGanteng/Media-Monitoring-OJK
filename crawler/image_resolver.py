"""
crawler/image_resolver.py
Menggunakan Playwright (headless browser) untuk:
1. Resolve Google News redirect URL ke URL artikel asli
2. Mengambil og:image dari halaman artikel asli

Digunakan sebagai fallback ketika requests biasa tidak bisa resolve URL.
"""

import logging
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# HTTP session untuk fetch og:image
_session = requests.Session()
_session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
})


def resolve_url_with_playwright(google_news_url: str, timeout_ms: int = 15000) -> str | None:
    """
    Resolve URL Google News ke URL artikel asli menggunakan Playwright.
    Playwright menjalankan browser headless yang bisa execute JavaScript redirect.

    Args:
        google_news_url: URL Google News RSS article
        timeout_ms: Timeout dalam milliseconds

    Returns:
        URL artikel asli, atau None jika gagal
    """
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                locale="id-ID",
            )
            page = context.new_page()

            # Navigate dan tunggu redirect selesai
            try:
                page.goto(google_news_url, timeout=timeout_ms, wait_until="domcontentloaded")
                # Tunggu sebentar untuk JavaScript redirect
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
        logger.warning("Playwright tidak terinstall. Install dengan: pip install playwright && playwright install chromium")
        return None
    except Exception as e:
        logger.error(f"Error Playwright resolve URL: {e}")
        return None


def fetch_article_data(url: str) -> dict:
    """
    Ambil URL gambar og:image dan isi paragraf teks dari halaman artikel.

    Args:
        url: URL artikel asli (bukan Google News)

    Returns:
        Dict berisi 'gambar_url' dan 'isi'
    """
    result = {"gambar_url": None, "isi": None}
    if not url or "google.com" in url:
        return result
    
    try:
        resp = _session.get(url, timeout=10, allow_redirects=True)
        if resp.status_code != 200:
            return result
        soup = BeautifulSoup(resp.text, "html.parser")

        # --- 1. Fetch Image ---
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

        # --- 2. Fetch Content ---
        article_body = soup.find('article') or soup.find(class_=lambda c: c and ('content' in c.lower() or 'detail' in c.lower() or 'read' in c.lower()))
        paragraphs = article_body.find_all('p') if article_body else soup.find_all('p')
            
        teks_list = []
        for p in paragraphs:
            text = p.get_text(strip=True)
            # Filter sederhana untuk mengabaikan teks pendek / ads
            if len(text) > 60 and "baca juga" not in text.lower() and "copyright" not in text.lower() and "kompas" not in text.lower():
                teks_list.append(f"<p style='margin-bottom: 1rem;'>{text}</p>")
                
        if teks_list:
            result["isi"] = "\n".join(teks_list)

    except Exception as e:
        logger.debug(f"Gagal fetch artikel dari {url}: {e}")
        
    return result


def decode_google_news_url(google_url: str) -> str | None:
    """Ekstrak URL asli langsung dari Base64 Protobuf Google News tanpa HTTP request."""
    import base64, re
    try:
        if '/articles/' in google_url:
            encoded = google_url.split('/articles/')[1].split('?')[0]
            padded = encoded + '=' * (-len(encoded) % 4)
            decoded = base64.urlsafe_b64decode(padded)
            # Regex untuk menangkap URL HTTP/HTTPS di dalam binary blob
            match = re.search(b'(https?://[^\x00-\x1f\x7f\x80-\xff]+)', decoded)
            if match:
                return match.group(1).decode('utf-8')
    except Exception as e:
        logger.debug(f"Base64 decode failed: {e}")
    return None

def resolve_and_fetch_image(google_news_url: str) -> dict:
    """
    Resolve Google News URL dan ambil gambar serta teks artikel.

    Args:
        google_news_url: URL Google News

    Returns:
        Dict dengan 'actual_url', 'gambar_url', dan 'isi'
    """
    result = {"actual_url": None, "gambar_url": None, "isi": None}

    logger.info(f"Resolving: {google_news_url[:60]}...")
    
    # 1. Coba decode secara instan dari URL
    actual_url = decode_google_news_url(google_news_url)
    
    # 2. Coba Playwright jika decode gagal
    if not actual_url:
        logger.info("Base64 decode failed, trying Playwright...")
        actual_url = resolve_url_with_playwright(google_news_url)
    
    # 3. Fallback ke requests biasa
    if not actual_url:
        logger.info("Playwright failed/missing, trying requests fallback...")
        try:
            resp = _session.get(google_news_url, timeout=10, allow_redirects=True)
            if resp.status_code == 200 and "google.com" not in resp.url:
                actual_url = resp.url
        except Exception as e:
            logger.debug(f"Requests fallback failed: {e}")

    if actual_url:
        logger.info(f"Resolved to: {actual_url[:60]}")
        result["actual_url"] = actual_url
        
        # Fetch gambar dan isi dari URL asli
        data = fetch_article_data(actual_url)
        if data.get("gambar_url"):
            logger.info(f"Image found: {data['gambar_url'][:60]}")
            result["gambar_url"] = data["gambar_url"]
        
        if data.get("isi"):
            logger.info("Content text successfully extracted.")
            result["isi"] = data["isi"]
    else:
        logger.warning(f"Could not resolve URL: {google_news_url[:60]}")

    return result
