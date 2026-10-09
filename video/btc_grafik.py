# -*- coding: utf-8 -*-
"""IG fragmanının kapanışındaki BTC günlük grafik kartı (Pillow ile doğrudan çizim).

Veri zinciri (hiçbiri fragmanı düşürmez):
  1. Coinbase Exchange public mumları (GitHub Actions ABD sunucularında Binance 451 verir)
  2. CoinGecko market_chart kapanışları -> çizgi grafik
  3. ikisi de olmazsa None: kapanışta grafik yok, boşluğu çağrı kaplar.

Çizim telefonda okunacak büyüklükte: başlık 44 px, etiketler ≥ 28 px (1080 genişlik),
az etiket (yalnız 30g en yüksek/düşük + ay adları), sitenin koyu paleti
(dogukanlive.com piyasa görünümü: 50g mor, 200g sarı, mumlar yeşil/kırmızı).
Sağ ~%35 bulanık + "Tamamı DM'de" kilidi.
"""
import os
import sys
from datetime import datetime, timezone

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from . import cizim as cz

COINBASE_URL = "https://api.exchange.coinbase.com/products/BTC-USD/candles"
COINGECKO_URL = "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart"
GUN = 300                     # çekilen gün (Coinbase üst sınırı; 200g ortalama 90 günün tamamında)
GORUNEN = 90                  # ekranda görünen gün (site ile aynı)
EN_AZ = 60                    # bundan az nokta: veri geçersiz
HTTP_SURE = 20

SMA50 = (124, 92, 255)        # #7c5cff
SMA200 = (240, 185, 11)       # #f0b90b
SEVIYE = (138, 138, 160)      # #8a8aa0
ETIKET = (200, 200, 212)
BULANIK_ORAN = 0.35
KILIT_METIN = "Tamamı DM'de"
AYLAR = ["Oca", "Şub", "Mar", "Nis", "May", "Haz", "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara"]
EMOJI_FONTLARI = [("/System/Library/Fonts/Apple Color Emoji.ttc", 160),
                  ("/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf", 109)]


def log(m):
    print(m, file=sys.stderr, flush=True)


def _http_getir(url, params=None, headers=None):
    import requests
    h = {"User-Agent": "crypto-daily-report/1.0"}
    h.update(headers or {})
    r = requests.get(url, params=params, headers=h, timeout=HTTP_SURE)
    r.raise_for_status()
    return r.json()


def coinbase_mumlari(getir=_http_getir):
    """-> [(gun_ts, acilis, yuksek, dusuk, kapanis)] eskiden yeniye."""
    ham = getir(COINBASE_URL, params={"granularity": 86400})
    mumlar = []
    for m in ham or []:
        t, dusuk, yuksek, acilis, kapanis = (float(x) for x in m[:5])   # [time, low, high, open, close, vol]
        mumlar.append((int(t), acilis, yuksek, dusuk, kapanis))
    mumlar.sort()
    if len(mumlar) < EN_AZ:
        raise ValueError(f"Coinbase: yalnız {len(mumlar)} mum")
    return mumlar[-GUN:]


