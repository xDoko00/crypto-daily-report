"""Video duyurusu: t.me/DogukanLive kanalı + bağlı sohbet grubu.

Ne yapar (Pazartesi 20:00 TSİ YouTube yayını sonrası):
  1) RSS'te yeni UZUN video (Shorts değil) görünce duyuru metnini şablondan
     kurar, duyuru_filtre'den geçirir.
  2) DUYURU_MOD:
       taslak (VARSAYILAN): metin önce Doğukan'a (admin özel) TASLAK gider.
                            Kanala/gruba yalnız `onayla` komutuyla gider.
       sinif:               şablona uyan + filtreden geçen duyuru sınıf
                            onayıyla doğrudan kanal + gruba gider. Geçmezse
                            taslağa düşer.
  3) Kanal gönderisi sabitlenir; kanaldaki önceki sabit kaldırılır.
  4) Kanal gönderisinden 24 saat sonra ikinci dokunuş (kısa, farklı açı, aynı
     link). Aynı mod kuralı geçerli; sabitlenmez.
Durum: state/video-duyuru.json (iş akışı commit'ler). Metin loga yazılmaz.

Komutlar:
  python video_duyuru.py calis                       # zamanlanmış tur
  python video_duyuru.py onayla --video ID [--asama ilk|ikinci] [--metin-dosya F]
  python video_duyuru.py taslak --video ID [--asama ilk|ikinci]   # yalnız ekrana
  --kuru : Telegram'a HİÇBİR çağrı yapılmaz, yapılacaklar ekrana yazılır.

Ortam:
  TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID (kanal), TELEGRAM_ADMIN_CHAT_ID,
  TELEGRAM_SOHBET_ID (varsayılan @DogukanLiveSohbet; '-' = gruba gönderme),
  VIDEO_DUYURU_AKTIF=1 (zamanlanmış tur bu olmadan hiçbir şey yapmaz),
  DUYURU_MOD=taslak|sinif, DUYURU_SABITLE=1, DUYURU_IKINCI=1,
  DUYURU_IKINCI_GRUP=0, DUYURU_PENCERE_SAAT=12, DUYURU_REKLAM_VEREN=<ad>.
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

import requests

import duyuru_filtre
import youtube_rss

KOK = os.path.dirname(os.path.abspath(__file__))
DURUM_YOL = os.path.join(KOK, "state", "video-duyuru.json")
VARSAYILAN_SOHBET = "@DogukanLiveSohbet"
HTTP_TIMEOUT = 20

VARSAYILAN_KANCA = "Tüm detayları videoda adım adım anlatıyorum."
IKINCI_KANCA = "Kısa bir mola ver, videoyu izle. Sorunu da yorumlara yaz, cevaplayayım."


# --------------------------------------------------------------------------- #
# Ayarlar
# --------------------------------------------------------------------------- #

def _env(ad, vars_=""):
    return os.environ.get(ad, vars_).strip()


def mod():
    m = _env("DUYURU_MOD", "taslak").lower()
    return m if m in ("taslak", "sinif") else "taslak"


def _bayrak(ad, varsayilan):
    return _env(ad, varsayilan) not in ("0", "", "hayir", "false")


def sohbet_id():
    s = _env("TELEGRAM_SOHBET_ID") or VARSAYILAN_SOHBET
    return "" if s == "-" else s


def _gizle(s):
    s = str(s)
    tok = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if tok:
        s = s.replace(tok, "***")
    return re.sub(r"bot\d{6,12}:[A-Za-z0-9_-]{10,}", "bot***", s)


# --------------------------------------------------------------------------- #
# Telegram (kuru modda ağ YOK)
# --------------------------------------------------------------------------- #

class Telegram:
    def __init__(self, token, kuru=False):
        self.token = token
        self.kuru = kuru
        self.kayit = []          # kuru modda yapılacak çağrılar
        self._sahte_id = 900000

    def cagir(self, yontem, **params):
        if self.kuru:
            self._sahte_id += 1
            self.kayit.append((yontem, params))
            print(f"[KURU] {yontem} {json.dumps(params, ensure_ascii=False)[:160]}")
            if yontem == "getChat":
                return {"id": params.get("chat_id")}
            if yontem.startswith("send"):
                return {"message_id": self._sahte_id}
            return True
        url = f"https://api.telegram.org/bot{self.token}/{yontem}"
        try:
            r = requests.post(url, json=params, timeout=HTTP_TIMEOUT)
            d = r.json()
        except Exception as e:                       # noqa: BLE001
            raise RuntimeError(f"{yontem} ağ hatası: {_gizle(e)}") from None
        if not d.get("ok"):
            raise RuntimeError(f"{yontem} hatası: {d.get('description')}")
        return d.get("result")

    def mesaj(self, chat_id, metin, onizleme=True):
        return self.cagir("sendMessage", chat_id=chat_id, text=metin,
                          disable_web_page_preview=not onizleme)


# --------------------------------------------------------------------------- #
# Durum
# --------------------------------------------------------------------------- #

def durum_oku(yol=None):
    try:
        with open(yol or DURUM_YOL, encoding="utf-8") as f:
            d = json.load(f)
        d.setdefault("videolar", {})
        return d
    except (FileNotFoundError, ValueError, OSError):
        return {"videolar": {}}


def durum_yaz(d, yol=None):
    yol = yol or DURUM_YOL
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    with open(yol, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)


def _simdi():
    return datetime.now(timezone.utc)


def _iso(dt):
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


# --------------------------------------------------------------------------- #
# Metin
# --------------------------------------------------------------------------- #

def kanca_sec(aciklama):
    """Açıklamanın ilk cümlesi (link yoksa, kısaysa, filtreden geçerse)."""
    for satir in (aciklama or "").splitlines():
        s = satir.strip()
        if not s:
            continue
        if duyuru_filtre._LINK_RE.search(s) or duyuru_filtre.SPONSOR_IZ_RE.search(s):
            return VARSAYILAN_KANCA
        cumle = re.split(r"(?<=[.!?])\s", s, maxsplit=1)[0].strip()
        if 15 <= len(cumle) <= 160:
            return cumle
        return VARSAYILAN_KANCA
    return VARSAYILAN_KANCA


def reklam_veren(video):
    """Reklam veren yalnız videonun açıklamasında/başlığında sponsor izi varsa
    kullanılır; böylece unutulan DUYURU_REKLAM_VEREN sonraki haftanın
    sponsorsuz videosuna 'Reklam:' satırı eklemez."""
    if not sponsor_izi(video):
        return ""
    return _env("DUYURU_REKLAM_VEREN") or video.get("reklam_veren", "")


def sponsor_izi(video):
    return bool(duyuru_filtre.SPONSOR_IZ_RE.search(
        (video.get("aciklama") or "") + " " + (video.get("baslik") or "")))


def metin_kur(video, asama="ilk"):
    link = youtube_rss.kisa_link(video["id"])
    baslik = re.sub(r"\s+", " ", video["baslik"]).strip()
    if asama == "ikinci":
        govde = f"⏰ Dünkü videoyu kaçırdıysan:\n\n{baslik}\n\n{IKINCI_KANCA}\n\n👇\n{link}"
    else:
        govde = (f"🎬 Yeni video yayında!\n\n{baslik}\n\n{kanca_sec(video.get('aciklama'))}"
                 f"\n\nİzlemek için 👇\n{link}")
    rv = reklam_veren(video)
    return f"Reklam: {rv}\n\n{govde}" if rv else govde


def filtrele(video, metin, sablon_zorunlu):
    return duyuru_filtre.hazirla(metin, video["id"], reklam_veren=reklam_veren(video),
                                 sponsor_izi=sponsor_izi(video),
                                 sablon_zorunlu=sablon_zorunlu)


# --------------------------------------------------------------------------- #
# Gönderim
# --------------------------------------------------------------------------- #

def sabitle(tg, kanal_id, yeni_id):
    """Önceki sabiti kaldır, yeni gönderiyi sessizce sabitle. Hata fırlatmaz."""
    notlar = []
    try:
        chat = tg.cagir("getChat", chat_id=kanal_id) or {}
        eski = (chat.get("pinned_message") or {}).get("message_id")
        if eski and eski != yeni_id:
            tg.cagir("unpinChatMessage", chat_id=kanal_id, message_id=eski)
            notlar.append(f"önceki sabit kaldırıldı: {eski}")
        tg.cagir("pinChatMessage", chat_id=kanal_id, message_id=yeni_id,
                 disable_notification=True)
        notlar.append(f"sabitlendi: {yeni_id}")
        return True, notlar
    except Exception as e:                           # noqa: BLE001
        notlar.append(f"sabitleme başarısız: {_gizle(e)}")
        return False, notlar


def yayinla(tg, video, metin, asama, kayit, simdi=None):
    """Filtreden GEÇMİŞ metni kanala (+ gruba) gönderir, kaydı günceller."""
    kanal = _env("TELEGRAM_CHAT_ID")
    admin = _env("TELEGRAM_ADMIN_CHAT_ID")
    grup = sohbet_id()
    sonuc = {"zaman": _iso(simdi or _simdi())}
    k = tg.mesaj(kanal, metin)
    sonuc["kanal_mesaj_id"] = (k or {}).get("message_id")
    notlar = []
    gruba = grup and (asama == "ilk" or _bayrak("DUYURU_IKINCI_GRUP", "0"))
    if gruba:
        try:
            g = tg.mesaj(grup, metin)
            sonuc["grup_mesaj_id"] = (g or {}).get("message_id")
        except Exception as e:                       # noqa: BLE001
            notlar.append(f"sohbet grubuna gönderilemedi: {_gizle(e)}")
    if asama == "ilk" and _bayrak("DUYURU_SABITLE", "1") and sonuc["kanal_mesaj_id"]:
        ok, n = sabitle(tg, kanal, sonuc["kanal_mesaj_id"])
        sonuc["sabit"] = ok
        notlar += n
    sonuc["notlar"] = notlar
    kayit[asama] = dict(kayit.get(asama, {}), durum="gonderildi", **sonuc)
    if admin:
        try:
            tg.mesaj(admin, f"✅ Video duyurusu ({asama}) gönderildi: {video['baslik']}\n"
                            + "\n".join(notlar), onizleme=False)
        except Exception:                            # noqa: BLE001
            pass
    return sonuc


def taslak_gonder(tg, video, metin, asama, kayit, sebep="", simdi=None):
    admin = _env("TELEGRAM_ADMIN_CHAT_ID")
    komut = (f"gh workflow run video-duyuru.yml -R xDoko00/crypto-daily-report "
             f"-f islem=onayla -f video={video['id']} -f asama={asama}")
    ust = (f"📝 TASLAK: video duyurusu ({'ilk' if asama == 'ilk' else '24. saat'})\n"
           + (f"Filtre: {sebep}\n" if sebep else "Filtreden geçti.\n")
           + "Kanala gitmedi. Onay: Alpha'ya 'duyuru onay' yaz ya da:\n" + komut
           + "\n\n──────────\n")
    if admin:
        tg.mesaj(admin, ust + (metin or "(metin yok, filtre engelledi)"), onizleme=False)
    kayit[asama] = dict(kayit.get(asama, {}), durum="taslak", zaman=_iso(simdi or _simdi()),
                        sebep=sebep)


# --------------------------------------------------------------------------- #
# Akış
# --------------------------------------------------------------------------- #

def _kayit_al(durum, video):
    k = durum["videolar"].setdefault(video["id"], {})
    k.setdefault("baslik", video["baslik"])
    k.setdefault("yayin", _iso(video["yayin"]) if isinstance(video["yayin"], datetime)
                 else video["yayin"])
    if video.get("aciklama"):
        k["aciklama"] = video["aciklama"][:500]
    return k


def asamayi_isle(tg, video, asama, kayit, simdi=None):
    """Moda göre: sınıf onayı + filtre geçerse yayınla, değilse taslak."""
    ham = metin_kur(video, asama)
    if mod() == "sinif":
        temiz, sebep = filtrele(video, ham, sablon_zorunlu=True)
        if temiz:
            return "gonderildi", yayinla(tg, video, temiz, asama, kayit, simdi)
        taslak_gonder(tg, video, ham, asama, kayit, sebep, simdi)
        return "taslak", sebep
    temiz, sebep = filtrele(video, ham, sablon_zorunlu=False)
    taslak_gonder(tg, video, temiz or ham, asama, kayit, sebep, simdi)
    return "taslak", sebep


def calis(tg, simdi=None, videolar=None, durum_yol=None):
    """Zamanlanmış tur. Döner: yapılan işlerin listesi."""
    simdi = simdi or _simdi()
    isler = []
    if _env("VIDEO_DUYURU_AKTIF") != "1":
        print("[bilgi] VIDEO_DUYURU_AKTIF=1 değil, hiçbir şey yapılmadı.")
        return isler
    durum = durum_oku(durum_yol)
    if videolar is None:
        videolar = youtube_rss.videolari_cek()
    pencere = timedelta(hours=float(_env("DUYURU_PENCERE_SAAT", "12") or 12))

    # 1) Yeni uzun video -> ilk duyuru
    for v in videolar:
        if v["kisa"] or v["yayin"] > simdi or simdi - v["yayin"] > pencere:
            continue
        if v["id"] in durum["videolar"] and durum["videolar"][v["id"]].get("ilk"):
            continue
        kayit = _kayit_al(durum, v)
        sonuc, ek = asamayi_isle(tg, v, "ilk", kayit, simdi)
        isler.append(("ilk", v["id"], sonuc, ek))
        break   # tur başına tek video

    # 2) 24. saat ikinci dokunuş
    if _bayrak("DUYURU_IKINCI", "1"):
        for vid, kayit in durum["videolar"].items():
            ilk = kayit.get("ilk") or {}
            if ilk.get("durum") != "gonderildi" or kayit.get("ikinci"):
                continue
            t0 = datetime.fromisoformat(ilk["zaman"])
            if not (timedelta(hours=24) <= simdi - t0 <= timedelta(hours=36)):
                continue
            v = {"id": vid, "baslik": kayit["baslik"], "aciklama": kayit.get("aciklama", ""),
                 "yayin": kayit.get("yayin")}
            sonuc, ek = asamayi_isle(tg, v, "ikinci", kayit, simdi)
            isler.append(("ikinci", vid, sonuc, ek))

    durum_yaz(durum, durum_yol)
    return isler


def onayla(tg, video_id, asama="ilk", metin_dosya=None, durum_yol=None, videolar=None):
    """Doğukan'ın tek tek onayı: taslağı (ya da verdiği metni) kanala gönderir."""
    durum = durum_oku(durum_yol)
    kayit = durum["videolar"].get(video_id)
    if kayit is None:
        if videolar is None:
            videolar = youtube_rss.videolari_cek()
        v = next((x for x in videolar if x["id"] == video_id), None)
        if v is None:
            raise SystemExit(f"Video RSS'te yok: {video_id}")
        kayit = _kayit_al(durum, v)
    if (kayit.get(asama) or {}).get("durum") == "gonderildi":
        raise SystemExit(f"Bu aşama zaten gönderilmiş: {video_id} {asama}")
    if asama == "ikinci" and (kayit.get("ilk") or {}).get("durum") != "gonderildi":
        raise SystemExit("İkinci dokunuş için önce ilk duyuru gönderilmiş olmalı.")
    v = {"id": video_id, "baslik": kayit["baslik"], "aciklama": kayit.get("aciklama", ""),
         "yayin": kayit.get("yayin")}
    ham = (open(metin_dosya, encoding="utf-8").read() if metin_dosya
           else metin_kur(v, asama))
    temiz, sebep = filtrele(v, ham, sablon_zorunlu=False)
    if not temiz:
        raise SystemExit(f"Filtre engelledi, gönderilmedi: {sebep}")
    sonuc = yayinla(tg, v, temiz, asama, kayit)
    durum_yaz(durum, durum_yol)
    return sonuc


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("islem", choices=["calis", "onayla", "taslak"])
    ap.add_argument("--video", default="")
    ap.add_argument("--asama", choices=["ilk", "ikinci"], default="ilk")
    ap.add_argument("--metin-dosya", default=None)
    ap.add_argument("--kuru", action="store_true")
    a = ap.parse_args(argv)
    tok = _env("TELEGRAM_BOT_TOKEN")
    if not tok and not a.kuru and a.islem != "taslak":
        print("HATA: TELEGRAM_BOT_TOKEN yok.", file=sys.stderr)
        return 1
    tg = Telegram(tok, kuru=a.kuru)
    if a.islem == "calis":
        for i in calis(tg):
            print("[iş]", i)
    elif a.islem == "onayla":
        if not a.video:
            print("HATA: --video gerekli", file=sys.stderr)
            return 1
        print("[gönderildi]", onayla(tg, a.video, a.asama, a.metin_dosya))
    else:
        d = durum_oku().get("videolar", {}).get(a.video)
        v = ({"id": a.video, "baslik": d["baslik"], "aciklama": d.get("aciklama", "")} if d
             else next((x for x in youtube_rss.videolari_cek() if x["id"] == a.video), None))
        if not v:
            print("Video bulunamadı", file=sys.stderr)
            return 1
        ham = metin_kur(v, a.asama)
        temiz, sebep = filtrele(v, ham, sablon_zorunlu=(mod() == "sinif"))
        print(temiz or ham)
        print("\n[filtre]", "GEÇER" if temiz else f"ENGEL: {sebep}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
