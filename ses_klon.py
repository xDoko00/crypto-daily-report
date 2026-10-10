# -*- coding: utf-8 -*-
"""Doğukan'ın klon sesiyle ~50-60 sn sesli özet (ElevenLabs).

VARSAYILAN KAPALI. Açmak için ortamda SESLI_OZET_ELEVENLABS=1 ve
ELEVENLABS_API_KEY tanımlı olmalı. Kapalıyken report.py eski edge-tts
sesini kullanmaya devam eder.

- Konuşma metni kanonik rapordan DETERMİNİSTİK şablonla kurulur (LLM yok).
- Metin ElevenLabs v4 audio tag'leriyle ([calm], [serious] …) kurulur. Model
  tag desteklemiyorsa (eleven_multilingual_v2) tag'ler istekten önce
  tts_metni()'nde temizlenir — yoksa sesli okunabilir.
- Hata (API, kota, ffmpeg) rapor akışını ASLA durdurmaz: ozet_ogg() None döner
  ve sebebi loga yazar. Anahtar hiçbir koşulda loglanmaz.
"""
import os
import re
import sys
import subprocess
import tempfile
from datetime import date

import telaffuz

# --------------------------------------------------------------------------- #
# Ayarlar
# --------------------------------------------------------------------------- #

BAYRAK = "SESLI_OZET_ELEVENLABS"
ANAHTAR_DEGISKENI = "ELEVENLABS_API_KEY"
YEREL_ANAHTAR_DOSYASI = os.path.expanduser("~/.config/elevenlabs/.env")

API_TABAN = "https://api.elevenlabs.io"
SES_ID = "l4Ygbni4CmTFHmTYdyhD"          # "Dogukan v1"
# Model + ses ayarı TEK YERDE. Varsayılan: Doğukan'ın kulakla seçtiği "A4" —
# PVC ince ayarı yalnız eleven_multilingual_v2'de. SES_MODEL=eleven_v4 ile geri dönülür.
MODEL_DEGISKENI = "SES_MODEL"
VARSAYILAN_MODEL = "eleven_multilingual_v2"
MODEL_ID = VARSAYILAN_MODEL
TAG_DESTEKLI_MODELLER = ("eleven_v3", "eleven_v4")
MODEL_AYARLARI = {
    "eleven_multilingual_v2": {"stability": 0.6, "similarity_boost": 0.9, "style": 0,
                               "use_speaker_boost": True},
}
DIL = "tr"
CIKTI_BICIMI = "mp3_44100_128"
HTTP_TIMEOUT = 90
MAX_DENEME = 2

MAKS_KARAKTER = 900                        # tag'ler dahil (faturalanan uzunluk)
YATAY_ESIGI = 0.5                          # |%değişim| bunun altındaysa "yatay"

TR_AYLAR = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
            "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
TR_GUNLER = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]

_BIRLER = ["", "bir", "iki", "üç", "dört", "beş", "altı", "yedi", "sekiz", "dokuz"]
_ONLAR = ["", "on", "yirmi", "otuz", "kırk", "elli"]

_EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF\U00002300-\U000027BF\U00002190-\U000021FF"
    "\U00002B00-\U00002BFF️₿Ξ]"
)


def aktif_mi(ortam=None):
    """Bayrak açık mı? (1/true/evet/on). Varsayılan KAPALI."""
    ortam = os.environ if ortam is None else ortam
    return str(ortam.get(BAYRAK, "")).strip().lower() in ("1", "true", "evet", "on", "yes")


def ses_modeli(ortam=None):
    """SES_MODEL ortam değişkeni, yoksa VARSAYILAN_MODEL."""
    ortam = os.environ if ortam is None else ortam
    return (ortam.get(MODEL_DEGISKENI) or "").strip() or VARSAYILAN_MODEL


def ses_ayarlari(model):
    """Modele özgü voice_settings (None = sesin kayıtlı varsayılanları)."""
    a = MODEL_AYARLARI.get(model)
    return dict(a) if a else None


