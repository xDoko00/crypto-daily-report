#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Günlük Kripto Raporu → kanonik JSON → Telegram + web sitesi
============================================================

Dört adımda çalışır:
  Adım 1  Sabit piyasa verilerini ücretsiz API'lerden çeker (LLM YOK).
  Adım 2  Headless Claude Code (claude -p) ile haber/analiz bölümünü
          ŞEMALI JSON olarak üretir; şema doğrulamasından geçmeyen çıktı
          düzeltme isteğiyle yeniden istenir.
  Adım 3  İkisini tek kanonik rapora birleştirip şemaya göre doğrular.
  Adım 4  Aynı JSON'dan Telegram mesajını, kartı ve sesli özeti üretir;
          raporu reports/ altına yazar ve gönderir.

Kritik tasarım kuralı: fiyat/dominans/hacim/Fear&Greed gibi sayılar YALNIZCA
API'den gelir ve JSON'a Python tarafından yazılır — model bu alanlara hiç
dokunmaz. Model yalnız metin/analiz üretir ve her gündem maddesinde kaynak
URL'i vermek zorundadır (şema kaynaksızını reddeder).

Kullanım:
  python report.py            → Raporu kanala (TELEGRAM_CHAT_ID) gönderir.
  python report.py --test     → Raporu SADECE admin'e (TELEGRAM_ADMIN_CHAT_ID) gönderir.
  python report.py --onizleme → Sadece admin'e; [TEST] etiketi yok, gerçek rapor görünümü.

Kimlik doğrulama ve gizli anahtarlar ortam değişkenlerinden okunur (koda gömülmez):
  CLAUDE_CODE_OAUTH_TOKEN     → Claude aboneliği token'ı (claude setup-token çıktısı)
  TELEGRAM_BOT_TOKEN          → BotFather'dan alınan bot token'ı
  TELEGRAM_CHAT_ID            → Raporun gideceği kanal
  TELEGRAM_ADMIN_CHAT_ID      → Senin özel chat'in (hata bildirimleri + test)
  BUTTONDOWN_API_KEY          → E-posta bülteni (isteğe bağlı; yoksa e-posta atlanır)
"""

import os
import sys
import time
import html
import json
import re
import shutil
import subprocess
import tempfile
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

import render
import sema

# --------------------------------------------------------------------------- #
# Sabitler
# --------------------------------------------------------------------------- #

def _env_yukle():
    """Yanında bir .env dosyası varsa değişkenleri ortama yükler (yerel test için).
    GitHub Actions'ta .env olmaz; değişkenler zaten secret'lardan gelir."""
    yol = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(yol):
        return
    with open(yol, encoding="utf-8") as f:
        for satir in f:
            satir = satir.strip()
            if not satir or satir.startswith("#") or "=" not in satir:
                continue
            anahtar, _, deger = satir.partition("=")
            # Ortamda zaten tanımlıysa üzerine yazma (secret'lar önceliklidir)
            os.environ.setdefault(anahtar.strip(), deger.strip())


_env_yukle()

IST = ZoneInfo("Europe/Istanbul")          # Tüm tarih/saatler İstanbul saatiyle
__imza__ = "DogukanLive"                    # gizli imza — aracın kökeni
TELEGRAM_LIMIT = 4096                        # Telegram tek mesaj karakter limiti
SAFE_LIMIT = 3800                            # HTML tag'leri için güvenli tampon bırakıyoruz
HTTP_TIMEOUT = 30                            # API çağrıları için saniye
MAX_RETRY = 3                                # Ağ hatalarında deneme sayısı
CLAUDE_TIMEOUT = 600                         # Claude Code üretimi için üst sınır (saniye)

# İzlenecek coin'ler: CoinGecko id -> gösterim adı (sembol)
COINS = {
    "bitcoin":     "BTC",
    "ethereum":    "ETH",
    "solana":      "SOL",
    "binancecoin": "BNB",
    "ripple":      "XRP",
}

# Türkçe ay ve gün adları (tarih başlığı için)
TR_AYLAR = [
    "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
    "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık",
]
TR_GUNLER = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]


# RAPOR PROMPTU — Adım 2'de headless Claude Code'a verilir.
# {market_data} çalışma anında doldurulur.
#
# Model artık Telegram HTML'i değil, YAPILANDIRILMIŞ JSON üretiyor. Biçim
# (emoji, <b>, satır düzeni) render.py'nin işi; modelin işi yalnız içerik.
RAPOR_PROMPTU = """Sen günlük kripto piyasa raporu hazırlayan, sabahları işe çıkmadan piyasayı 1 dakikada özetleyen bir analistsin. Web araması yaparak SON 24 SAATİN gelişmelerini araştır ve sonucu TEK BİR JSON nesnesi olarak ver.

