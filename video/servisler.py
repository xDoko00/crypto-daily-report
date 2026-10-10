# -*- coding: utf-8 -*-
"""Dış servis: ElevenLabs zaman damgalı TTS (+ Scribe STT yedeği).

Anahtar hiçbir koşulda loglanmaz / yazdırılmaz. B-roll üretimi (Higgsfield) bu
depoda yok; kütüphane ~/gunaydin-video'da üretilip video/broll/'a kopyalanır.
"""
import base64
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ses_klon as sk                    # noqa: E402  model/ayar/tag temizliği tek merkezde

ELEVEN_ENV = os.path.expanduser("~/.config/elevenlabs/.env")

SES_ID = "l4Ygbni4CmTFHmTYdyhD"
SES_BICIM = "mp3_44100_128"
HTTP_SURE = 120


class ServisHatasi(RuntimeError):
    pass


def anahtar_oku(dosya, ad):
    """Önce yerel .env dosyası (zshrc'deki eski ELEVENLABS_API_KEY'i gölgelemesin), sonra ortam.
    GitHub Actions'ta dosya yoktur; anahtar secret'tan ortama gelir."""
    if os.path.exists(dosya):
        with open(dosya, encoding="utf-8") as f:
            for satir in f:
                k, _, v = satir.strip().partition("=")
                if k.replace("export ", "").strip() == ad:
                    return v.strip().strip('"').strip("'")
    return (os.environ.get(ad) or "").strip()


def seslendir_zamanli(metin, hedef_mp3, log=print, http=None, model=None):
    """POST /with-timestamps -> (mp3 yazılır) dict(alignment, maliyet).
    Model/ayar ses_klon'dan (SES_MODEL); tag'ler model desteklemiyorsa temizlenir."""
    if http is None:
        import requests as http
    anahtar = anahtar_oku(ELEVEN_ENV, "ELEVENLABS_API_KEY")
    if not anahtar:
        raise ServisHatasi("ELEVENLABS_API_KEY yok")
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{SES_ID}/with-timestamps"
    r = http.post(url, params={"output_format": SES_BICIM},
                  headers={"xi-api-key": anahtar, "Content-Type": "application/json"},
                  json=sk.istek_govdesi(metin, model),
                  timeout=HTTP_SURE)
    if r.status_code != 200:
        raise ServisHatasi(f"ElevenLabs HTTP {r.status_code}: {r.text[:200]}")
    d = r.json()
    with open(hedef_mp3, "wb") as f:
        f.write(base64.b64decode(d["audio_base64"]))
    maliyet = r.headers.get("character-cost") or r.headers.get("x-character-count")
    log(f"[ses] ElevenLabs tamam, faturalanan karakter: {maliyet}")
    return {"alignment": d.get("alignment"), "normalized_alignment": d.get("normalized_alignment"),
            "maliyet": int(maliyet) if str(maliyet or "").isdigit() else None}


def scribe_kelimeler(mp3, http=None):
    """Yedek: hizalama yoksa Scribe STT ile kelime zamanları [(kelime, bas, son)]."""
    if http is None:
        import requests as http
    anahtar = anahtar_oku(ELEVEN_ENV, "ELEVENLABS_API_KEY")
    with open(mp3, "rb") as f:
        r = http.post("https://api.elevenlabs.io/v1/speech-to-text",
                      headers={"xi-api-key": anahtar},
                      data={"model_id": "scribe_v1", "language_code": "tur",
                            "timestamps_granularity": "word"},
                      files={"file": ("ses.mp3", f, "audio/mpeg")}, timeout=HTTP_SURE)
    if r.status_code != 200:
        raise ServisHatasi(f"Scribe HTTP {r.status_code}: {r.text[:200]}")
    return [(w["text"], w["start"], w["end"]) for w in r.json().get("words", [])
            if w.get("type", "word") == "word"]
