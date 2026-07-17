#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Günlük Kripto Raporu → Telegram Botu
=====================================

Üç adımda çalışır:
  Adım 1  Sabit piyasa verilerini ücretsiz API'lerden çeker (LLM YOK).
  Adım 2  Headless Claude Code (claude -p) ile haber/analiz bölümünü üretir.
  Adım 3  Raporu Telegram'a HTML formatında, 4096 karakter limitine uyarak gönderir.

Kullanım:
  python report.py            → Raporu kanala (TELEGRAM_CHAT_ID) gönderir.
  python report.py --test     → Raporu SADECE admin'e (TELEGRAM_ADMIN_CHAT_ID) gönderir.

Kimlik doğrulama ve gizli anahtarlar ortam değişkenlerinden okunur (koda gömülmez):
  CLAUDE_CODE_OAUTH_TOKEN     → Claude aboneliği token'ı (claude setup-token çıktısı)
  TELEGRAM_BOT_TOKEN          → BotFather'dan alınan bot token'ı
  TELEGRAM_CHAT_ID            → Raporun gideceği kanal
  TELEGRAM_ADMIN_CHAT_ID      → Senin özel chat'in (hata bildirimleri + test)
"""

import os
import sys
import time
import html
import shutil
import subprocess
import tempfile
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

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
# {market_data} ve {tarih} çalışma anında doldurulur.
RAPOR_PROMPTU = """Sen günlük kripto piyasa raporu hazırlayan titiz bir analistsin. Web araması yaparak SON 24 SAATİN gelişmelerini araştır ve aşağıdaki formatta Türkçe rapor yaz.

SANA VERİLEN PİYASA VERİLERİ:
{market_data}
Fiyat, dominans, hacim ve Fear & Greed değerlerini YALNIZCA buradan kullan; bu sayıları kendin arama, değiştirme, uydurma.

FORMAT — Telegram HTML (<b>, <i>, <a href="">); markdown ve tablo KULLANMA:

📊 <b>GÜNAYDIN KRİPTO RAPORU — {tarih}</b>

1) <b>ÖZET</b> — Günün tablosunu 4-5 kısa maddeyle ver (en önemliler önce)

2) <b>PİYASA</b> — Verilen sayılarla kompakt fiyat bloğu (coin başına tek satır: fiyat + 24s değişim), altına toplam piyasa değeri, dominans, Fear & Greed (dün ve geçen haftayla kıyasla)

3) <b>EN ÖNEMLİ 5 GELİŞME</b> — Her biri: başlık + 2-3 cümle + neden önemli + kaynak linki. Önem etiketi: 🔴 kritik / 🟡 önemli / 🟢 bilgi. Makro (Fed, TÜFE, jeopolitik) gelişmeler kriptoyu etkiliyorsa dahil et.

4) <b>TÜRKİYE</b> — SPK, MKK, TCMB, BDDK veya mevzuatta kriptoyu ilgilendiren YENİ gelişme varsa yaz; yoksa tek satır "Yeni gelişme yok" de. Asla gelişme uydurma.

5) <b>BUGÜN TAKİPTE</b> — Bugün ve yarın açıklanacak önemli veriler/olaylar, saatleriyle (TSİ)

6) <b>RİSKLER</b> — 2-3 madde, kısa

KURALLAR:
- Doğrulayamadığın hiçbir sayıyı yazma; gerekiyorsa "doğrulanamadı" de. Boş/okunamayan veriyi sıfır sayma.
- 100 üzerinden etki puanı, güven skoru gibi uydurma metrikler KULLANMA. Önem için sadece 🔴🟡🟢 etiketi.
- Al/sat/tut önerisi verme. Fiyat hedefi verme.
- Her gelişmede en az bir birincil veya kurumsal kaynak linki olsun; link URL'lerindeki utm parametrelerini temizle.
- Toplam uzunluk 3.000-6.000 karakter. Kısa ve yoğun yaz; tekrar eden uyarılar ekleme.
- En sona tek satır ekle: <i>Yatırım tavsiyesi değildir.</i>

