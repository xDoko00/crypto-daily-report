# -*- coding: utf-8 -*-
"""Paylaşılabilir sabah kartı (Pillow). Ağ/LLM gerektirmez; rapor verisinden çizer.

1080x1350 (4:5) PNG döndürür. Kanalda günde tek gönderinin görseli budur.

Tasarımlar (KART_TASARIM ortam değişkeni ya da tasarim= argümanı):
  sari    (varsayılan) sarı zemin, siyah BTC kartı, yatay F&G çubuğu,
          2x2 coin kartı. Telefon akışında en okunur ve en dikkat çekici
          (11 Kas 2026 karşılaştırması).
  vitrin  koyu zemin, sarı marka rozeti, dev BTC fiyatı,
          yarım daire Fear & Greed göstergesi, 4 coin mini kartı
  serit   koyu zemin, BTC + F&G halkası yan yana, coin satırları, risk kutusu
  klasik  10 Kas 2026 öncesi kart (geri dönüş için)

Yazı tipi: repo içindeki fonts/Montserrat-VF.ttf (OFL). Bulunamazsa DejaVu,
o da yoksa Pillow varsayılanı. Türkçe karakterler Montserrat'ta tam.
Kural: em tire yok, kâr vaadi/sinyal/fiyat tahmini yazısı yok.
"""
import io
import math
import os
from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1350
M = 84  # kenar boşluğu

KOK = os.path.dirname(os.path.abspath(__file__))
FONT_VF = os.path.join(KOK, "fonts", "Montserrat-VF.ttf")
VARSAYILAN_TASARIM = "sari"
TASARIMLAR = ("vitrin", "sari", "serit", "klasik")

# Doğukan Live kimliği: sarı + siyah
SIYAH   = (10, 10, 11)
KOYU    = (24, 24, 27)
KOYU2   = (38, 38, 43)
SARI    = (255, 212, 0)
BEYAZ   = (246, 246, 242)
GRI     = (150, 150, 158)
CIZGI   = (44, 44, 50)
YESIL   = (38, 208, 124)
KIRMIZI = (255, 77, 94)
TURUNCU = (255, 140, 50)
ACIK_YESIL = (150, 210, 70)

# Klasik tema (eski kart)
BG      = (13, 18, 27)
CARD    = (20, 28, 41)
INK     = (233, 238, 244)
MUTED   = (150, 162, 178)
ACCENT  = (241, 196, 15)
UP      = (52, 211, 153)
DOWN    = (245, 120, 124)
LINE    = (35, 45, 60)

_ADAY = {
    "bold": ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
             "C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf"],
    "reg":  ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
             "C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf"],
}
_ONBELLEK = {}


def _f(tip, boyut):
    """Font. tip: 'bold'/'reg' ya da Montserrat ağırlığı (100-900)."""
    agirlik = int({"bold": 800, "reg": 500}.get(tip, tip))
    anahtar = (agirlik, boyut)
    if anahtar in _ONBELLEK:
        return _ONBELLEK[anahtar]
    fnt = None
    if os.path.exists(FONT_VF):
        try:
            fnt = ImageFont.truetype(FONT_VF, boyut)
            fnt.set_variation_by_axes([agirlik])
        except Exception:                            # noqa: BLE001
            fnt = None
    if fnt is None:
        for yol in _ADAY["bold" if agirlik >= 600 else "reg"]:
            if os.path.exists(yol):
                fnt = ImageFont.truetype(yol, boyut)
                break
    if fnt is None:
        fnt = ImageFont.load_default()
    _ONBELLEK[anahtar] = fnt
    return fnt


# --------------------------------------------------------------------------- #
# Biçim yardımcıları
# --------------------------------------------------------------------------- #

def _para(v):
    if v is None:
        return "n/a"
    if v >= 1000:
        return f"${v:,.0f}"
    if v >= 1:
        return f"${v:,.2f}"
    return f"${v:.4f}"


