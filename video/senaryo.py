# -*- coding: utf-8 -*-
"""Kanonik rapordan (reports/latest.json) video senaryosu: sahneler + konuşma metni.

Tamamen kurallı/deterministik (LLM yok). Rakamlar rapordan birebir alınır;
ekranda TR biçimiyle (83.589 $, +%0,46), seste konuşma diliyle okunur.

Telaffuz yardımcıları depo kökündeki ses_klon.py'den (sesli özetle ortak) alınır.
"""
import os
import re
import sys
from datetime import date, timedelta

DEPO_KOKU = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if DEPO_KOKU not in sys.path:
    sys.path.insert(0, DEPO_KOKU)
import ses_klon as sk                    # noqa: E402
import telaffuz                          # noqa: E402

# --------------------------------------------------------------------------- #
# Kolay değiştirilebilir metinler
# --------------------------------------------------------------------------- #

UST_ETIKET = "DOĞUKAN DOĞAN · GÜNAYDIN KRİPTO"
SITE = "dogukanlive.com"
SITE_KONUSMA = "Doğukan Live nokta com"   # fonetik; altyazıda SITE olarak birleşir
AKADEMI_CAGRISI = "Akademi: ücretsiz kripto eğitimi"
AKADEMI_KONUSMA = "Ücretsiz kripto eğitimi için: " + SITE_KONUSMA + "."
# Şeffaflık notu: Doğukan'ın tercihiyle KALDIRILDI (boş = gösterilmez).
SEFFAFLIK_NOTU = ""
KAPANIS_KONUSMA = "[warm] Bay bay."
VARSAYILAN_UYARI = "Bilgilendirme amaçlıdır, yatırım tavsiyesi değildir."

HABER_ADET = 2           # haber sahnesi sayısı
TAKIP_ADET = 3           # "Bugün takip et" madde sayısı
YATAY_ESIGI = sk.YATAY_ESIGI
KANCA_MAKS_KELIME = 8         # kanca manşeti: ≤ ~5 sn konuşma
KANCA_HAREKET_ESIGI = 1.0     # |BTC %24s| bunun altındaysa kancada rakam yok

# --------------------------------------------------------------------------- #
# B-roll tema kütüphanesi. Klipler broll/<tema>/<tema>-NN.mp4 (katalog:
# broll/kutuphane.json, bkz. kutuphane.py); tema içinde günden güne döndürülür.
# Klip üretimi (Higgsfield) bu depoda yok, ~/gunaydin-video'da yapılır; buradaki
# promptlar yeni tema eklerken referans içindir. Boş tema YEDEK_TEMA'ya düşer.
# --------------------------------------------------------------------------- #

_ORTAK = ("vertical 9:16 composition, photorealistic, cinematic, smooth slow camera movement, "
          "shallow depth of field, 35mm film look, dark moody background with warm amber and golden accents, "
          "no people, no faces, no hands, no text, no letters, no numbers, no logos, no brands, no watermark")
