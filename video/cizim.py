# -*- coding: utf-8 -*-
"""Sahne grafikleri (Pillow). Her öğe RGBA görüntü + konum + giriş zamanı döner.

Tuval 1080x1920. Güvenli alan: sol 64 px, sağ 180 px (Shorts/Reels/TikTok
butonları), üst 220 px (ilerleme çubuğu + etiket), alt %20 (384 px) boş.
Altyazı alt-orta bandında (y ≈ 1330-1500).
"""
import math
import os

from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1920
SOL, SAG = 64, 900              # içerik x aralığı (sağda 180 px boş)
GEN = SAG - SOL

# dogukanlive.com CSS değişkenleri (~/dogukan-website/index.html :root)
BG = (11, 11, 12)
INK = (236, 236, 236)
MUTED = (143, 143, 153)
ACCENT = (240, 185, 11)
UP = (46, 230, 160)
DOWN = (255, 92, 108)

# Archivo (SIL OFL 1.1, bkz. fonts/OFL.txt) depoyla birlikte gelir; CI'da kurulum gerekmez.
_FONT_ADAYLARI = [os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts", "Archivo.ttf"),
                  os.path.expanduser("~/Library/Fonts/Archivo.ttf"), "/Library/Fonts/Archivo.ttf"]
_YEDEK = ["/System/Library/Fonts/HelveticaNeue.ttc", "/System/Library/Fonts/Helvetica.ttc",
          "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
_cache = {}


def font(boyut, agirlik=700, genislik=100):
    k = (boyut, agirlik, genislik)
    if k in _cache:
        return _cache[k]
    f = None
    for yol in _FONT_ADAYLARI:
        if os.path.exists(yol):
            f = ImageFont.truetype(yol, boyut)
            try:
                f.set_variation_by_axes([agirlik, genislik])
            except Exception:  # noqa: BLE001 — değişken olmayan font
                pass
            break
    if f is None:
        for yol in _YEDEK:
            if os.path.exists(yol):
                f = ImageFont.truetype(yol, boyut, index=1 if agirlik >= 600 and yol.endswith(".ttc") else 0)
                break
    _cache[k] = f or ImageFont.load_default()
    return _cache[k]


def metin_gen(f, s, aralik=0):
    return f.getlength(s) + aralik * max(len(s) - 1, 0)


def sar(s, f, gen):
    """Kelime kaydırma."""
    satirlar, cur = [], ""
    for k in s.split():
        aday = (cur + " " + k).strip()
        if cur and f.getlength(aday) > gen:
            satirlar.append(cur)
            cur = k
        else:
            cur = aday
    if cur:
        satirlar.append(cur)
    return satirlar


def sigdir(s, gen, boyut, agirlik=800, min_boyut=40, genislik=100):
    while boyut > min_boyut and font(boyut, agirlik, genislik).getlength(s) > gen:
        boyut -= 2
    return font(boyut, agirlik, genislik)


def aralikli(d, xy, s, f, fill, aralik):
    """Harf aralıklı (letter-spacing) yazı."""
    x, y = xy
    for ch in s:
        d.text((x, y), ch, font=f, fill=fill)
        x += f.getlength(ch) + aralik
    return x


class Oge:
    def __init__(self, img, x, y, giris=0.0, anim=True):
        self.img, self.x, self.y, self.giris, self.anim = img, x, y, giris, anim


def _tuval(w, h):
    return Image.new("RGBA", (int(w), int(h)), (0, 0, 0, 0))


def kart(w, h, r=28, dolgu=(11, 11, 12, 200), kenar=(255, 255, 255, 28), sol_serit=None):
    """Kenar yumuşatmalı (2x örnekleme) yuvarlak köşeli kart."""
    s = 2
    im = _tuval(w * s, h * s)
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, w * s - 1, h * s - 1], r * s, fill=dolgu, outline=kenar, width=2 * s)
    if sol_serit:
        m = _tuval(w * s, h * s)
        ImageDraw.Draw(m).rounded_rectangle([0, 0, w * s - 1, h * s - 1], r * s, fill=(255, 255, 255, 255))
        serit = _tuval(w * s, h * s)
        ImageDraw.Draw(serit).rectangle([0, 0, 8 * s, h * s], fill=sol_serit + (255,))
        im.alpha_composite(Image.composite(serit, _tuval(w * s, h * s), m.getchannel("A")))
    return im.resize((int(w), int(h)), Image.LANCZOS)


