# -*- coding: utf-8 -*-
"""
Günlük raporu e-posta bültenine gönderir (Buttondown).
=======================================================

Kanonik rapor JSON'undan Markdown gövde üretir ve Buttondown API'sine
yollar. Telegram gönderimiyle aynı veriden beslenir — iki kanal arasında
içerik farkı olamaz.

Tasarım notu: Telegram HTML'i burada KULLANILMAZ. Telegram'ın etiket seti
dar (<b>, <i>, <a>) ve e-posta istemcilerinde farklı davranır. Buttondown
Markdown bekliyor, o yüzden ayrı bir renderer var.

Gönderim başarısız olursa rapor akışı DURMAZ — Telegram'a giden rapor
e-posta yüzünden engellenmemeli (brief §6.6).
"""

import json
import os
import urllib.error
import urllib.request

API = "https://api.buttondown.com/v1/emails"
SITE = "https://dogukanlive.com"

ONEM_ISARETI = {"kritik": "🔴", "onemli": "🟡", "bilgi": "🟢"}


def _para(v):
    if v is None:
        return "—"
    return f"${v:,.2f}" if v < 100 else f"${v:,.0f}"


def _yuzde(v):
    return "—" if v is None else f"{v:+.2f}%"


def _buyuk(v):
    if v is None:
        return "—"
    if v >= 1e12:
        return f"${v / 1e12:.2f}T"
    if v >= 1e9:
        return f"${v / 1e9:.2f}B"
    return f"${v:,.0f}"


def konu(rapor):
    """E-posta konu satırı. Hava ve BTC fiyatı, gelen kutusunda tek bakışta bilgi."""
    btc = (rapor["market"]["coins"].get("BTC") or {}).get("priceUsd")
    hava = rapor["brief"]["mood"]
    parca = f" · BTC {_para(btc)}" if btc is not None else ""
    return f"{rapor['title']} — {hava}{parca}"


def govde(rapor):
    """Raporu Markdown'a çevirir."""
    p = rapor["market"]
    b = rapor["brief"]
    s = rapor["sections"]
    tarih_id = rapor["id"]
    satir = []

    # --- 60 saniye ---
    fng = p.get("fearGreed", {})
    fng_str = "—"
    if fng.get("value") is not None:
        fng_str = str(fng["value"])
        if fng.get("label"):
            fng_str += f" ({fng['label']})"

    satir.append("## 60 saniye\n")
    satir.append(f"**Hava:** {b['mood']}  ")
    satir.append(f"**Korku & Açgözlülük:** {fng_str}\n")
    satir.append(f"**Neden:** {b['why']}\n")
    if b.get("criticalEvents"):
        satir.append("**Bugünün kritik saatleri:**\n")
        for e in b["criticalEvents"]:
            saat = f"**{e['timeTr']}** — " if e.get("timeTr") else ""
            satir.append(f"- {saat}{e['title']}")
        satir.append("")
    satir.append(f"**Günün ana riski:** {b['mainRisk']}\n")

    # --- piyasa ---
    satir.append("## Piyasa\n")
    satir.append("| Coin | Fiyat | 24s |")
    satir.append("|---|---|---|")
    for sembol, d in p["coins"].items():
        satir.append(f"| {sembol} | {_para(d.get('priceUsd'))} | {_yuzde(d.get('change24h'))} |")
    satir.append("")
    dom = "—"
    if p.get("btcDominance") is not None and p.get("ethDominance") is not None:
        dom = f"BTC %{p['btcDominance']:.1f} · ETH %{p['ethDominance']:.1f}"
    satir.append(f"Dominans: {dom} · 24s hacim: {_buyuk(p.get('volume24hUsd'))}\n")

    # --- dünden ---
    if s.get("yesterday"):
        satir.append("## Dünden hesap\n")
        satir.append("Dün \"takip edilecek\" dediklerimizin bugünkü sonucu:\n")
        for m in s["yesterday"]:
            satir.append(f"- **{m['item']}** → {m['outcome']}")
        satir.append("")

    # --- gündem ---
    satir.append("## Günün öne çıkan gelişmeleri\n")
    for m in s["agenda"]:
        isaret = ONEM_ISARETI.get(m["importance"], "🟢")
        kay = m["source"]
        satir.append(f"### {isaret} {m['title']}\n")
        satir.append(f"{m['summary']}\n")
        satir.append(f"[{kay.get('publisher') or 'Kaynak'}]({kay['url']})\n")

    # --- takvim ---
    if s.get("today"):
        satir.append("## Bugün takipte\n")
        satir.append("_Saatler TSİ._\n")
        for m in s["today"]:
            saat = f"**{m['timeTr']}** — " if m.get("timeTr") else ""
            satir.append(f"- {saat}{m['title']}")
        satir.append("")

    # --- türkiye ---
    tr = s.get("turkey", {})
    satir.append("## Türkiye\n")
    if tr.get("hasNews") and tr.get("items"):
        for m in tr["items"]:
            satir.append(f"**{m['title']}** — {m['summary']} "
                         f"[{m['source'].get('publisher') or 'Kaynak'}]({m['source']['url']})\n")
    else:
        satir.append("SPK, MKK, TCMB, BDDK ve mevzuat tarafında bugün yeni bir gelişme yok.\n")

    # --- riskler ---
    if s.get("risks"):
        satir.append("## Riskler\n")
        for r in s["risks"]:
            satir.append(f"- {r}")
        satir.append("")

    # --- yarın ---
    if rapor.get("followUps"):
        satir.append("## Yarın bunlara bakacağız\n")
        for t in rapor["followUps"]:
            satir.append(f"- {t}")
        satir.append("")

    satir.append("---\n")
    satir.append(f"[Raporun tam hâli ve kaynak listesi →]({SITE}/gunluk-raporlar/{tarih_id}/)\n")
    satir.append(f"Canlı fiyatlar: [{SITE}/piyasa]({SITE}/piyasa) · "
                 f"Hesaplayıcılar: [{SITE}/araclar/]({SITE}/araclar/)\n")
    satir.append(f"_{rapor.get('disclaimer', 'Yatırım tavsiyesi değildir.')}_")
    return "\n".join(satir)