SANA VERİLEN PİYASA VERİLERİ (yorumlarken kullan, JSON'a YAZMA — sistemde zaten var):
{market_data}
Bu sayıları kendin arama, değiştirme, uydurma. JSON çıktısında hiçbir fiyat/dominans/hacim/Fear&Greed alanı OLMAYACAK.

ÇIKTI BİÇİMİ — çok önemli:
Yanıtın SADECE geçerli bir JSON nesnesi olsun. Açıklama cümlesi, başlık, markdown kod bloğu işareti YAZMA. İlk karakter { olsun, son karakter } olsun.

Şu yapıya harfiyen uy:

{
  "brief": {
    "mood": "Temkinli",
    "why": "Piyasa son 24 saatte NEDEN böyle hareket etti — en önemli sebep, 1-2 cümle",
    "criticalEvents": [{"timeTr": "15:30", "title": "ABD TÜFE verisi"}],
    "mainRisk": "Günün ana riski, tek cümle"
  },
  "sections": {
    "yesterday": [{"item": "dünkü takip maddesi", "outcome": "bugünkü sonucu — isabet mi ıska mı belli olsun"}],
    "agenda": [
      {"importance": "kritik",
       "title": "Gelişmenin kısa başlığı",
       "summary": "1-2 cümle: ne oldu ve neden önemli",
       "source": {"url": "https://...", "title": "Haberin başlığı", "publisher": "Reuters"}}
    ],
    "today": [{"timeTr": "14:00", "title": "Takip edilecek olay"}],
    "turkey": {"hasNews": false, "items": []},
    "risks": ["Kısa risk maddesi"]
  },
  "followUps": ["Yarın sonucuna bakılacak ölçülebilir madde"]
}

ALAN KURALLARI:
- "mood": tam olarak şu dörtten biri — Temkinli, İyimser, Kararsız, Riskli.
- "why": en kritik alan. Hareketin gerçek sebebini araştır; net tek sebep yoksa "belirgin tek sebep yok" diye başla.
- "criticalEvents": bugünün en önemli 2-3 olayı. Bunlar tek satırda yan yana dizilecek, o yüzden "title" ÇOK KISA olmalı — en fazla 60 karakter, parantez içi açıklama yok (ör. "Fed tutanakları", "Beyaz Saray kripto zirvesi"). "timeTr" TSİ ve HH:MM biçiminde; saat belli değilse null yaz.
- "yesterday": aşağıda "dünkü takip maddeleri" verildiyse her biri için bir kayıt. Verilmediyse boş dizi [].
- "agenda": son 24 saatin en önemli 3 gelişmesi (en az 1, en fazla 5). "importance" yalnız şu üçünden biri: kritik, onemli, bilgi.
- "source": HER gündem maddesinde ZORUNLU. Gerçekten okuduğun, https ile başlayan, erişilebilir bir sayfa olmalı; tercihen birincil/kurumsal kaynak. URL'deki utm_ parametrelerini temizle. Kaynağını doğrulayamadığın gelişmeyi HİÇ YAZMA — eksik madde, uydurma kaynaktan iyidir.
- "today": gün içinde takip edilecek olaylar, zaman sıralı, en fazla 8.
- "turkey": SPK, MKK, TCMB, BDDK veya mevzuatta YENİ gelişme varsa "hasNews": true ve maddeleri kaynaklarıyla yaz. Yoksa "hasNews": false ve "items": []. Asla uydurma.
- "risks": en fazla 2-3 kısa madde.
- "followUps": bugün öne çıkan, YARIN sonucuna bakılacak 2-4 madde. Her biri kısa ve sonucu ölçülebilir olsun (ör. "ABD TÜFE verisi beklentiyi aştı mı").

İÇERİK KURALLARI:
- Al/sat/tut önerisi, fiyat hedefi, garanti veya kesin tahmin verme.
- Uydurma metrik (100 üzerinden puan, güven skoru) kullanma.
- Doğrulayamadığın hiçbir bilgiyi yazma.
- Metin alanlarında HTML etiketi, markdown veya emoji KULLANMA — düz Türkçe metin yaz. Biçimlendirmeyi sistem yapıyor.
- Metinler kısa ve yoğun olsun; "summary" 1-2 cümleyi geçmesin."""


# --------------------------------------------------------------------------- #
# Yardımcı: ağ isteği için retry sarmalayıcı
# --------------------------------------------------------------------------- #

def _get_json(url, params=None):
    """Verilen URL'den JSON çeker; ağ hatalarında MAX_RETRY kez dener."""
    last_err = None
    for deneme in range(1, MAX_RETRY + 1):
        try:
            r = requests.get(url, params=params, timeout=HTTP_TIMEOUT,
                             headers={"User-Agent": "crypto-daily-report/1.0"})
            r.raise_for_status()
            return r.json()
        except Exception as e:                       # noqa: BLE001 (her ağ hatasını yakala)
            last_err = e
            print(f"[uyarı] İstek başarısız ({deneme}/{MAX_RETRY}): {url} -> {e}",
                  file=sys.stderr)
            if deneme < MAX_RETRY:
                time.sleep(2 * deneme)               # kademeli bekleme
    raise RuntimeError(f"API çağrısı {MAX_RETRY} denemede başarısız: {url} ({last_err})")


# --------------------------------------------------------------------------- #
# Adım 1 — Sabit piyasa verileri (LLM KULLANMADAN)
# --------------------------------------------------------------------------- #

def piyasa_verilerini_cek():
    """
    CoinGecko + Alternative.me'den ham sayıları çeker ve LLM'e verilecek
    okunabilir bir metin bloğu üretir. LLM bu sayıları asla değiştirmez.
    """
    # 1a) Coin fiyatları + 24s değişim
    fiyatlar = _get_json(
        "https://api.coingecko.com/api/v3/simple/price",
        params={
            "ids": ",".join(COINS.keys()),
            "vs_currencies": "usd",
            "include_24hr_change": "true",
        },
    )

    # 1b) Global piyasa: toplam market cap, hacim, dominans
    glob = _get_json("https://api.coingecko.com/api/v3/global").get("data", {})
    toplam_mcap = glob.get("total_market_cap", {}).get("usd")
    toplam_hacim = glob.get("total_volume", {}).get("usd")
    dom = glob.get("market_cap_percentage", {})
    btc_dom = dom.get("btc")
    eth_dom = dom.get("eth")

    # 1c) Fear & Greed endeksi (bugün, dün, 7 gün önce)
    fng_veri = _get_json("https://api.alternative.me/fng/", params={"limit": 8}).get("data", [])

    def fng_at(i):
        """i. indeksteki F&G kaydını 'değer (etiket)' biçiminde döndürür."""
        if len(fng_veri) > i and fng_veri[i]:
            return f"{fng_veri[i].get('value')} ({fng_veri[i].get('value_classification')})"
        return "doğrulanamadı"

    fng_bugun = fng_at(0)
    fng_dun = fng_at(1)
    fng_7gun = fng_at(7)

    # --- LLM'e verilecek okunabilir metin bloğunu kur ---
    satirlar = ["Coin fiyatları (USD, 24s değişim):"]
    for cg_id, sembol in COINS.items():
        d = fiyatlar.get(cg_id, {})
        fiyat = d.get("usd")
        degisim = d.get("usd_24h_change")
        if fiyat is None:
            satirlar.append(f"  {sembol}: doğrulanamadı")
        else:
            fiyat_str = f"${fiyat:,.2f}" if fiyat < 100 else f"${fiyat:,.0f}"
            degisim_str = f"{degisim:+.2f}%" if degisim is not None else "n/a"
            satirlar.append(f"  {sembol}: {fiyat_str} ({degisim_str})")

    def usd_kisalt(v):
        """Büyük USD tutarını T/B (trilyon/milyar) biçiminde kısaltır."""
        if v is None:
            return "doğrulanamadı"
        if v >= 1e12:
            return f"${v / 1e12:.2f}T"
        if v >= 1e9:
            return f"${v / 1e9:.2f}B"
        return f"${v:,.0f}"

    satirlar.append("")
    satirlar.append(f"Toplam piyasa değeri: {usd_kisalt(toplam_mcap)}")
    satirlar.append(f"24s toplam hacim: {usd_kisalt(toplam_hacim)}")
    satirlar.append(
        "BTC dominansı: "
        + (f"{btc_dom:.1f}%" if btc_dom is not None else "doğrulanamadı")
    )
    satirlar.append(
        "ETH dominansı: "
        + (f"{eth_dom:.1f}%" if eth_dom is not None else "doğrulanamadı")
    )
    satirlar.append("")
    satirlar.append(f"Fear & Greed — bugün: {fng_bugun} | dün: {fng_dun} | 7 gün önce: {fng_7gun}")

    # --- Kanonik rapordaki "market" bloğu ---
    # Bu blok doğrudan JSON'a gider; modelin eline hiç geçmez. Web sitesi,
    # kart ve Telegram aynı sayıları buradan okur.
    _ETIKET_TR = {"Extreme Fear": "Aşırı Korku", "Fear": "Korku", "Neutral": "Nötr",
                  "Greed": "Açgözlülük", "Extreme Greed": "Aşırı Açgözlülük"}

    def _iint(v):
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    def _coin(cg_id):
        cd = fiyatlar.get(cg_id, {})
        return {"priceUsd": cd.get("usd"), "change24h": cd.get("usd_24h_change")}

    _f0 = fng_veri[0] if fng_veri else {}
    _f1 = fng_veri[1] if len(fng_veri) > 1 else {}
    _f7 = fng_veri[7] if len(fng_veri) > 7 else {}

    market = {
        "asOf": sema.simdi_iso(datetime.now(IST)),
        "coins": {sembol: _coin(cg_id) for cg_id, sembol in COINS.items()},
        "btcDominance": btc_dom,
        "ethDominance": eth_dom,
        "totalMarketCapUsd": toplam_mcap,
        "volume24hUsd": toplam_hacim,
        "fearGreed": {
            "value": _iint(_f0.get("value")),
            "label": _ETIKET_TR.get(_f0.get("value_classification"),
                                    _f0.get("value_classification")) or None,
            "previousValue": _iint(_f1.get("value")),
            "weekAgoValue": _iint(_f7.get("value")),
        },
    }

    return "\n".join(satirlar), market


# --------------------------------------------------------------------------- #
# Adım 2 — Headless Claude Code ile haber/analiz üretimi
# --------------------------------------------------------------------------- #

def tarih_basligi():
    """Bugünün tarihini '17 Temmuz 2026, Perşembe' biçiminde döndürür (TSİ)."""
    now = datetime.now(IST)
    return f"{now.day} {TR_AYLAR[now.month - 1]} {now.year}, {TR_GUNLER[now.weekday()]}"


def _claude_calistir(prompt):
    """Headless Claude Code'u (claude -p) bir kez çağırıp düz metin çıktısını döndürür.

    Anthropic API KEY kullanmaz; kimlik doğrulama CLAUDE_CODE_OAUTH_TOKEN ile
    abonelikten yapılır. Sadece WebSearch/WebFetch araçlarına izin verilir."""
    # Windows'ta npm 'claude' (bash script) + 'claude.cmd' üretir; subprocess ancak
    # .cmd/.exe çalıştırabilir. Bu yüzden platforma göre uygun olanı seç.
    adaylar = ["claude.cmd", "claude.exe", "claude"] if os.name == "nt" else ["claude"]
    claude_bin = next((shutil.which(a) for a in adaylar if shutil.which(a)), None)
    if not claude_bin:
        raise RuntimeError(
            "'claude' komutu bulunamadı. Kurulum: npm install -g @anthropic-ai/claude-code"
        )
    komut = [
        claude_bin,
        "-p", prompt,
        "--allowedTools", "WebSearch", "WebFetch",
        "--output-format", "text",
    ]
    try:
        sonuc = subprocess.run(
            komut, capture_output=True, text=True,
            encoding="utf-8", timeout=CLAUDE_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"{CLAUDE_TIMEOUT} sn'de yanıt yok") from None

    if sonuc.returncode != 0:
        raise RuntimeError("kod %d: %s" % (
            sonuc.returncode,
            (sonuc.stderr.strip() or sonuc.stdout.strip() or "(çıktı boş)")[:600]))
    cikti = (sonuc.stdout or "").strip()
    if len(cikti) < 200:
        raise RuntimeError("beklenenden kısa çıktı: %r" % cikti)
    return cikti


def json_ayikla(cikti):
    """Model çıktısındaki JSON nesnesini ayıklar.

    `claude -p` bazen JSON'un önüne bir cümle ya da ```json çiti koyabiliyor.
    İlk '{' ile son '}' arasını alıp ayrıştırıyoruz; böylece çevresindeki
    gürültü raporu düşürmüyor."""
    metin = cikti.strip()
    if "```" in metin:
        # ```json ... ``` çitinin içini al
        m = re.search(r"```(?:json)?\s*(.*?)```", metin, re.S)
        if m:
            metin = m.group(1).strip()
    bas, son = metin.find("{"), metin.rfind("}")
    if bas == -1 or son <= bas:
        raise ValueError("çıktıda JSON nesnesi bulunamadı: %r" % cikti[:200])
    return json.loads(metin[bas:son + 1])


def llm_ciktisi_uret(market_data, dun_takip):
    """Modelden şemaya uyan JSON alır; uymazsa hatayı söyleyip düzeltmesini ister.

    08:00 raporu tek şansa çalıştığı için üç katmanlı savunma var:
      1) Ağ/CLI hatasında yeniden dene (kademeli bekleme).
      2) JSON ayrıştırılamazsa veya şema tutmazsa, hatayı prompt'a ekleyip
         modelin kendi çıktısını düzeltmesini iste.
      3) Hepsi tükenirse RuntimeError — main() admin'e bildirir."""
    if not os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
        print("[uyarı] CLAUDE_CODE_OAUTH_TOKEN yok; mevcut yerel claude oturumu "
              "kullanılacak (CI'da secret gereklidir).", file=sys.stderr)

    temel = RAPOR_PROMPTU.replace("{market_data}", market_data)
    if dun_takip:
        temel += chr(10) * 2 + ("DÜNKÜ TAKİP MADDELERİ (sections.yesterday için "
                                "sonuçlarını araştır): ") + "; ".join(dun_takip)
    else:
        temel += chr(10) * 2 + 'DÜNKÜ TAKİP MADDELERİ: yok (sections.yesterday boş dizi olsun).'

    print("[bilgi] Claude Code raporu üretiyor (web araması yapılıyor)...", file=sys.stderr)
    prompt = temel
    son_hata = None
    for deneme in range(1, MAX_RETRY + 1):
        try:
            cikti = _claude_calistir(prompt)
            veri = json_ayikla(cikti)
            sema.dogrula_llm_ciktisi(veri)
            return veri
        except (RuntimeError, ValueError, sema.RaporSemaHatasi) as e:
            son_hata = str(e)
            print(f"[uyarı] Rapor üretimi başarısız ({deneme}/{MAX_RETRY}): {son_hata[:300]}",
                  file=sys.stderr)
            # Biçim/şema hatasıysa modele ne yanlış yaptığını söyleyip tekrar sor.
            if isinstance(e, (ValueError, sema.RaporSemaHatasi)):
                prompt = (temel + chr(10) * 2
                          + "ÖNCEKİ DENEMEN GEÇERSİZDİ. Hata: " + son_hata[:500]
                          + chr(10) + "Bu hatayı düzelt ve SADECE geçerli JSON döndür.")
            if deneme < MAX_RETRY:
                time.sleep(8 * deneme)

    raise RuntimeError(f"Claude Code {MAX_RETRY} denemede geçerli rapor üretemedi: {son_hata}")


# --------------------------------------------------------------------------- #
# Adım 4 — Telegram'a gönderim
# --------------------------------------------------------------------------- #

def mesaji_bol(metin, limit=SAFE_LIMIT):
    """
    Uzun raporu, bölüm sınırlarını mümkün olduğunca koruyarak <limit karakterlik
    parçalara böler. Önce paragraf (çift satır), gerekirse satır, en son
    zorunlu olarak karakter bazında böler.
    """
    if len(metin) <= limit:
        return [metin]

    parcalar = []
    tampon = ""

    def akit():
        nonlocal tampon
        if tampon.strip():
            parcalar.append(tampon.strip())
        tampon = ""

    for paragraf in metin.split("\n\n"):
        # Paragraf tek başına limitten büyükse satır bazında böl
        if len(paragraf) > limit:
            akit()
            for satir in paragraf.split("\n"):
                while len(satir) > limit:
                    parcalar.append(satir[:limit])
                    satir = satir[limit:]
                if len(tampon) + len(satir) + 1 > limit:
                    akit()
                tampon = (tampon + "\n" + satir) if tampon else satir
            continue

        # Normal durum: paragrafı tampona ekle, taşarsa akıt
        if len(tampon) + len(paragraf) + 2 > limit:
            akit()
        tampon = (tampon + "\n\n" + paragraf) if tampon else paragraf

    akit()
    return parcalar


def _html_temizle(metin):
    """HTML etiketlerini kaldırıp düz metne çevirir (fallback için)."""
    metin = re.sub(r"<[^>]+>", "", metin)
    return (metin.replace("&lt;", "<").replace("&gt;", ">")
                 .replace("&quot;", chr(34)).replace("&amp;", "&"))


def _gizle(metin):
    """Log'a yazılacak metinden Telegram bot token'ını siler.

    Telegram uç noktası token'ı URL'in içinde taşır (…/bot<TOKEN>/sendMessage).
    Ağ hatasında `requests` bu URL'i hata mesajına gömer; mesaj da Actions
    loguna düşer. Repo public olduğu için o log herkese açıktır. GitHub zaten
    secret'ları maskeler, bu ikinci savunma katmanı: maskeleme yalnız birebir
    eşleşmeyi yakalar, burada kaynağında temizliyoruz.
    """
    s = str(metin)
    tok = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if tok:
        s = s.replace(tok, "***")
    return re.sub(r"bot\d{6,12}:[A-Za-z0-9_-]{10,}", "bot***", s)


def telegram_gonder(bot_token, chat_id, metin, html_modu=True):
    """Tek bir Telegram mesajı gönderir. HTML ayrıştırma hatasında (ör. bölme bir
    etiketi bozmuşsa) düz metne düşer; ağ hatalarında retry yapar."""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": metin,
        "disable_web_page_preview": True,
    }
    if html_modu:
        payload["parse_mode"] = "HTML"
    last_err = None
    for deneme in range(1, MAX_RETRY + 1):
        try:
            r = requests.post(url, json=payload, timeout=HTTP_TIMEOUT)
            data = r.json()
            if not data.get("ok"):
                aciklama = str(data.get("description", ""))
                # HTML ayrıştırma hatasıysa: etiketleri temizleyip düz metin olarak
                # TEK sefer yeniden dene (mesajın hiç gitmemesindense düz gitsin).
                if html_modu and any(k in aciklama.lower()
                                     for k in ("parse", "entit", "tag")):
                    print(f"[uyarı] HTML hatası, düz metne düşülüyor: {aciklama}",
                          file=sys.stderr)
                    return telegram_gonder(bot_token, chat_id,
                                           _html_temizle(metin), html_modu=False)
                raise RuntimeError(f"Telegram API hatası: {aciklama}")
            return data
        except Exception as e:                       # noqa: BLE001
            last_err = e
            print(f"[uyarı] Telegram gönderimi başarısız ({deneme}/{MAX_RETRY}): {_gizle(e)}",
                  file=sys.stderr)
            if deneme < MAX_RETRY:
                time.sleep(2 * deneme)
    raise RuntimeError(f"Telegram gönderimi {MAX_RETRY} denemede başarısız: {_gizle(last_err)}")