BROLL_PROMPTLARI = {
    "sabah-sehir": "Aerial shot of a modern city skyline at sunrise, soft golden morning light, "
                   "gentle haze over glass towers, calm peaceful atmosphere, slow drone push-in, " + _ORTAK,
    "piyasa-yukselis": "Sun rising over a dark mountain ridge, warm golden rays breaking through clouds, "
                       "time-lapse, slow push-in, " + _ORTAK,
    "piyasa-dusus": "Dark storm clouds rolling over a city skyline at dawn, dramatic moody light, "
                    "distant lightning, time-lapse, " + _ORTAK,
    "sakin-yatay": "Abstract macro shot of glowing warm golden light particles and soft bokeh drifting "
                   "slowly over a deep black background, elegant financial mood, " + _ORTAK,
    "hack-guvenlik": "Dark server room with rows of racks and blinking red lights, "
                     "tense cyber security atmosphere, slow dolly forward, " + _ORTAK,
    "kilit": "A massive round steel bank vault door slowly opening, warm golden light spilling out "
             "into a dark room, floating dust particles, " + _ORTAK,
    "etf-kurumsal": "Looking up at modern glass skyscrapers in a financial district at dusk, amber sky "
                    "reflected in the glass, slow upward tilt, " + _ORTAK,
    "fed-makro": "Neoclassical building with tall stone columns at dusk, warm floodlights, plain facade "
                 "without inscriptions or flags, slow push-in, " + _ORTAK,
    "regulasyon-hukuk": "Classical courthouse columns at sunrise, marble steps, soft golden light, "
                        "slow upward tilt, " + _ORTAK,
    "takvim-veri": "Minimalist wooden desk with a blank paper calendar, an analog clock and a cup of "
                   "steaming coffee, soft morning window light, slow dolly, " + _ORTAK,
    "bitcoin-madencilik": "Long aisle of cryptocurrency mining machines in a dark warehouse, cooling fans "
                          "spinning, small amber status lights, slow dolly forward, " + _ORTAK,
    "altcoin-cesitlilik": "Many small glowing orbs of different warm colors floating in dark space like a "
                          "constellation, slow camera drift, " + _ORTAK,
    "stablecoin-dolar": "Perfectly still dark water with a single glowing golden sphere floating calmly, "
                        "gentle ripples, slow push-in, " + _ORTAK,
    "borsa-islem-masasi": "Empty trading desk at night with curved monitors showing abstract glowing charts, "
                          "unreadable, slow dolly in, " + _ORTAK,
    "kapanis": "City skyline turning from dusk to night, windows lighting up, warm amber glow, "
               "slow drone pull-back, vertical composition, level horizon, " + _ORTAK,
    "istanbul-sabah": "Istanbul Bosphorus at sunrise, morning mist over the water, suspension bridge "
                      "silhouetted in the distance, seagulls gliding, level horizon, slow drone push-in, " + _ORTAK,
    "jeopolitik": "Unmarked oil tankers anchored in a dark harbor at night, warm lights reflecting on black "
                  "water, fog, tense quiet mood, slow drone glide, " + _ORTAK,
    "ethereum-defi": "Abstract network of fluid glowing light streams flowing between translucent nodes in "
                     "dark space, liquidity flow, slow camera drift, " + _ORTAK,
    "yapay-zeka-teknoloji": "Extreme macro of a blank unmarked processor chip surface, warm amber light "
                            "pulses across circuitry, slow macro push-in, " + _ORTAK,
}
YEDEK_TEMA = "sakin-yatay"

# Sahne türü -> tema (haber: anahtar kelime; fiyat/duygu: BTC yönü).
# "kanca-sabah" birleşik tema: sabah-sehir ∪ istanbul-sabah, dönüşümlü (kutuphane.BIRLESIK)
SABAH_TEMA = "kanca-sabah"
RISK_TEMA = "piyasa-dusus"
TAKIP_TEMA = "takvim-veri"
KAPANIS_TEMA = "kapanis"

# Haber metninden tema (öncelik sırasıyla; alt dize, TR küçük harf).
# "dolar" yok: neredeyse her haber özetinde tutar olarak geçer.
TEMA_ANAHTARLARI = [
    ("hack-guvenlik", ["hack", "saldır", "exploit", "çalıntı", "istismar", "sızıntı", "dolandırıcı",
                       "phishing", "oltalama", "güvenlik açığı"]),
    ("kilit", ["unlock", "kilit"]),
    ("etf-kurumsal", ["etf", "kurumsal", "fon giriş", "fon çıkış", "blackrock", "fidelity", "grayscale",
                      "microstrategy", "strategy ", "hazine", "treasur"]),
    ("fed-makro", ["enflasyon", "pce", "cpi", "fed", "faiz", "istihdam", "jolts", "tarım dışı", "gsyh",
                   "powell", "merkez bankası", "resesyon", "tarife", "gümrük"]),
    ("jeopolitik", ["savaş", "çatışma", " iran", " israil", "rusya", "ukrayna", "yaptırım", "gerilim",
                    "petrol"]),
    ("regulasyon-hukuk", ["sec ", "regülasyon", "düzenleme", " yasa", "mahkeme", "dava", "cftc", "mica",
                          "soruşturma", "ceza", "lisans"]),
    ("stablecoin-dolar", ["stablecoin", "stabil coin", "usdt", "usdc", "tether", "circle", "dai "]),
    ("bitcoin-madencilik", ["madenc", "mining", "hashrate", "hash oranı", "halving", "yarılanma"]),
    ("yapay-zeka-teknoloji", ["yapay zek", " ai ", " ai'", " ai,", " ai.", " ai-", "nvidia", " çip",
                              "teknoloji"]),
    ("borsa-islem-masasi", ["borsa", "exchange", "binance", "coinbase", "kraken", "okx", "bybit",
                            "listele", "işlem hacmi", "vadeli", "likidasyon", "tasfiye"]),
    # " eth": başta boşluk, "tether" eşleşmesin
    ("ethereum-defi", ["ethereum", " eth", "defi", "staking", "stake", "likidite", "akıllı sözleşme",
                       "layer 2", "layer-2", " l2"]),
    ("altcoin-cesitlilik", ["altcoin", "solana", "xrp", "cardano", "memecoin", "meme coin",
                            "airdrop", "token", "ağ yükseltme", "layer"]),
]


