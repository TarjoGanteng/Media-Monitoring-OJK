"""
Test kecil: generate PDF dari xhtml2pdf untuk verifikasi template valid.
Jalankan: python test_pdf.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app

app = create_app()

with app.app_context():
    from services.laporan_service import LaporanService
    from datetime import date

    print("Mengambil preview data...")
    tgl_dari   = date(date.today().year, 1, 1)
    tgl_sampai = date.today()

    preview = LaporanService.get_preview_data(tgl_dari, tgl_sampai)
    print(f"  Total berita: {preview['total']}")

    if preview['total'] == 0:
        print("  PERINGATAN: Tidak ada data berita. PDF mungkin kosong.")
    
    print("Mengumpulkan data laporan...")
    data = LaporanService.get_data_laporan(tgl_dari, tgl_sampai)
    print(f"  Data terkumpul: {len(data)} kunci")

    params = {
        "nomor_laporan": "TEST-001",
        "judul": "Test Laporan PDF",
        "periode_label": "Test 2026",
        "jenis_periode": "tahunan",
        "tanggal_dari": tgl_dari,
        "tanggal_sampai": tgl_sampai,
        "tanggal_dari_str": tgl_dari.strftime("%d %B %Y"),
        "tanggal_sampai_str": tgl_sampai.strftime("%d %B %Y"),
        "wilayah": "Jawa Barat",
        "topik": None,
        "jenis_media": "semua",
        "dibuat_oleh_nama": "Test User",
        "tanggal_cetak": "18 Juli 2026, 13:00 WIB",
    }

    output_dir = os.path.join(app.instance_path, "laporan_test")
    print(f"Generating PDF ke {output_dir}...")
    
    try:
        path = LaporanService.generate_pdf(data, params, output_dir)
        size_kb = os.path.getsize(path) / 1024
        print(f"\nSUCCESS! PDF berhasil dibuat: {path}")
        print(f"Ukuran file: {size_kb:.1f} KB")
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
