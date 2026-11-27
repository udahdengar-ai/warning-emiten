"""Pantauan spike 3 titik per hari bursa (GitHub Actions, tanpa Claude).

Titik ditentukan dari jam data terakhir (bukan jam robot jalan), supaya robot yang telat tetap masuk titik yang benar:
  pagi  = data sebelum 13.30 WIB      -> "Pembukaan"         (robot ±09.30)
  siang = data 13.30 s/d 15.49 WIB    -> "Setelah istirahat" (robot ±14.00, Jumat ±14.30)
  tutup = data 15.50 WIB ke atas      -> "Penutupan"         (robot 17.00, setelah build.py)

Per emiten per titik: perubahan dari penutupan kemarin, harga buka (gap), tertinggi/terendah sejauh ini,
volume sejauh ini dibanding rata-rata volume pada jam yang sama (sampai 20 hari bursa sebelumnya).
Spike = perubahan >= 3% (naik/turun) dan minimal 2 fraksi harga.
Status bertingkat sepanjang hari:
  Muncul        = spike terdeteksi (belum dikonfirmasi)
  Terkonfirmasi = spike yang sama masih di atas ambang pada titik berikutnya DAN volume >= 1,5x normal
  Pudar         = sempat spike (atau sempat menyentuh 3%) lalu kembali di bawah ambang
"""
import json, os, sys, time, datetime, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from aturan import fraksi, batas_ar

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
def p(n): return os.path.join(DATA, n)
def baca(n, d):
    try: return json.load(open(p(n), encoding="utf-8"))
    except Exception: return d

AMBANG = 3.0
VOL_KONFIRMASI = 1.5
NAMA_TITIK = {"pagi": "Pembukaan", "siang": "Setelah istirahat", "tutup": "Penutupan"}
URUT = ["pagi", "siang", "tutup"]
WIB = datetime.timezone(datetime.timedelta(hours=7))
now = datetime.datetime.now(WIB)
KODE = baca("emiten.json", {}).get("kode", [])
harian = baca("harga.json", {}).get("rows", [])


def ambil(simbol):
    err = None
    for host in ("query1", "query2"):
        for coba in range(3):
            try:
                url = f"https://{host}.finance.yahoo.com/v8/finance/chart/{simbol}?range=1mo&interval=5m&events=div"
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
                return json.load(urllib.request.urlopen(req, timeout=30))["chart"]["result"][0]
            except Exception as e:
                err = e; time.sleep(2 + coba * 3)
    raise err

def per_hari(res):
    q = res["indicators"]["quote"][0]; hari = {}
    for i, t in enumerate(res.get("timestamp") or []):
        w = datetime.datetime.fromtimestamp(t, WIB)
        o, h, l, c, v = (q[k][i] for k in ("open", "high", "low", "close", "volume"))
        if c is None: continue
        hari.setdefault(w.strftime("%Y-%m-%d"), []).append((w.strftime("%H:%M"), o if o is not None else c, h or c, l or c, c, v or 0))
    return hari

def hitung(k, res):
    hari = per_hari(res)
    if not hari: return None
    tgl = max(hari); bars = hari[tgl]
    jam = bars[-1][0]
    lalu = sorted(d for d in hari if d < tgl)
    tutup_kemarin = None
    for r in reversed(harian):                       # utamakan penutupan resmi dari harga.json
        if r[0] == k and r[1] < tgl: tutup_kemarin = r[2]; break
    if tutup_kemarin is None and lalu: tutup_kemarin = hari[lalu[-1]][-1][4]
    if not tutup_kemarin: return None
    ara, arb = batas_ar(tutup_kemarin, tgl)
    div = 0.0
    for t, d in ((res.get("events") or {}).get("dividends") or {}).items():
        if datetime.datetime.fromtimestamp(int(t), WIB).strftime("%Y-%m-%d") == tgl: div = float(d.get("amount", 0))
    acuan = tutup_kemarin - div                      # hari ex-dividen: turun sebesar dividen bukan spike
    buka = bars[0][1]; tinggi = max(b[2] for b in bars); rendah = min(b[3] for b in bars); harga = bars[-1][4]
    vol = sum(b[5] for b in bars)
    pemb = [sum(b[5] for b in hari[d] if b[0] <= jam) for d in lalu[-20:]]
    pemb = [x for x in pemb if x > 0]
    rv = round(vol / (sum(pemb) / len(pemb)), 2) if pemb else None
    pc = lambda x: round((x / acuan - 1) * 100, 2)
    jauh = lambda x: abs(x - acuan) >= 2 * fraksi(acuan)
    ubah, gap, naik, turun = pc(harga), pc(buka), pc(tinggi), pc(rendah)
    arah = "naik" if ubah >= AMBANG and jauh(harga) else "turun" if ubah <= -AMBANG and jauh(harga) else None
    sempat = "naik" if naik >= AMBANG and jauh(tinggi) else "turun" if turun <= -AMBANG and jauh(rendah) else None
    batas = "ARB" if harga <= arb else "ARA" if harga >= ara else ""
    sentuh = "ARB" if rendah <= arb else "ARA" if tinggi >= ara else ""
    return tgl, dict(jam_data=jam, tutup_kemarin=tutup_kemarin, ara=ara, arb=arb, batas=batas, sentuh=sentuh, dividen=div, buka=buka, harga=harga, tertinggi=tinggi, terendah=rendah,
                     ubah=ubah, gap=gap, naik_maks=naik, turun_maks=turun, volume=vol, rasio_volume=rv, arah=arah, sempat=sempat)

