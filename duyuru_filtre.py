"""Video duyurusu çıkış filtresi (kod, model değil).

kanal_filtre.py'nin iç işaret / dosya yolu / model konuşması / sinyal
denetimlerini kullanır; üstüne duyuruya özel kurallar:
  - tek link: yalnız o videonun https://youtu.be/<id> linki (borsa referans
    linki ya da başka link gitmez)
  - kâr vaadi dili yok: garanti, risksiz, güvenli kazanç, uyurken kazan...
  - em tire yok (temizlenir)
  - sponsorlu videoda ilk satır 'Reklam: <reklam veren>' (Reklam Yönetmeliği
    md.23/A). Açıklamada reklam/sponsor izi var ama reklam veren bilinmiyorsa
    ENGEL (taslak olarak Doğukan'a gider).
  - şablon kontrolü (sınıf onayı için): metin şablondan çıkmış olmalı.
Log'a metnin kendisi yazılmaz (repo herkese açık).
"""

import os
import re

import kanal_filtre

KOK = os.path.dirname(os.path.abspath(__file__))
LOG_YOL = os.path.join(KOK, "state", "duyuru-filtre-log.jsonl")
LIMIT = 1000

_LINK_RE = re.compile(r"(https?://\S+|t\.me/\S+|www\.\S+)", re.IGNORECASE)
_VAAT_RE = re.compile(
    r"(garanti|risksiz|güvenli kazanç|guvenli kazanc|uyurken kazan|pasif gelir|"
    r"kesin kâr|kesin kar\b|zengin ol|katla(?:yın|)\b|\bx\d+\b|fiyat tahmin|"
    r"referans kod|ref kod|davet kod)",
    re.IGNORECASE)
SPONSOR_IZ_RE = re.compile(r"(#?reklam\b|sponsor|işbirliği|iş birliği|#ad\b|paid partnership)",
                           re.IGNORECASE)
# Şablon ilk satırları (video_duyuru.py metinleri bunlarla başlar).
SABLON_BASLAR = ("🎬 Yeni video yayında!", "⏰ Dünkü videoyu kaçırdıysan:")


def _govde(metin):
    """Reklam satırı hariç gövde."""
    satir = metin.strip().splitlines()
    if satir and satir[0].startswith("Reklam: "):
        satir = satir[1:]
    return "\n".join(satir).strip()


def kontrol(metin, video_id, reklam_veren="", sponsor_izi=False, sablon_zorunlu=False):
    """(gecer_mi, sebep). metin em tiresi temizlenmiş olmalı."""
    if metin is None or not str(metin).strip():
        return False, "bos metin"
    m = str(metin).strip()
    if "[SILENT]" in m.upper():
        return False, "[SILENT] işareti"
    if "—" in m:
        return False, "em tire var"
    if len(m) > LIMIT:
        return False, f"çok uzun: {len(m)} karakter (en çok {LIMIT})"

    beklenen = f"https://youtu.be/{video_id}"
    linkler = _LINK_RE.findall(m)
    if linkler != [beklenen]:
        return False, f"link kuralı: yalnız {beklenen} olmalı, bulunan {linkler}"

    ilk = m.splitlines()[0].strip()
    if reklam_veren:
        if ilk != f"Reklam: {reklam_veren}":
            return False, f"sponsorlu: ilk satır 'Reklam: {reklam_veren}' olmalı"
    elif ilk.startswith("Reklam:"):
        pass
    elif sponsor_izi:
        return False, "sponsor izi var ama reklam veren belirsiz: 'Reklam: <reklam veren>' satırı gerekli"

    if sablon_zorunlu and not _govde(m).startswith(SABLON_BASLAR):
        return False, "şablon dışı metin: sınıf onayı yalnız şablon metne geçer"

    duz = re.sub(r"<[^>]+>", " ", m).replace(beklenen, " ")
    for k in kanal_filtre._KOK_RE.finditer(duz):
        devami = duz[k.start():k.start() + 20].lower()
        if any(devami.startswith(ist) for ist in kanal_filtre._ISTISNA_ON_EK):
            continue
        return False, f"iç işaret: '{k.group(0)}'"
    for ad, rx in (("iç işaret (ajan adı)", kanal_filtre._AD_RE),
                   ("dosya yolu/uzantı", kanal_filtre._YOL_RE),
                   ("model üst konuşması", kanal_filtre._META_RE),
                   ("kâr vaadi/sinyal", kanal_filtre._SINYAL_RE),
                   ("kâr vaadi", _VAAT_RE)):
        s = rx.search(duz)
        if s:
            return False, f"{ad}: '{s.group(0)}'"
    return True, ""


def hazirla(metin, video_id, reklam_veren="", sponsor_izi=False, sablon_zorunlu=False,
            log_yol=None):
    """(temiz | None, sebep). None dönerse kanala/gruba HİÇBİR ŞEY gitmez."""
    temiz = kanal_filtre.em_tire_temizle(metin or "").strip()
    ok, sebep = kontrol(temiz, video_id, reklam_veren, sponsor_izi, sablon_zorunlu)
    if not ok:
        kanal_filtre.logla("duyuru: " + sebep, temiz, log_yol=log_yol or LOG_YOL)
        return None, sebep
    return temiz, ""