def _kisalt(v):
    if v is None:
        return "n/a"
    if v >= 1e12:
        return f"${v/1e12:.2f}T"
    if v >= 1e9:
        return f"${v/1e9:.1f}B"
    return f"${v:,.0f}"


def _yuzde(deg):
    return "n/a" if deg is None else f"%{abs(deg):.2f}"


def _yon_renk(deg):
    if deg is None:
        return GRI
    return YESIL if deg >= 0 else KIRMIZI


def _fng_renk(deger, tema="yeni"):
    if deger is None:
        return GRI if tema == "yeni" else MUTED
    if deger < 25:
        return KIRMIZI if tema == "yeni" else DOWN
    if deger < 45:
        return TURUNCU
    if deger < 55:
        return SARI if tema == "yeni" else ACCENT
    if deger < 75:
        return ACIK_YESIL
    return YESIL if tema == "yeni" else UP


def _ok(d, x, y, boy, yukari, renk):
    """Yukarı/aşağı üçgen (font glifine güvenmeden). (x, y) sol üst."""
    if yukari:
        d.polygon([(x, y + boy), (x + boy, y + boy), (x + boy / 2, y)], fill=renk)
    else:
        d.polygon([(x, y), (x + boy, y), (x + boy / 2, y + boy)], fill=renk)


def _degisim_yaz(d, x, y, deg, boyut, hiza="sol", renk=None):
    """Üçgen + yüzde (ör. ▼ %1.18). Genişliği döndürür."""
    renk = renk or _yon_renk(deg)
    fnt = _f(800, boyut)
    metin = _yuzde(deg)
    ok = int(boyut * 0.62) if deg is not None else 0
    bosluk = int(boyut * 0.28) if deg is not None else 0
    gen = ok + bosluk + d.textlength(metin, font=fnt)
    if hiza == "sag":
        x = x - gen
    if deg is not None:
        _ok(d, x, y + boyut * 0.30, ok, deg >= 0, renk)
    d.text((x + ok + bosluk, y), metin, font=fnt, fill=renk)
    return gen


def _sigdir(d, metin, agirlik, boyut, max_gen, en_kucuk=20):
    """Metni max genişliğe sığana kadar küçültür; font döndürür."""
    while boyut > en_kucuk and d.textlength(metin, font=_f(agirlik, boyut)) > max_gen:
        boyut -= 2
    return _f(agirlik, boyut)


def _sar(d, metin, font, max_gen):
    """Metni max genişliğe göre satırlara böler."""
    kelimeler = metin.split()
    satirlar, cur = [], ""
    for k in kelimeler:
        dene = (cur + " " + k).strip()
        if d.textlength(dene, font=font) <= max_gen:
            cur = dene
        else:
            if cur:
                satirlar.append(cur)
            cur = k
    if cur:
        satirlar.append(cur)
    return satirlar


def _satir_kirp(d, satirlar, font, max_gen, adet):
    """En çok `adet` satır; taşarsa son satır '...' ile biter."""
    if len(satirlar) <= adet:
        return satirlar
    son = satirlar[adet - 1]
    while son and d.textlength(son + "...", font=font) > max_gen:
        son = son.rsplit(" ", 1)[0] if " " in son else son[:-1]
    return satirlar[:adet - 1] + [son.rstrip(" ,;:") + "..."]


def _tr_buyuk(metin):
    """Türkçe büyük harf: i -> İ, ı -> I ('Temkinli' -> 'TEMKİNLİ')."""
    return metin.replace("i", "İ").replace("ı", "I").upper()


def _coinler(veri):
    return [(ad, veri.get(k) or {}) for ad, k in
            (("ETH", "eth"), ("SOL", "sol"), ("BNB", "bnb"), ("XRP", "xrp"))
            if veri.get(k)]


def _marka(d, x, y, boyut=30, zemin=SARI, yazi=SIYAH):
    """'DOĞUKAN LIVE' rozeti. Genişliği döndürür."""
    fnt = _f(900, boyut)
    metin = "DOĞUKAN LIVE"
    tw = d.textlength(metin, font=fnt)
    px, py = int(boyut * 0.55), int(boyut * 0.38)
    d.rounded_rectangle([x, y, x + tw + 2 * px, y + boyut + 2 * py], radius=int(boyut * 0.35),
                        fill=zemin)
    d.text((x + px, y + py + boyut * 0.5), metin, font=fnt, fill=yazi, anchor="lm")
    return tw + 2 * px


