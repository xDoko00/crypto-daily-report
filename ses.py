# -*- coding: utf-8 -*-
"""45 saniyelik sesli özet üretimi (edge-tts + ffmpeg). Ücretsiz, Türkçe doğal ses.
Brief'i (60 SANİYE) akıcı bir konuşma metnine çevirip Telegram sesli mesajı (OGG/Opus) üretir."""
import os
import re
import asyncio
import tempfile
import subprocess

import edge_tts

VARSAYILAN_SES = "tr-TR-AhmetNeural"   # erkek; kadın: tr-TR-EmelNeural

# Emoji ve süs karakterlerini temizlemek için (⏰, ⚡, 🌡️, ⚠️ vb. dahil)
_EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF\U00002300-\U000027BF\U00002190-\U000021FF"
    "\U00002B00-\U00002BFF️₿Ξ]"
)


def seslendirme_metni(brief, tarih=""):
    """Brief'ten Hava/Neden/Kritik/Risk alanlarını çıkarıp akıcı bir konuşma metni derler.
    Fiyatlar sese konmaz (onlar kartta görsel)."""
    duz = re.sub(r"<[^>]+>", "", brief)

    def sonra(anahtar):
        for s in duz.splitlines():
            if anahtar in s:
                return s.split(anahtar, 1)[1].strip()
        return ""

    hava = sonra("Hava:").split("·")[0].strip()
    neden = sonra("Neden:")
    kritik = sonra("Kritik:")
    risk = sonra("Risk:")

    parcalar = ["Günaydın."]
    if tarih:
        parcalar.append(tarih + ".")
    if hava:
        parcalar.append(f"Piyasa havası {hava}.")
    if neden:
        parcalar.append(f"Nedeni: {neden}")
    if kritik:
        parcalar.append(f"Bugün öne çıkan saatler: {kritik}")
    if risk:
        parcalar.append(f"Günün ana riski: {risk}")
    parcalar.append("Detaylar kanalda. Yatırım tavsiyesi değildir.")

    t = " ".join(parcalar)
    t = t.replace("F&amp;G", "korku açgözlülük endeksi").replace("F&G", "korku açgözlülük endeksi")
    t = _EMOJI.sub("", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


async def _mp3_uret(metin, ses):
    communicate = edge_tts.Communicate(metin, ses)
    buf = bytearray()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            buf.extend(chunk["data"])
    return bytes(buf)


def ses_uret(brief, tarih="", ses=VARSAYILAN_SES):
    """Brief'ten Telegram sesli mesajı (OGG/Opus) bytes üretir."""
    metin = seslendirme_metni(brief, tarih)
    if len(metin) < 20:
        raise RuntimeError("Seslendirme metni çok kısa")
    mp3 = asyncio.run(_mp3_uret(metin, ses))
    with tempfile.TemporaryDirectory() as d:
        mp3p = os.path.join(d, "s.mp3")
        oggp = os.path.join(d, "s.ogg")
        with open(mp3p, "wb") as f:
            f.write(mp3)
        # Telegram sesli mesaj = OGG/Opus
        subprocess.run(
            ["ffmpeg", "-y", "-i", mp3p, "-c:a", "libopus", "-b:a", "48k", "-ac", "1", oggp],
            capture_output=True, check=True,
        )
        with open(oggp, "rb") as f:
            return f.read()


if __name__ == "__main__":
    ornek = ('📊 <b>GÜNAYDIN — 18 Temmuz, Cumartesi</b>\n\n⚡ <b>60 SANİYE</b>\n'
             '🌡️ Hava: Temkinli · F&amp;G 27 (dün 25)\n₿ BTC $64.000 · Ξ ETH $1.840\n'
             '🔑 <b>Neden:</b> Fed tutanakları şahin algılandı, risk iştahı düştü.\n'
             '⏰ <b>Kritik:</b> 15:30 ABD TÜFE, 21:00 işsizlik.\n'
             '⚠️ <b>Risk:</b> TÜFE beklenti üstü gelirse sert satış.')
    print("Metin:", seslendirme_metni(ornek, "18 Temmuz Cumartesi"))
    ogg = ses_uret(ornek, "18 Temmuz Cumartesi")
    open("ses_ornek.ogg", "wb").write(ogg)
    print("ses_ornek.ogg:", len(ogg), "byte")