def piyasa_temasi(rapor):
    """BTC 24s değişimine göre: yükseliş / düşüş / yatay (YATAY_ESIGI)."""
    ch = (((rapor.get("market") or {}).get("coins") or {}).get("BTC") or {}).get("change24h")
    if ch is None or abs(ch) < YATAY_ESIGI:
        return "sakin-yatay"
    return "piyasa-yukselis" if ch > 0 else "piyasa-dusus"


# Kanca başlığının ikinci satırı: rapordaki "why" metninde geçen temalar
BASLIK_TEMALARI = [
    (["hack", "saldır", "exploit", "çalıntı"], "saldırı gölgesi"),
    (["pce", "cpi", "enflasyon"], "enflasyon bekleyişi"),
    (["fed", "faiz"], "Fed bekleyişi"),
    (["etf"], "ETF akışları"),
    (["unlock", "kilit"], "kilit açılımları"),
    (["regülasyon", "sec "], "regülasyon gündemi"),
]

# İngilizce terimleri Türkçeleştir (yalnız ses/altyazı; sıra önemli: uzundan kısaya)
SES_TERIMLERI = [
    (r"JOLTS açık iş verisi", "açık iş pozisyonları verisi"),
    (r"JOLTS verisi", "açık iş pozisyonları verisi"),
    (r"JOLTS", "açık iş pozisyonları"),
    (r"hackerinin", "saldırganının"), (r"hackerın", "saldırganın"), (r"hackerin", "saldırganın"),
    (r"hackeriyle", "saldırganıyla"), (r"hackeri", "saldırganı"), (r"hacker", "saldırgan"),
    (r"hackin", "saldırının"), (r"hackle", "saldırıyla"), (r"hacke", "saldırıya"),
    (r"hackten", "saldırıdan"), (r"hack", "saldırı"),
    (r"exploit", "açık istismarı"),
    (r"kilidi açılışı", "kilit açılımı"), (r"kilit açılışı", "kilit açılımı"),
    (r"unlock", "kilit açılımı"),
    (r"whale", "balina"), (r"airdrop", "ücretsiz token dağıtımı"),
]
# Ekranda da Türkçeleştirilecekler (kısa, tanıdık "hack" ekranda kalır)
EKRAN_TERIMLERI = [(r"unlock", "kilit açılımı")]
# Kesme işaretli adlar: ses_klon'un baş isim yöntemine token ekle
# (HYPE'ta -> HYPE tokeninde). Global sözlüğü değiştirir: rapor süreci bu modülü
# içe aktarmaz, ama aynı süreçte içe aktaran her şeyde (ör. testler) sesli özet de etkilenir.
sk._BAS_ISIM.setdefault("token", {
    "yalin": "tokeni", "bulunma": "tokeninde", "ayrilma": "tokeninden", "ilgi": "tokeninin",
    "yonelme": "tokenine", "belirtme": "tokenini", "vasita": "tokeniyle", "ki": "tokenindeki"})