def raporu_yolla(bot_token, chat_id, rapor):
    """Raporu parçalara bölüp sırayla gönderir (mesajlar arası 1 sn bekler)."""
    bolumler = [b.strip() for b in rapor.split("---DETAY---") if b.strip()] or [rapor]
    parcalar = []
    for bolum in bolumler:
        parcalar.extend(mesaji_bol(bolum))
    toplam = len(parcalar)
    for i, parca in enumerate(parcalar, 1):
        # Birden fazla parça varsa küçük bir sayfa göstergesi ekle
        if toplam > 1:
            parca = f"{parca}\n\n<i>({i}/{toplam})</i>"
        telegram_gonder(bot_token, chat_id, parca)
        if i < toplam:
            time.sleep(1)
    return toplam


# --------------------------------------------------------------------------- #
# Hata bildirimi
# --------------------------------------------------------------------------- #

def admin_hata_bildir(mesaj):
    """Üretim/gönderim hatasında admin'e kısa bir özet gönderir (best-effort)."""
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    admin_id = os.environ.get("TELEGRAM_ADMIN_CHAT_ID")
    if not (bot_token and admin_id):
        return
    now = datetime.now(IST).strftime("%d.%m.%Y %H:%M")
    guvenli = html.escape(mesaj[:1000])
    metin = f"⚠️ <b>Kripto rapor botu HATASI</b>\n{now} (TSİ)\n\n<code>{guvenli}</code>"
    try:
        telegram_gonder(bot_token, admin_id, metin)
    except Exception as e:                           # noqa: BLE001
        print(f"[uyarı] Admin'e hata bildirimi de gönderilemedi: {_gizle(e)}", file=sys.stderr)


