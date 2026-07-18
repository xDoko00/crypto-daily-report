# -*- coding: utf-8 -*-
"""Paylaşılabilir sabah kartı üretimi (Pillow). Ağ/LLM gerektirmez; verilerden çizer.
1080x1350 PNG döndürür — Instagram/WhatsApp için uygun."""
import io
import os
from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1350
M = 84  # kenar boşluğu

# Koyu premium tema
BG      = (13, 18, 27)
CARD    = (20, 28, 41)
INK     = (233, 238, 244)
MUTED   = (150, 162, 178)
ACCENT  = (241, 196, 15)   # #F1C40F
UP      = (52, 211, 153)
DOWN    = (245, 120, 124)
LINE    = (35, 45, 60)

_ADAY = {
    "bold": ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
             "C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf"],
    "reg":  ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
             "C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf"],
}


def _f(tip, boyut):
    for yol in _ADAY[tip]:
        if os.path.exists(yol):
            return ImageFont.truetype(yol, boyut)
    return ImageFont.load_default()


def _para(v):
    if v is None:
        return "—"
    if v >= 1000:
        return f"${v:,.0f}"
    if v >= 1:
        return f"${v:,.2f}"
    return f"${v:.4f}"


def _kisalt(v):
    if v is None:
        return "—"
    if v >= 1e12:
        return f"${v/1e12:.2f}T"
    if v >= 1e9:
        return f"${v/1e9:.1f}B"
    return f"${v:,.0f}"


def _fng_renk(deger):
    if deger is None:
        return MUTED
    if deger < 25:
        return DOWN
    if deger < 45:
        return (230, 150, 80)
    if deger < 55:
        return ACCENT
    if deger < 75:
        return (120, 200, 120)
    return UP


def _coin_satiri(d, y, ad, veri):
    """Bir coin bloğu: ad + fiyat solda, değişim çipi sağda."""
    fiyat = veri.get("fiyat")
    deg = veri.get("degisim")
    d.text((M, y), ad, font=_f("reg", 40), fill=MUTED)
    d.text((M, y + 46), _para(fiyat), font=_f("bold", 82), fill=INK)
    # değişim çipi (sağ)
    if deg is not None:
        renk = UP if deg >= 0 else DOWN
        ok = "▲" if deg >= 0 else "▼"
        metin = f"{ok} {abs(deg):.2f}%"
        fnt = _f("bold", 44)
        tw = d.textlength(metin, font=fnt)
        pad = 26
        x1 = W - M - tw - pad * 2
        y1 = y + 60
        d.rounded_rectangle([x1, y1, W - M, y1 + 74], radius=20,
                            fill=(renk[0], renk[1], renk[2], 40))
        d.text((x1 + pad, y1 + 14), metin, font=fnt, fill=renk)


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