for _ad in ("HYPE", "SUI", "ARB", "OP", "APT", "TIA", "STRK", "ZRO", "JUP", "WLD"):
    sk.OZEL_ADLAR.setdefault(_ad, "token")

# --------------------------------------------------------------------------- #
# Ekran biçimleri (TR)
# --------------------------------------------------------------------------- #


def _binlik(n):
    return f"{n:,}".replace(",", ".")


def fiyat_tr(v):
    """83589 -> '$83.589', 2681.71 -> '$2.681,71', 1.5 -> '$1,50'."""
    v = float(v)
    if v >= 10000:
        return "$" + _binlik(int(round(v)))
    tam, kesir = f"{v:.2f}".split(".")
    return "$" + _binlik(int(tam)) + "," + kesir


def yuzde_tr(ch, basamak=2):
    """0.458 -> '+%0,46', -0.61 -> '−%0,61'."""
    isaret = "+" if ch >= 0 else "−"
    return f"{isaret}%{abs(ch):.{basamak}f}".replace(".", ",")


def buyuk_usd_tr(v):
    """2.87e12 -> '$2,87 trilyon', 1.356e11 -> '$135,6 milyar'."""
    v = float(v)
    for esik, ad in ((1e12, "trilyon"), (1e9, "milyar"), (1e6, "milyon")):
        if v >= esik:
            x = v / esik
            s = f"{x:.2f}" if x < 10 else f"{x:.1f}"
            return "$" + s.replace(".", ",") + " " + ad
    return fiyat_tr(v)


def tr_buyuk(s):
    return s.replace("i", "İ").replace("ı", "I").upper()


def tarih_ekran(rapor):
    g = date.fromisoformat(rapor["id"])
    return f"{g.day} {tr_buyuk(sk.TR_AYLAR[g.month - 1])} {g.year} · {tr_buyuk(sk.TR_GUNLER[g.weekday()])}"


# --------------------------------------------------------------------------- #
# Konuşma dili
# --------------------------------------------------------------------------- #


def _goreli_tarih(metin, rapor):
    """'29 Eylül'de' -> 'bugün', '30 Eylül'de' -> 'yarın' (rapor gününe göre)."""
    try:
        bugun = date.fromisoformat(rapor["id"])
    except (KeyError, ValueError):
        return metin

    def degis(m):
        gun, ay = int(m.group(1)), m.group(2)
        if ay not in sk.TR_AYLAR:
            return m.group(0)
        try:
            g = date(bugun.year, sk.TR_AYLAR.index(ay) + 1, gun)
        except ValueError:
            return m.group(0)
        if g == bugun:
            return "bugün"
        if g == bugun + timedelta(days=1):
            return "yarın"
        return m.group(0)

    return re.sub(r"\b(\d{1,2}) ([A-ZÇĞİÖŞÜ][a-zçğıöşü]+)(?:'(?:de|da|te|ta)| günü)\b", degis, metin)


def _terimler(metin, tablo):
    for kalip, yeni in tablo:
        metin = re.sub(rf"(?<![\w]){kalip}(?![\w])", yeni, metin, flags=re.IGNORECASE)
    return metin


# konusma() çağrılarının okunuş eşlemeleri; sahneler() her sahneye "telaffuz" olarak dağıtır
_ESLEMELER = []
# Sayı okunuşu eşlemeleri ("on beş otuzda" -> "15:30'da"); sahneye "rakam" olarak, metin sırasıyla
_RAKAMLAR = []


def _rakam(okunus, orijinal):
    """Sesteki yazıyla sayıyı altyazı için rakam yazımına eşler; okunuşu döndürür."""
    if okunus and orijinal and okunus != orijinal:
        _RAKAMLAR.append((tuple(okunus.split()), tuple(orijinal.split())))
    return okunus


def _usd_rakam(tutar):
    """usd_konusma çıktısının rakam yazımı: '85 bin 600' -> '85.600', 'bin' -> '1.000'."""
    m = re.fullmatch(r"(?:(\d+) )?bin(?: (\d+))?", tutar)
    return _binlik(int(m.group(1) or 1) * 1000 + int(m.group(2) or 0)) if m else tutar


