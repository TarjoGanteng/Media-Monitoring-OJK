import json
import os
import sys
from datetime import datetime

# Impor fungsi create_app untuk mendapatkan context Flask
from app import create_app
from database.extensions import db
from database.models import User, Berita, Keyword, CrawlLog

# File tujuan penyimpanan data (akan di-push ke GitHub)
SEED_FILE = "seed_data.json"


def datetime_converter(o):
    """Fungsi helper untuk serialize datetime ke string JSON"""
    if isinstance(o, datetime):
        return o.isoformat()


def export_data():
    """Mengekspor isi database ke file JSON"""
    app = create_app("development")

    with app.app_context():
        data = {"users": [], "berita": [], "keywords": [], "crawl_logs": []}

        # Ambil data User
        for user in User.query.all():
            data["users"].append(
                {
                    "username": user.username,
                    "nama_lengkap": user.nama_lengkap,
                    "password_hash": user.password_hash,
                    "role": user.role,
                    "status": user.status,
                    "last_login": user.last_login,
                    "created_at": user.created_at,
                }
            )

        # Ambil data Keyword
        for kw in Keyword.query.all():
            data["keywords"].append(
                {"kata": kw.kata, "aktif": kw.aktif, "created_at": kw.created_at}
            )

        # Ambil data Berita (Batasi misalnya 500 terbaru agar file tidak terlalu besar jika terlalu banyak)
        # Jika Anda ingin mengikutkan SEMUA berita, hapus `.limit(500)`
        for b in Berita.query.order_by(Berita.id.desc()).limit(500).all():
            data["berita"].append(b.to_dict())

        # Ambil data CrawlLog (Batasi 50 terakhir)
        for log in CrawlLog.query.order_by(CrawlLog.id.desc()).limit(50).all():
            data["crawl_logs"].append(
                {
                    "keyword": log.keyword,
                    "jumlah_ditemukan": log.jumlah_ditemukan,
                    "jumlah_disimpan": log.jumlah_disimpan,
                    "jumlah_duplikat": log.jumlah_duplikat,
                    "status": log.status,
                    "pesan": log.pesan,
                    "created_at": log.created_at,
                }
            )

        # Simpan ke file json
        with open(SEED_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, default=datetime_converter)

        print(f"[OK] Data berhasil diekspor ke {SEED_FILE}!")
        print(
            f"Total: {len(data['users'])} User, {len(data['keywords'])} Keyword, {len(data['berita'])} Berita."
        )
        print("Silakan push file seeder ini ke GitHub.")


def import_data():
    """Mengimpor data dari file JSON ke dalam database lokal"""
    if not os.path.exists(SEED_FILE):
        print(f"[ERROR] File {SEED_FILE} tidak ditemukan!")
        print("Teman Anda harus memastikan file seeder ini ada.")
        return

    app = create_app("development")

    with app.app_context():
        # Pastikan tabel sudah ada
        db.create_all()

        with open(SEED_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        print("Mulai mengimpor data...")

        # Import Users
        for user_data in data.get("users", []):
            if not User.query.filter_by(username=user_data["username"]).first():
                user = User(
                    username=user_data["username"],
                    nama_lengkap=user_data.get("nama_lengkap"),
                    password_hash=user_data["password_hash"],
                    role=user_data["role"],
                    status=user_data["status"],
                    last_login=datetime.fromisoformat(user_data["last_login"])
                    if user_data.get("last_login")
                    else None,
                    created_at=datetime.fromisoformat(user_data["created_at"])
                    if user_data.get("created_at")
                    else datetime.utcnow(),
                )
                db.session.add(user)

        # Import Keywords
        for kw_data in data.get("keywords", []):
            if not Keyword.query.filter_by(kata=kw_data["kata"]).first():
                kw = Keyword(
                    kata=kw_data["kata"],
                    aktif=kw_data["aktif"],
                    created_at=datetime.fromisoformat(kw_data["created_at"])
                    if kw_data.get("created_at")
                    else datetime.utcnow(),
                )
                db.session.add(kw)

        # Import Berita (Pengecekan by link agar tidak duplikat)
        for b_data in data.get("berita", []):
            if not Berita.query.filter_by(link=b_data["link"]).first():
                berita = Berita(
                    judul=b_data["judul"],
                    link=b_data["link"],
                    media=b_data.get("media"),
                    tanggal=datetime.fromisoformat(b_data["tanggal"])
                    if b_data.get("tanggal")
                    else None,
                    isi=b_data.get("isi"),
                    ringkasan=b_data.get("ringkasan"),
                    gambar_url=b_data.get("gambar_url"),
                    sentimen=b_data.get("sentimen"),
                    topik=b_data.get("topik"),
                    wilayah=b_data.get("wilayah"),
                    narasumber=b_data.get("narasumber"),
                    bulan=b_data.get("bulan"),
                    tahun=b_data.get("tahun"),
                    triwulan=b_data.get("triwulan"),
                    status=b_data.get("status", "aktif"),
                    keyword=b_data.get("keyword"),
                    created_at=datetime.fromisoformat(b_data["created_at"])
                    if b_data.get("created_at")
                    else datetime.utcnow(),
                )
                db.session.add(berita)

        # Commit perubahan
        try:
            db.session.commit()
            print("[OK] Data seeder berhasil diimpor ke database lokal Anda!")
        except Exception as e:
            db.session.rollback()
            print(f"[ERROR] Gagal mengimpor data: {e}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Penggunaan:")
        print(
            "  python seeder.py export  -> Menyimpan database Anda ke json untuk di push ke Git"
        )
        print(
            "  python seeder.py import  -> (Untuk teman Anda) Memasukkan json Git ke database lokalnya"
        )
    else:
        command = sys.argv[1].lower()
        if command == "export":
            export_data()
        elif command == "import":
            import_data()
        else:
            print("Perintah tidak dikenali. Gunakan 'export' atau 'import'.")