# --------------------------------------------------------------------------- #
# Ana akış
# --------------------------------------------------------------------------- #

# Rapor, teslim saatinden en fazla bu kadar önce üretilir (veri taze kalsın diye).
GONDERIM_URETIM_BUTCESI = 720  # saniye (~12 dk; Claude'un 10 dk timeout'unu aşacak pay)


def _hedef_zaman_ist(hhmm):
    """Bugün için Europe/Istanbul HH:MM zaman damgasını döndürür."""
    saat, dakika = hhmm.split(":")
    return datetime.now(IST).replace(hour=int(saat), minute=int(dakika),
                                     second=0, microsecond=0)


def _bekle_kadar(hedef_dt, aciklama):
    """hedef_dt'ye kadar bekler; zaman geçmişse hiç beklemez."""
    kalan = hedef_dt.timestamp() - datetime.now(IST).timestamp()
    if kalan > 0:
        print(f"[bilgi] {aciklama} ({int(kalan)} sn bekleniyor)...", file=sys.stderr)
        time.sleep(kalan)


STATE_YOL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state", "takip.json")


def dunku_takip_oku():
    """Dünkü takip maddelerini döndürür (yoksa []).

    Asıl kaynak artık kanonik raporun kendisidir (reports/latest.json →
    followUps). state/takip.json yalnız geçiş dönemi için yedek: reports/
    henüz oluşmamışsa oradan okunur."""
    try:
        with open(os.path.join(sema.RAPORLAR_DIZINI, "latest.json"), encoding="utf-8") as f:
            t = json.load(f).get("followUps", [])
        if isinstance(t, list) and t:
            return [str(x) for x in t]
    except (FileNotFoundError, ValueError, OSError):
        pass
    try:
        with open(STATE_YOL, encoding="utf-8") as f:
            t = json.load(f).get("takip", [])
        return t if isinstance(t, list) else []
    except (FileNotFoundError, ValueError, OSError):
        return []