def _yuzde_rakam(ch):
    a = round(abs(float(ch)), 1)
    return "%" + (str(int(a)) if a == int(a) else f"{a:.1f}".replace(".", ","))


def _saat_rakam(hhmm, okunus):
    """('15:30', 'saat on beş otuzda') -> "15:30'da" (ek okunuştan)."""
    s, d = re.fullmatch(r"\s*(\d{1,2})[:.](\d{2})\s*", hhmm).groups()
    return f"{int(s)}:{d}'{okunus[-2:]}"


def konusma(metin, rapor):
    """Rapor metnini sesli okumaya uygun, Türkçeleştirilmiş cümleye çevirir."""
    t = _goreli_tarih(metin or "", rapor)
    t = sk.telaffuz_duzelt(t, fonetik=False, eslemeler=_RAKAMLAR)
    t = _terimler(t, SES_TERIMLERI)
    t, eslemeler = telaffuz.donustur_eslemeli(t)
    _ESLEMELER.extend(eslemeler)
    return t


def ekran(metin):
    return _terimler((metin or "").strip(), EKRAN_TERIMLERI)


def _cumle(s):
    return sk._cumle(s)


def _yan_cumle(ozet):
    """Özetin ';' sonrası kısa ikinci yarısı (varsa) — ek bilgi cümlesi."""
    parca = [p.strip() for p in (ozet or "").split(";") if p.strip()]
    if len(parca) >= 2 and len(parca[1]) <= 95:
        return parca[1]
    return ""


def _anahtar_adlar(baslik):
    kel = re.findall(r"[A-ZÇĞİÖŞÜ][\wÇĞİÖŞÜçğıöşü]{2,}", baslik or "")
    return {k for k in kel if k.lower() not in ("abd",)}


def haber_sec(rapor, adet=HABER_ADET):
    """Gündemden haber seçer; aynı özel adı paylaşan tekrar haberleri atlar."""
    secilen, gorulen = [], set()
    gundem = (rapor.get("sections") or {}).get("agenda") or []
    for h in gundem:
        adlar = _anahtar_adlar(h.get("title", ""))
        if adlar & gorulen:
            continue
        secilen.append(h)
        gorulen |= adlar
        if len(secilen) == adet:
            break
    return secilen


def tema_bul(metin, varsayilan=YEDEK_TEMA):
    k = " " + sk.tr_kucuk(metin or "") + " "      # " yasa": "piyasa" eşleşmesin
    for tema, anahtarlar in TEMA_ANAHTARLARI:
        if any(a in k for a in anahtarlar):
            return tema
    return varsayilan


def baslik_temalari(rapor, adet=2):
    k = sk.tr_kucuk((rapor.get("brief") or {}).get("why", "")) + " "
    return [ifade for anahtarlar, ifade in BASLIK_TEMALARI if any(a in k for a in anahtarlar)][:adet]


def _para_vurgusu(metin):
    """Metindeki ilk '387,5 milyon dolar' -> '$387,5 milyon' (rapordan birebir)."""
    m = re.search(r"(\d[\d.,]*)\s*(milyon|milyar)\s*dolar", metin or "")
    return f"${m.group(1)} {m.group(2)}" if m else ""


def _coin_konusma(ad, coin, yatay_ek):
    fiyat = (coin or {}).get("priceUsd")
    if fiyat is None:
        return ""
    tutar = sk.usd_konusma(fiyat)
    ch = coin.get("change24h")
    if ch is None or abs(ch) < YATAY_ESIGI:
        return f"{ad} {_rakam(tutar, _usd_rakam(tutar))} dolar civarında, {yatay_ek}."
    yon = "artıyla" if ch > 0 else "düşüşle"
    yuzde = _rakam("yüzde " + sk.yuzde_konusma(ch), _yuzde_rakam(ch))
    return f"{ad} {yuzde} {yon} {_rakam(tutar, _usd_rakam(tutar))} dolarda."