def tag_destekli(model):
    return model in TAG_DESTEKLI_MODELLER


_TAG = re.compile(r"\s*\[([a-z][a-z ]*)\]\s*")
_DURAKLAMA = ("short pause", "pause", "long pause")


def tagsiz(metin):
    """Audio tag'lerini doğal noktalamayla değiştirir: duraklama tag'i önünde
    noktalama yoksa virgül olur, diğer tag'ler (ton) tamamen silinir."""
    def degis(m):
        if m.group(1) in _DURAKLAMA:
            once = metin[:m.start()].rstrip()
            if once and once[-1] not in ".,;:!?…":
                return ", "
        return " "
    t = _TAG.sub(degis, metin)
    t = re.sub(r"\s+([,.;:!?])", r"\1", t)
    return re.sub(r"\s+", " ", t).strip()


def tts_metni(metin, model):
    """ElevenLabs'e gidecek metin: model tag desteklemiyorsa tag'ler temizlenir."""
    return metin if tag_destekli(model) else tagsiz(metin)


def istek_govdesi(metin, model=None):
    """TTS isteğinin JSON gövdesi (tag temizliği + model + ayarlar) — tek merkez.
    language_code=tr multilingual_v2'de de kabul ediliyor (10 Eki 2026, HTTP 200)."""
    model = model or ses_modeli()
    g = {"text": tts_metni(metin, model), "model_id": model, "language_code": DIL}
    ayar = ses_ayarlari(model)
    if ayar:
        g["voice_settings"] = ayar
    return g


def onbellek_imzasi(model=None):
    """TTS önbelleği için model + ayar imzası (değişince eski ses kullanılmaz)."""
    model = model or ses_modeli()
    ayar = ses_ayarlari(model) or {}
    return model + "|" + ",".join(f"{k}={ayar[k]}" for k in sorted(ayar))


# --------------------------------------------------------------------------- #
# Türkçe yardımcılar
# --------------------------------------------------------------------------- #

def tr_kucuk(s):
    return s.replace("İ", "i").replace("I", "ı").lower()


def tr_buyuk_bas(s):
    if not s:
        return s
    ilk = {"i": "İ", "ı": "I"}.get(s[0], s[0].upper())
    return ilk + s[1:]