hasil, tgl_data, gagal = {}, None, []
for k in KODE:
    try:
        h = hitung(k, ambil(k + ".JK"))
        if h: tgl_data = max(tgl_data or h[0], h[0]); hasil[k] = h
    except Exception as e:
        gagal.append(f"{k}: {e}")
    time.sleep(0.4)
if not hasil:
    print("Tidak ada data intraday. Gagal:", gagal); raise SystemExit(0)
rows = {k: v for k, (t, v) in hasil.items() if t == tgl_data}
if not rows:
    print("Tidak ada data untuk tanggal terbaru"); raise SystemExit(0)
jam_akhir = max(v["jam_data"] for v in rows.values())
titik = "pagi" if jam_akhir < "13:30" else "siang" if jam_akhir < "15:50" else "tutup"

simpan = baca("intraday.json", {})
if simpan.get("tanggal") != tgl_data: simpan = {"tanggal": tgl_data, "titik": {}}
simpan["titik"][titik] = {"nama": NAMA_TITIK[titik], "jam_data": jam_akhir, "dijalankan": now.strftime("%H:%M"), "gagal": gagal, "rows": rows}

def pct(x): return (f"+{x:.1f}" if x > 0 else f"{x:.1f}").replace(".", ",") + "%"
status = {}
for k in KODE:
    aktif, st, cat, batas_akhir = None, None, [], ""
    for t in URUT:
        r = simpan["titik"].get(t, {}).get("rows", {}).get(k)
        if not r: continue
        rv = r.get("rasio_volume")
        tv = f"volume {str(rv).replace('.', ',')}x normal" if rv is not None else "volume tidak ada data"
        nm = NAMA_TITIK[t]
        if r.get("dividen"): cat.append(f"{nm}: ex-dividen Rp{str(round(r['dividen'], 2)).replace('.', ',')} (penurunan karena dividen tidak dihitung spike)")
        if r.get("batas"):
            aktif = "turun" if r["batas"] == "ARB" else "naik"; st = "Terkonfirmasi"; batas_akhir = r["batas"]
            cat.append(f"{nm}: DI {r['batas']} Rp{r['arb' if r['batas'] == 'ARB' else 'ara']:,}".replace(",", ".") + f" ({pct(r['ubah'])}), {tv}")
            continue
        if r.get("sentuh"):
            cat.append(f"{nm}: sempat menyentuh {r['sentuh']}, sekarang {pct(r['ubah'])}")
        batas_akhir = ""
        if aktif is None:
            if r["arah"]:
                aktif, st = r["arah"], "Muncul"
                cat.append(f"{nm}: {pct(r['ubah'])} (buka {pct(r['gap'])}), {tv}")
            elif r["sempat"]:
                aktif, st = r["sempat"], "Pudar"
                cat.append(f"{nm}: sempat {pct(r['naik_maks'] if r['sempat'] == 'naik' else r['turun_maks'])}, sekarang {pct(r['ubah'])}")
        else:
            if r["arah"] == aktif:
                if rv is not None and rv >= VOL_KONFIRMASI: st = "Terkonfirmasi"
                elif st == "Pudar": st = "Muncul"
                cat.append(f"{nm}: masih {pct(r['ubah'])}, {tv}")
            else:
                st = "Pudar"
                cat.append(f"{nm}: kembali ke {pct(r['ubah'])}")
    if st: status[k] = {"status": st, "arah": aktif, "catatan": cat, "batas": batas_akhir}
simpan["status"] = status
simpan["diperbarui"] = now.strftime("%Y-%m-%d %H:%M WIB")
with open(p("intraday.json"), "w", encoding="utf-8") as f: json.dump(simpan, f, ensure_ascii=False, separators=(",", ":"))
print("tanggal", tgl_data, "| titik", titik, "| data per", jam_akhir, "| gagal", gagal)
for k, s in status.items(): print(k, s)