def _takip_ifadesi(olay, rapor):
    saat = sk.saat_konusma(olay.get("timeTr") or "")
    if saat:      # önce saat: eşlemeler metin sırasıyla tutulur
        _rakam(saat.split(" ", 1)[1], _saat_rakam(olay["timeTr"], saat))
    baslik = konusma(olay.get("title", ""), rapor).rstrip(".")
    return (sk.tr_buyuk_bas(saat) + " " + baslik) if saat else ("Gün içinde de " + baslik)


_ZAYIF_SON = {"ve", "ile", "için", "ama", "fakat", "bir", "de", "da", "ki", "gibi", "olarak",
              "sonra", "önce", "kadar", "en", "çok", "daha", "bu", "şu", "o", "the", "of"}


def kanca_manseti(rapor, maks=KANCA_MAKS_KELIME):
    """Günün manşeti (ilk gündem başlığı), kancada okunacak kadar kısa: ≤ maks kelime.
    Uzunsa ilk yan cümle (virgül/iki nokta öncesi), o da uzunsa ilk `maks` kelime; zayıf
    bağlaçla bitmez. Başlık yoksa ""."""
    gundem = (rapor.get("sections") or {}).get("agenda") or []
    baslik = re.sub(r"\s+", " ", ((gundem[0] or {}).get("title") or "") if gundem else "").strip()
    baslik = baslik.rstrip(" .;,:!?")
    kel = baslik.split()
    if len(kel) <= maks:
        return baslik
    ilk = re.split(r"\s*[,;:–—]\s*|\s+-\s+", baslik)[0].split()
    if 3 <= len(ilk) <= maks:
        return " ".join(ilk)
    kel = kel[:maks]
    while len(kel) > 3 and sk.tr_kucuk(kel[-1]).strip(",;:") in _ZAYIF_SON:
        kel.pop()
    return " ".join(kel).rstrip(",;:")


def _kanca_btc(coin):
    """'Bitcoin 82 bin dolarda, günde yüzde 1,6 düşüşte.' — hareket küçükse ""."""
    fiyat, ch = (coin or {}).get("priceUsd"), (coin or {}).get("change24h")
    if fiyat is None or ch is None or abs(ch) < KANCA_HAREKET_ESIGI or fiyat < 1000:
        return ""
    tutar = f"{round(fiyat / 1000)} bin"
    yon = "düşüşte" if ch < 0 else "yükselişte"
    yuzde = _rakam("yüzde " + sk.yuzde_konusma(ch), _yuzde_rakam(ch))
    return f"Bitcoin {tutar} dolarda, günde {yuzde} {yon}."


# --------------------------------------------------------------------------- #
# Sahneler
# --------------------------------------------------------------------------- #


