"""Warning Emiten: harga & volume harian Yahoo Finance -> status, titik masuk/keluar, gabung berita.

Dijalankan otomatis oleh GitHub Actions tiap hari bursa sekitar 17.00 WIB (lihat .github/workflows/harian.yml).
Tidak memakai Claude dan tidak memakai rata-rata beli (rata-rata beli dikunci PIN dan hanya dibuka di HP).

Masukan : data/emiten.json  (daftar kode)
          data/berita.json  (berita & narasi, diperbarui Claude tiap Senin dan Kamis)
          data/sinyal.json, data/riwayat.json (hasil jalan sebelumnya, untuk kolom "berubah")
Keluaran: data/sinyal.json, data/harga.json, data/riwayat.json, data/judul.json

Aturan (sama dengan dashboard lama):
 Grafik  Bahaya  = harga terendah 3 bulan | tembus ke bawah MA50 | turun >=5% sehari dengan volume melonjak
         Waspada = tembus ke bawah MA20 | turun >=5% sehari | volume melonjak saat harga turun
                   | di bawah MA20 & MA50 dan turun >=5% dalam 5 hari
         Pantau  = tembus ke atas MA20/MA50 | tertinggi 3 bulan | naik >=5% sehari | volume melonjak saat harga naik
 Berita  Bahaya dipakai 90 hari (atau selama "berlaku": true), lainnya 30 hari.
 Titik   lantai (area tambah) = titik balik bawah terdekat di bawah harga (60 hari)
         atap (area kurangi)  = titik balik atas terdekat minimal 2% di atas harga
         batas gagal          = harga terendah 60 hari sebelum hari terakhir; "dekat" = dalam 3%.
"""
import json, os, time, datetime, statistics as st, urllib.request, urllib.parse
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
def p(n): return os.path.join(DATA, n)
def baca(n, d):
    try: return json.load(open(p(n), encoding="utf-8"))
    except Exception: return d
def tulis(n, obj):
    with open(p(n), "w", encoding="utf-8") as f: json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))

now = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=7)   # WIB
today = now.strftime("%Y-%m-%d")
drop_today = now.hour * 60 + now.minute < 16 * 60 + 30
KODE = baca("emiten.json", {}).get("kode", [])
news = baca("berita.json", {"berita": [], "narasi": {}, "dicek": [], "dicek_pada": ""})
prev = {x.get("kode"): x for x in baca("sinyal.json", {}).get("rows", []) if isinstance(x, dict)}
lama = {x.get("id"): x for x in baca("riwayat.json", {}).get("rows", []) if isinstance(x, dict) and x.get("id")}

LV = {"Bahaya": 3, "Waspada": 2}
NAMA = {3: "Bahaya", 2: "Waspada", 1: "Pantau", 0: "Tenang"}
NAMAB = {3: "Bahaya", 2: "Waspada", 0: "Tanpa catatan"}
def umur(t):
    try: return (now.date() - datetime.date.fromisoformat(t)).days
    except Exception: return 999
def pakai(x): return bool(x.get("berlaku")) or umur(x.get("tanggal", "")) <= (90 if x.get("dampak") == "Bahaya" else 30)
BERITA = [x for x in news.get("berita", []) if pakai(x)]

def fraksi(v): return 1 if v < 200 else 2 if v < 500 else 5 if v < 2000 else 10 if v < 5000 else 25
def bulat(v): t = fraksi(v); return int(round(v / t) * t)
def rp(x): return "Rp" + f"{x:,.0f}".replace(",", ".")
def d1(x): return f"{x:.1f}".replace(".", ",")

def ambil(simbol):
    err = None
    for host in ("query1", "query2"):
        for coba in range(3):
            try:
                url = f"https://{host}.finance.yahoo.com/v8/finance/chart/{simbol}?range=1y&interval=1d"
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
                res = json.load(urllib.request.urlopen(req, timeout=30))["chart"]["result"][0]
                q = res["indicators"]["quote"][0]
                r = []
                for t, c, v, h, l in zip(res["timestamp"], q["close"], q["volume"], q["high"], q["low"]):
                    if None in (c, v, h, l): continue
                    d = (datetime.datetime.fromtimestamp(t, datetime.timezone.utc) + datetime.timedelta(hours=7)).strftime("%Y-%m-%d")
                    r.append((d, c, v, h, l))
                return res, [x for x in r if not (drop_today and x[0] == today)]
            except Exception as e:
                err = e; time.sleep(2 + coba * 3)
    raise err

