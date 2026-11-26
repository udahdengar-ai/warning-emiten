# Warning Emiten

Aplikasi pantau emiten IDX (PWA). Buka: https://udahdengar-ai.github.io/warning-emiten/

- **Harga, volume, label**: `scripts/build.py`, dijalankan GitHub Actions tiap hari bursa 17.00 WIB (`.github/workflows/harian.yml`).
- **Berita & narasi**: `data/berita.json`, diperbarui Claude tiap Senin & Kamis pagi.
- **Daftar emiten**: `data/emiten.json`.
- **Rata-rata beli**: `data/rahasia.json`, terenkripsi (AES-GCM, kunci dari PIN lewat PBKDF2). Diubah dari menu Pengaturan di aplikasi.

Alat pantau, bukan saran beli atau jual.