def sahneler(rapor):
    """[{tur, tema, konusma (etiketli), veri...}] — sırayla videonun sahneleri."""
    b = rapor.get("brief") or {}
    m = rapor.get("market") or {}
    coins = m.get("coins") or {}
    mood = b.get("mood") or "Kararsız"
    temalar = baslik_temalari(rapor)
    s = []
    _ESLEMELER.clear()
    _RAKAMLAR.clear()

    def ekle(sahne):
        sahne["telaffuz"] = list(_ESLEMELER)
        sahne["rakam"] = list(_RAKAMLAR)
        _ESLEMELER.clear()
        _RAKAMLAR.clear()
        s.append(sahne)

    # 1) Kanca: günün manşeti + BTC hareketi (manşet yoksa eski ruh hâli cümlesi)
    manset = kanca_manseti(rapor)
    if manset:
        k = f"[cheerful] Günaydın! [calm] {_cumle(konusma(manset, rapor))}"
        btc = _kanca_btc(coins.get("BTC"))
        k += f" {btc}" if btc else ""
        alt = ekran(manset)
    else:
        gundem = (" ve ".join(temalar)) if temalar else ""
        k = f"[cheerful] Günaydın! Bugün {sk._tarih(rapor)}. [calm] Piyasa {sk.tr_kucuk(mood)}"
        k += f"; gündemde {konusma(gundem, rapor)}." if gundem else "."
        alt = sk.tr_buyuk_bas(", ".join(temalar)) if temalar else ""
    ekle({"tur": "kanca", "tema": SABAH_TEMA, "konusma": k,
          "tarih": tarih_ekran(rapor), "mood": mood, "alt": alt})

    # 2) Fiyat kartı
    satirlar = []
    for sembol in ("BTC", "ETH", "SOL", "BNB", "XRP"):
        c = coins.get(sembol)
        if c and c.get("priceUsd") is not None:
            satirlar.append({"sembol": sembol, "fiyat": fiyat_tr(c["priceUsd"]),
                             "degisim": c.get("change24h")})
    fk = " ".join(x for x in (
        _coin_konusma("Bitcoin", coins.get("BTC"), "yatay seyrediyor"),
        _coin_konusma("Ethereum", coins.get("ETH"), "o da yatay")) if x)
    ekle({"tur": "fiyat", "tema": piyasa_temasi(rapor), "konusma": fk, "satirlar": satirlar,
          "toplam": buyuk_usd_tr(m["totalMarketCapUsd"]) if m.get("totalMarketCapUsd") else "",
          "dominans": ("%" + f"{m['btcDominance']:.1f}".replace(".", ",")) if m.get("btcDominance") else ""})

    # 3) Korku-açgözlülük
    fg = m.get("fearGreed") or {}
    if fg.get("value") is not None:
        ekle({"tur": "duygu", "tema": piyasa_temasi(rapor), "konusma": sk._fng_cumlesi(fg),
              "deger": int(fg["value"]), "etiket": fg.get("label") or "",
              "dun": fg.get("previousValue"), "hafta": fg.get("weekAgoValue")})

    # 4-5) Haberler
    for i, h in enumerate(haber_sec(rapor)):
        ek = _yan_cumle(h.get("summary")) if i == 0 else ""   # süre: ek cümle yalnız ana haberde
        on = "[serious] Günün haberi: " if i == 0 else "[calm] Bir başlık daha: "
        metin = on + _cumle(konusma(h.get("title", ""), rapor))
        if ek:
            metin += " " + _cumle(konusma(ek, rapor))
        onem = h.get("importance") or ""
        ekle({"tur": "haber", "tema": tema_bul(h.get("title", "") + " " + h.get("summary", "")),
              "konusma": metin, "onem": onem, "baslik": ekran(h.get("title", "")),
              "kaynak": ((h.get("source") or {}).get("publisher") or ""),
              "vurgu": _para_vurgusu(h.get("summary", "")) if not _para_vurgusu(h.get("title", "")) else ""})

    # 6) Ana risk
    if b.get("mainRisk"):
        ekle({"tur": "risk", "tema": RISK_TEMA,
              "konusma": "[serious] Ana risk şu: " + _cumle(konusma(b["mainRisk"], rapor)),
              "metin": ekran(b["mainRisk"])})

    # 7) Bugün takip et
    olaylar = (b.get("criticalEvents") or (rapor.get("sections") or {}).get("today") or [])[:TAKIP_ADET]
    if olaylar:
        ifadeler = [_takip_ifadesi(o, rapor) for o in olaylar]
        ekle({"tur": "takip", "tema": TAKIP_TEMA,
              "konusma": "[calm] Bugün takip et: " + " ".join(_cumle(x) for x in ifadeler),
              "maddeler": [{"saat": o.get("timeTr"), "baslik": ekran(o.get("title", ""))}
                           for o in olaylar]})

    # 8) Kapanış
    uyari = rapor.get("disclaimer") or VARSAYILAN_UYARI
    ekle({"tur": "kapanis", "tema": KAPANIS_TEMA,
          "konusma": f"[calm] {uyari} {AKADEMI_KONUSMA} {KAPANIS_KONUSMA}",
          "uyari": uyari, "site": SITE, "akademi": AKADEMI_CAGRISI, "not": SEFFAFLIK_NOTU})
    for x in s:
        x["konusma"] = re.sub(r"\s+", " ", x["konusma"]).strip()
    return s


ETIKET = re.compile(r"\[[^\]]+\]\s*")


def etiketsiz(metin):
    return re.sub(r"\s+", " ", ETIKET.sub("", metin)).strip()


def tam_metin(sahne_listesi):
    """ElevenLabs'e giden etiketli metin."""
    return " ".join(x["konusma"] for x in sahne_listesi)