def cip(yazi, zemin, renk=(0, 0, 0), boyut=30, pad=(20, 10)):
    f = font(boyut, 800, 100)
    ar = 3
    tw = metin_gen(f, yazi, ar)
    w, h = int(tw + pad[0] * 2), int(boyut + pad[1] * 2 + 4)
    s = 2
    im = _tuval(w * s, h * s)
    ImageDraw.Draw(im).rounded_rectangle([0, 0, w * s - 1, h * s - 1], 10 * s, fill=zemin + (255,))
    im = im.resize((w, h), Image.LANCZOS)
    aralikli(ImageDraw.Draw(im), (pad[0], pad[1] - 2), yazi, f, renk, ar)
    return im


def ucgen(d, x, y, boyut, yukari, renk):
    if yukari:
        d.polygon([(x, y + boyut), (x + boyut, y + boyut), (x + boyut / 2, y)], fill=renk)
    else:
        d.polygon([(x, y), (x + boyut, y), (x + boyut / 2, y + boyut)], fill=renk)


# --------------------------------------------------------------------------- #
# Sabit katmanlar
# --------------------------------------------------------------------------- #

def ust_etiket(yazi):
    f = font(28, 700, 100)
    im = _tuval(GEN, 44)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 10, 5, 36], fill=ACCENT)
    aralikli(d, (18, 6), yazi, f, INK + (230,), 3)
    return im


def ilerleme(d, sure_listesi, t, y=70):
    """Hikâye tarzı bölümlü ilerleme çubuğu."""
    n = len(sure_listesi)
    bosluk = 8
    x0, x1 = SOL, W - SOL
    parca = (x1 - x0 - bosluk * (n - 1)) / n
    for i, (bas, son) in enumerate(sure_listesi):
        a = x0 + i * (parca + bosluk)
        d.rounded_rectangle([a, y, a + parca, y + 6], 3, fill=(255, 255, 255, 70))
        if t >= son:
            oran = 1.0
        elif t <= bas:
            oran = 0.0
        else:
            oran = (t - bas) / max(son - bas, 1e-3)
        if oran > 0:
            d.rounded_rectangle([a, y, a + max(parca * oran, 6), y + 6], 3, fill=ACCENT + (255,))


# --------------------------------------------------------------------------- #
# Sahneler
# --------------------------------------------------------------------------- #

def sahne_kanca(s):
    o = []
    y = 470
    tarih = cip(s["tarih"], ACCENT, (0, 0, 0), 34)
    o.append(Oge(tarih, SOL, y, 0, anim=False))
    y += tarih.height + 40
    if s.get("manset"):                   # günün manşeti büyük; ruh hâli satırı yok
        boyut = 112
        while True:
            f = font(boyut, 900, 100)
            sat = sar(s["alt"], f, GEN)
            if (len(sat) <= 4 and all(f.getlength(x) <= GEN for x in sat)) or boyut <= 64:
                break
            boyut -= 4
        satir_h = int(boyut * 1.12)
        im = _tuval(GEN, len(sat) * satir_h + 16)
        d = ImageDraw.Draw(im)
        for i, x in enumerate(sat):
            d.text((0, i * satir_h), x, font=f, fill=INK)
        o.append(Oge(im, SOL - 4, y, 0, anim=False))
        return o
    mood = s["mood"].replace("i", "İ").upper() if s["mood"] else ""
    satir1, satir2 = "PİYASA", mood
    f1 = sigdir(satir1, GEN, 150, 900, 60, 100)
    f2 = sigdir(satir2, GEN, 150, 900, 60, 100)
    h1 = int(f1.size * 1.02)
    h2 = int(f2.size * 1.1)
    im = _tuval(GEN, h1 + h2 + 10)
    d = ImageDraw.Draw(im)
    d.text((0, 0), satir1, font=f1, fill=INK)
    d.text((0, h1), satir2, font=f2, fill=ACCENT)
    o.append(Oge(im, SOL - 6, y, 0, anim=False))
    y += im.height + 36
    if s.get("alt"):
        f = font(60, 600, 100)
        sat = sar(s["alt"], f, GEN)
        im = _tuval(GEN, len(sat) * 74 + 10)
        d = ImageDraw.Draw(im)
        for i, x in enumerate(sat):
            d.text((0, i * 74), x, font=f, fill=INK)
        o.append(Oge(im, SOL, y, 0, anim=False))
    return o