def takip_yaz(takip):
    """Nöbetçi kilidini ve takip listesini state/takip.json'a yazar.

    Takip maddeleri artık kanonik raporda da var; bu dosya asıl olarak
    'bugünün raporu gönderildi mi' kilidini taşıyor (bugun_gonderildi_mi ve
    _uzaktan_gonderilmis_mi buraya bakar)."""
    os.makedirs(os.path.dirname(STATE_YOL), exist_ok=True)
    with open(STATE_YOL, "w", encoding="utf-8") as f:
        json.dump({"tarih": datetime.now(IST).strftime("%Y-%m-%d"), "takip": takip},
                  f, ensure_ascii=False, indent=2)


def bugun_gonderildi_mi():
    """Bugünün raporu gönderildi mi? (nöbetçi koruması)

    GitHub cron'u saatlerce geciktirebildiği için gün içinde birden fazla
    "nöbetçi" tetiklemesi var. İlk uyanan raporu gönderir ve takip.json'a
    bugünün tarihini yazar; geç uyanan nöbetçiler burayı görüp hiç
    çalışmadan çıkar. Böylece teslim saati sabit kalır, çift rapor gitmez.
    """
    try:
        with open(STATE_YOL, encoding="utf-8") as f:
            veri = json.load(f)
    except (FileNotFoundError, ValueError, OSError):
        return False
    return veri.get("tarih") == datetime.now(IST).strftime("%Y-%m-%d")


