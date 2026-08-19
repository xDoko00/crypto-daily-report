# -*- coding: utf-8 -*-
"""
Kanonik rapor JSON'undan çıktı üretir.
======================================

Tek girdi: sema.py'nin tanımladığı rapor dict'i.
Üç çıktı: Telegram HTML (brief + detay), sesli özet metni, kart verisi.

Biçimlendirme artık LLM'de değil burada. Kazancı: model formatı bozamaz,
Telegram etiketleri her zaman dengeli kapanır ve metinler HTML-escape'lenir
(model çıktısındaki & veya < karakteri mesajı düşürmez).
"""

import html

# Gündem maddesi önem derecesi → görsel işaret
ONEM_SIMGESI = {"kritik": "🔴", "onemli": "🟡", "bilgi": "🟢"}

# Telegram'ın iki bölümü ayırmakta kullandığı işaretçi (report.py bölüyor).
DETAY_AYRACI = "---DETAY---"


# --------------------------------------------------------------------------- #
# Biçimlendirme yardımcıları
# --------------------------------------------------------------------------- #

def _k(metin):
    """Telegram HTML'i için kaçış. Model metnindeki & < > mesajı bozmasın."""
    return html.escape(str(metin), quote=False)


def para(v):
    """USD fiyatı okunur biçimde: küçük fiyatlarda kuruş, büyüklerde tam sayı."""
    if v is None:
        return "doğrulanamadı"
    return f"${v:,.2f}" if v < 100 else f"${v:,.0f}"


def yuzde(v):
    """24 saatlik değişim: işaretli, iki hane."""
    return "n/a" if v is None else f"{v:+.2f}%"


def buyuk_usd(v):
    """Trilyon/milyar kısaltması (2.30T, 92.00B)."""
    if v is None:
        return "doğrulanamadı"
    if v >= 1e12:
        return f"${v / 1e12:.2f}T"
    if v >= 1e9:
        return f"${v / 1e9:.2f}B"
    return f"${v:,.0f}"


def _yuzde_alan(v):
    """Dominans gibi yüzde alanları: '%58.2'."""
    return f"%{v:.1f}" if v is not None else "doğrulanamadı"


def _zamanli(madde, ayrac=" — "):
    """{timeTr, title} → '15:30 — başlık' (saat yoksa yalnız başlık).

    Brief'te satır kısa kalsın diye ayraçsız ("15:30 başlık"), takvim
    listesinde okunaklı olsun diye tireli kullanılır."""
    saat = madde.get("timeTr")
    baslik = _k(madde["title"])
    return f"{saat}{ayrac}{baslik}" if saat else baslik


# --------------------------------------------------------------------------- #
# Telegram — BÖLÜM 1: 60 saniye
# --------------------------------------------------------------------------- #

def brief_html(rapor):
    """Bir dakikada okunan özet. Kart altyazısı olarak da kullanılır (<=1024 krk)."""
    p = rapor["market"]
    coin = p["coins"]
    fng = p["fearGreed"]

    fng_str = "doğrulanamadı"
    if fng.get("value") is not None:
        fng_str = str(fng["value"])
        if fng.get("previousValue") is not None:
            fng_str += f" (dün {fng['previousValue']})"

    btc = coin.get("BTC", {})
    eth = coin.get("ETH", {})

    kritik = rapor["brief"]["criticalEvents"]
    kritik_str = (" · ".join(_zamanli(e, " ") for e in kritik)
                  if kritik else "öne çıkan saat yok")

    satirlar = [
        f"📊 <b>GÜNAYDIN — {_k(rapor['title'])}</b>",
        "",
        "⚡ <b>60 SANİYE</b>",
        f"🌡️ Hava: {_k(rapor['brief']['mood'])} · F&amp;G {fng_str}",
        f"₿ BTC {para(btc.get('priceUsd'))} ({yuzde(btc.get('change24h'))})"
        f" · Ξ ETH {para(eth.get('priceUsd'))} ({yuzde(eth.get('change24h'))})",
        f"🔑 <b>Neden:</b> {_k(rapor['brief']['why'])}",
        f"⏰ <b>Kritik:</b> {kritik_str}",
        f"⚠️ <b>Risk:</b> {_k(rapor['brief']['mainRisk'])}",
    ]
    return "\n".join(satirlar)


# --------------------------------------------------------------------------- #
# Telegram — BÖLÜM 2: detay
# --------------------------------------------------------------------------- #

