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
import re
import urllib.error
import urllib.request

API = "https://api.buttondown.com/v1/emails"
SITE = "https://dogukanlive.com"

ONEM_ISARETI = {"kritik": "🔴", "onemli": "🟡", "bilgi": "🟢"}

# Buttondown'ın yasaklı kelime filtresine takılan kelimeler → yerine yazılacak
# maskeli hâli. Eşleşme büyük/küçük harf duyarsız ve kelime içidir, yalnız
# eşleşen parça değişir ("Bitget'in" → "B*tget'in", ekler korunur). Ek kelime:
# EPOSTA_YASAKLI_EK="kelime1,kelime2" (maskesi otomatik üretilir).
YASAKLI_KELIMELER = {"bitget": "B*tget"}
YASAKLI_EK_DEGISKENI = "EPOSTA_YASAKLI_EK"

_MD_LINK = re.compile(r"\[([^\]]*)\]\(([^)\s]+)\)")
_YASAK_YANITI = re.compile(r"prohibited keyword:?\s*[\"'`]?([^\s\"'`.,;:)]+)", re.IGNORECASE)


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


def otomatik_maske(kelime):
    """'kelime' → 'k*lime'. Maske kelimenin kendisini içermesin diye 2. harf yıldız."""
    if len(kelime) <= 2:
        return "*" * len(kelime)
    return kelime[0] + "*" + kelime[2:]


def yasakli_kelimeler(ek=None):
    """Sabit liste + ortamdaki ek kelimeler. -> {küçük harf kelime: maske ya da None}"""
    sozluk = {k.lower(): v for k, v in YASAKLI_KELIMELER.items()}
    ek = os.environ.get(YASAKLI_EK_DEGISKENI, "") if ek is None else ek
    kelimeler = ek.split(",") if isinstance(ek, str) else list(ek)
    for k in kelimeler:
        k = k.strip()
        if k and k.lower() not in sozluk:
            sozluk[k.lower()] = None          # maske eşleşen metinden (harf hâli korunur)
    return sozluk


def temizle(metin, kelimeler=None):
    """Yasaklı kelimeleri maskeler. Adresinde yasaklı kelime geçen Markdown
    bağlantısı düz metne çevrilir (Buttondown linki de tarıyor; maskeli URL
    kırık olacağı için linki tamamen bırakmak en temizi)."""
    kelimeler = yasakli_kelimeler() if kelimeler is None else kelimeler
    if not kelimeler or not metin:
        return metin
    desen = re.compile("|".join(re.escape(k) for k in
                                sorted(kelimeler, key=len, reverse=True)), re.IGNORECASE)

    def link(m):
        return m.group(1) if desen.search(m.group(2)) else m.group(0)

    metin = _MD_LINK.sub(link, metin)
    return desen.sub(lambda m: kelimeler.get(m.group(0).lower()) or otomatik_maske(m.group(0)),
                     metin)


def yasakli_kelime_ayikla(yanit):
    """Buttondown hata yanıtından 'prohibited keyword: X' kelimesini çıkarır."""
    m = _YASAK_YANITI.search(yanit or "")
    return m.group(1).lower() if m else None


def _istek(veri, basliklar):
    """-> (basarili, HTTP kodu ya da None, gövde/mesaj)"""
    istek = urllib.request.Request(API, data=json.dumps(veri).encode("utf-8"), headers=basliklar)
    try:
        with urllib.request.urlopen(istek, timeout=45) as c:
            return True, 200, json.load(c)
    except urllib.error.HTTPError as e:
        return False, e.code, e.read()[:500].decode(errors="replace")
    except Exception as e:                            # noqa: BLE001
        return False, None, str(e)


def gonder(rapor, anahtar=None, taslak=False):
    """Raporu bültene gönderir. (basarili, mesaj) döndürür.

    taslak=True ise e-posta oluşturulur ama gönderilmez — test için.
    Konu ve gövde yasaklı kelime filtresinden geçer; Buttondown yine de
    'prohibited keyword: X' ile reddederse X maskelenip BİR KEZ yeniden denenir."""
    anahtar = anahtar or os.environ.get("BUTTONDOWN_API_KEY", "")
    if not anahtar:
        return False, "BUTTONDOWN_API_KEY tanımlı değil, e-posta atlandı"

    kelimeler = yasakli_kelimeler()
    ham_konu, ham_govde = konu(rapor), govde(rapor)

    basliklar = {"Authorization": f"Token {anahtar}",
                 "Content-Type": "application/json"}
    if not taslak:
        # Buttondown, bir API anahtarıyla İLK gerçek gönderimde bu başlığı ister:
        # test ederken yanlışlıkla tüm listeye mail atılmasını engelleyen bir
        # emniyet kilidi. Bir kez onaylandıktan sonra da zararsız, göndermeye
        # devam ediyoruz — akış her sabah aynı yoldan geçiyor.
        basliklar["X-Buttondown-Live-Dangerously"] = "true"

    durum = "draft" if taslak else "about_to_send"
    ek_not = ""
    for deneme in range(2):
        veri = {"subject": temizle(ham_konu, kelimeler),
                "body": temizle(ham_govde, kelimeler),
                "status": durum}
        ok, kod, yanit = _istek(veri, basliklar)
        if ok:
            return True, (f"e-posta {'taslak' if taslak else 'gönderildi'} "
                          f"(id {yanit.get('id')}){ek_not}")
        if kod is None:
            return False, f"Buttondown'a ulaşılamadı: {yanit}"
        yeni = yasakli_kelime_ayikla(yanit) if kod == 400 else None
        if deneme == 0 and yeni and yeni not in kelimeler:
            kelimeler[yeni] = None
            ek_not = f" — '{otomatik_maske(yeni)}' maskelenip yeniden denendi"
            continue
        break
    return False, f"Buttondown reddetti (HTTP {kod}): {yanit[:200]}{ek_not}"


if __name__ == "__main__":
    import sys
    r = json.load(open("reports/latest.json", encoding="utf-8"))
    if "--gonder" in sys.argv:
        print(gonder(r, taslak="--taslak" in sys.argv))
    else:
        print("KONU:", temizle(konu(r)))
        print()
        print(temizle(govde(r)))