def _uzaktan_gonderilmis_mi():
    """Göndermeden HEMEN önce uzak (remote) state'i tazeleyip bugünün raporunun
    başka bir nöbetçi tarafından zaten gönderilip gönderilmediğine bakar.

    `bugun_gonderildi_mi()` yalnız checkout ANINDAKİ dosyayı görür; başka bir
    nöbetçi bu arada gönderip push etmiş ama o push henüz bu runner'ın gördüğü
    kopyaya yayılmamış olabilir — 2026-08-17'de rapor tam bu yüzden 2 kez gitti.
    Bu kontrol gönderimden hemen önce remote'u çekerek yarışı kapatır. Sadece
    GitHub Actions'ta anlamlıdır; ağ/git hatası olursa False döner (gönderimi
    asla engellemez, teslim garantide kalır)."""
    if os.environ.get("GITHUB_ACTIONS") != "true":
        return False
    try:
        subprocess.run(["git", "fetch", "--quiet", "origin", "main"],
                       capture_output=True, timeout=30)
        r = subprocess.run(["git", "show", "origin/main:state/takip.json"],
                           capture_output=True, text=True, timeout=15)
        if r.returncode == 0 and r.stdout.strip():
            veri = json.loads(r.stdout)
            return veri.get("tarih") == datetime.now(IST).strftime("%Y-%m-%d")
    except Exception:                                # noqa: BLE001
        pass
    return False