def sahne_fiyat(s):
    o = []
    y = 300
    bas = _tuval(GEN, 60)
    d = ImageDraw.Draw(bas)
    aralikli(d, (0, 4), "PİYASA", font(40, 900), ACCENT, 4)
    d.text((200, 12), "24 saatlik değişim", font=font(32, 500), fill=MUTED)
    o.append(Oge(bas, SOL, y, 0.0))
    y += 84
    satir_h, gen = 132, GEN
    for i, r in enumerate(s["satirlar"]):
        k = kart(gen, satir_h - 16, 22)
        d = ImageDraw.Draw(k)
        d.text((32, 22), r["sembol"], font=font(60, 900), fill=INK)
        fiyat_f = font(56, 700)
        d.text((230, 26), r["fiyat"], font=fiyat_f, fill=INK)
        ch = r["degisim"]
        if ch is not None:
            from .senaryo import yuzde_tr
            renk = UP if ch >= 0 else DOWN
            yz = yuzde_tr(ch)
            ff = font(46, 800)
            tw = ff.getlength(yz)
            px = gen - 32 - tw
            ucgen(d, px - 38, 44, 26, ch >= 0, renk)
            d.text((px, 32), yz, font=ff, fill=renk)
        o.append(Oge(k, SOL, y, 0.12 + i * 0.1))
        y += satir_h
    alt = []
    if s.get("toplam"):
        alt.append("Toplam piyasa " + s["toplam"])
    if s.get("dominans"):
        alt.append("BTC dominansı  " + s["dominans"])
    if alt:
        im = _tuval(GEN, 50)
        ImageDraw.Draw(im).text((4, 6), "   ·   ".join(alt), font=font(32, 600), fill=MUTED)
        o.append(Oge(im, SOL, y + 8, 0.7))
    return o


def _renk_gecis(v):
    duraklar = [(0, DOWN), (25, (255, 140, 60)), (50, (200, 200, 200)), (75, (150, 220, 90)), (100, UP)]
    for (a, ca), (b, cb) in zip(duraklar, duraklar[1:]):
        if v <= b:
            o = (v - a) / (b - a)
            return tuple(int(ca[i] + (cb[i] - ca[i]) * o) for i in range(3))
    return UP


def gosterge(deger, ibre_deger, etiket):
    """Yarım daire korku-açgözlülük göstergesi (2x örnekleme)."""
    s = 2
    w, h = GEN, 560
    im = _tuval(w * s, h * s)
    d = ImageDraw.Draw(im)
    cx, cy, r = w * s // 2, 430 * s, 360 * s
    kal = 44 * s
    for i in range(100):
        a0 = 180 + i * 1.8
        d.arc([cx - r, cy - r, cx + r, cy + r], a0, a0 + 1.9, fill=_renk_gecis(i + 0.5) + (255,), width=kal)
    # ibre
    ang = math.radians(180 + 1.8 * ibre_deger)
    L = r - kal - 24 * s
    ux, uy = math.cos(ang), math.sin(ang)
    px, py = -uy, ux
    tip = (cx + ux * L, cy + uy * L)
    b1 = (cx + px * 14 * s, cy + py * 14 * s)
    b2 = (cx - px * 14 * s, cy - py * 14 * s)
    d.polygon([tip, b1, b2], fill=INK + (255,))
    d.ellipse([cx - 26 * s, cy - 26 * s, cx + 26 * s, cy + 26 * s], fill=INK + (255,))
    im = im.resize((w, h), Image.LANCZOS)
    d = ImageDraw.Draw(im)
    for v, x in ((0, cx / s - r / s - 10), (100, cx / s + r / s - 40)):
        d.text((x, 440), str(v), font=font(30, 600), fill=MUTED)
    return im