def detay_html(rapor):
    """İsteyen için uzun bölüm: piyasa tablosu, dünden, gündem, takvim, TR, riskler."""
    p = rapor["market"]
    b = rapor["sections"]
    parcalar = []

    # --- piyasa ---
    piyasa = ["📈 <b>PİYASA</b>"]
    for sembol, d in p["coins"].items():
        piyasa.append(f"{_k(sembol)} — {para(d.get('priceUsd'))} ({yuzde(d.get('change24h'))})")
    piyasa.append(
        f"Dominans: BTC {_yuzde_alan(p.get('btcDominance'))}"
        f" · ETH {_yuzde_alan(p.get('ethDominance'))}"
        f" — Hacim: {buyuk_usd(p.get('volume24hUsd'))}"
    )
    parcalar.append("\n".join(piyasa))

    # --- dünden (dünkü takip maddelerinin bugünkü sonucu) ---
    if b["yesterday"]:
        dunden = ["⏮️ <b>DÜNDEN</b>"]
        for m in b["yesterday"]:
            dunden.append(f"• {_k(m['item'])} → {_k(m['outcome'])}")
        parcalar.append("\n".join(dunden))

    # --- gündem: her madde kaynak linkli (şema kaynaksızını zaten geçirmez) ---
    gundem = ["📰 <b>GÜNDEM</b>"]
    for m in b["agenda"]:
        simge = ONEM_SIMGESI.get(m["importance"], "🟢")
        kaynak = m["source"]
        gundem.append(
            f"{simge} <b>{_k(m['title'])}</b> — {_k(m['summary'])} — "
            f"<a href=\"{_k(kaynak['url'])}\">{_k(kaynak.get('publisher') or 'kaynak')}</a>"
        )
    parcalar.append("\n".join(gundem))

    # --- bugün takipte ---
    if b["today"]:
        bugun = ["⏰ <b>BUGÜN TAKİPTE</b>"]
        for m in b["today"]:
            bugun.append(_zamanli(m))
        parcalar.append("\n".join(bugun))

    # --- türkiye ---
    tr = b["turkey"]
    if tr["hasNews"] and tr["items"]:
        tr_satir = ["🇹🇷 <b>TÜRKİYE</b>"]
        for m in tr["items"]:
            tr_satir.append(
                f"• <b>{_k(m['title'])}</b> — {_k(m['summary'])} — "
                f"<a href=\"{_k(m['source']['url'])}\">"
                f"{_k(m['source'].get('publisher') or 'kaynak')}</a>"
            )
        parcalar.append("\n".join(tr_satir))
    else:
        parcalar.append("🇹🇷 <b>TÜRKİYE</b> — Yeni gelişme yok.")

    # --- riskler ---
    if b["risks"]:
        riskler = ["⚠️ <b>RİSKLER</b>"]
        for r in b["risks"]:
            riskler.append(f"• {_k(r)}")
        parcalar.append("\n".join(riskler))

    parcalar.append(f"<i>{_k(rapor['disclaimer'])}</i>")
    return "\n\n".join(parcalar)


def telegram_html(rapor):
    """Brief + ayraç + detay — report.py bunu ---DETAY--- üzerinden bölüp gönderir."""
    return f"{brief_html(rapor)}\n{DETAY_AYRACI}\n{detay_html(rapor)}"


# --------------------------------------------------------------------------- #
# Sesli özet metni
# --------------------------------------------------------------------------- #

def seslendirme_metni(rapor):
    """45 saniyelik sesli özetin konuşma metni.

    Fiyatlar okunmaz (onlar kartta görsel); hava, neden, kritik saatler ve
    ana risk anlatılır."""
    b = rapor["brief"]
    parcalar = ["Günaydın.", rapor["title"] + "."]
    parcalar.append(f"Piyasa havası {b['mood']}.")
    parcalar.append(f"Nedeni: {b['why']}")
    if b["criticalEvents"]:
        olaylar = ", ".join(
            (f"{e['timeTr']} {e['title']}" if e.get("timeTr") else e["title"])
            for e in b["criticalEvents"]
        )
        parcalar.append(f"Bugün öne çıkan saatler: {olaylar}.")
    parcalar.append(f"Günün ana riski: {b['mainRisk']}")
    parcalar.append("Detaylar kanalda. Yatırım tavsiyesi değildir.")
    return " ".join(parcalar)


# --------------------------------------------------------------------------- #
# Kart verisi
# --------------------------------------------------------------------------- #

def kart_verisi(rapor):
    """kart.py'nin beklediği düz dict'e çevirir (o modül şemadan habersiz kalsın)."""
    p = rapor["market"]
    c = p["coins"]

    def _c(sembol):
        d = c.get(sembol, {})
        return {"fiyat": d.get("priceUsd"), "degisim": d.get("change24h")}

    fng = p["fearGreed"]
    return {
        "btc": _c("BTC"), "eth": _c("ETH"), "sol": _c("SOL"),
        "bnb": _c("BNB"), "xrp": _c("XRP"),
        "btc_dom": p.get("btcDominance"), "eth_dom": p.get("ethDominance"),
        "hacim": p.get("volume24hUsd"), "mcap": p.get("totalMarketCapUsd"),
        "fng_deger": fng.get("value"),
        "fng_etiket": fng.get("label") or "",
        "fng_dun": fng.get("previousValue"),
    }