def sayi_yazi(n):
    """0-59 arası sayıyı yazıya çevirir (saat/dakika için)."""
    if n == 0:
        return "sıfır"
    return " ".join(p for p in (_ONLAR[n // 10], _BIRLER[n % 10]) if p)


def bulunma_eki(kelime):
    """Kelimeye -de/-da/-te/-ta ekler (ünlü uyumu + sert ünsüz)."""
    son_unlu = next((c for c in reversed(kelime) if c in "aeıioöuü"), "e")
    unlu = "a" if son_unlu in "aıou" else "e"
    unsuz = "t" if kelime[-1] in "fstkçşhp" else "d"
    return kelime + unsuz + unlu


def saat_konusma(hhmm):
    """'11:00' -> 'saat on birde', '15:30' -> 'saat on beş otuzda'."""
    m = re.fullmatch(r"\s*(\d{1,2})[:.](\d{2})\s*", hhmm or "")
    if not m:
        return None
    s, d = int(m.group(1)), int(m.group(2))
    if not (0 <= s <= 23 and 0 <= d <= 59):
        return None
    if d == 0:
        ifade = sayi_yazi(s)
    elif d < 10:
        ifade = f"{sayi_yazi(s)} sıfır {sayi_yazi(d)}"
    else:
        ifade = f"{sayi_yazi(s)} {sayi_yazi(d)}"
    return "saat " + bulunma_eki(ifade)


def yuzde_konusma(v):
    """1.02 -> 'bir', 2.345 -> '2,3', 12 -> '12'."""
    a = round(abs(float(v)), 1)
    if a == int(a):
        a = int(a)
        return _BIRLER[a] if 1 <= a <= 9 else ("on" if a == 10 else str(a))
    return f"{a:.1f}".replace(".", ",")


def usd_konusma(v):
    """Konuşma diliyle yuvarlanmış tutar ('dolar' kelimesi hariç).
    83589 -> '83 bin 600', 2681.71 -> '2 bin 680', 387.5e6 -> '387 milyon'."""
    v = float(v)
    if v >= 1e9:
        x = v / 1e9
        return (f"{x:.1f}".replace(".", ",").replace(",0", "") if x < 10 else str(int(x))) + " milyar"
    if v >= 1e6:
        x = v / 1e6
        return (f"{x:.1f}".replace(".", ",").replace(",0", "") if x < 10 else str(int(x))) + " milyon"
    if v >= 1000:
        basamak = len(str(int(v)))
        adim = 10 ** max(basamak - 3, 0)
        n = int(round(v / adim) * adim)
        if n >= 1_000_000:
            return usd_konusma(n)
        binler, kalan = divmod(n, 1000)
        bas = "bin" if binler == 1 else f"{binler} bin"
        return f"{bas} {kalan}" if kalan else bas
    if v >= 100:
        return str(int(round(v)))
    return f"{round(v, 2):g}".replace(".", ",")


# --------------------------------------------------------------------------- #
# Telaffuz düzeltici
# --------------------------------------------------------------------------- #

# Kesme işaretli yabancı özel adlar TTS'te "Bitget, teki" diye bölünüyor.
# Bilinen adlarda ek, bir baş isme taşınır: Bitget'teki -> Bitget borsasındaki.
_BAS_ISIM = {
    "borsa": {"yalin": "borsası", "bulunma": "borsasında", "ayrilma": "borsasından",
              "ilgi": "borsasının", "yonelme": "borsasına", "belirtme": "borsasını",
              "vasita": "borsasıyla", "ki": "borsasındaki"},
    "ag": {"yalin": "ağı", "bulunma": "ağında", "ayrilma": "ağından",
           "ilgi": "ağının", "yonelme": "ağına", "belirtme": "ağını",
           "vasita": "ağıyla", "ki": "ağındaki"},
}
OZEL_ADLAR = {
    # borsalar
    "Bitget": "borsa", "Binance": "borsa", "Coinbase": "borsa", "Bybit": "borsa",
    "Kraken": "borsa", "OKX": "borsa", "KuCoin": "borsa", "Bitfinex": "borsa",
    "BtcTurk": "borsa", "Paribu": "borsa", "Upbit": "borsa", "MEXC": "borsa",
    "HTX": "borsa", "Bithumb": "borsa", "Gemini": "borsa",
    # ağlar / protokoller
    "THORChain": "ag", "Osmosis": "ag", "Hyperliquid": "ag", "Arbitrum": "ag",
    "Optimism": "ag", "Polygon": "ag", "Avalanche": "ag", "Cardano": "ag",
}


def _hal(ek):
    ek = tr_kucuk(ek)
    if ek.endswith("ki") and len(ek) > 2:
        return "ki"
    if ek in ("de", "da", "te", "ta"):
        return "bulunma"
    if ek in ("den", "dan", "ten", "tan"):
        return "ayrilma"
    if ek in ("in", "ın", "un", "ün", "nin", "nın", "nun", "nün"):
        return "ilgi"
    if ek in ("e", "a", "ye", "ya"):
        return "yonelme"
    if ek in ("i", "ı", "u", "ü", "yi", "yı", "yu", "yü"):
        return "belirtme"
    if ek in ("le", "la", "yle", "yla"):
        return "vasita"
    return None


KESME_KORU_HARF = 4
_KESME = r"\b(?P<ad>[A-Za-zÇĞİÖŞÜçğıöşü][\w.]*?)'(?P<ek>[a-zçğıöşü]+)\b"


def _kesme_duzelt(m):
    ad, ek = m.group("ad"), m.group("ek")
    tur = OZEL_ADLAR.get(ad)
    if tur:
        hal = _hal(ek)
        if hal:
            return f"{ad} {_BAS_ISIM[tur][hal]}"
    if ad.isupper():                 # ABD'nin, HYPE'ın: kısaltmada kesme kalsın
        return f"{ad}'{ek}"
    if len(ad) <= KESME_KORU_HARF and telaffuz.donustur(ad) == ad:
        return f"{ad}'{ek}"          # Fed'den: ElevenLabs kesmeli kısa adı doğru okuyor (9 Eki testi)
    return ad + ek                   # bilinmeyen ad: kesmeyi kaldır (Bitcoin'in -> Bitcoinin)


def _usd_nokta(m):
    return usd_konusma(float(m.group(1).replace(",", ""))) + " dolar"


# Sayı içeren ifade (saat, $/% önekli, binlik, milyon/milyar, dolar, % sonekli): _sayilar()
# zinciri yalnız bu kalıbın içinde iş görür; kalıp zincirin tükettiği her bağlamı kapsamalı.
_SAYI_IFADESI = re.compile(r"(?:\bsaat\s+)?(?:[$%]\s?)?\b\d(?:[\d.,:]*\d)?"
                           r"(?:\s*'?(?:de|da|te|ta)\b)?(?:\s*(?:milyon|milyar)\b)?"
                           r"(?:\s*dolar)?(?:\s?%(?!\s?\d))?")

_SAYI_VEYA_KESME = re.compile(rf"(?P<kesme>{_KESME})|{_SAYI_IFADESI.pattern}")


def _sayi_eslemesi(okunus, orijinal):
    """Ortak baş/son kelimeler atılmış (okunuş, orijinal) kelime demetleri; fark yoksa None."""
    o, g = okunus.split(), orijinal.split()
    while o and g and o[0] == g[0]:
        o, g = o[1:], g[1:]
    while o and g and o[-1] == g[-1]:
        o, g = o[:-1], g[:-1]
    return (tuple(o), tuple(g)) if o and g else None


def telaffuz_duzelt(metin, fonetik=True, eslemeler=None):
    """LLM'in yazdığı serbest metni sesli okumaya uygun hale getirir.
    fonetik=False: telaffuz.py sözlüğü uygulanmaz (çağıran sonra kendisi uygular).
    eslemeler (liste): sayı ve kesme dönüşümlerinin (okunuş, orijinal) kelime eşlemeleri metin
    sırasıyla eklenir (altyazıda "on beş otuzda" yerine "15:30'da", "Bitcoinin" yerine
    "Bitcoin'in" yazmak için)."""
    t = re.sub(r"<[^>]+>", "", metin or "")
    t = _EMOJI.sub("", t)
    t = t.replace("’", "'").replace("‘", "'")
    t = t.replace("F&amp;G", "korku açgözlülük endeksi").replace("F&G", "korku açgözlülük endeksi")
    t = re.sub(r"\(\s*TSİ\s*\)|\bTSİ\b", "", t)

    def ifade(m):
        if m.group("kesme"):                     # Kesme + ek
            okunus = _kesme_duzelt(m)
            es = ((okunus,), (m.group(0),)) if okunus == m.group("ad") + m.group("ek") else None
        else:
            okunus = _sayilar(m.group(0))
            es = _sayi_eslemesi(okunus, m.group(0))
        if es and eslemeler is not None:
            eslemeler.append(es)
        return okunus

    # Sayı ifadeleri ve kesmeler tek geçişte: eşlemeler metin sırasıyla birikir
    t = _SAYI_VEYA_KESME.sub(ifade, t)
    if fonetik:
        t = telaffuz.donustur(t)
    t = re.sub(r"\s+([,.;:])", r"\1", t)
    return re.sub(r"\s+", " ", t).strip()


def _sayilar(t):
    """Saat, dolar ve yüzde yazımlarını konuşma diline çevirir (tek ifade üzerinde)."""
    # Saatler: "saat 11:00'de", "15:30" -> "saat on birde" / "saat on beş otuzda"
    t = re.sub(r"(?:\bsaat\s+)?\b(\d{1,2}:\d{2})(?:\s*'?(?:de|da|te|ta)\b)?",
               lambda m: saat_konusma(m.group(1)) or m.group(0), t)
    # Dolar: "$387,5 milyon" -> "387,5 milyon dolar"; "$83,600" -> "83 bin 600 dolar"
    t = re.sub(r"\$\s?(\d+(?:[.,]\d+)?)\s*(milyon|milyar)\b", r"\1 \2 dolar", t)
    t = re.sub(r"\$\s?(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)", _usd_nokta, t)
    # Türkçe binlik ayraçlı tutar: "83.600 dolar" -> "83 bin 600 dolar"
    t = re.sub(r"\b(\d{1,3}(?:\.\d{3})+)(?=\s*dolar)",
               lambda m: usd_konusma(float(m.group(1).replace(".", ""))), t)
    # Büyük sayılar: "387,5 milyon" -> "387 milyon" (10 ve üstünde küsurat atılır)
    t = re.sub(r"\b(\d{2,})[.,]\d+(\s*(?:milyon|milyar))", r"\1\2", t)
    # Yüzdeler: "%2,5" / "2.5%" -> "yüzde 2,5"
    t = re.sub(r"%\s?(\d+(?:[.,]\d+)?)", lambda m: "yüzde " + m.group(1).replace(".", ","), t)
    t = re.sub(r"(\d+(?:[.,]\d+)?)\s?%", lambda m: "yüzde " + m.group(1).replace(".", ","), t)
    return t


# --------------------------------------------------------------------------- #
# Konuşma metni (deterministik şablon)
# --------------------------------------------------------------------------- #

def _cumle(s):
    s = s.strip().rstrip(";,")
    if not s:
        return s
    s = tr_buyuk_bas(s)
    return s if s[-1] in ".!?" else s + "."


def _parcalar(metin):
    """Metni cümle / noktalı virgül sınırlarından parçalara ayırır."""
    return [p.strip() for p in re.split(r"(?<=[.!?])\s+|;\s*", metin or "") if p.strip()]


def _fiyat_tekrari_mi(parca):
    """'Fiyatlar dar bir bantta yatay seyrediyor' gibi, fiyat cümlesini
    tekrarlayan kısa parçalar (fiyat zaten ayrıca okunuyor)."""
    k = tr_kucuk(parca)
    return len(parca) < 70 and any(x in k for x in ("yatay", "dar bir bant", "dar bant"))


def _tarih(rapor):
    try:
        g = date.fromisoformat(rapor["id"])
        return f"{g.day} {TR_AYLAR[g.month - 1]} {TR_GUNLER[g.weekday()]}"
    except (KeyError, ValueError, TypeError):
        return re.sub(r"\s*\d{4},?", "", rapor.get("title", "")).strip()


def _coin_cumlesi(ad, coin, yatay_ek):
    fiyat = (coin or {}).get("priceUsd")
    if fiyat is None:
        return ""
    tutar = usd_konusma(fiyat)
    ch = (coin or {}).get("change24h")
    if ch is None or abs(ch) < YATAY_ESIGI:
        return f"{ad} {tutar} dolar civarında, {yatay_ek}."
    yon = "artıyla" if ch > 0 else "düşüşle"
    return f"{ad} yüzde {yuzde_konusma(ch)} {yon} {tutar} dolarda."


def _fng_cumlesi(fg):
    if not fg or fg.get("value") is None:
        return ""
    v = int(fg["value"])

    def bant(x):
        if x is None:
            return None
        return 0 if x < 25 else 1 if x < 45 else 2 if x <= 55 else 3 if x < 75 else 4

    durum = ["aşırı korkulu", "korkulu", "kararsız", "açgözlü", "aşırı açgözlü"][bant(v)]
    hala = "hâlâ " if bant(fg.get("previousValue")) == bant(v) else ""
    tag = "[serious]" if v < 45 else "[lighthearted]"
    return f"{tag} Korku ve açgözlülük endeksi {v}, yani piyasa {hala}{durum}."


def _takip(rapor, adet):
    olaylar = rapor["brief"].get("criticalEvents") or rapor.get("sections", {}).get("today") or []
    ifadeler = []
    for e in olaylar[:adet]:
        baslik = telaffuz_duzelt(e.get("title", "")).rstrip(".")
        if not baslik:
            continue
        saat = saat_konusma(e.get("timeTr") or "")
        ifadeler.append(f"{saat} {baslik}" if saat else baslik)
    if not ifadeler:
        return ""
    liste = ifadeler[0] if len(ifadeler) == 1 else ", ".join(ifadeler[:-1]) + " ve " + ifadeler[-1]
    return f"Bugün takip edeceklerimiz: {liste}."


def _kur(rapor, neden_adet, takip_adet, risk_adet):
    b = rapor["brief"]
    coins = rapor.get("market", {}).get("coins", {})
    btc = coins.get("BTC") or {}
    ch = btc.get("change24h")

    s = [f"[cheerful] Günaydın, {_tarih(rapor)}.",
         f"[calm] Piyasanın havası bugün {tr_kucuk(b.get('mood', 'kararsız'))}."]
    for c in (_coin_cumlesi("Bitcoin", btc, "dar bir bantta yatay gidiyor"),
              _coin_cumlesi("Ethereum", coins.get("ETH"), "yatay seyrediyor")):
        if c:
            s.append(c)

    neden = [p for p in _parcalar(b.get("why", "")) if not _fiyat_tekrari_mi(p)] \
        or _parcalar(b.get("why", ""))
    neden = [_cumle(telaffuz_duzelt(p)) for p in neden[:neden_adet]]
    if neden:
        if ch is None or abs(ch) < YATAY_ESIGI:
            soru = "Neden bu sessizlik?"
        else:
            soru = "Peki bu yükseliş neden?" if ch > 0 else "Peki bu düşüş neden?"
        s.append(f"[curious] {soru} [serious] " + " [short pause] ".join(neden))

    takip = _takip(rapor, takip_adet) if takip_adet else ""
    if takip:
        s.append(("[short pause] " if neden else "") + takip)

    risk = [_cumle(telaffuz_duzelt(p)) for p in _parcalar(b.get("mainRisk", ""))[:risk_adet]]
    if risk:
        s.append("[serious] Ana risk şu: [short pause] " + " ".join(risk))

    fng = _fng_cumlesi(rapor.get("market", {}).get("fearGreed"))
    if fng:
        s.append(fng)
    s.append("[calm] Bilgilendirme amaçlıdır, yatırım tavsiyesi değildir.")
    s.append("[warm] Bay bay.")
    return re.sub(r"\s+", " ", " ".join(s)).strip()


# Sınırı aşarsa sırayla kısaltılır (cümle ortasından KESİLMEZ):
# (neden parçası, takip adedi, risk cümlesi)
_KADEMELER = [(3, 3, 2), (2, 3, 1), (2, 2, 1), (1, 2, 1), (1, 1, 1), (1, 0, 1), (0, 0, 1), (0, 0, 0)]


def konusma_metni(rapor, maks=MAKS_KARAKTER):
    """Kanonik rapordan tag'li konuşma metni. Her zaman '[warm] Bay bay.' ile biter."""
    metin = ""
    for kademe in _KADEMELER:
        metin = _kur(rapor, *kademe)
        if len(metin) <= maks:
            return metin
    return metin


# --------------------------------------------------------------------------- #
# ElevenLabs API katmanı
# --------------------------------------------------------------------------- #

class SesHatasi(RuntimeError):
    pass


def anahtar_al(ortam=None, dosya=YEREL_ANAHTAR_DOSYASI):
    """Önce ortam değişkeni; yoksa yerelde ~/.config/elevenlabs/.env."""
    ortam = os.environ if ortam is None else ortam
    anahtar = (ortam.get(ANAHTAR_DEGISKENI) or "").strip()
    if anahtar or not dosya or not os.path.exists(dosya):
        return anahtar
    with open(dosya, encoding="utf-8") as f:
        for satir in f:
            ad, _, deger = satir.strip().partition("=")
            ad = re.sub(r"^export\s+", "", ad.strip())
            if ad == ANAHTAR_DEGISKENI:
                return deger.strip().strip('"').strip("'")
    return ""


class ElevenLabsIstemci:
    """İnce TTS istemcisi. `http` requests uyumlu (post) — testte sahtesi verilir."""

    def __init__(self, api_key, http=None, ses_id=SES_ID, model_id=None,
                 cikti=CIKTI_BICIMI, timeout=HTTP_TIMEOUT, deneme=MAX_DENEME):
        if not api_key:
            raise SesHatasi(f"{ANAHTAR_DEGISKENI} tanımlı değil")
        if http is None:
            import requests
            http = requests
        self._anahtar = api_key
        self.http, self.ses_id, self.model_id = http, ses_id, model_id or ses_modeli()
        self.cikti, self.timeout, self.deneme = cikti, timeout, deneme

    def __repr__(self):                       # anahtar asla görünmesin
        return f"ElevenLabsIstemci(ses_id={self.ses_id!r}, model_id={self.model_id!r})"

    def seslendir(self, metin):
        """(ses_bytes, karakter_maliyeti) döner. 4xx'te tekrar denemez."""
        url = f"{API_TABAN}/v1/text-to-speech/{self.ses_id}"
        son = None
        for i in range(1, self.deneme + 1):
            try:
                r = self.http.post(
                    url, params={"output_format": self.cikti},
                    headers={"xi-api-key": self._anahtar, "Content-Type": "application/json",
                             "Accept": "audio/mpeg"},
                    json=istek_govdesi(metin, self.model_id),
                    timeout=self.timeout)
            except Exception as e:            # noqa: BLE001 — ağ hatası
                son = SesHatasi(f"ağ hatası: {type(e).__name__}")
                continue
            if r.status_code == 200 and r.content:
                basliklar = getattr(r, "headers", {}) or {}
                maliyet = basliklar.get("character-cost") or basliklar.get("x-character-count")
                return r.content, int(maliyet) if str(maliyet or "").isdigit() else len(metin)
            govde = (getattr(r, "text", "") or "")[:200]
            son = SesHatasi(f"HTTP {r.status_code}: {govde}")
            if 400 <= r.status_code < 500 and r.status_code != 429:
                break
        raise son


def mp3_ogg(mp3):
    """MP3 -> Telegram sesli mesajı (OGG/Opus) — ffmpeg gerekir."""
    with tempfile.TemporaryDirectory() as d:
        g, c = os.path.join(d, "s.mp3"), os.path.join(d, "s.ogg")
        with open(g, "wb") as f:
            f.write(mp3)
        subprocess.run(["ffmpeg", "-y", "-i", g, "-c:a", "libopus", "-b:a", "48k", "-ac", "1", c],
                       capture_output=True, check=True)
        with open(c, "rb") as f:
            return f.read()


def ozet_sesleri(rapor, istemci=None, donustur=mp3_ogg, log=None):
    """Rapordan (OGG/Opus, ham MP3). OGG Telegram'a, MP3 web sürümüne kaynak.
    HİÇBİR hatada exception fırlatmaz → (None, None). Tek API çağrısı."""
    log = log or (lambda m: print(m, file=sys.stderr))
    try:
        metin = konusma_metni(rapor)
        istemci = istemci or ElevenLabsIstemci(anahtar_al())
        mp3, maliyet = istemci.seslendir(metin)
        ogg = donustur(mp3)
        log(f"[bilgi] Klon sesli özet hazır ({len(metin)} karakter, maliyet {maliyet}).")
        return ogg, mp3
    except Exception as e:                    # noqa: BLE001
        log(f"[uyarı] Klon sesli özet atlandı: {type(e).__name__}: {e}")
        return None, None


def ozet_ogg(rapor, istemci=None, donustur=mp3_ogg, log=None):
    """Rapordan OGG/Opus sesli özet. HİÇBİR hatada exception fırlatmaz → None."""
    return ozet_sesleri(rapor, istemci=istemci, donustur=donustur, log=log)[0]


# --------------------------------------------------------------------------- #
# Web sürümü: reports/ses/YYYY-MM-DD.mp3 (+ latest.mp3)
# --------------------------------------------------------------------------- #
# Site (dogukanlive.com/bugun/) raporla birlikte bu dosyayı da çekip kendi
# alanından sunuyor. Repo şişmesin diye: mono, düşük bit hızı (~0,5 MB/dk),
# 1 MB üstü yazılmaz, 14 günden eskisi silinir. Hata olursa dosya yazılmaz,
# rapor ve Telegram akışı etkilenmez.

WEB_SES_DIZINI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports", "ses")
WEB_BIT_HIZI = "64k"
WEB_MAKS_BAYT = 1_000_000
WEB_TUT_GUN = 14
_WEB_DOSYA = re.compile(r"^(\d{4}-\d{2}-\d{2})\.mp3$")


def mp3_web(mp3):
    """Ham MP3 -> web için mono 64 kbps MP3 — ffmpeg gerekir."""
    with tempfile.TemporaryDirectory() as d:
        g, c = os.path.join(d, "g.mp3"), os.path.join(d, "c.mp3")
        with open(g, "wb") as f:
            f.write(mp3)
        subprocess.run(["ffmpeg", "-y", "-i", g, "-vn", "-map_metadata", "-1",
                        "-c:a", "libmp3lame", "-b:a", WEB_BIT_HIZI, "-ac", "1", c],
                       capture_output=True, check=True)
        with open(c, "rb") as f:
            return f.read()


def eski_web_sesleri_sil(tarih_id, dizin=WEB_SES_DIZINI, tut_gun=WEB_TUT_GUN):
    """tarih_id dahil son `tut_gun` günden eski YYYY-MM-DD.mp3'leri siler.
    Silinen dosya adlarını döner. Tanımadığı dosyalara dokunmaz."""
    sinir = date.fromisoformat(tarih_id).toordinal() - (tut_gun - 1)
    silinen = []
    for ad in sorted(os.listdir(dizin)):
        m = _WEB_DOSYA.match(ad)
        if not m:
            continue
        try:
            gun = date.fromisoformat(m.group(1)).toordinal()
        except ValueError:
            continue
        if gun < sinir:
            os.remove(os.path.join(dizin, ad))
            silinen.append(ad)
    return silinen


def web_ses_yaz(tarih_id, mp3, dizin=WEB_SES_DIZINI, donustur=mp3_web, log=None,
                maks=WEB_MAKS_BAYT, tut_gun=WEB_TUT_GUN):
    """Web MP3'ünü <dizin>/<tarih_id>.mp3 ve latest.mp3 olarak yazar, eskileri
    siler. Yazılan dosyanın yolunu ya da None döner. ASLA exception fırlatmaz."""
    log = log or (lambda m: print(m, file=sys.stderr))
    try:
        date.fromisoformat(tarih_id)
        if not mp3:
            return None
        web = donustur(mp3)
        if not web or len(web) > maks:
            log(f"[uyarı] Web sesli özet yazılmadı: boyut uygun değil ({len(web or b'')} B).")
            return None
        os.makedirs(dizin, exist_ok=True)
        hedef = os.path.join(dizin, f"{tarih_id}.mp3")
        for yol in (hedef, os.path.join(dizin, "latest.mp3")):
            gecici = yol + ".tmp"
            with open(gecici, "wb") as f:
                f.write(web)
            os.replace(gecici, yol)
        silinen = eski_web_sesleri_sil(tarih_id, dizin, tut_gun)
        log(f"[bilgi] Web sesli özet yazıldı ({len(web)} B)"
            + (f", {len(silinen)} eski dosya silindi." if silinen else "."))
        return hedef
    except Exception as e:                    # noqa: BLE001
        log(f"[uyarı] Web sesli özet yazılmadı: {type(e).__name__}: {e}")
        return None
