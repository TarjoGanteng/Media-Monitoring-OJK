"""
Test: Resolve Google News URL via JavaScript parsing.
"""
import re
import requests
from bs4 import BeautifulSoup

session = requests.Session()
session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
})

# Link dari database
test_link = "https://news.google.com/rss/articles/CBMitAFBVV95cUxNZnh3VktzQlpxUHdsYzVFNm9oM09UcEs2VUxjank1SXBhR1B4b3BscFE3NmJkR21RNUhZZlBYYXFXb0pFVXdpNXg1aE81ZFJfUUhqelI0VzM2Z0k0NHhWWVp1QTdFRFpwcHRpV1BYRlRpU1lNekFLaTlSbTN6VHVWQXBPamJQb1hpRFNXdE5vNkhaM2lFY3VCajRBSHBOeWdONHB3WlFScTBMczFHVnVBaDl1VmhXWl9ERFJyZg"

def resolve_via_js(link):
    """Parse JavaScript redirect dari halaman Google News."""
    # Ganti /rss/articles/ ke /articles/
    web_url = link.replace("/rss/articles/", "/articles/").split("?")[0]
    print(f"Fetching: {web_url[:80]}")
    
    try:
        resp = session.get(web_url, timeout=15, allow_redirects=True)
        print(f"Final URL: {resp.url[:80]}")
        print(f"Status: {resp.status_code}")
        
        # Cek apakah sudah redirect ke URL asli
        if "google.com" not in resp.url:
            return resp.url
        
        # Parse HTML untuk cari redirect URL
        html = resp.text
        
        # Pattern 1: window.location
        patterns = [
            r'window\.location(?:\.replace)?\s*[=(]\s*["\']([^"\']+)["\']',
            r'window\.location\.href\s*=\s*["\']([^"\']+)["\']',
            r'<meta[^>]+http-equiv=["\']refresh["\'][^>]+content=["\'][^;]+;\s*url=([^"\']+)["\']',
            r'href=["\']([^"\']*updatebali[^"\']*)["\']',
        ]
        
        for pat in patterns:
            matches = re.findall(pat, html, re.IGNORECASE)
            for m in matches:
                if m.startswith("http") and "google.com" not in m:
                    print(f"Found via regex: {m[:80]}")
                    return m
        
        # Parse dengan BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        
        # Cari semua script tags
        for script in soup.find_all("script"):
            content = script.string or ""
            if "http" in content and "google.com" not in content:
                urls = re.findall(r'https?://[^"\'\\s,\)]+', content)
                for u in urls:
                    if not any(x in u for x in ["google", "gstatic", "googleapis", "schema.org"]):
                        print(f"Found in script: {u[:80]}")
                        return u
        
        # Cari tag a dengan href non-google
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.startswith("http") and "google.com" not in href:
                print(f"Found in <a>: {href[:80]}")
                return href
        
        print("HTML snippet:")
        print(html[:500])
        return None
        
    except Exception as e:
        print(f"Error: {e}")
        return None

actual_url = resolve_via_js(test_link)
print(f"\n=== RESULT ===")
print(f"Actual URL: {actual_url}")

if actual_url:
    # Coba ambil gambar
    try:
        resp2 = session.get(actual_url, timeout=10)
        soup2 = BeautifulSoup(resp2.text, "html.parser")
        og = soup2.find("meta", property="og:image")
        if og:
            print(f"OG Image: {og.get('content','')}")
        else:
            print("No og:image found")
    except Exception as e:
        print(f"Error fetching image: {e}")
