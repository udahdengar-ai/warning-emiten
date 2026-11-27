"""Aturan bursa yang dipakai bersama oleh build.py dan intraday.py.

Fraksi harga dan batas auto rejection (ARA/ARB) pasar reguler BEI.
- ARA: Rp1–10 = Rp1; Rp11–200 = 35%; >200–5.000 = 25%; >5.000 = 20%.
- ARB 19 Okt – 31 Des 2026 (Kep-00157/BEI/10-2026, asimetris): Rp1–14 = Rp1; >Rp14 = 7%.
- ARB mulai 1 Jan 2027: simetris dengan ARA (sesuai pengumuman BEI Sept 2026).
Kalau BEI mengubah aturan lagi, cukup ubah fungsi batas_ar di bawah.
Saham di Papan Pemantauan Khusus memakai batas sendiri (tidak dihitung di sini).
"""
import math

def fraksi(p):
    return 1 if p < 200 else 2 if p < 500 else 5 if p < 2000 else 10 if p < 5000 else 25

def _ara_pct(p):
    return 0.35 if p <= 200 else 0.25 if p <= 5000 else 0.20

def batas_ar(acuan, tanggal):
    """Kembalikan (ARA, ARB) untuk harga acuan (penutupan kemarin) pada tanggal 'YYYY-MM-DD'."""
    if acuan <= 10:
        return acuan + 1, max(1, acuan - 1)
    ara = acuan * (1 + _ara_pct(acuan))
    ara = math.floor(ara / fraksi(ara)) * fraksi(ara)
    if tanggal <= "2026-12-31":
        if acuan <= 14:
            return int(ara), acuan - 1
        arb = acuan * 0.93
    else:
        arb = acuan * (1 - _ara_pct(acuan))
    arb = math.ceil(arb / fraksi(arb)) * fraksi(arb)
    return int(ara), int(arb)