def teknikal(c, v, i):
    last = c[i]
    ma20, ma50, pma20, pma50 = st.mean(c[i-19:i+1]), st.mean(c[i-49:i+1]), st.mean(c[i-20:i]), st.mean(c[i-50:i])
    avg20 = st.mean(v[i-20:i]); vr = v[i] / avg20 if avg20 else 0
    ch1 = (c[i] / c[i-1] - 1) * 100; ch5 = (c[i] / c[i-5] - 1) * 100
    lo, hi = min(c[i-59:i+1]), max(c[i-59:i+1])
    pola, lt = [], 0
    def add(t, lv):
        nonlocal lt
        pola.append(t); lt = max(lt, lv)
    if last <= lo: add("Harga terendah 3 bulan", 3)
    if c[i-1] >= pma50 and last < ma50: add("Tembus ke bawah MA50", 3)
    if c[i-1] >= pma20 and last < ma20: add("Tembus ke bawah MA20", 2)
    if ch1 <= -5: add("Turun 5% atau lebih dalam sehari", 3 if vr >= 2 else 2)
    if vr >= 2 and -5 < ch1 < 0: add("Volume melonjak saat harga turun", 2)
    if last < ma20 and last < ma50 and ch5 <= -5: add("Di bawah MA20 & MA50 dan turun 5% atau lebih dalam 5 hari", 2)
    if c[i-1] <= pma20 and last > ma20: add("Tembus ke atas MA20", 1)
    if c[i-1] <= pma50 and last > ma50: add("Tembus ke atas MA50", 1)
    if last >= hi: add("Harga tertinggi 3 bulan", 1)
    if ch1 >= 5: add("Naik 5% atau lebih dalam sehari", 1)
    if vr >= 2 and ch1 >= 0: add("Volume melonjak saat harga naik", 1)
    return lt, pola, dict(ma20=ma20, ma50=ma50, avg20=avg20, vr=vr, ch1=ch1, ch5=ch5, lo=lo, hi=hi)

def maju(c, i, k): return round((c[i+k] / c[i] - 1) * 100, 2) if i + k < len(c) else None

gagal, gagal_judul, sig, hist, riw = [], [], [], [], {}
try:
    _, ih = ambil("%5EJKSE"); ihd = [x[0] for x in ih]; ihc = [x[1] for x in ih]
except Exception as e:
    ihd, ihc = [], []; gagal.append(f"IHSG: {e}")
def ihsg(tgl, k):
    if tgl not in ihd: return None
    j = ihd.index(tgl)
    return (ihc[j] / ihc[j-k] - 1) * 100 if j >= k else None

