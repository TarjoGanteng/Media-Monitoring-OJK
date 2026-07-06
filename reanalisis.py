"""
reanalisis.py - Script untuk re-analisis sentimen semua berita di database
Jalankan sekali: python reanalisis.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app import create_app
from database.extensions import db
from database.models import Berita
from services.sentiment_service import SentimentAnalyzer

app = create_app()

with app.app_context():
    berita_list = Berita.query.filter_by(status='aktif').all()
    total = len(berita_list)
    print(f"Total berita: {total}")

    positif = netral = negatif = 0

    for i, berita in enumerate(berita_list):
        hasil = SentimentAnalyzer.analisis(berita.judul, berita.isi)
        topik = SentimentAnalyzer.analisis_topik(berita.judul, berita.isi)
        wilayah = SentimentAnalyzer.analisis_wilayah(berita.judul, berita.isi)

        berita.sentimen = hasil['sentimen']
        if not berita.topik:
            berita.topik = topik
        if not berita.wilayah:
            berita.wilayah = wilayah

        if hasil['sentimen'] == 'Positif': positif += 1
        elif hasil['sentimen'] == 'Negatif': negatif += 1
        else: netral += 1

        if (i + 1) % 100 == 0:
            db.session.commit()
            print(f"  Diproses: {i+1}/{total}")

    db.session.commit()
    print(f"\nSelesai!")
    print(f"  Positif : {positif}")
    print(f"  Netral  : {netral}")
    print(f"  Negatif : {negatif}")
