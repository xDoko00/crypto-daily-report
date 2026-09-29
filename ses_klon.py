# -*- coding: utf-8 -*-
"""Doğukan'ın klon sesiyle ~50-60 sn sesli özet (ElevenLabs).

VARSAYILAN KAPALI. Açmak için ortamda SESLI_OZET_ELEVENLABS=1 ve
ELEVENLABS_API_KEY tanımlı olmalı. Kapalıyken report.py eski edge-tts
sesini kullanmaya devam eder.

- Konuşma metni kanonik rapordan DETERMİNİSTİK şablonla kurulur (LLM yok).
- ElevenLabs audio tag'leri ([calm], [serious] …) sesli okunmaz, tonu verir.
- Hata (API, kota, ffmpeg) rapor akışını ASLA durdurmaz: ozet_ogg() None döner
  ve sebebi loga yazar. Anahtar hiçbir koşulda loglanmaz.
"""
import os
import re
import sys
import subprocess
import tempfile
from datetime import date

# --------------------------------------------------------------------------- #
# Ayarlar
# --------------------------------------------------------------------------- #

BAYRAK = "SESLI_OZET_ELEVENLABS"
ANAHTAR_DEGISKENI = "ELEVENLABS_API_KEY"
YEREL_ANAHTAR_DOSYASI = os.path.expanduser("~/.config/elevenlabs/.env")

API_TABAN = "https://api.elevenlabs.io"
SES_ID = "l4Ygbni4CmTFHmTYdyhD"          # "Dogukan v1"
MODEL_ID = "eleven_v4"
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
KISALTMALAR = {"BTC": "Bitcoin", "ETH": "Ethereum"}


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


def _kesme_duzelt(m):
    ad, ek = m.group(1), m.group(2)
    tur = OZEL_ADLAR.get(ad)
    if tur:
        hal = _hal(ek)
        if hal:
            return f"{ad} {_BAS_ISIM[tur][hal]}"
    if ad.isupper():                 # ABD'nin, HYPE'ın: kısaltmada kesme kalsın
        return f"{ad}'{ek}"
    return ad + ek                   # bilinmeyen ad: kesmeyi kaldır (Bitcoin'in -> Bitcoinin)


def _usd_nokta(m):
    return usd_konusma(float(m.group(1).replace(",", ""))) + " dolar"


def telaffuz_duzelt(metin):
    """LLM'in yazdığı serbest metni sesli okumaya uygun hale getirir."""
    t = re.sub(r"<[^>]+>", "", metin or "")
    t = _EMOJI.sub("", t)
    t = t.replace("’", "'").replace("‘", "'")
    t = t.replace("F&amp;G", "korku açgözlülük endeksi").replace("F&G", "korku açgözlülük endeksi")
    t = re.sub(r"\(\s*TSİ\s*\)|\bTSİ\b", "", t)
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
    # Kesme + ek
    t = re.sub(r"\b([A-Za-zÇĞİÖŞÜçğıöşü][\w.]*?)'([a-zçğıöşü]+)\b", _kesme_duzelt, t)
    # Tek başına kısaltmalar
    for k, v in KISALTMALAR.items():
        t = re.sub(rf"\b{k}\b(?!')", v, t)
    t = re.sub(r"\s+([,.;:])", r"\1", t)
    return re.sub(r"\s+", " ", t).strip()


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

    def __init__(self, api_key, http=None, ses_id=SES_ID, model_id=MODEL_ID,
                 cikti=CIKTI_BICIMI, timeout=HTTP_TIMEOUT, deneme=MAX_DENEME):
        if not api_key:
            raise SesHatasi(f"{ANAHTAR_DEGISKENI} tanımlı değil")
        if http is None:
            import requests
            http = requests
        self._anahtar = api_key
        self.http, self.ses_id, self.model_id = http, ses_id, model_id
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
                    json={"text": metin, "model_id": self.model_id, "language_code": DIL},
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


def ozet_ogg(rapor, istemci=None, donustur=mp3_ogg, log=None):
    """Rapordan OGG/Opus sesli özet. HİÇBİR hatada exception fırlatmaz → None."""
    log = log or (lambda m: print(m, file=sys.stderr))
    try:
        metin = konusma_metni(rapor)
        istemci = istemci or ElevenLabsIstemci(anahtar_al())
        mp3, maliyet = istemci.seslendir(metin)
        ogg = donustur(mp3)
        log(f"[bilgi] Klon sesli özet hazır ({len(metin)} karakter, maliyet {maliyet}).")
        return ogg
    except Exception as e:                    # noqa: BLE001
        log(f"[uyarı] Klon sesli özet atlandı: {type(e).__name__}: {e}")
        return None
