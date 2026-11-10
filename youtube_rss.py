"""YouTube kanal RSS okuyucu (API anahtarı gerekmez).

Kaynak: https://www.youtube.com/feeds/videos.xml?channel_id=<id>
Son ~15 yüklemeyi verir. Shorts'u bağlantısından ayırırız (/shorts/).
Ağ hatasında boş liste döner; çağıran akışı asla bozmaz.
"""

import os
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

IST = ZoneInfo("Europe/Istanbul")
# @DogukanLive (Doğukan Doğan) kanal kimliği. YT_KANAL_ID ile değişir.
VARSAYILAN_KANAL_ID = "UCtS7LejxzBSeV8w_un1J2qQ"
_NS = {"a": "http://www.w3.org/2005/Atom",
       "yt": "http://www.youtube.com/xml/schemas/2015",
       "media": "http://search.yahoo.com/mrss/"}


def rss_url(kanal_id=None):
    kid = kanal_id or os.environ.get("YT_KANAL_ID", "").strip() or VARSAYILAN_KANAL_ID
    return f"https://www.youtube.com/feeds/videos.xml?channel_id={kid}"


def ayristir(xml_metin):
    """RSS XML -> [{id, baslik, yayin(datetime, aware), link, kisa(bool), aciklama}]
    (yeniden eskiye)."""
    kok = ET.fromstring(xml_metin)
    out = []
    for e in kok.findall("a:entry", _NS):
        vid = (e.findtext("yt:videoId", default="", namespaces=_NS) or "").strip()
        if not vid:
            continue
        link_el = e.find("a:link", _NS)
        link = link_el.get("href", "") if link_el is not None else ""
        yayin = datetime.fromisoformat(
            (e.findtext("a:published", default="", namespaces=_NS) or "").replace("Z", "+00:00"))
        acik = e.findtext("media:group/media:description", default="", namespaces=_NS) or ""
        out.append({
            "id": vid,
            "baslik": (e.findtext("a:title", default="", namespaces=_NS) or "").strip(),
            "yayin": yayin,
            "link": link,
            "kisa": "/shorts/" in link,
            "aciklama": acik,
        })
    out.sort(key=lambda v: v["yayin"], reverse=True)
    return out


def videolari_cek(kanal_id=None, zaman_asimi=15):
    """RSS'i çeker. Hata olursa [] (best-effort)."""
    try:
        r = requests.get(rss_url(kanal_id), timeout=zaman_asimi,
                         headers={"User-Agent": "Mozilla/5.0 (crypto-daily-report)"})
        if r.status_code != 200:
            return []
        return ayristir(r.text)
    except Exception:                                # noqa: BLE001
        return []


def kisa_link(video_id):
    return f"https://youtu.be/{video_id}"


def son_pazartesi_videosu(videolar, simdi=None, gun=7):
    """Son `gun` gün içinde Pazartesi (TSİ) yayınlanmış en yeni UZUN video (Shorts değil)."""
    simdi = simdi or datetime.now(IST)
    for v in videolar:
        if v["kisa"]:
            continue
        y = v["yayin"].astimezone(IST)
        if y > simdi or simdi - y > timedelta(days=gun):
            continue
        if y.weekday() == 0:
            return v
    return None
