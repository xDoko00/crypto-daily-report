# -*- coding: utf-8 -*-
"""ElevenLabs'e giden metnin okunuş sözlüğü (tek merkez).

Yeni girdi = ilgili sözlüğe tek satır. Anlam çevirisi burada YAPILMAZ
(o iş video/senaryo.py SES_TERIMLERI'nde); burada yalnız okunuş değişir.
"""
import difflib
import re

# Kısaltmalar: Doğukan'ın kulakla seçtiği okunuşlar (İngilizce harf adları). Büyük harfli
# tam kelime eşleşir. Küçük harfle başlayan okunuş (ör. "yapay zekâ") cins isimdir, kesme işareti almaz.
HARF_HARF = {
    "ETF": "İtief",
    "CFTC": "Si-Ef-Ti-Si",        # "Sieftisi" ElevenLabs'te "Siftisi" okundu (6 Eki)
    "SEC": "Es-İ-Si",
    "FOMC": "Ef-O-Em-Si",
    "CPI": "Si-Pi-Ay",
    "PMI": "Piemay",
    "PCE": "Pi-Si-İ",
    "ISM": "Ay-Es-Em",
    "OTC": "Otisi",
    "ABD": "A-Be-De",
    "DCA": "Decea",
    "NFT": "Enefti",
    "BNB": "Bi-En-Bi",
    "TVL": "Ti-Vi-El",
    "ATH": "Atehaş",
    "KYC": "Key-Vay-Si",
    "AI": "yapay zekâ",          # sözlük kararı: "Ay Ay" değil
}

# Coin sembolleri: yalnız büyük harfli tam kelime ("LINK" değişir, "link" değişmez).
COINLER = {
    "BTC": "Bitcoin",
    "ETH": "Ethereum",
    "SOL": "Solana",
    "XRP": "Ripıl",
    "ENA": "Ena",
    "HYPE": "Hayp",
    "DOGE": "Doge",
    "ADA": "Kardano",
    "AVAX": "Avaks",
    "LINK": "Çeynlink",
    "TRX": "Tron",
    "DOT": "Polkadot",
    "LTC": "Laytkoin",
    "SHIB": "Şiba",
}

# İngilizce terim ve adlar: fonetik yazım. Büyük/küçük harf duyarsız, Türkçe eki korunur
# (stakingde -> steykingde). Baş harf büyükse okunuşun baş harfi de büyük olur.
TERIMLER = {
    "staking": "steyking",
    "airdrop": "erdrop",
    "altcoin": "altkoin",
    "stablecoin": "steybılkoin",
    "hyperliquid": "Hayperlikuid",
    "binance": "Baynens",
    "coinbase": "Koinbeys",
    "ripple": "Ripıl",
    "chainlink": "Çeynlink",
    "ethena": "Etina",
    "cardano": "Kardano",
}
# Harf duyarlı terimler (küçük harfli hâli Türkçe bir kelimeyle çakışabilir: "defin").
TERIMLER_DUYARLI = {
    "DeFi": "difay",
    "DEFI": "difay",
}

_INCE = set("eiöü")
_UNLU = set("aeıioöuüâîû")
_SERT = set("fstkçşhp")
_EK = r"[a-zçğıöşü]+"


def _kucuk(s):
    return s.replace("İ", "i").replace("I", "ı").lower()


def _bas_buyuk(s):
    return ({"i": "İ", "ı": "I"}.get(s[0], s[0].upper()) + s[1:]) if s else s


def _son_unlu(s):
    for h in reversed(_kucuk(s)):
        if h in _UNLU:
            return {"â": "a", "î": "i", "û": "u"}.get(h, h)
    return "e"


def _uyumla(ek, son):
    """Ekteki ünlüleri `son` ünlüsünden başlayarak büyük/küçük ünlü uyumuna göre yeniden yazar."""
    cikti = []
    for h in ek:
        if h in "ea":
            h = "e" if son in _INCE else "a"
        elif h in "ıiuü":
            if son in "ei":
                h = "i"
            elif son in "aı":
                h = "ı"
            elif son in "öü":
                h = "ü"
            else:
                h = "u"
        if h in _UNLU:
            son = h
        cikti.append(h)
    return "".join(cikti)


def ek_uyumla(okunus, ek):
    """Kısaltmanın eki, yeni okunuşa göre: ("Es-İ-Si", "in") -> "nin", ("Solana", "ü") -> "yı"."""
    ek = _kucuk(ek)
    sonu_unlu = _kucuk(okunus)[-1] in _UNLU
    kaynastirma = ""
    if ek[:1] in ("n", "y", "s") and ek[1:2] in _UNLU:
        kaynastirma, ek = ek[0], ek[1:]
    elif ek.startswith("yl"):
        ek = ek[1:]
    ek = _uyumla(ek, _son_unlu(okunus))
    if ek[:1] in ("d", "t"):
        ek = ("t" if _kucuk(okunus)[-1] in _SERT else "d") + ek[1:]
    if sonu_unlu and ek[:1] in _UNLU:
        if not kaynastirma:
            kaynastirma = "n" if ek in ("ın", "in", "un", "ün") else "y"
        ek = kaynastirma + ek
    elif sonu_unlu and ek in ("le", "la"):
        ek = "y" + ek
    return ek


def _kisaltma(okunus):
    def degis(m):
        ek = m.group(1)
        if not ek:
            return okunus
        yeni = ek_uyumla(okunus, ek)
        return okunus + yeni if okunus[:1].islower() else f"{okunus}'{yeni}"
    return degis


def _terim(okunus):
    def degis(m):
        bas = m.group(1)
        yeni = _bas_buyuk(okunus) if bas[:1].isupper() else okunus
        return yeni + m.group(2)
    return degis


def donustur(metin):
    """Kısaltma, coin sembolü ve İngilizce terimleri Türkçe okunuşa çevirir."""
    t = metin
    for sozluk in (HARF_HARF, COINLER):
        for k, v in sozluk.items():
            t = re.sub(rf"(?<![\w']){k}(?:'({_EK}))?(?![\w'])", _kisaltma(v), t)
    for k, v in TERIMLER.items():
        t = re.sub(rf"(?<![\w])({k})({_EK}|)(?![\w])", _terim(v), t, flags=re.IGNORECASE)
    for k, v in TERIMLER_DUYARLI.items():
        t = re.sub(rf"(?<![\w]){k}({_EK}|)(?![\w])", rf"{v}\1", t)
    return t


def donustur_eslemeli(metin):
    """donustur + kelime düzeyinde eşleme: (yeni, [(okunus_kelimeleri, orijinal_kelimeler)]).
    Kelimeler kenar noktalaması olmadan, metindeki sırayla döner (altyazıda geri çevirmek için)."""
    yeni = donustur(metin)
    a, b = metin.split(), yeni.split()
    eslemeler = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op != "replace":
            continue
        tek = [(donustur(k).split(), [k]) for k in a[i1:i2]]
        if sum((o for o, _ in tek), []) != b[j1:j2]:
            tek = [(b[j1:j2], a[i1:i2])]
        eslemeler.extend((tuple(_cekirdek(k) for k in o), tuple(_cekirdek(k) for k in g))
                         for o, g in tek if o != g)
    return yeni, eslemeler


def _cekirdek(kelime):
    return re.sub(r"^\W+|[^\w']+$", "", kelime)