ÖNEMLİ: Çıktı olarak SADECE raporun kendisini ver. Baştan/sona açıklama, "işte rapor" gibi ekleme yapma. İlk satır doğrudan "📊 <b>GÜNAYDIN KRİPTO RAPORU" ile başlasın."""


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

    return "\n".join(satirlar)


# --------------------------------------------------------------------------- #
# Adım 2 — Headless Claude Code ile haber/analiz üretimi
# --------------------------------------------------------------------------- #

def tarih_basligi():
    """Bugünün tarihini '17 Temmuz 2026, Perşembe' biçiminde döndürür (TSİ)."""
    now = datetime.now(IST)
    return f"{now.day} {TR_AYLAR[now.month - 1]} {now.year}, {TR_GUNLER[now.weekday()]}"


def rapor_uret(market_data):
    """
    Headless Claude Code'u (claude -p) çağırır. Anthropic API KEY kullanmaz;
    kimlik doğrulama CLAUDE_CODE_OAUTH_TOKEN ile abonelikten yapılır.
    Sadece WebSearch/WebFetch araçlarına izin verilir.
    """
    # Windows'ta npm 'claude' (bash script) + 'claude.cmd' üretir; subprocess ancak
    # .cmd/.exe çalıştırabilir. Bu yüzden platforma göre uygun olanı seç.
    adaylar = ["claude.cmd", "claude.exe", "claude"] if os.name == "nt" else ["claude"]
    claude_bin = next((shutil.which(a) for a in adaylar if shutil.which(a)), None)
    if not claude_bin:
        raise RuntimeError(
            "'claude' komutu bulunamadı. Kurulum: npm install -g @anthropic-ai/claude-code"
        )
    # CI'da kimlik CLAUDE_CODE_OAUTH_TOKEN ile gelir. Yerelde bu değişken yoksa,
    # makinede zaten giriş yapılmış claude oturumu kullanılır (uyarı verip devam et).
    if not os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
        print("[uyarı] CLAUDE_CODE_OAUTH_TOKEN yok; mevcut yerel claude oturumu "
              "kullanılacak (CI'da secret gereklidir).", file=sys.stderr)

    prompt = RAPOR_PROMPTU.format(market_data=market_data, tarih=tarih_basligi())

    # Çıktıyı düz metin olarak alıyoruz. --allowedTools ile sadece web araçlarına izin.
    komut = [
        claude_bin,
        "-p", prompt,
        "--allowedTools", "WebSearch", "WebFetch",
        "--output-format", "text",
    ]

    print("[bilgi] Claude Code raporu üretiyor (web araması yapılıyor)...", file=sys.stderr)
    try:
        sonuc = subprocess.run(
            komut,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=CLAUDE_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Claude Code {CLAUDE_TIMEOUT} saniyede yanıt vermedi.")

    if sonuc.returncode != 0:
        raise RuntimeError(
            f"Claude Code hata verdi (kod {sonuc.returncode}): {sonuc.stderr.strip()[:500]}"
        )

    rapor = (sonuc.stdout or "").strip()
    if len(rapor) < 200:
        raise RuntimeError(f"Claude Code beklenenden kısa çıktı verdi: {rapor!r}")

    return rapor


# --------------------------------------------------------------------------- #
# Adım 3 — Telegram'a gönderim
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


def telegram_gonder(bot_token, chat_id, metin):
    """Tek bir Telegram mesajı gönderir (HTML modu). Ağ hatalarında retry yapar."""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": metin,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    last_err = None
    for deneme in range(1, MAX_RETRY + 1):
        try:
            r = requests.post(url, json=payload, timeout=HTTP_TIMEOUT)
            data = r.json()
            if not data.get("ok"):
                # Telegram API mantıksal hatası (ör. yanlış chat_id / bozuk HTML)
                raise RuntimeError(f"Telegram API hatası: {data.get('description')}")
            return data
        except Exception as e:                       # noqa: BLE001
            last_err = e
            print(f"[uyarı] Telegram gönderimi başarısız ({deneme}/{MAX_RETRY}): {e}",
                  file=sys.stderr)
            if deneme < MAX_RETRY:
                time.sleep(2 * deneme)
    raise RuntimeError(f"Telegram gönderimi {MAX_RETRY} denemede başarısız: {last_err}")


def raporu_yolla(bot_token, chat_id, rapor):
    """Raporu parçalara bölüp sırayla gönderir (mesajlar arası 1 sn bekler)."""
    parcalar = mesaji_bol(rapor)
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
        print(f"[uyarı] Admin'e hata bildirimi de gönderilemedi: {e}", file=sys.stderr)


# --------------------------------------------------------------------------- #
# Ana akış
# --------------------------------------------------------------------------- #

def main():
    test_modu = "--test" in sys.argv

    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    kanal_id = os.environ.get("TELEGRAM_CHAT_ID")
    admin_id = os.environ.get("TELEGRAM_ADMIN_CHAT_ID")

    if not bot_token:
        print("HATA: TELEGRAM_BOT_TOKEN tanımlı değil.", file=sys.stderr)
        sys.exit(1)

    # Test modunda rapor kanala DEĞİL, admin'e gider
    hedef_id = admin_id if test_modu else kanal_id
    if not hedef_id:
        eksik = "TELEGRAM_ADMIN_CHAT_ID" if test_modu else "TELEGRAM_CHAT_ID"
        print(f"HATA: {eksik} tanımlı değil.", file=sys.stderr)
        sys.exit(1)

    try:
        # Adım 1
        print("[bilgi] Adım 1: Piyasa verileri çekiliyor...", file=sys.stderr)
        market_data = piyasa_verilerini_cek()

        # Adım 2
        print("[bilgi] Adım 2: Rapor üretiliyor...", file=sys.stderr)
        rapor = rapor_uret(market_data)

        if test_modu:
            # Testte rapor başına küçük bir işaret koy
            rapor = "🧪 <b>[TEST]</b>\n\n" + rapor

        # Adım 3
        print("[bilgi] Adım 3: Telegram'a gönderiliyor...", file=sys.stderr)
        adet = raporu_yolla(bot_token, hedef_id, rapor)

        hedef_ad = "ADMIN (test)" if test_modu else "kanal"
        print(f"[başarılı] Rapor {hedef_ad} hedefine {adet} mesaj olarak gönderildi.",
              file=sys.stderr)

    except Exception as e:                           # noqa: BLE001
        print(f"[HATA] {e}", file=sys.stderr)
        admin_hata_bildir(str(e))
        sys.exit(1)                                  # Workflow'u failed düşür


if __name__ == "__main__":
    main()
