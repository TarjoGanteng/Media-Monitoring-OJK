"""
Test: Fetch gambar langsung dari URL artikel di database.
Karena artikel ternyata bisa diakses langsung via link media.
"""
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
})

# URL artikel ASLI yang kita tahu dari browser user
actual_urls = [
    "https://updatebali.com/ojk-perkuat-industri-aset-kripto-dan-keuangan-digital-fokus-pada-regulasi-dan-perlindungan-konsumen/",
    "https://www.antaranews.com/berita/5352089/mata-uang-iran-melemah-apa-bedanya-rial-dan-toman",
]

def fetch_og_image(url):
    try:
        resp = session.get(url, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")
        for attr in [
            {"property": "og:image"},
            {"name": "twitter:image"},
            {"name": "twitter:image:src"},
        ]:
            tag = soup.find("meta", attr)
            if tag and tag.get("content","").startswith("http"):
                return tag["content"]
        # Coba cari gambar pertama di artikel
        article = soup.find("article") or soup.find("div", class_=lambda c: c and "content" in c.lower())
        if article:
            img = article.find("img", src=lambda s: s and s.startswith("http"))
            if img:
                return img["src"]
    except Exception as e:
        print(f"  Error: {e}")
    return None

for url in actual_urls:
    print(f"\nURL: {url[:80]}")
    img = fetch_og_image(url)
    print(f"Image: {img}")
