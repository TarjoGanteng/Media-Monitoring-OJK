"""
crawler/rss_crawler.py - Crawler berita menggunakan Google News RSS
Menggunakan feedparser untuk parsing feed RSS tanpa scraping langsung.
"""

import feedparser
import requests
import logging
from bs4 import BeautifulSoup
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus

logger = logging.getLogger(__name__)


class RSSCrawler:
    """
    Crawler berita berbasis Google News RSS Feed.
    Menggunakan feedparser untuk parsing, tidak menggunakan Selenium atau scraping langsung.
    """

    BASE_URL = "https://news.google.com/rss/search?q={keyword}&hl=id&gl=ID&ceid=ID:id"

    def __init__(self, timeout: int = 30):
        """
        Inisialisasi crawler.

        Args:
            timeout: Timeout request dalam detik
        """
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            }
        )

    def build_url(self, keyword: str) -> str:
        """
        Membuat URL RSS berdasarkan keyword.

        Args:
            keyword: Kata kunci pencarian

        Returns:
            URL RSS yang sudah di-encode
        """
        encoded_keyword = quote_plus(keyword)
        return self.BASE_URL.format(keyword=encoded_keyword)

    def parse_tanggal(self, date_string: str) -> datetime | None:
        """
        Mengubah string tanggal dari RSS ke objek datetime.

        Args:
            date_string: String tanggal dalam format RFC 2822

        Returns:
            Objek datetime atau None jika gagal parse
        """
        if not date_string:
            return None
        try:
            return parsedate_to_datetime(date_string).replace(tzinfo=None)
        except Exception:
            try:
                # Fallback: coba parse manual
                return datetime.strptime(date_string[:25], "%a, %d %b %Y %H:%M:%S")
            except Exception:
                logger.warning(f"Gagal parse tanggal: {date_string}")
                return None

    def ekstrak_media(self, entry: dict) -> str:
        """
        Ekstrak nama media/sumber dari entry RSS.

        Args:
            entry: Entry dari feedparser

        Returns:
            Nama media sebagai string
        """
        # Coba ambil dari source
        if hasattr(entry, "source") and entry.source:
            return entry.source.get("title", "Unknown")

        # Coba ambil dari tags
        if hasattr(entry, "tags") and entry.tags:
            return entry.tags[0].get("term", "Unknown")

        # Coba parse dari judul (format Google News: "judul - NamaMedia")
        if hasattr(entry, "title") and " - " in entry.title:
            return entry.title.rsplit(" - ", 1)[-1].strip()

        return "Unknown"

    def ekstrak_link_asli(self, entry: dict) -> str:
        """
        Mengambil link asli artikel (bukan link redirect Google).

        Args:
            entry: Entry dari feedparser

        Returns:
            URL artikel asli
        """
        # feedparser menyimpan link langsung di entry.link
        link = getattr(entry, "link", "")

        # Bersihkan jika ada prefix Google redirect
        if "news.google.com" in link and "url=" in link:
            try:
                from urllib.parse import urlparse, parse_qs

                parsed = urlparse(link)
                params = parse_qs(parsed.query)
                if "url" in params:
                    return params["url"][0]
            except Exception:
                pass

        return link

    def bersihkan_judul(self, judul: str) -> str:
        """
        Membersihkan judul dari suffix nama media.

        Args:
            judul: Judul berita raw

        Returns:
            Judul yang sudah dibersihkan
        """
        if " - " in judul:
            return judul.rsplit(" - ", 1)[0].strip()
        return judul.strip()

    def resolve_google_news_url(self, link: str) -> str:
        """
        Resolve Google News redirect URL ke URL artikel asli.
        Strategy:
        1. Ganti /rss/articles/ dengan /articles/ untuk dapat halaman web
        2. Cari canonical URL di halaman tersebut
        3. Fallback: follow HTTP redirect biasa
        """
        if "news.google.com" not in link:
            return link
        try:
            # Coba konversi RSS link ke web article link
            web_url = link.replace("/rss/articles/", "/articles/")
            # Hapus query string RSS spesifik jika ada
            if "?" in web_url:
                web_url = web_url.split("?")[0]

            resp = self.session.get(
                web_url, timeout=10, allow_redirects=True,
                headers={"Accept-Language": "id-ID,id;q=0.9,en;q=0.8"}
            )
            # Cek apakah kita sudah keluar dari google
            if "google.com" not in resp.url:
                return resp.url

            # Masih di Google - cari canonical atau href di halaman
            soup = BeautifulSoup(resp.text, "html.parser")

            # Cari canonical link
            canonical = soup.find("link", rel="canonical")
            if canonical:
                href = canonical.get("href", "")
                if href.startswith("http") and "google.com" not in href:
                    return href

            # Cari link utama artikel (biasanya ada di tag <a> dengan kelas tertentu)
            for a_tag in soup.find_all("a", href=True):
                href = a_tag["href"]
                if href.startswith("http") and "google.com" not in href:
                    return href

        except Exception as e:
            logger.debug(f"Gagal resolve Google News URL via web: {e}")

        # Fallback: coba follow redirect langsung dari link RSS
        try:
            resp = self.session.get(link, timeout=10, allow_redirects=True)
            if "google.com" not in resp.url:
                return resp.url
        except Exception as e:
            logger.debug(f"Gagal follow redirect: {e}")

        return link  # Kembalikan link asli jika semua gagal

    def ekstrak_gambar(self, link: str) -> str | None:
        """
        Mengambil URL gambar thumbnail dari halaman artikel via og:image.
        Jika link adalah Google News redirect, akan di-resolve dulu.

        Args:
            link: URL artikel (bisa berupa Google News redirect)

        Returns:
            URL gambar atau None jika tidak ditemukan
        """
        if not link:
            return None

        # Resolve Google News redirect ke URL asli
        actual_url = self.resolve_google_news_url(link)

        # Jika tetap di google, skip
        if "google.com" in actual_url:
            return None

        try:
            resp = self.session.get(actual_url, timeout=8, allow_redirects=True)
            if resp.status_code != 200:
                return None
            soup = BeautifulSoup(resp.text, "html.parser")
            # Prioritas: og:image -> twitter:image -> link rel=image_src
            for attr in [
                {"property": "og:image"},
                {"name": "twitter:image"},
                {"name": "twitter:image:src"},
            ]:
                tag = soup.find("meta", attr)
                if tag and tag.get("content"):
                    url = tag["content"].strip()
                    if url.startswith("http"):
                        return url
            # Fallback: link rel="image_src"
            tag = soup.find("link", rel="image_src")
            if tag and tag.get("href", "").startswith("http"):
                return tag["href"].strip()
        except Exception as e:
            logger.debug(f"Gagal ambil gambar dari {actual_url}: {e}")
        return None

    def crawl_keyword(self, keyword: str) -> list[dict]:
        """
        Melakukan crawling untuk satu keyword.

        Args:
            keyword: Kata kunci yang akan di-crawl

        Returns:
            List dictionary artikel yang berhasil dikumpulkan
        """
        url = self.build_url(keyword)
        logger.info(f"Crawling keyword: '{keyword}' | URL: {url}")

        articles = []

        try:
            # Gunakan feedparser untuk parsing RSS
            feed = feedparser.parse(url)

            if feed.bozo and feed.bozo_exception:
                logger.warning(
                    f"Peringatan parsing feed: {feed.bozo_exception}"
                )

            entries = feed.get("entries", [])
            logger.info(f"Ditemukan {len(entries)} artikel untuk keyword '{keyword}'")

            for entry in entries:
                try:
                    judul_raw = getattr(entry, "title", "")
                    link = self.ekstrak_link_asli(entry)
                    media = self.ekstrak_media(entry)
                    tanggal_str = getattr(entry, "published", "") or getattr(
                        entry, "updated", ""
                    )
                    tanggal = self.parse_tanggal(tanggal_str)
                    judul = self.bersihkan_judul(judul_raw)

                    # Skip artikel yang tidak memiliki judul atau link
                    if not judul or not link:
                        continue

                    # Gambar TIDAK diambil di sini agar crawl tetap cepat.
                    # Gunakan endpoint /api/crawler/fetch-images secara terpisah.
                    gambar_url = None

                    article = {
                        "judul": judul,
                        "link": link,
                        "media": media,
                        "tanggal": tanggal,
                        "keyword": keyword,
                        "isi": None,
                        "ringkasan": None,
                        "gambar_url": gambar_url,
                        "sentimen": "Netral",  # default - akan diisi AI nanti
                        "topik": None,
                        "wilayah": None,
                        "narasumber": None,
                    }

                    # Hitung bulan, tahun, triwulan jika ada tanggal
                    if tanggal:
                        article["bulan"] = tanggal.month
                        article["tahun"] = tanggal.year
                        article["triwulan"] = self._hitung_triwulan(tanggal.month)
                    else:
                        article["bulan"] = None
                        article["tahun"] = None
                        article["triwulan"] = None

                    articles.append(article)

                except Exception as e:
                    logger.error(f"Gagal memproses entry: {e}")
                    continue

        except Exception as e:
            logger.error(f"Gagal crawl keyword '{keyword}': {e}")
            raise

        return articles

    def _hitung_triwulan(self, bulan: int) -> int:
        """Menghitung nomor triwulan dari bulan."""
        return (bulan - 1) // 3 + 1

    def crawl_multiple_keywords(self, keywords: list[str]) -> dict:
        """
        Melakukan crawling untuk multiple keyword sekaligus.

        Args:
            keywords: List kata kunci

        Returns:
            Dictionary hasil crawling per keyword
        """
        hasil = {}
        for keyword in keywords:
            try:
                articles = self.crawl_keyword(keyword)
                hasil[keyword] = {"articles": articles, "error": None}
            except Exception as e:
                hasil[keyword] = {"articles": [], "error": str(e)}
                logger.error(f"Error crawl keyword '{keyword}': {e}")

        return hasil