def sahne_duygu(s):
    o = []
    y = 300
    bas = _tuval(GEN, 110)
    d = ImageDraw.Draw(bas)
    aralikli(d, (0, 0), "KORKU & AÇGÖZLÜLÜK", font(40, 900), ACCENT, 4)
    d.text((0, 56), "Endeks, 0-100", font=font(32, 500), fill=MUTED)
    o.append(Oge(bas, SOL, y, 0))
    g = {"y": y + 130, "deger": s["deger"]}
    renk = _renk_gecis(s["deger"])
    alt = _tuval(GEN, 260)
    d = ImageDraw.Draw(alt)
    f = font(150, 900)
    yz = str(s["deger"])
    d.text(((GEN - f.getlength(yz)) / 2, 0), yz, font=f, fill=INK)
    fe = font(56, 800)
    d.text(((GEN - fe.getlength(s["etiket"])) / 2, 160), s["etiket"], font=fe, fill=renk)
    o.append(Oge(alt, SOL, g["y"] + 470, 0.35))
    parca = []
    if s.get("dun") is not None:
        parca.append(f"Dün {s['dun']}")
    if s.get("hafta") is not None:
        parca.append(f"Geçen hafta {s['hafta']}")
    if parca:
        im = _tuval(GEN, 50)
        ff = font(34, 600)
        yz = "  ·  ".join(parca)
        ImageDraw.Draw(im).text(((GEN - ff.getlength(yz)) / 2, 4), yz, font=ff, fill=MUTED)
        o.append(Oge(im, SOL, g["y"] + 740, 0.6))
    return o, g


ONEM = {"kritik": ("KRİTİK", DOWN, (0, 0, 0)), "onemli": ("ÖNEMLİ", ACCENT, (0, 0, 0))}


def sahne_haber(s, sira):
    o = []
    y = 330
    ad, zemin, renk = ONEM.get(s.get("onem"), ("GÜNDEM", MUTED, (0, 0, 0)))
    c = cip(ad, zemin, renk, 30)
    etiket = _tuval(GEN, c.height)
    etiket.alpha_composite(c, (0, 0))
    aralikli(ImageDraw.Draw(etiket), (c.width + 20, 12), "GÜNÜN HABERİ" if sira == 0 else "GÜNDEM",
             font(30, 800), INK, 3)
    o.append(Oge(etiket, SOL, y, 0))
    y += c.height + 34
    if s.get("vurgu"):
        f = sigdir(s["vurgu"], GEN, 120, 900, 60)
        im = _tuval(GEN, int(f.size * 1.2))
        ImageDraw.Draw(im).text((0, 0), s["vurgu"], font=f, fill=ACCENT)
        o.append(Oge(im, SOL - 4, y, 0.15))
        y += im.height + 18
    f = font(64, 800)
    sat = sar(s["baslik"], f, GEN)
    if len(sat) > 4:
        f = font(54, 800)
        sat = sar(s["baslik"], f, GEN)
    lh = int(f.size * 1.18)
    im = _tuval(GEN, lh * len(sat) + 12)
    d = ImageDraw.Draw(im)
    for i, x in enumerate(sat):
        d.text((0, i * lh), x, font=f, fill=INK)
    o.append(Oge(im, SOL, y, 0.3))
    y += im.height + 26
    if s.get("kaynak"):
        im = _tuval(GEN, 46)
        d = ImageDraw.Draw(im)
        d.rectangle([0, 20, 40, 23], fill=ACCENT)
        d.text((56, 4), "Kaynak: " + s["kaynak"], font=font(32, 600), fill=MUTED)
        o.append(Oge(im, SOL, y, 0.5))
    return o


def sahne_risk(s):
    o = []
    y = 360
    c = cip("ANA RİSK", DOWN, (0, 0, 0), 32)
    o.append(Oge(c, SOL, y, 0))
    y += c.height + 30
    f = font(58, 700)
    sat = sar(s["metin"], f, GEN - 80)
    lh = int(f.size * 1.25)
    k = kart(GEN, lh * len(sat) + 80, 26, (11, 11, 12, 190), (255, 92, 108, 90), DOWN)
    d = ImageDraw.Draw(k)
    for i, x in enumerate(sat):
        d.text((48, 40 + i * lh), x, font=f, fill=INK)
    o.append(Oge(k, SOL, y, 0.2))
    return o


