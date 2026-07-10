import requests
import os

os.makedirs("static/geojson", exist_ok=True)
out_path = "static/geojson/jawa-barat.geojson"

# GitHub menyediakan URL khusus untuk file LFS via media.githubusercontent.com
urls = [
    # LFS media URL
    "https://media.githubusercontent.com/media/hitamcoklat/Jawa-Barat-Geo-JSON/master/Jabar_By_Kab.geojson",
    # GitHub raw via /raw/ path (berbeda dari raw.githubusercontent.com)
    "https://github.com/hitamcoklat/Jawa-Barat-Geo-JSON/raw/master/Jabar_By_Kab.geojson",
    # Sumber alternatif dengan data kabupaten Jawa Barat
    "https://raw.githubusercontent.com/superpikar/indonesia-geojson/master/jawa-barat-district.geojson",
    "https://raw.githubusercontent.com/dhanifudin/geojson/master/jawa-barat.geojson",
    "https://raw.githubusercontent.com/okyaneka/indonesia-provinces-geojson/main/32.geojson",
]

for url in urls:
    try:
        print(f"\nMencoba: {url}")
        r = requests.get(url, timeout=30, allow_redirects=True)
        content = r.content
        print(f"  Status: {r.status_code}, Size: {len(content)} bytes")
        print(f"  Preview: {content[:120]}")
        if r.status_code == 200 and len(content) > 50000:
            with open(out_path, "wb") as f:
                f.write(content)
            print(f"  >>> BERHASIL disimpan ke {out_path}")
            break
        else:
            print("  Gagal: konten terlalu kecil atau error")
    except Exception as e:
        print(f"  Error: {e}")
else:
    print("\nSemua URL gagal.")