def foto_gonder(bot_token, chat_id, png_bytes, caption="", html_modu=True):
    """Telegram'a fotoğraf (kart) gönderir. Altyazı HTML ayrıştırma hatası verirse düz
    metne düşer; ağ hatasında retry yapar."""
    url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
    veri = {"chat_id": chat_id, "caption": caption}
    if caption and html_modu:
        veri["parse_mode"] = "HTML"
    last_err = None
    for deneme in range(1, MAX_RETRY + 1):
        try:
            r = requests.post(url, data=veri,
                              files={"photo": ("kart.png", png_bytes, "image/png")},
                              timeout=HTTP_TIMEOUT)
            cevap = r.json()
            if not cevap.get("ok"):
                aciklama = str(cevap.get("description", ""))
                if caption and html_modu and any(k in aciklama.lower()
                                                 for k in ("parse", "entit", "tag")):
                    return foto_gonder(bot_token, chat_id, png_bytes,
                                       _html_temizle(caption), html_modu=False)
                raise RuntimeError(f"sendPhoto hatası: {aciklama}")
            return cevap
        except Exception as e:                       # noqa: BLE001
            last_err = e
            print(f"[uyarı] Kart gönderimi başarısız ({deneme}/{MAX_RETRY}): {_gizle(e)}",
                  file=sys.stderr)
            if deneme < MAX_RETRY:
                time.sleep(2 * deneme)
    raise RuntimeError(f"Kart gönderimi {MAX_RETRY} denemede başarısız: {_gizle(last_err)}")


def ses_gonder(bot_token, chat_id, ogg_bytes):
    """Telegram'a sesli mesaj (OGG/Opus) gönderir; ağ hatasında retry yapar."""
    url = f"https://api.telegram.org/bot{bot_token}/sendVoice"
    last_err = None
    for deneme in range(1, MAX_RETRY + 1):
        try:
            r = requests.post(url, data={"chat_id": chat_id},
                              files={"voice": ("ses.ogg", ogg_bytes, "audio/ogg")},
                              timeout=HTTP_TIMEOUT)
            cevap = r.json()
            if not cevap.get("ok"):
                raise RuntimeError(f"sendVoice hatası: {cevap.get('description')}")
            return cevap
        except Exception as e:                       # noqa: BLE001
            last_err = e
            print(f"[uyarı] Ses gönderimi başarısız ({deneme}/{MAX_RETRY}): {_gizle(e)}",
                  file=sys.stderr)
            if deneme < MAX_RETRY:
                time.sleep(2 * deneme)
    raise RuntimeError(f"Ses gönderimi {MAX_RETRY} denemede başarısız: {_gizle(last_err)}")