def sahne_takip(s):
    o = []
    y = 320
    bas = _tuval(GEN, 110)
    d = ImageDraw.Draw(bas)
    aralikli(d, (0, 0), "BUGÜN TAKİP ET", font(46, 900), ACCENT, 4)
    d.text((0, 62), "Saatler Türkiye saati", font=font(32, 500), fill=MUTED)
    o.append(Oge(bas, SOL, y, 0))
    y += 140
    for i, m in enumerate(s["maddeler"]):
        f = font(50, 700)
        pil_gen = 190
        sat = sar(m["baslik"], f, GEN - pil_gen - 70)
        lh = int(f.size * 1.2)
        h = max(130, lh * len(sat) + 56)
        k = kart(GEN, h, 22)
        d = ImageDraw.Draw(k)
        saat = m.get("saat") or "GÜN İÇİ"
        c = cip(saat, ACCENT if m.get("saat") else (70, 70, 78), (0, 0, 0) if m.get("saat") else INK,
                36 if m.get("saat") else 28)
        k.alpha_composite(c, (28, (h - c.height) // 2))
        ty = (h - lh * len(sat)) // 2 - 4
        for j, x in enumerate(sat):
            d.text((pil_gen + 40, ty + j * lh), x, font=f, fill=INK)
        o.append(Oge(k, SOL, y, 0.15 + i * 0.25))
        y += h + 22
    return o


def sahne_kapanis(s):
    o = []
    y = 400
    f = font(46, 600)
    sat = sar(s["uyari"], f, GEN)
    im = _tuval(GEN, len(sat) * 60 + 10)
    d = ImageDraw.Draw(im)
    for i, x in enumerate(sat):
        d.text((0, i * 60), x, font=f, fill=INK)
    o.append(Oge(im, SOL, y, 0))
    y += im.height + 70
    fs = sigdir(s["site"], GEN, 104, 900, 60)
    im = _tuval(GEN, int(fs.size * 1.3))
    ImageDraw.Draw(im).text((0, 0), s["site"], font=fs, fill=ACCENT)
    o.append(Oge(im, SOL - 4, y, 0.25))
    y += im.height + 10
    fa = font(48, 700)
    sat = sar(s["akademi"], fa, GEN)
    im = _tuval(GEN, len(sat) * 62 + 10)
    d = ImageDraw.Draw(im)
    for i, x in enumerate(sat):
        d.text((0, i * 62), x, font=fa, fill=INK)
    o.append(Oge(im, SOL, y, 0.45))
    y += im.height + 90
    bay = font(96, 900)
    im = _tuval(GEN, 120)
    ImageDraw.Draw(im).text((0, 0), "Bay bay.", font=bay, fill=INK)
    o.append(Oge(im, SOL - 4, y, 0.7))
    y += im.height + 20
    if s.get("not"):
        fn = font(28, 500)
        sat = sar(s["not"], fn, GEN)
        im = _tuval(GEN, len(sat) * 38 + 6)
        d = ImageDraw.Draw(im)
        for i, x in enumerate(sat):
            d.text((0, i * 38), x, font=fn, fill=MUTED)
        o.append(Oge(im, SOL, y, 0.9))
    return o


# --------------------------------------------------------------------------- #
# Altyazı
# --------------------------------------------------------------------------- #

ALTYAZI_Y = 1430            # blok dikey merkezi (alt %20 = y>1536 boş)
ALTYAZI_GEN = 820
ALTYAZI_MERKEZ = SOL + GEN // 2 + 20


def altyazi(kelimeler, aktif):
    """kelimeler: [str]; aktif: vurgulanan indeks (aksan rengi). Büyük harf, konturlu."""
    from .senaryo import tr_buyuk
    ks = [k if "." in k.strip(".") else tr_buyuk(k) for k in kelimeler]   # adres küçük harf kalır
    boyut = 84
    while True:
        f = font(boyut, 900, 100)
        bosluk = f.getlength(" ")
        satirlar, cur, cur_w = [], [], 0
        for i, k in enumerate(ks):
            kw = f.getlength(k)
            if cur and cur_w + bosluk + kw > ALTYAZI_GEN:
                satirlar.append(cur)
                cur, cur_w = [], 0
            cur_w += (bosluk if cur else 0) + kw
            cur.append(i)
        if cur:
            satirlar.append(cur)
        if len(satirlar) <= 2 or boyut <= 56:
            break
        boyut -= 4
    lh = int(boyut * 1.12)
    im = _tuval(W, lh * len(satirlar) + 40)
    d = ImageDraw.Draw(im)
    for si, sat in enumerate(satirlar):
        genis = sum(f.getlength(ks[i]) for i in sat) + bosluk * (len(sat) - 1)
        x = ALTYAZI_MERKEZ - genis / 2
        yy = 10 + si * lh
        for i in sat:
            renk = ACCENT if i == aktif else (255, 255, 255)
            d.text((x + 3, yy + 5), ks[i], font=f, fill=(0, 0, 0, 150))
            d.text((x, yy), ks[i], font=f, fill=renk, stroke_width=7, stroke_fill=(0, 0, 0))
            x += f.getlength(ks[i]) + bosluk
    return im