for k in KODE:
    try:
        res, r = ambil(k + ".JK")
    except Exception as e:
        gagal.append(f"{k}: {e}")
        if k in prev: sig.append(prev[k])          # pakai data lama supaya emiten tidak hilang
        continue
    if len(r) < 66:
        gagal.append(f"{k}: data kurang dari 66 hari"); continue
    tg = [x[0] for x in r]; c = [x[1] for x in r]; v = [x[2] for x in r]; h = [x[3] for x in r]; l = [x[4] for x in r]
    last = c[-1]; n = len(c)
    lt, pola, a = teknikal(c, v, n - 1)
    ma50 = a["ma50"]
    base = st.mean(v[-25:-5]); tr = st.mean(v[-5:]) / base if base else 1
    ch20 = (c[-1] / c[-21] - 1) * 100
    mine = sorted([x for x in BERITA if x["kode"] == k], key=lambda x: x["tanggal"], reverse=True)
    lb = max([LV.get(x.get("dampak"), 0) for x in mine] + [0])
    pemicu = [x["judul"] for x in mine if LV.get(x.get("dampak"), 0) == lb and lb >= 2]
    lvl = max(lt, lb)
    plo = [l[i] for i in range(n-60, n-2) if l[i] == min(l[i-3:i+4])]
    phi = [h[i] for i in range(n-60, n-2) if h[i] == max(h[i-3:i+4])]
    dasar = min(l[-61:-1])
    bawah = [x for x in plo if x <= last]; atas = [x for x in phi if x > last * 1.02]
    lantai = bulat(max(bawah)) if bawah else bulat(dasar)
    atap = bulat(min(atas)) if atas else bulat(max(h[-60:]))
    bg = bulat(dasar)
    jl = (last / lantai - 1) * 100; ja = (atap / last - 1) * 100
    dekat_l = last <= lantai * 1.03; dekat_a = last >= atap * 0.97
    turun = " Tren masih turun (harga di bawah MA50)." if last < ma50 else ""
    # label dibuat dua versi: kalau dipegang / belum dipegang. Aplikasi memilih setelah membuka rata-rata beli dengan PIN.
    if last < dasar:
        lp = lb_ = "Batas gagal jebol"; cp = cb = f"Harga ditutup di bawah terendah 3 bulan ({rp(bg)}). Lantai tidak menahan."
    elif dekat_l and dekat_a:
        lp = lb_ = "Rentang sempit"; cp = cb = f"Lantai {rp(lantai)} dan atap {rp(atap)} terlalu rapat. Tunggu harga keluar dari rentang ini."
    elif dekat_l and lvl == 3:
        lp = lb_ = "Dekat lantai, status Bahaya"; cp = cb = f"Harga dekat lantai {rp(lantai)}, tetapi status Bahaya. Bukan area tambah sampai statusnya turun."
    elif dekat_l:
        lp, cp = "Dekat area tambah", f"Harga dekat lantai {rp(lantai)}.{turun}"
        lb_, cb = "Dekat area masuk", f"Belum dipegang. Harga dekat lantai {rp(lantai)}; batas gagal {rp(bg)}.{turun}"
    elif dekat_a:
        lp, cp = "Dekat area kurangi", f"Harga dekat atap {rp(atap)}."
        lb_, cb = "Dekat atap", f"Belum dipegang. Harga dekat atap {rp(atap)}, bukan area masuk."
    else:
        lp, lb_ = "Tahan", "Menunggu area masuk"
        cp = cb = f"Jarak turun ke lantai {rp(lantai)}: {d1(jl)}%. Jarak naik ke atap {rp(atap)}: {d1(ja)}%."
    i5, i20 = ihsg(tg[-1], 5), ihsg(tg[-1], 20)
    v20 = round(ch20 - i20, 2) if i20 is not None else None
    kuat = "Tidak ada data" if v20 is None else "Lebih kuat dari pasar" if v20 >= 3 else "Lebih lemah dari pasar" if v20 <= -3 else "Sejalan dengan pasar"
    sg, sb = NAMA[lt], NAMAB[lb]
    pv = prev.get(k)
    ubah = []
    if pv and pv.get("tanggal") and pv.get("tanggal") < tg[-1]:
        seb = pv
    elif pv:
        seb = pv.get("_seb") or {}
    else:
        seb = {}
    if seb:
        if seb.get("status_grafik") != sg: ubah.append(f"Status grafik: {seb.get('status_grafik')} → {sg}")
        if seb.get("status_berita") != sb: ubah.append(f"Status berita: {seb.get('status_berita')} → {sb}")
        for nm, a0, b0 in (("Lantai", seb.get("lantai"), lantai), ("Atap", seb.get("atap"), atap), ("Batas gagal", seb.get("batas_gagal"), bg)):
            if a0 is not None and a0 != b0: ubah.append(f"{nm}: {rp(a0)} → {rp(b0)}")
    seb_ringkas = {f: seb.get(f) for f in ("tanggal", "status_grafik", "status_berita", "lantai", "atap", "batas_gagal", "label_pegang", "label_belum")} if seb else None
    sig.append(dict(kode=k, nama=res["meta"].get("longName") or res["meta"].get("shortName") or k, tanggal=tg[-1],
        harga=last, ubah_1h=round(a["ch1"], 2), ubah_5h=round(a["ch5"], 2), ubah_20h=round(ch20, 2),
        level=lvl, level_grafik=lt, level_berita=lb, status_grafik=sg, status_berita=sb,
        pola="; ".join(pola), alasan_berita=pemicu[0] if pemicu else "",
        label_pegang=lp, catatan_pegang=cp, label_belum=lb_, catatan_belum=cb,
        lantai=lantai, atap=atap, batas_gagal=bg, jarak_lantai_pct=round(jl, 1), jarak_atap_pct=round(ja, 1),
        ma20=round(a["ma20"], 1), ma50=round(ma50, 1),
        volume=v[-1], rasio_volume=round(a["vr"], 2),
        status_volume="Melonjak" if a["vr"] >= 2 else "Sepi" if a["vr"] <= 0.5 else "Normal",
        tren_volume="Meningkat" if tr >= 1.3 else "Menurun" if tr <= 0.7 else "Stabil",
        vs_ihsg_20h=v20, kekuatan=kuat, narasi=news.get("narasi", {}).get(k, ""),
        perubahan=ubah, _seb=seb_ringkas))
    hist += [[k, x[0], x[1], x[2]] for x in r[-60:]]
    # riwayat sinyal grafik (dihitung ulang dari 1 tahun) untuk rapor sinyal
    sblm = teknikal(c, v, 60)[:2] if n > 61 else (0, [])
    for i in range(61, n):
        li, pi, _ = teknikal(c, v, i)
        if li >= 1 and (li != sblm[0] or pi != sblm[1]):
            riw[f"{k}-{tg[i]}"] = dict(id=f"{k}-{tg[i]}", kode=k, tanggal=tg[i], ke=NAMA[li], pemicu="; ".join(pi),
                                      harga=c[i], ubah_5h=maju(c, i, 5), ubah_20h=maju(c, i, 20))
        sblm = (li, pi)
    time.sleep(0.4)