def _marka_gen(boyut):
    d = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    return d.textlength("DOĞUKAN LIVE", font=_f(900, boyut)) + 2 * int(boyut * 0.55)


# --------------------------------------------------------------------------- #
# Göstergeler (kenar yumuşatma için 4x çizilip küçültülür)
# --------------------------------------------------------------------------- #

_FNG_BOLGE = [(0, 25, KIRMIZI), (25, 45, TURUNCU), (45, 55, SARI),
              (55, 75, ACIK_YESIL), (75, 100, YESIL)]


def _bolge_aktif(a, b, deger):
    return deger is not None and (a <= deger < b or (deger >= 100 and b == 100))


def _yarim_gosterge(img, cx, cy, r, kalinlik, deger, zemin):
    """Yarım daire F&G göstergesi + değer işaretçisi. (cx, cy) yay merkezi."""
    S = 4
    dis = r + kalinlik // 2
    w, h = (dis + 12) * 2 * S, (dis + 24) * S
    kat = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    k = ImageDraw.Draw(kat)
    ox, oy = w // 2, (dis + 12) * S
    R = dis * S
    for a, b, renk in _FNG_BOLGE:
        bas = 180 + a * 1.8 + (1.0 if a else 0)
        son = 180 + b * 1.8 - (1.0 if b < 100 else 0)
        alfa = 255 if _bolge_aktif(a, b, deger) else 80
        k.arc([ox - R, oy - R, ox + R, oy + R], bas, son, fill=renk + (alfa,),
              width=kalinlik * S)
    if deger is not None:
        aci = math.radians(180 + max(0, min(100, deger)) * 1.8)
        rm = (dis - kalinlik / 2) * S
        mx, my = ox + rm * math.cos(aci), oy + rm * math.sin(aci)
        rr = (kalinlik / 2 + 9) * S
        k.ellipse([mx - rr, my - rr, mx + rr, my + rr], fill=zemin + (255,))
        rr2 = (kalinlik / 2 + 2) * S
        k.ellipse([mx - rr2, my - rr2, mx + rr2, my + rr2], fill=BEYAZ + (255,))
        rr3 = (kalinlik / 2 - 5) * S
        k.ellipse([mx - rr3, my - rr3, mx + rr3, my + rr3], fill=_fng_renk(deger) + (255,))
    kat = kat.resize((w // S, h // S), Image.LANCZOS)
    img.paste(kat, (cx - dis - 12, cy - dis - 12), kat)


def _halka(img, cx, cy, r, kalinlik, deger, zemin_renk):
    """Tam halka F&G göstergesi (0-100)."""
    S = 4
    w = (r + kalinlik) * 2 * S
    kat = Image.new("RGBA", (w, w), (0, 0, 0, 0))
    k = ImageDraw.Draw(kat)
    o = w // 2
    R = r * S
    k.arc([o - R, o - R, o + R, o + R], 0, 360, fill=zemin_renk + (255,), width=kalinlik * S)
    if deger:
        k.arc([o - R, o - R, o + R, o + R], -90, -90 + 360 * max(0, min(100, deger)) / 100,
              fill=_fng_renk(deger) + (255,), width=kalinlik * S)
    kat = kat.resize((w // S, w // S), Image.LANCZOS)
    img.paste(kat, (cx - w // S // 2, cy - w // S // 2), kat)


def _yatay_gosterge(img, x, y, gen, yuk, deger, iz=None):
    """Yatay F&G çubuğu (5 bölge) + işaretçi."""
    S = 4
    kat = Image.new("RGBA", ((gen + 40) * S, (yuk + 40) * S), (0, 0, 0, 0))
    k = ImageDraw.Draw(kat)
    ox, oy = 20 * S, 20 * S
    if iz:
        p = 7 * S
        k.rounded_rectangle([ox - p, oy - p, ox + gen * S + p, oy + yuk * S + p],
                            radius=(yuk * S + 2 * p) // 2, fill=iz + (255,))
    for a, b, renk in _FNG_BOLGE:
        x1 = ox + int(gen * S * a / 100) + (3 * S if a else 0)
        x2 = ox + int(gen * S * b / 100) - (3 * S if b < 100 else 0)
        k.rounded_rectangle([x1, oy, x2, oy + yuk * S], radius=yuk * S // 2, fill=renk + (255,))
    if deger is not None:
        mx = ox + int(gen * S * max(0, min(100, deger)) / 100)
        orta = oy + yuk * S // 2
        rr = int(yuk * 0.95) * S
        k.ellipse([mx - rr, orta - rr, mx + rr, orta + rr], fill=SIYAH + (255,))
        rr2 = rr - 6 * S
        k.ellipse([mx - rr2, orta - rr2, mx + rr2, orta + rr2], fill=BEYAZ + (255,))
        rr3 = rr - 14 * S
        k.ellipse([mx - rr3, orta - rr3, mx + rr3, orta + rr3], fill=_fng_renk(deger) + (255,))
    kat = kat.resize((gen + 40, yuk + 40), Image.LANCZOS)
    img.paste(kat, (x - 20, y - 20), kat)


def _alt_bilgi(d, y, renk_yazi, renk_cizgi, renk_site):
    d.line([M, y, W - M, y], fill=renk_cizgi, width=2)
    d.text((M, y + 30), "dogukanlive.com", font=_f(700, 30), fill=renk_site)
    d.text((W - M, y + 36), "Bilgilendirme amaçlıdır, yatırım tavsiyesi değildir",
           font=_f(500, 22), fill=renk_yazi, anchor="ra")


def _baslik(d, x, y, tarih, boyut, renk_selam, renk_nokta, renk_tarih, max_x):
    """'Günaydın · <tarih>' tek satır; sığmazsa tarih küçülür."""
    fs = _f(800, boyut)
    d.text((x, y), "Günaydın", font=fs, fill=renk_selam)
    gx = x + d.textlength("Günaydın", font=fs)
    orta = y + boyut * 0.62
    r = max(4, int(boyut * 0.07))
    nx = gx + boyut * 0.36
    d.ellipse([nx - r, orta - r, nx + r, orta + r], fill=renk_nokta)
    tx = nx + boyut * 0.34
    d.text((tx, orta), tarih, font=_sigdir(d, tarih, 600, int(boyut * 0.5), max_x - tx),
           fill=renk_tarih, anchor="lm")


# --------------------------------------------------------------------------- #
# Tasarım: VİTRİN
# --------------------------------------------------------------------------- #

def _vitrin(veri, hava, risk, tarih):
    img = Image.new("RGB", (W, H), SIYAH)
    d = ImageDraw.Draw(img, "RGBA")
    sol, sag = M - 24, W - M + 24

    _marka(d, M, 60, 28)
    d.text((W - M, 60 + 25), "t.me/DogukanLive", font=_f(600, 26), fill=GRI, anchor="rm")
    _baslik(d, M, 150, tarih, 76, BEYAZ, SARI, GRI, W - M)

    # BTC kahraman kartı
    btc = veri.get("btc") or {}
    deg = btc.get("degisim")
    yk, yb = 290, 620
    d.rounded_rectangle([sol, yk, sag, yb], radius=36, fill=KOYU)
    d.text((M + 20, yk + 40), "BITCOIN", font=_f(800, 34), fill=SARI)
    fiyat = _para(btc.get("fiyat"))
    d.text((M + 12, yk + 214), fiyat, font=_sigdir(d, fiyat, 900, 160, W - 2 * M - 30),
           fill=BEYAZ, anchor="ls")
    renk = _yon_renk(deg)
    cy = yk + 256
    gen = d.textlength(_yuzde(deg), font=_f(800, 42)) + (42 if deg is not None else 0)
    d.rounded_rectangle([M + 20, cy, M + 20 + gen + 56, cy + 64], radius=32, fill=renk + (46,))
    _degisim_yaz(d, M + 48, cy + 8, deg, 42)
    d.text((sag - 36, cy + 32), "son 24 saat", font=_f(500, 28), fill=GRI, anchor="rm")

    # F&G (sol) + hava/dominans (sağ)
    fy, fb = 650, 990
    fx2 = 560
    d.rounded_rectangle([sol, fy, fx2, fb], radius=36, fill=KOYU)
    fng = veri.get("fng_deger")
    gx = (sol + fx2) // 2
    d.text((gx, fy + 44), "KORKU & AÇGÖZLÜLÜK", font=_f(800, 24), fill=GRI, anchor="ms")
    _yarim_gosterge(img, gx, fy + 250, 150, 28, fng, KOYU)
    d.text((gx, fy + 246), str(fng) if fng is not None else "n/a", font=_f(900, 84),
           fill=BEYAZ, anchor="ms")
    etiket = veri.get("fng_etiket") or ""
    dun = veri.get("fng_dun")
    d.text((gx, fy + 294), etiket, font=_f(800, 36), fill=_fng_renk(fng), anchor="ms")
    if dun is not None:
        d.text((gx, fb - 16), f"dün {dun}", font=_f(600, 24), fill=GRI, anchor="ms")

    sx = 584
    d.rounded_rectangle([sx, fy, sag, fy + 160], radius=36, fill=SARI)
    d.text((sx + 32, fy + 34), "PİYASA HAVASI", font=_f(800, 24), fill=(80, 66, 0))
    hv = hava or "n/a"
    d.text((sx + 32, fy + 72), hv, font=_sigdir(d, hv, 900, 54, sag - sx - 64), fill=SIYAH)
    d.rounded_rectangle([sx, fy + 180, sag, fb], radius=36, fill=KOYU)
    bd = veri.get("btc_dom")
    d.text((sx + 32, fy + 214), "BTC DOMİNANS", font=_f(800, 24), fill=GRI)
    d.text((sx + 32, fy + 252), f"%{bd:.1f}" if bd is not None else "n/a",
           font=_f(900, 54), fill=BEYAZ)

    # mini coin kartları (1x4)
    coinler = _coinler(veri)
    my, mh = 1020, 196
    if coinler:
        bosluk = 18
        kg = (sag - sol - bosluk * (len(coinler) - 1)) / len(coinler)
        for i, (ad, c) in enumerate(coinler):
            x1 = sol + i * (kg + bosluk)
            d.rounded_rectangle([x1, my, x1 + kg, my + mh], radius=28, fill=KOYU)
            d.text((x1 + 26, my + 26), ad, font=_f(800, 30), fill=SARI)
            fy_ = _para(c.get("fiyat"))
            d.text((x1 + 26, my + 74), fy_, font=_sigdir(d, fy_, 800, 40, kg - 44), fill=BEYAZ)
            _degisim_yaz(d, x1 + 26, my + 134, c.get("degisim"), 30)

    _alt_bilgi(d, H - 108, GRI, CIZGI, SARI)
    return img


# --------------------------------------------------------------------------- #
# Tasarım: SARI (varsayılan, marka zemini)
# --------------------------------------------------------------------------- #

def _sari(veri, hava, risk, tarih):
    img = Image.new("RGB", (W, H), SARI)
    d = ImageDraw.Draw(img, "RGBA")
    koyu_yazi = (70, 58, 0)
    sol, sag = M - 30, W - M + 30

    _marka(d, M, 60, 26, zemin=SIYAH, yazi=SARI)
    d.text((W - M, 60 + 24), "t.me/DogukanLive", font=_f(700, 26), fill=koyu_yazi, anchor="rm")
    d.text((M, 136), "Günaydın", font=_f(900, 96), fill=SIYAH)
    d.text((M, 252), tarih, font=_sigdir(d, tarih, 700, 40, W - 2 * M), fill=koyu_yazi)

    btc = veri.get("btc") or {}
    deg = btc.get("degisim")
    yk, yb = 326, 656
    d.rounded_rectangle([sol, yk, sag, yb], radius=44, fill=SIYAH)
    d.text((M + 14, yk + 34), "BITCOIN", font=_f(800, 36), fill=SARI)
    fiyat = _para(btc.get("fiyat"))
    d.text((M + 8, yk + 226), fiyat, font=_sigdir(d, fiyat, 900, 156, W - 2 * M - 20),
           fill=BEYAZ, anchor="ls")
    _degisim_yaz(d, M + 14, yk + 258, deg, 48)
    d.text((W - M - 10, yk + 276), "son 24 saat", font=_f(600, 28), fill=GRI, anchor="ra")

    fng = veri.get("fng_deger")
    fy = 690
    d.text((M, fy + 6), "KORKU & AÇGÖZLÜLÜK", font=_f(800, 28), fill=koyu_yazi)
    deger_s = (f"{fng} · {veri.get('fng_etiket') or ''}".strip(" ·")
               if fng is not None else "n/a")
    d.text((W - M, fy - 4), deger_s, font=_f(900, 44), fill=SIYAH, anchor="ra")
    _yatay_gosterge(img, M, fy + 72, W - 2 * M, 26, fng, iz=SIYAH)
    dun = veri.get("fng_dun")
    alt = f"dün {dun}" if dun is not None else ""
    if hava:
        alt = (alt + "  ·  " if alt else "") + f"Piyasa havası: {hava}"
    d.text((M, fy + 120), alt, font=_f(700, 32), fill=koyu_yazi)

    coinler = _coinler(veri)
    gy = 870
    b = 20
    kg, kh = (sag - sol - b) / 2, 168
    for i, (ad, c) in enumerate(coinler[:4]):
        sx = sol + (i % 2) * (kg + b)
        sy = gy + (i // 2) * (kh + b)
        d.rounded_rectangle([sx, sy, sx + kg, sy + kh], radius=32, fill=SIYAH)
        d.text((sx + 32, sy + 26), ad, font=_f(800, 34), fill=SARI)
        _degisim_yaz(d, sx + kg - 32, sy + 26, c.get("degisim"), 34, hiza="sag")
        fy_ = _para(c.get("fiyat"))
        d.text((sx + 32, sy + 76), fy_, font=_sigdir(d, fy_, 900, 60, kg - 64), fill=BEYAZ)

    _alt_bilgi(d, H - 100, koyu_yazi, (215, 178, 0), SIYAH)
    return img


# --------------------------------------------------------------------------- #
# Tasarım: ŞERİT (halka + coin satırları + risk)
# --------------------------------------------------------------------------- #

def _serit(veri, hava, risk, tarih):
    img = Image.new("RGB", (W, H), SIYAH)
    d = ImageDraw.Draw(img, "RGBA")
    d.rectangle([0, 0, W, 14], fill=SARI)

    _marka(d, M, 54, 26)
    d.text((W - M, 54 + 24), "t.me/DogukanLive", font=_f(600, 26), fill=GRI, anchor="rm")
    _baslik(d, M, 136, tarih, 66, SARI, BEYAZ, BEYAZ, W - M)

    btc = veri.get("btc") or {}
    deg = btc.get("degisim")
    by = 270
    d.text((M, by), "BITCOIN", font=_f(800, 32), fill=GRI)
    fiyat = _para(btc.get("fiyat"))
    d.text((M - 4, by + 170), fiyat, font=_sigdir(d, fiyat, 900, 128, 600), fill=BEYAZ,
           anchor="ls")
    _degisim_yaz(d, M, by + 200, deg, 52)

    fng = veri.get("fng_deger")
    hx, hy, hr = W - M - 120, by + 120, 100
    _halka(img, hx, hy, hr, 22, fng, KOYU2)
    d.text((hx, hy + 4), str(fng) if fng is not None else "n/a", font=_f(900, 70),
           fill=BEYAZ, anchor="mm")
    d.text((hx, hy + 150), _tr_buyuk(veri.get("fng_etiket") or ""), font=_f(800, 28),
           fill=_fng_renk(fng), anchor="mm")
    d.text((hx, hy + 186), "Korku & Açgözlülük", font=_f(500, 22), fill=GRI, anchor="mm")

    ly = 610
    d.line([M, ly, W - M, ly], fill=CIZGI, width=2)
    for i, (ad, c) in enumerate(_coinler(veri)[:4]):
        y = ly + i * 92
        d.text((M, y + 46), ad, font=_f(800, 40), fill=SARI, anchor="lm")
        d.text((M + 190, y + 46), _para(c.get("fiyat")), font=_f(800, 44), fill=BEYAZ,
               anchor="lm")
        _degisim_yaz(d, W - M, y + 27, c.get("degisim"), 38, hiza="sag")
        d.line([M, y + 92, W - M, y + 92], fill=CIZGI, width=2)

    ry = 1010
    d.rounded_rectangle([M - 20, ry, W - M + 20, ry + 196], radius=30, fill=KOYU)
    d.text((M + 14, ry + 28), f"HAVA: {_tr_buyuk(hava or 'n/a')}", font=_f(900, 28), fill=SARI)
    d.text((M + 14, ry + 70), "Günün riski", font=_f(700, 24), fill=GRI)
    rf = _f(600, 30)
    satirlar = _satir_kirp(d, _sar(d, risk or "", rf, W - 2 * M - 30), rf, W - 2 * M - 30, 2)
    for i, s in enumerate(satirlar):
        d.text((M + 14, ry + 106 + i * 40), s, font=rf, fill=BEYAZ)

    _alt_bilgi(d, H - 108, GRI, CIZGI, SARI)
    return img


# --------------------------------------------------------------------------- #
# Tasarım: KLASİK (eski kart, düzen değişmedi)
# --------------------------------------------------------------------------- #

def _klasik_f(tip, boyut):
    for yol in _ADAY[tip]:
        if os.path.exists(yol):
            return ImageFont.truetype(yol, boyut)
    return _f(tip, boyut)


def _klasik_coin(d, y, ad, veri):
    fiyat = veri.get("fiyat")
    deg = veri.get("degisim")
    d.text((M, y), ad, font=_klasik_f("reg", 40), fill=MUTED)
    d.text((M, y + 46), _para(fiyat), font=_klasik_f("bold", 82), fill=INK)
    if deg is not None:
        renk = UP if deg >= 0 else DOWN
        ok = "▲" if deg >= 0 else "▼"
        metin = f"{ok} {abs(deg):.2f}%"
        fnt = _klasik_f("bold", 44)
        tw = d.textlength(metin, font=fnt)
        pad = 26
        x1 = W - M - tw - pad * 2
        y1 = y + 60
        d.rounded_rectangle([x1, y1, W - M, y1 + 74], radius=20,
                            fill=(renk[0], renk[1], renk[2], 40))
        d.text((x1 + pad, y1 + 14), metin, font=fnt, fill=renk)


def _klasik(veri, hava, risk, tarih):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img, "RGBA")
    f = _klasik_f
    d.text((M, 74), "GÜNAYDIN KRİPTO", font=f("bold", 40), fill=ACCENT)
    d.text((W - M, 82), "@DogukanLive", font=f("reg", 30), fill=MUTED, anchor="ra")
    d.text((M, 128), tarih, font=f("reg", 32), fill=MUTED)
    d.line([M, 196, W - M, 196], fill=LINE, width=2)
    _klasik_coin(d, 236, "BITCOIN", veri.get("btc", {}))
    _klasik_coin(d, 404, "ETHEREUM", veri.get("eth", {}))
    d.line([M, 596, W - M, 596], fill=LINE, width=2)
    y = 640
    yarim = W // 2
    d.text((M, y), "DOMİNANS", font=f("reg", 30), fill=MUTED)
    bd = veri.get("btc_dom")
    ed = veri.get("eth_dom")
    dom = (f"BTC %{bd:.1f} · ETH %{ed:.1f}" if bd is not None and ed is not None else "n/a")
    d.text((M, y + 42), dom, font=f("bold", 40), fill=INK)
    d.text((yarim + 30, y), "24S HACİM", font=f("reg", 30), fill=MUTED)
    d.text((yarim + 30, y + 42), _kisalt(veri.get("hacim")), font=f("bold", 40), fill=INK)
    y = 786
    fng = veri.get("fng_deger")
    renk = _fng_renk(fng, tema="klasik")
    d.text((M, y), "FEAR & GREED", font=f("reg", 30), fill=MUTED)
    d.text((M, y + 40), (str(fng) if fng is not None else "n/a"), font=f("bold", 96), fill=renk)
    d.text((M + 190, y + 92), veri.get("fng_etiket", ""), font=f("bold", 44), fill=renk)
    dun = veri.get("fng_dun")
    if dun is not None:
        d.text((M + 190, y + 52), f"dün {dun}", font=f("reg", 30), fill=MUTED)
    hfnt = f("bold", 46)
    htxt = f"Hava: {hava}"
    tw = d.textlength(htxt, font=hfnt)
    d.rounded_rectangle([W - M - tw - 56, 794, W - M, 874], radius=22,
                        fill=(ACCENT[0], ACCENT[1], ACCENT[2], 34))
    d.text((W - M - tw - 28, 808), htxt, font=hfnt, fill=ACCENT)
    ry = 950
    d.rounded_rectangle([M, ry, W - M, ry + 210], radius=28, fill=CARD)
    tx, ty, sz = M + 40, ry + 28, 30
    d.polygon([(tx, ty + sz), (tx + sz, ty + sz), (tx + sz / 2, ty)], fill=ACCENT)
    d.text((tx + sz + 16, ry + 30), "ANA RİSK", font=f("bold", 32), fill=ACCENT)
    rfnt = f("reg", 40)
    for i, s in enumerate(_sar(d, risk, rfnt, W - 2 * M - 72)[:3]):
        d.text((M + 36, ry + 82 + i * 46), s, font=rfnt, fill=INK)
    d.line([M, H - 132, W - M, H - 132], fill=LINE, width=2)
    d.text((M, H - 104), "Yatırım tavsiyesi değildir", font=f("reg", 30), fill=MUTED)
    return img


_CIZICI = {"vitrin": _vitrin, "sari": _sari, "serit": _serit, "klasik": _klasik}


def tasarim_sec(tasarim=None):
    """Argüman > KART_TASARIM ortam değişkeni > varsayılan. Bilinmeyen ad varsayılana düşer."""
    ad = (tasarim or os.environ.get("KART_TASARIM") or VARSAYILAN_TASARIM).strip().lower()
    return ad if ad in _CIZICI else VARSAYILAN_TASARIM


def kart_olustur(veri, hava, risk, tarih, tasarim=None):
    """PNG bytes döndürür. veri: render.kart_verisi(); hava/risk/tarih: str."""
    img = _CIZICI[tasarim_sec(tasarim)](veri or {}, hava or "", risk or "", tarih or "")
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()


if __name__ == "__main__":
    # Kuru üretim: python kart.py [rapor.json] [çıktı_klasörü]  (gönderim YOK)
    import json
    import sys
    import render
    yol = sys.argv[1] if len(sys.argv) > 1 else os.path.join(KOK, "reports", "latest.json")
    hedef = sys.argv[2] if len(sys.argv) > 2 else "."
    with open(yol, encoding="utf-8") as fh:
        rapor = json.load(fh)
    os.makedirs(hedef, exist_ok=True)
    for ad in TASARIMLAR:
        png = kart_olustur(render.kart_verisi(rapor), rapor["brief"]["mood"],
                           rapor["brief"]["mainRisk"], rapor["title"], tasarim=ad)
        cikti = os.path.join(hedef, f"kart_{ad}.png")
        with open(cikti, "wb") as fh:
            fh.write(png)
        print(cikti, len(png), "byte")
