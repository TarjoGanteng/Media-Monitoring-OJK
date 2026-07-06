"""
Test: Direct RSS feeds dari situs berita Indonesia.
Cek apakah feed menyertakan gambar di media_content/media_thumbnail.
"""
import feedparser

# Direct RSS feeds dari situs berita Indonesia yang cover OJK
DIRECT_FEEDS = [
    ("Kompas Ekonomi", "https://rss.kompas.com/rss/xml/channel/money.kompas.com"),
    ("Detik Finance", "https://rss.detik.com/index.php/detikfinance"),
    ("CNBC Indonesia", "https://www.cnbcindonesia.com/api/rss"),
    ("Antara Ekonomi", "https://www.antaranews.com/rss/ekonomi.xml"),
    ("Bisnis", "https://bisnis.com/feeds"),
    ("Kumparan", "https://kumparan.com/feed.rss"),
    ("IDNTimes", "https://www.idntimes.com/feed/rss"),
    ("Republika Ekonomi", "https://www.republika.co.id/rss/ekonomi"),
    ("Liputan6 Bisnis", "https://www.liputan6.com/rssfeed/bisnis"),
    ("Tempo Bisnis", "https://www.tempo.co/rss/bisnis"),
]

for name, url in DIRECT_FEEDS:
    try:
        feed = feedparser.parse(url)
        entries = feed.get("entries", [])
        print(f"\n=== {name} ({len(entries)} entries) ===")
        if entries:
            e = entries[0]
            print(f"  Title: {e.get('title','')[:60]}")
            print(f"  Link: {e.get('link','')[:80]}")
            mc = getattr(e, 'media_content', None)
            mt = getattr(e, 'media_thumbnail', None)
            enc = getattr(e, 'enclosures', [])
            print(f"  media_content: {mc}")
            print(f"  media_thumbnail: {mt}")
            print(f"  enclosures: {enc}")
        else:
            print(f"  No entries (status: {feed.get('status', 'unknown')})")
    except Exception as ex:
        print(f"  Error: {ex}")
