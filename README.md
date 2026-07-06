# Media Monitoring OJK Jawa Barat

Sistem monitoring pemberitaan OJK Provinsi Jawa Barat.

## Cara Install
pip install -r requirements.txt

## Cara Menjalankan
python app.py

Buka: http://localhost:5000

## Crawl Berita
Klik 'Crawl Sekarang' di sidebar atau:
curl -X POST http://localhost:5000/api/crawler/run