def kart_olustur(veri, hava, risk, tarih):
    """PNG bytes döndürür. veri: piyasa dict; hava/risk: str; tarih: str."""
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img, "RGBA")

    # ---- üst şerit ----
    d.text((M, 74), "GÜNAYDIN KRİPTO", font=_f("bold", 40), fill=ACCENT)
    d.text((W - M, 82), "@DogukanLive", font=_f("reg", 30), fill=MUTED, anchor="ra")
    d.text((M, 128), tarih, font=_f("reg", 32), fill=MUTED)
    d.line([M, 196, W - M, 196], fill=LINE, width=2)

    # ---- BTC / ETH ----
    _coin_satiri(d, 236, "BITCOIN", veri.get("btc", {}))
    _coin_satiri(d, 404, "ETHEREUM", veri.get("eth", {}))
    d.line([M, 596, W - M, 596], fill=LINE, width=2)

    # ---- dominans + hacim (iki sütun) ----
    y = 640
    yarim = W // 2
    d.text((M, y), "DOMİNANS", font=_f("reg", 30), fill=MUTED)
    bd = veri.get("btc_dom"); ed = veri.get("eth_dom")
    dom = (f"BTC %{bd:.1f} · ETH %{ed:.1f}" if bd is not None and ed is not None else "—")
    d.text((M, y + 42), dom, font=_f("bold", 40), fill=INK)
    d.text((yarim + 30, y), "24S HACİM", font=_f("reg", 30), fill=MUTED)
    d.text((yarim + 30, y + 42), _kisalt(veri.get("hacim")), font=_f("bold", 40), fill=INK)

    # ---- Fear & Greed ----
    y = 786
    fng = veri.get("fng_deger")
    renk = _fng_renk(fng)
    d.text((M, y), "FEAR & GREED", font=_f("reg", 30), fill=MUTED)
    d.text((M, y + 40), (str(fng) if fng is not None else "—"), font=_f("bold", 96), fill=renk)
    etiket = veri.get("fng_etiket", "")
    d.text((M + 190, y + 92), etiket, font=_f("bold", 44), fill=renk)
    dun = veri.get("fng_dun")
    if dun is not None:
        d.text((M + 190, y + 52), f"dün {dun}", font=_f("reg", 30), fill=MUTED)

    # ---- Hava (mood) çipi ----
    hy = 786
    hfnt = _f("bold", 46)
    htxt = f"Hava: {hava}"
    tw = d.textlength(htxt, font=hfnt)
    d.rounded_rectangle([W - M - tw - 56, hy + 8, W - M, hy + 88], radius=22,
                        fill=(ACCENT[0], ACCENT[1], ACCENT[2], 34))
    d.text((W - M - tw - 28, hy + 22), htxt, font=hfnt, fill=ACCENT)

    # ---- Ana risk kutusu ----
    ry = 950
    d.rounded_rectangle([M, ry, W - M, ry + 210], radius=28, fill=CARD)
    # çizilmiş uyarı üçgeni (emoji font'ta olmadığı için)
    tx, ty, sz = M + 40, ry + 28, 30
    d.polygon([(tx, ty + sz), (tx + sz, ty + sz), (tx + sz / 2, ty)], fill=ACCENT)
    cx = tx + sz / 2
    d.rectangle([cx - 2, ty + 9, cx + 2, ty + sz - 9], fill=CARD)
    d.ellipse([cx - 2.5, ty + sz - 8, cx + 2.5, ty + sz - 3], fill=CARD)
    d.text((tx + sz + 16, ry + 30), "ANA RİSK", font=_f("bold", 32), fill=ACCENT)
    rfnt = _f("reg", 40)
    satirlar = _sar(d, risk, rfnt, W - 2 * M - 72)[:3]
    for i, s in enumerate(satirlar):
        d.text((M + 36, ry + 82 + i * 46), s, font=rfnt, fill=INK)

    # ---- footer ----
    d.line([M, H - 132, W - M, H - 132], fill=LINE, width=2)
    d.text((M, H - 104), "Yatırım tavsiyesi değildir", font=_f("reg", 30), fill=MUTED)

    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


if __name__ == "__main__":
    ornek = {
        "btc": {"fiyat": 64000, "degisim": -0.3},
        "eth": {"fiyat": 1840, "degisim": -1.8},
        "btc_dom": 56.4, "eth_dom": 9.8,
        "hacim": 6.68e10,
        "fng_deger": 27, "fng_etiket": "Korku", "fng_dun": 25,
    }
    from datetime import datetime
    from zoneinfo import ZoneInfo
    _AY = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz",
           "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
    _GN = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
    _n = datetime.now(ZoneInfo("Europe/Istanbul"))
    _tarih = f"{_n.day} {_AY[_n.month - 1]} {_n.year}, {_GN[_n.weekday()]}"
    png = kart_olustur(ornek, "Temkinli",
                       "TÜFE beklenti üstü gelirse risk iştahı düşer, sert satış görülebilir",
                       _tarih)
    open("kart_ornek.png", "wb").write(png)
    print("kart_ornek.png yazildi,", len(png), "byte")