def main():
    test_modu = "--test" in sys.argv
    onizleme = "--onizleme" in sys.argv  # sadece admin, etiketsiz (önizleme)
    both_modu = "--both" in sys.argv    # Ayni raporu hem admin'e hem kanala gonder

    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    kanal_id = os.environ.get("TELEGRAM_CHAT_ID")
    admin_id = os.environ.get("TELEGRAM_ADMIN_CHAT_ID")

    if not bot_token:
        print("HATA: TELEGRAM_BOT_TOKEN tanımlı değil.", file=sys.stderr)
        sys.exit(1)

    if both_modu:
        hedefler = [("admin", admin_id), ("kanal", kanal_id)]
    elif test_modu or onizleme:
        hedefler = [("admin", admin_id)]
    else:
        hedefler = [("kanal", kanal_id)]

    for ad, hid in hedefler:
        if not hid:
            degisken = "TELEGRAM_ADMIN_CHAT_ID" if ad == "admin" else "TELEGRAM_CHAT_ID"
            print(f"HATA: {degisken} tanımlı değil.", file=sys.stderr)
            sys.exit(1)

    # Nöbetçi koruması: rapor bugün zaten gönderildiyse boşuna çalışma.
    if not test_modu and not onizleme and bugun_gonderildi_mi():
        print("[bilgi] Rapor bugün zaten gönderilmiş — nöbetçi çıkıyor.", file=sys.stderr)
        return

    # SABİT TESLİM SAATİ: DELIVER_AT_TR (ör. "08:00") tanımlıysa rapor HER GÜN tam bu
    # saatte gider. GitHub cron erken tetikler; biz tam saate kadar bekleriz. Böylece
    # tetikleme kaysa bile teslim saati sabit kalır (alışkanlık için).
    teslim = os.environ.get("DELIVER_AT_TR", "").strip()
    zamanli = bool(teslim)
    hedef_dt = _hedef_zaman_ist(teslim) if zamanli else None

    try:
        # Veri taze kalsın diye üretimi teslim saatinden hemen önce başlat
        if zamanli:
            uret_penceresi = datetime.fromtimestamp(
                hedef_dt.timestamp() - GONDERIM_URETIM_BUTCESI, IST)
            _bekle_kadar(uret_penceresi, "Üretim penceresine")

        print("[bilgi] Adım 1: Piyasa verileri çekiliyor...", file=sys.stderr)
        market_data, market = piyasa_verilerini_cek()

        print("[bilgi] Adım 2: Rapor üretiliyor...", file=sys.stderr)
        dun_takip = dunku_takip_oku()
        llm_ciktisi = llm_ciktisi_uret(market_data, dun_takip)

        print("[bilgi] Adım 3: Kanonik rapor kuruluyor ve doğrulanıyor...", file=sys.stderr)
        tarih_id = datetime.now(IST).strftime("%Y-%m-%d")
        rapor = sema.rapor_kur(
            market=market,
            llm_ciktisi=llm_ciktisi,
            tarih_id=tarih_id,
            baslik=tarih_basligi(),
            simdi_iso=sema.simdi_iso(datetime.now(IST)),
            # Aynı gün ikinci üretim yeni kayıt açmasın: publishedAt korunur.
            onceki_rapor=sema.rapor_oku(tarih_id),
        )
        sema.dogrula(rapor)
        bugun_takip = rapor["followUps"]

        # --- Adım 4: aynı JSON'dan Telegram / kart / ses üret ---
        brief = render.brief_html(rapor)
        detaylar = [render.detay_html(rapor)]
        if test_modu:
            brief = "🧪 <b>[TEST]</b>" + chr(10) * 2 + brief

        # Tam teslim saatine kadar bekle (dakikası dakikasına gönderim)
        if zamanli:
            _bekle_kadar(hedef_dt, f"Teslim saati {teslim} TSİ'ye")

        print("[bilgi] Adım 4: Telegram'a gönderiliyor...", file=sys.stderr)

        # Kartı bir kez üret (best-effort — hata olsa rapor yine gider)
        png = None
        try:
            import kart
            png = kart.kart_olustur(render.kart_verisi(rapor),
                                    rapor["brief"]["mood"],
                                    rapor["brief"]["mainRisk"],
                                    rapor["title"])
        except Exception as kart_hata:               # noqa: BLE001
            print(f"[uyarı] Kart oluşturulamadı: {kart_hata}", file=sys.stderr)

        # Sesli özeti bir kez üret (best-effort — hata olsa rapor yine gider)
        ogg = None
        try:
            import ses
            ogg = ses.ses_uret_metin(render.seslendirme_metni(rapor))
        except Exception as ses_hata:                # noqa: BLE001
            print(f"[uyarı] Sesli özet oluşturulamadı: {ses_hata}", file=sys.stderr)

        # SON KONTROL (yarışa karşı): kart/ses üretilirken başka bir nöbetçi
        # göndermiş olabilir. Göndermeden hemen önce remote'u tazeleyip bak.
        if not test_modu and not onizleme and _uzaktan_gonderilmis_mi():
            print("[bilgi] Başka nöbetçi bu sabah zaten göndermiş (uzak kontrol) — çıkılıyor.",
                  file=sys.stderr)
            return

        # --- Kanonik raporu diske yaz (web sitesinin veri kaynağı) ---
        # Uzak kontrolden SONRA yazıyoruz: erken çıkan nöbetçi, gönderen
        # nöbetçinin raporunun üzerine kendi sürümünü commit'lemesin.
        # Test/önizlemede arşivi hiç kirletmiyoruz.
        if not test_modu and not onizleme:
            try:
                arsiv, _latest = sema.rapor_yaz(rapor)
                print(f"[bilgi] Rapor yazıldı → "
                      f"{os.path.relpath(arsiv, sema.KOK)} + reports/latest.json",
                      file=sys.stderr)
            except Exception as yaz_hata:            # noqa: BLE001
                # Web çıktısı yazılamasa bile Telegram gönderimi durmamalı
                # (iki hedef birbirinden bağımsız).
                print(f"[uyarı] Rapor dosyaya yazılamadı: {yaz_hata}", file=sys.stderr)

        for ad, hid in hedefler:
            # 1) İLK MESAJ = kart + brief (görsel ilk mesaja bağlı). Kart yoksa brief metin.
            if png is not None and len(brief) <= 1024:
                foto_gonder(bot_token, hid, png, caption=brief)
            else:
                raporu_yolla(bot_token, hid, brief)
                if png is not None:
                    foto_gonder(bot_token, hid, png)
            # 2) Sesli özet
            if ogg is not None:
                time.sleep(1)
                ses_gonder(bot_token, hid, ogg)
            # 3) Detay mesaj(lar)ı
            for detay in detaylar:
                time.sleep(1)
                raporu_yolla(bot_token, hid, detay)
            print(f"[başarılı] '{ad}' hedefine gönderildi (kart + brief + ses + detay).", file=sys.stderr)

        # --- E-posta bülteni (best-effort) ---
        # Telegram gönderimi bittikten SONRA çalışır: e-posta servisi düşse
        # bile kanal raporu almış olur (brief §6.6 — hedefler bağımsız).
        if not test_modu and not onizleme:
            try:
                import eposta
                ok, mesaj = eposta.gonder(rapor)
                print(f"[{'başarılı' if ok else 'uyarı'}] E-posta: {mesaj}", file=sys.stderr)
            except Exception as e_hata:               # noqa: BLE001
                print(f"[uyarı] E-posta gönderilemedi: {e_hata}", file=sys.stderr)

        # Bugünün takip listesini yarın için kaydet (test modunda kaydetme)
        if not test_modu and not onizleme:
            try:
                takip_yaz(bugun_takip)
                print(f"[bilgi] {len(bugun_takip)} takip maddesi kaydedildi.", file=sys.stderr)
            except Exception as se:                   # noqa: BLE001
                print(f"[uyarı] Takip kaydedilemedi: {se}", file=sys.stderr)

    except Exception as e:                           # noqa: BLE001
        print(f"[HATA] {_gizle(e)}", file=sys.stderr)
        admin_hata_bildir(_gizle(e))
        sys.exit(1)


if __name__ == "__main__":
    main()


# ──────────────────────────────────────────────────────────────────
#  🌅 Günaydın Kripto — topluluğa ÜCRETSİZ sunulmuştur.
#  Hazırlayan / imza: DogukanLive · youtube.com/@DogukanLive
#  Bu imzayı koru: aracın kökeni buradan bilinir.
# ──────────────────────────────────────────────────────────────────