for x in lama.values(): riw.setdefault(x["id"], x)
URUT = {"Batas gagal jebol": 0, "Dekat lantai, status Bahaya": 1}
sig.sort(key=lambda s: (-s.get("level", 0), URUT.get(s.get("label_pegang"), 5), s["kode"]))

# judul berita harian (Google News RSS), tanpa ringkasan
judul = []
for k in KODE:
    try:
        q = urllib.parse.quote(f'"{k}" saham')
        url = f"https://news.google.com/rss/search?q={q}+when:7d&hl=id&gl=ID&ceid=ID:id"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        root = ET.fromstring(urllib.request.urlopen(req, timeout=20).read())
        for it in root.iter("item"):
            t = it.findtext("title") or ""; src = it.findtext("source") or ""
            if src and t.endswith(" - " + src): t = t[: -len(src) - 3]
            try: tgl = parsedate_to_datetime(it.findtext("pubDate")).strftime("%Y-%m-%d")
            except Exception: tgl = ""
            judul.append(dict(kode=k, tanggal=tgl, judul=t, sumber=src, url=it.findtext("link") or ""))
            if sum(1 for j in judul if j["kode"] == k) >= 3: break
    except Exception as e:
        gagal_judul.append(f"{k}: {e}")
    time.sleep(0.5)

meta = dict(dijalankan=now.strftime("%Y-%m-%d %H:%M WIB"), tanggal_harga=max([s["tanggal"] for s in sig] or [""]),
            gagal=gagal, gagal_judul=len(gagal_judul), berita_dicek_pada=news.get("dicek_pada", ""))
tulis("sinyal.json", {"rows": sig, "meta": meta})
tulis("harga.json", {"kolom": ["kode", "tanggal", "harga", "volume"], "rows": hist})
tulis("riwayat.json", {"rows": sorted(riw.values(), key=lambda x: (x["tanggal"], x["kode"]), reverse=True)[:1500]})
if judul or not os.path.exists(p("judul.json")):
    tulis("judul.json", {"rows": judul, "dicek_pada": today})
print("emiten", len(sig), "| gagal", gagal, "| tanggal", meta["tanggal_harga"])
for s in sig: print(s["kode"], s["status_grafik"], s["status_berita"], s["label_pegang"], s["harga"], s["lantai"], s["atap"], s["perubahan"])