def gonder(rapor, anahtar=None, taslak=False):
    """Raporu bültene gönderir. (basarili, mesaj) döndürür.

    taslak=True ise e-posta oluşturulur ama gönderilmez — test için."""
    anahtar = anahtar or os.environ.get("BUTTONDOWN_API_KEY", "")
    if not anahtar:
        return False, "BUTTONDOWN_API_KEY tanımlı değil, e-posta atlandı"

    veri = json.dumps({
        "subject": konu(rapor),
        "body": govde(rapor),
        "status": "draft" if taslak else "about_to_send",
    }).encode("utf-8")

    basliklar = {"Authorization": f"Token {anahtar}",
                 "Content-Type": "application/json"}
    if not taslak:
        # Buttondown, bir API anahtarıyla İLK gerçek gönderimde bu başlığı ister:
        # test ederken yanlışlıkla tüm listeye mail atılmasını engelleyen bir
        # emniyet kilidi. Bir kez onaylandıktan sonra da zararsız, göndermeye
        # devam ediyoruz — akış her sabah aynı yoldan geçiyor.
        basliklar["X-Buttondown-Live-Dangerously"] = "true"

    istek = urllib.request.Request(API, data=veri, headers=basliklar)
    try:
        with urllib.request.urlopen(istek, timeout=45) as c:
            d = json.load(c)
        return True, f"e-posta {'taslak' if taslak else 'gönderildi'} (id {d.get('id')})"
    except urllib.error.HTTPError as e:
        return False, f"Buttondown reddetti (HTTP {e.code}): {e.read()[:200].decode(errors='replace')}"
    except Exception as e:                            # noqa: BLE001
        return False, f"Buttondown'a ulaşılamadı: {e}"


if __name__ == "__main__":
    import sys
    r = json.load(open("reports/latest.json", encoding="utf-8"))
    if "--gonder" in sys.argv:
        print(gonder(r, taslak="--taslak" in sys.argv))
    else:
        print("KONU:", konu(r))
        print()
        print(govde(r))