def coingecko_kapanislari(getir=_http_getir):
    """-> [(gun_ts, kapanis)] eskiden yeniye (market_chart, günlük)."""
    anahtar = os.environ.get("COINGECKO_DEMO_API_KEY", "").strip()
    d = getir(COINGECKO_URL, params={"vs_currency": "usd", "days": GUN, "interval": "daily"},
              headers={"x-cg-demo-api-key": anahtar} if anahtar else None)
    nokta = sorted((int(ms // 1000), float(p)) for ms, p in (d or {}).get("prices") or [])
    if len(nokta) < EN_AZ:
        raise ValueError(f"CoinGecko: yalnız {len(nokta)} nokta")
    return nokta[-GUN:]


def veri_al(getir=_http_getir):
    """Coinbase -> CoinGecko -> None. Asla fırlatmaz.
    -> {"tur": "mum"|"cizgi", "kaynak", "zaman", "kapanis", "mumlar"?} ya da None."""
    try:
        m = coinbase_mumlari(getir)
        return {"tur": "mum", "kaynak": "Coinbase", "mumlar": m,
                "zaman": [x[0] for x in m], "kapanis": [x[4] for x in m]}
    except Exception as e:  # noqa: BLE001
        log(f"[grafik] Coinbase alınamadı, CoinGecko deneniyor: {str(e)[:200]}")
    try:
        k = coingecko_kapanislari(getir)
        return {"tur": "cizgi", "kaynak": "CoinGecko", "zaman": [x[0] for x in k], "kapanis": [x[1] for x in k]}
    except Exception as e:  # noqa: BLE001
        log(f"[grafik] CoinGecko da alınamadı, fragman grafiksiz: {str(e)[:200]}")
    return None


def sma(seri, n):
    out, top = [], 0.0
    for i, v in enumerate(seri):
        top += v
        if i >= n:
            top -= seri[i - n]
        out.append(top / n if i >= n - 1 else None)
    return out


def ozet(veri, gorunen=GORUNEN):
    """Görünen pencere + göstergeler (test edilebilir, çizimsiz)."""
    kap = veri["kapanis"]
    n = min(gorunen, len(kap))
    bas = len(kap) - n
    s50, s200 = sma(kap, 50)[bas:], sma(kap, 200)[bas:]
    if veri["tur"] == "mum":
        mum = veri["mumlar"][bas:]
        yuk = [x[2] for x in mum]
        dus = [x[3] for x in mum]
    else:
        mum = None
        yuk = dus = kap[bas:]
    son30 = slice(max(0, len(yuk) - 30), len(yuk))
    return {"zaman": veri["zaman"][bas:], "kapanis": kap[bas:], "mumlar": mum, "s50": s50, "s200": s200,
            "yuksek30": max(yuk[son30]), "dusuk30": min(dus[son30]),
            "ust": max(yuk), "alt": min(dus)}


# --------------------------------------------------------------------------- #
# Çizim
# --------------------------------------------------------------------------- #

def emoji(ch, boyut):
    """Renkli emoji (Apple / Noto); font yoksa None."""
    for yol, oz in EMOJI_FONTLARI:
        if not os.path.exists(yol):
            continue
        try:
            ef = ImageFont.truetype(yol, oz)
            e = Image.new("RGBA", (oz + oz // 4, oz + oz // 4), (0, 0, 0, 0))
            ImageDraw.Draw(e).text((0, 0), ch, font=ef, embedded_color=True)
            kutu = e.getbbox()
            if not kutu:
                continue
            e = e.crop(kutu)
            return e.resize((boyut, max(1, int(boyut * e.height / e.width))), Image.LANCZOS)
        except Exception:  # noqa: BLE001
            continue
    return None


def kilit_ikonu(boyut, renk):
    """Emoji fontu yoksa çizilmiş kilit."""
    s = 4
    im = Image.new("RGBA", (boyut * s, boyut * s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    B = boyut * s
    d.rounded_rectangle((B * .14, B * .44, B * .86, B * .98), radius=B * .1, fill=renk + (255,))
    d.arc((B * .26, B * .04, B * .74, B * .64), 180, 360, fill=renk + (255,), width=int(B * .11))
    d.line((B * .26 + B * .055, B * .34, B * .26 + B * .055, B * .46), fill=renk + (255,), width=int(B * .11))
    d.line((B * .74 - B * .055, B * .34, B * .74 - B * .055, B * .46), fill=renk + (255,), width=int(B * .11))
    return im.resize((boyut, boyut), Image.LANCZOS)


def _kesik(d, x0, x1, y, renk, w, parca=18, bosluk=12):
    x = x0
    while x < x1:
        d.line((x, y, min(x + parca, x1), y), fill=renk, width=w)
        x += parca + bosluk


def _fiyat(v):
    return "$" + f"{int(round(v)):,}".replace(",", ".")


def _cizgi(d, noktalar, renk, w):
    noktalar = [p for p in noktalar if p is not None]
    if len(noktalar) >= 2:
        d.line(noktalar, fill=renk, width=w, joint="curve")


def kart(veri, gen=cz.GEN, yuk=520):
    """Grafik kartı (RGBA). Hata -> None (fragman grafiksiz devam eder)."""
    try:
        return _kart(veri, gen, yuk)
    except Exception as e:  # noqa: BLE001
        log(f"[grafik] çizilemedi, fragman grafiksiz: {e}")
        return None


def _kart(veri, gen, yuk):
    o = ozet(veri)
    ic, bas_h, alt_h = 24, 78, 50
    pw, ph = gen - 2 * ic, yuk - bas_h - alt_h - ic
    S = 2                                        # 2x örnekle çiz, küçült (kenar yumuşatma)
    plot = Image.new("RGBA", (pw * S, ph * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(plot)
    ust = max([o["ust"]] + [v for v in o["s50"] + o["s200"] if v is not None])
    alt = min([o["alt"]] + [v for v in o["s50"] + o["s200"] if v is not None])
    pay = (ust - alt) * 0.08 or 1.0
    ust, alt = ust + pay * 1.6, alt - pay
    n = len(o["kapanis"])
    adim = pw * S / (n + 3)

    def X(i):
        return (i + 0.5) * adim

    def Y(v):
        return (ust - v) / (ust - alt) * ph * S

    for k in range(1, 4):                        # silik yatay ızgara
        d.line((0, ph * S * k / 4, pw * S, ph * S * k / 4), fill=(255, 255, 255, 14), width=S)
    for etk, v in (("30g en yüksek", o["yuksek30"]), ("30g en düşük", o["dusuk30"])):
        _kesik(d, 0, pw * S, Y(v), SEVIYE + (255,), 2 * S, 14 * S, 10 * S)
    if o["mumlar"]:
        gv = max(2, adim * 0.62)
        for i, (_, a, h, lo, c) in enumerate(o["mumlar"]):
            renk = (cz.UP if c >= a else cz.DOWN) + (255,)
            d.line((X(i), Y(h), X(i), Y(lo)), fill=renk, width=max(2, S + 1))
            y0, y1 = sorted((Y(a), Y(c)))
            d.rectangle((X(i) - gv / 2, y0, X(i) + gv / 2, max(y1, y0 + S)), fill=renk)
    else:
        _cizgi(d, [(X(i), Y(v)) for i, v in enumerate(o["kapanis"])], cz.INK + (255,), 3 * S)
    _cizgi(d, [(X(i), Y(v)) if v is not None else None for i, v in enumerate(o["s200"])], SMA200 + (255,), 3 * S)
    _cizgi(d, [(X(i), Y(v)) if v is not None else None for i, v in enumerate(o["s50"])], SMA50 + (255,), 3 * S)
    plot = plot.resize((pw, ph), Image.LANCZOS)

    # seviye etiketleri (solda, okunur: koyu zeminli)
    fe = cz.font(28, 700)
    dp = ImageDraw.Draw(plot)
    for etk, v, yukari in (("30g yüksek", o["yuksek30"], True), ("30g düşük", o["dusuk30"], False)):
        y = Y(v) / S
        yazi = f"{etk} {_fiyat(v)}"
        tw = fe.getlength(yazi)
        ty = y - 40 if yukari else y + 6
        ty = min(max(ty, 2), ph - 38)
        dp.rounded_rectangle((6, ty, 6 + tw + 20, ty + 36), radius=10, fill=(11, 11, 12, 200))
        dp.text((16, ty + 18), yazi, font=fe, fill=ETIKET, anchor="lm")

    # sağ %35 bulanık + kilit
    x0 = int(pw * (1 - BULANIK_ORAN))
    bul = plot.filter(ImageFilter.GaussianBlur(9))
    bul.alpha_composite(Image.new("RGBA", plot.size, (11, 11, 12, 70)))
    maske = Image.new("L", plot.size, 0)
    md = ImageDraw.Draw(maske)
    for x in range(x0 - 50, pw):
        md.line([(x, 0), (x, ph)], fill=int(255 * min(1, max(0, (x - x0 + 50) / 70))))
    plot = Image.composite(bul, plot, maske)
    fk = cz.font(36, 800)
    ik = emoji("\U0001F512", 40) or kilit_ikonu(36, cz.ACCENT)
    tw = fk.getlength(KILIT_METIN)
    eh = 66
    ew = int(24 + tw + 12 + ik.width + 24)
    et = Image.new("RGBA", (ew, eh), (0, 0, 0, 0))
    de = ImageDraw.Draw(et)
    de.rounded_rectangle((0, 0, ew - 1, eh - 1), radius=eh // 2, fill=(11, 11, 12, 235),
                         outline=cz.ACCENT + (255,), width=3)
    de.text((24, eh // 2), KILIT_METIN, font=fk, fill=cz.ACCENT, anchor="lm")
    et.alpha_composite(ik, (int(24 + tw + 12), (eh - ik.height) // 2))
    ex = min(pw - ew - 8, x0 + (pw - x0 - ew) // 2)
    plot.alpha_composite(et, (ex, int(ph * 0.42 - eh / 2)))

    # kart
    k = cz.kart(gen, yuk, 24, dolgu=(11, 11, 12, 232))
    d = ImageDraw.Draw(k)
    d.text((ic + 2, ic + 2), "BTC · günlük", font=cz.font(44, 800), fill=cz.INK)
    fl = cz.font(28, 600)
    lx = gen - ic
    for ad, renk in (("200g ort.", SMA200), ("50g ort.", SMA50)):
        lx -= fl.getlength(ad)
        d.text((lx, ic + 30), ad, font=fl, fill=ETIKET, anchor="lm")
        d.line((lx - 40, ic + 30, lx - 10, ic + 30), fill=renk, width=5)
        lx -= 40 + 28
    k.alpha_composite(plot, (ic, bas_h))
    # ay etiketleri (yalnız bulanık olmayan bölgede)
    fa = cz.font(28, 600)
    ay_y = bas_h + ph + 8
    onceki = None
    for i, t in enumerate(o["zaman"]):
        g = datetime.fromtimestamp(t, timezone.utc)
        if onceki is not None and g.month != onceki and X(i) / S < x0 - 60:
            d.text((ic + X(i) / S, ay_y), AYLAR[g.month - 1], font=fa, fill=cz.MUTED, anchor="ma")
        onceki = g.month
    fn = cz.font(22, 500)
    d.text((gen - ic, ay_y + 6), "Veri: " + veri["kaynak"], font=fn, fill=cz.MUTED, anchor="ra")
    return k
