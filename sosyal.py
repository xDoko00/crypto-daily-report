# -*- coding: utf-8 -*-
"""
Sosyal medya + ManyChat otomasyonu (günlük, best-effort)
=========================================================

İki iş:
  1. `paylas`  — Günün dikey videosunu GitHub Release asset'i olarak barındırır
     ve Buffer üzerinden Instagram HİKÂYE + X + TikTok'a `SOSYAL_GECIKME_DK`
     (vars. 30) dakika sonrasına zamanlar. Admin Telegram'a saat + gönderi
     id'leri gider; iptal Buffer'dan silerek yapılır.
  2. `manychat` — ManyChat bot alanı `bugun_ozet`'i günün 3 başlığıyla günceller.

Metinler şablonla üretilir (LLM yok). Kanal çizgisi: kâr vaadi / al-sat /
fiyat tahmini yok — şüpheli kelime görülen platforma gönderilmez, admin uyarılır.

Bayraklar (ortam):
  BUFFER_API_KEY / MANYCHAT_API_KEY   gizli anahtarlar (yoksa uyarıyla atlanır)
  SOSYAL_YAYIN=kapali                 sosyal paylaşımı tamamen kapatır
  SOSYAL_KURU=1                       kuru deneme: istekleri maskeli yazdırır, göndermez
  SOSYAL_GECIKME_DK=30                zamanlama gecikmesi (dakika)
  GH_TOKEN + GITHUB_REPOSITORY        release asset yükleme (`gh` CLI)

Hiçbir hata rapor akışını bozmaz: CLI her durumda 0 ile çıkar.

Kullanım:
  python sosyal.py manychat --rapor rapor.json
  python sosyal.py paylas --rapor rapor.json --video gunaydin.mp4 [--ig-cikti yol]
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

KOK = os.path.dirname(os.path.abspath(__file__))
IST = ZoneInfo("Europe/Istanbul")
TR_AYLAR = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
            "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]

SITE_BUGUN = "dogukanlive.com/bugun"
UYARI = "Yatırım tavsiyesi değildir."
X_SINIR = 280
TIKTOK_SINIR = 2200
MANYCHAT_SINIR = 600
BASLIK_SINIR = 90                 # tek başlık en fazla (karakter)
ETIKETLER = ["#kripto", "#bitcoin", "#günaydınkripto", "#kriptopara", "#ethereum", "#kriptohaber"]

BUFFER_API = "https://api.buffer.com"
ORG_ID = "6ac5fc216cdfcd627dfdac35"
KANALLAR = {                      # sıra = gönderim sırası
    "instagram": "6ac5fc4c6a5c39ccb63d7b1c",   # dogukanlive (hikâye)
    "x": "6ac5fcb16a5c39ccb63d823e",           # DogukanDogan
    "tiktok": "6ac5fc7f6a5c39ccb63d7f09",      # gercekdogukandogan
}
PLATFORM_AD = {"instagram": "Instagram hikâye", "x": "X", "tiktok": "TikTok"}
VARSAYILAN_GECIKME_DK = 30

MANYCHAT_API = "https://api.manychat.com/fb/page/setBotField"
MANYCHAT_ALAN_ID = 5115106        # bugun_ozet

RELEASE_TAG = "gunluk-video"
ASSET_SAKLAMA_GUN = 7
_ASSET_RE = re.compile(r"^gunaydin-(\d{4}-\d{2}-\d{2})(-ig)?\.mp4$")

DURUM_DOSYASI = os.path.join(KOK, "state", "sosyal-son.json")
HTTP_TIMEOUT = 30

# Kanal çizgisi filtresi: tam kelime/ifade eşleşmesi (Türkçe küçük harfle).
# "aldı", "satış", "satın aldı" gibi haber dili TAKILMAZ; emir/vaat kipi takılır.
SUPHELI_IFADELER = [
    "al", "sat", "alın", "satın", "al-sat", "al sat", "satın al", "satın alın",
    "kesin", "kesinlikle", "garanti", "garantili", "garantisi", "uçacak", "patlayacak",
    "kaçırma", "kaçırmayın", "hedef fiyat", "fiyat tahmini", "kazandırır",
    "kazandıracak", "zengin", "kâr vaadi", "kar et", "kâr et", "100x", "10x",
]
_SUPHELI_RE = re.compile(
    r"(?<![\w-])(" + "|".join(re.escape(k) for k in sorted(SUPHELI_IFADELER, key=len, reverse=True))
    + r")(?![\w-])")
# "satın" yalnız başına haberde "satın aldı" olarak geçer; tek başına emir değil.
_SATIN_ALDI_RE = re.compile(r"satın\s+al(?:dı|dığı|ıyor|acak|ım|ma)\w*")


def log(m):
    print(m, file=sys.stderr, flush=True)


def aktions_uyari(m):
    """Actions'ta görünür uyarı satırı (yerelde de zararsız)."""
    print(f"::warning::{m}", flush=True)


# --------------------------------------------------------------------------- #
# Maskeleme
# --------------------------------------------------------------------------- #

def _gizli_degerler(ortam=None):
    ortam = os.environ if ortam is None else ortam
    return [v for k in ("BUFFER_API_KEY", "MANYCHAT_API_KEY", "TELEGRAM_BOT_TOKEN", "GH_TOKEN", "GITHUB_TOKEN")
            if (v := (ortam.get(k) or "").strip())]


def gizle(s, ortam=None):
    s = str(s)
    for v in _gizli_degerler(ortam):
        s = s.replace(v, "***")
    s = re.sub(r"bot\d{6,12}:[A-Za-z0-9_-]{10,}", "bot***", s)
    return re.sub(r"(Bearer\s+)\S+", r"\1***", s)


def maskeli_baslik(basliklar):
    return {k: ("Bearer ***" if k.lower() == "authorization" else v) for k, v in basliklar.items()}


# --------------------------------------------------------------------------- #
# Metinler
# --------------------------------------------------------------------------- #

def tr_kucuk(s):
    return (s or "").replace("İ", "i").replace("I", "ı").lower()


def tarih_kisa(rapor):
    g = date.fromisoformat(rapor["id"])
    return f"{g.day} {TR_AYLAR[g.month - 1]}"


def _kisalt(s, sinir):
    s = re.sub(r"\s+", " ", (s or "").strip()).rstrip(".")
    if len(s) <= sinir:
        return s
    kes = s[:sinir - 1]
    if " " in kes:
        kes = kes[:kes.rfind(" ")]
    return kes.rstrip(" ,;:-") + "…"


def basliklar(rapor, adet=3):
    """Günün başlıkları: önce gündem (agenda) başlıkları, eksikse kritik olaylar."""
    sonuc, gorulen = [], set()
    adaylar = [h.get("title") for h in ((rapor.get("sections") or {}).get("agenda") or [])]
    adaylar += [o.get("title") for o in ((rapor.get("brief") or {}).get("criticalEvents") or [])]
    for b in adaylar:
        b = _kisalt(b, BASLIK_SINIR)
        if b and tr_kucuk(b) not in gorulen:
            sonuc.append(b)
            gorulen.add(tr_kucuk(b))
        if len(sonuc) == adet:
            break
    return sonuc


def supheli_kelimeler(metin):
    """Kanal çizgisine aykırı olabilecek ifadeler (boş liste = temiz)."""
    k = _SATIN_ALDI_RE.sub(" ", tr_kucuk(metin))
    return sorted({m.group(1) for m in _SUPHELI_RE.finditer(k)})


def _madde_metni(ust, bas, alt, sinir, en_az=2):
    """`ust` + başlık maddeleri + `alt`; sınıra sığana kadar başlık azaltır/kısaltır."""
    for n in range(len(bas), 0, -1):
        govde = "\n".join(f"• {b}" for b in bas[:n])
        metin = f"{ust}\n\n{govde}\n\n{alt}" if govde else f"{ust}\n\n{alt}"
        if len(metin) <= sinir and (n >= min(en_az, len(bas)) or n == 1):
            return metin
    # en kısa hâli bile sığmıyorsa: tek başlığı kısalt
    bos = len(f"{ust}\n\n• \n\n{alt}")
    tek = _kisalt(bas[0], max(sinir - bos, 10)) if bas else ""
    return (f"{ust}\n\n• {tek}\n\n{alt}" if tek else f"{ust}\n\n{alt}")[:sinir]


def x_metni(rapor):
    ust = f"Günaydın Kripto · {tarih_kisa(rapor)}"
    alt = f"{SITE_BUGUN}\n{UYARI}"
    return _madde_metni(ust, basliklar(rapor, 3), alt, X_SINIR)


def tiktok_metni(rapor):
    ust = f"Günaydın Kripto · {tarih_kisa(rapor)} — günün kripto özeti"
    alt = f"Detaylar: {SITE_BUGUN}\n{UYARI}\n\n" + " ".join(ETIKETLER)
    return _madde_metni(ust, basliklar(rapor, 3), alt, TIKTOK_SINIR)


def manychat_metni(rapor):
    bas = basliklar(rapor, 3)
    ust = f"📅 {tarih_kisa(rapor)}"
    for n in range(len(bas), -1, -1):
        metin = "\n".join([ust] + [f"• {b}" for b in bas[:n]])
        if len(metin) <= MANYCHAT_SINIR:
            return metin
    return ust


# --------------------------------------------------------------------------- #
# Zamanlama + çift gönderi koruması
# --------------------------------------------------------------------------- #

def gecikme_dk(ortam=None):
    ortam = os.environ if ortam is None else ortam
    try:
        return max(int((ortam.get("SOSYAL_GECIKME_DK") or VARSAYILAN_GECIKME_DK)), 1)
    except ValueError:
        return VARSAYILAN_GECIKME_DK


def due_at(simdi=None, dakika=VARSAYILAN_GECIKME_DK):
    """-> (Buffer için ISO UTC 'Z' metni, TSİ datetime)."""
    simdi = simdi or datetime.now(timezone.utc)
    if simdi.tzinfo is None:
        simdi = simdi.replace(tzinfo=timezone.utc)
    zaman = (simdi + timedelta(minutes=dakika)).astimezone(timezone.utc).replace(second=0, microsecond=0)
    return zaman.strftime("%Y-%m-%dT%H:%M:%S.000Z"), zaman.astimezone(IST)


def gun_araligi(gun):
    """TSİ günün [00:00, ertesi 00:00) aralığı, UTC ISO."""
    bas = datetime.combine(date.fromisoformat(gun), datetime.min.time(), IST)
    son = bas + timedelta(days=1)
    f = "%Y-%m-%dT%H:%M:%S.000Z"
    return bas.astimezone(timezone.utc).strftime(f), son.astimezone(timezone.utc).strftime(f)


def durum_oku(yol=DURUM_DOSYASI):
    try:
        with open(yol, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def durum_yaz(gun, platform, post_id, yol=DURUM_DOSYASI):
    d = durum_oku(yol)
    if d.get("tarih") != gun:
        d = {"tarih": gun, "gonderiler": {}}
    d.setdefault("gonderiler", {})[platform] = post_id
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    with open(yol, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
        f.write("\n")


def durumda_gonderilmis(gun, yol=DURUM_DOSYASI):
    d = durum_oku(yol)
    return set((d.get("gonderiler") or {}).keys()) if d.get("tarih") == gun else set()


# --------------------------------------------------------------------------- #
# HTTP (requests; testlerde sahte nesne enjekte edilir)
# --------------------------------------------------------------------------- #

def _http():
    import requests
    return requests


class Buffer:
    POSTLAR_Q = ("query Postlar($input: PostsInput!, $first: Int) { posts(input: $input, first: $first) "
                 "{ edges { node { id channelId status dueAt via text } } } }")
    OLUSTUR_Q = ("mutation Olustur($input: CreatePostInput!) { createPost(input: $input) { "
                 "... on PostActionSuccess { post { id dueAt status channelId } } "
                 "... on MutationError { message } } }")

    def __init__(self, anahtar, http=None, kuru=False):
        self.anahtar = anahtar or ""
        self.http = http
        self.kuru = kuru

    def _istek(self, sorgu, degiskenler):
        basliklar = {"Authorization": f"Bearer {self.anahtar}", "Content-Type": "application/json"}
        govde = {"query": sorgu, "variables": degiskenler}
        if self.kuru:
            log("[sosyal][KURU] POST " + BUFFER_API + " " + json.dumps(maskeli_baslik(basliklar)))
            log(json.dumps(govde, ensure_ascii=False, indent=1))
            return None
        http = self.http or _http()
        r = http.post(BUFFER_API, json=govde, headers=basliklar, timeout=HTTP_TIMEOUT)
        d = r.json()
        if d.get("errors"):
            raise RuntimeError("Buffer hatası: " + gizle("; ".join(str(e.get("message")) for e in d["errors"])))
        return d.get("data") or {}

    def bugun_zamanlanmis(self, gun):
        """O TSİ günü için API'den (via=api) oluşturulmuş canlı gönderisi olan platformlar."""
        bas, son = gun_araligi(gun)
        ters = {v: k for k, v in KANALLAR.items()}
        veri = self._istek(self.POSTLAR_Q, {"first": 50, "input": {
            "organizationId": ORG_ID,
            "filter": {"channelIds": list(KANALLAR.values()),
                       "status": ["scheduled", "sending", "sent", "needs_approval"],
                       "dueAt": {"start": bas, "end": son}}}})
        if veri is None:
            return set()
        bulunan = set()
        for e in (veri.get("posts") or {}).get("edges") or []:
            n = e.get("node") or {}
            if n.get("via") == "api" and n.get("channelId") in ters:
                bulunan.add(ters[n["channelId"]])
        return bulunan

    def gonderi_girdisi(self, platform, video_url, metin, due):
        girdi = {"channelId": KANALLAR[platform], "schedulingType": "automatic",
                 "mode": "customScheduled", "dueAt": due,
                 "assets": [{"video": {"url": video_url}}]}
        if platform == "instagram":
            girdi["metadata"] = {"instagram": {"type": "story", "shouldShareToFeed": False}}
        else:
            girdi["text"] = metin
        return girdi

    def gonderi_olustur(self, platform, video_url, metin, due):
        veri = self._istek(self.OLUSTUR_Q, {"input": self.gonderi_girdisi(platform, video_url, metin, due)})
        if veri is None:
            return "KURU"
        sonuc = veri.get("createPost") or {}
        if (sonuc.get("post") or {}).get("id"):
            return sonuc["post"]["id"]
        raise RuntimeError("createPost: " + gizle(sonuc.get("message") or "bilinmeyen yanıt"))


def manychat_govdesi(metin):
    return {"field_id": MANYCHAT_ALAN_ID, "field_value": metin}


def manychat_guncelle(rapor, anahtar, http=None, kuru=False):
    metin = manychat_metni(rapor)
    basliklar_ = {"Authorization": f"Bearer {anahtar}", "Content-Type": "application/json",
                  "Accept": "application/json"}
    govde = manychat_govdesi(metin)
    if kuru:
        log("[manychat][KURU] POST " + MANYCHAT_API + " " + json.dumps(maskeli_baslik(basliklar_)))
        log(json.dumps(govde, ensure_ascii=False, indent=1))
        return metin
    http = http or _http()
    r = http.post(MANYCHAT_API, json=govde, headers=basliklar_, timeout=HTTP_TIMEOUT)
    try:
        d = r.json()
    except ValueError:
        d = {}
    if d.get("status") != "success":
        raise RuntimeError(f"ManyChat yanıtı: HTTP {getattr(r, 'status_code', '?')} {gizle(d)[:300]}")
    return metin


# --------------------------------------------------------------------------- #
# Telegram (admin) — düz metin
# --------------------------------------------------------------------------- #

def telegram_bildir(metin, ortam=None, http=None, kuru=False):
    ortam = os.environ if ortam is None else ortam
    if kuru:
        log("[sosyal][KURU] Telegram admin mesajı:\n" + metin)
        return
    tok, chat = (ortam.get("TELEGRAM_BOT_TOKEN") or "").strip(), (ortam.get("TELEGRAM_ADMIN_CHAT_ID") or "").strip()
    if not (tok and chat):
        log("[sosyal] Telegram admin bilgisi yok — bildirim atlandı.")
        return
    try:
        http = http or _http()
        r = http.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                      json={"chat_id": chat, "text": metin[:4000], "disable_web_page_preview": True},
                      timeout=HTTP_TIMEOUT)
        if not r.json().get("ok"):
            raise RuntimeError(str(r.json().get("description")))
    except Exception as e:                    # noqa: BLE001
        log(f"[uyarı] Telegram bildirimi gönderilemedi: {gizle(e)}")


# --------------------------------------------------------------------------- #
# GitHub Release asset barındırma (`gh` CLI)
# --------------------------------------------------------------------------- #

def asset_adlari(gun):
    return f"gunaydin-{gun}.mp4", f"gunaydin-{gun}-ig.mp4"


def silinecek_assetler(adlar, bugun, gun_sayisi=ASSET_SAKLAMA_GUN):
    """Adı `gunaydin-YYYY-MM-DD(-ig).mp4` olup `gun_sayisi` günden eski assetler."""
    sinir = date.fromisoformat(bugun) - timedelta(days=gun_sayisi)
    sil = []
    for ad in adlar:
        m = _ASSET_RE.match(ad)
        if m and date.fromisoformat(m.group(1)) < sinir:
            sil.append(ad)
    return sorted(sil)


def depo_adi(ortam=None):
    ortam = os.environ if ortam is None else ortam
    if ortam.get("GITHUB_REPOSITORY"):
        return ortam["GITHUB_REPOSITORY"]
    try:
        url = subprocess.run(["git", "-C", KOK, "remote", "get-url", "origin"], capture_output=True,
                             text=True, check=True).stdout.strip()
        m = re.search(r"github\.com[:/]([^/]+/[^/.]+)", url)
        if m:
            return m.group(1)
    except Exception:                         # noqa: BLE001
        pass
    return "xDoko00/crypto-daily-report"


def asset_url(depo, ad):
    return f"https://github.com/{depo}/releases/download/{RELEASE_TAG}/{ad}"


class Release:
    def __init__(self, depo, calistir=None, kuru=False):
        self.depo = depo
        self.kuru = kuru
        self.calistir = calistir or (lambda a: subprocess.run(a, capture_output=True, text=True))

    def _gh(self, *args, kontrol=True):
        komut = ["gh", "release", *args, "--repo", self.depo]
        if self.kuru:
            log("[sosyal][KURU] " + " ".join(komut))
            return None
        p = self.calistir(komut)
        if kontrol and p.returncode != 0:
            raise RuntimeError(f"gh release {args[0]} başarısız: {gizle(p.stderr or p.stdout)[:300]}")
        return p

    def hazirla(self):
        p = self._gh("view", RELEASE_TAG, "--json", "assets", kontrol=False)
        if p is None:
            return []
        if p.returncode != 0:
            self._gh("create", RELEASE_TAG, "--prerelease", "--latest=false",
                     "--title", "Günlük video (otomatik)",
                     "--notes", "Günaydın Kripto günlük videoları — sosyal medya zamanlaması için "
                                "geçici barındırma. 7 günden eski dosyalar otomatik silinir.")
            return []
        try:
            return [a["name"] for a in json.loads(p.stdout or "{}").get("assets") or []]
        except ValueError:
            return []

    def yukle(self, yollar):
        self._gh("upload", RELEASE_TAG, *yollar, "--clobber")

    def temizle(self, adlar, bugun):
        silinen = []
        for ad in silinecek_assetler(adlar, bugun):
            try:
                self._gh("delete-asset", RELEASE_TAG, ad, "--yes")
                silinen.append(ad)
            except Exception as e:            # noqa: BLE001
                log(f"[uyarı] Eski asset silinemedi ({ad}): {e}")
        return silinen


def url_erisilebilir(url, http=None):
    try:
        http = http or _http()
        r = http.head(url, allow_redirects=True, timeout=HTTP_TIMEOUT)
        return r.status_code == 200
    except Exception:                         # noqa: BLE001
        return False


# --------------------------------------------------------------------------- #
# Instagram varyantı: son ~3 sn'ye "DM'den BUGÜN yaz" çağrısı
# --------------------------------------------------------------------------- #

IG_CAGRI_SN = 3.0
IG_CAGRI_Y = 1560                 # altyazı merkezi 1430 (cizim.ALTYAZI_Y), Doğan balonu y 1096-1328
IG_CAGRI_YUKSEKLIK = 112          # 1560-1672: IG hikâye alt güvenli alanının (son ~250 px) üstünde
IG_CAGRI_METIN = "DM'den BUGÜN yaz"


def cagri_katmani(yol, w=1080, h=1920):
    """Saydam 1080x1920 PNG: sarı hap içinde siyah yazı + çizilmiş aşağı ok (emoji fontuna güvenmez)."""
    from PIL import Image, ImageDraw
    from video import cizim as cz
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    f = cz.font(58, 800)
    yazi_gen = f.getlength(IG_CAGRI_METIN)
    ok_gen, bosluk, ic = 40, 22, 44
    gen = int(ic + yazi_gen + bosluk + ok_gen + ic)
    x0 = (w - gen) // 2
    y0, y1 = IG_CAGRI_Y, IG_CAGRI_Y + IG_CAGRI_YUKSEKLIK
    d.rounded_rectangle((x0 + 4, y0 + 6, x0 + gen + 4, y1 + 6), radius=(y1 - y0) // 2, fill=(0, 0, 0, 110))
    d.rounded_rectangle((x0, y0, x0 + gen, y1), radius=(y1 - y0) // 2, fill=cz.ACCENT + (255,))
    orta = (y0 + y1) // 2
    d.text((x0 + ic, orta), IG_CAGRI_METIN, font=f, fill=(0, 0, 0, 255), anchor="lm")
    ox = x0 + ic + yazi_gen + bosluk
    sap = 12
    d.rectangle((ox + ok_gen / 2 - sap / 2, orta - 30, ox + ok_gen / 2 + sap / 2, orta + 6), fill=(0, 0, 0, 255))
    d.polygon([(ox, orta + 2), (ox + ok_gen, orta + 2), (ox + ok_gen / 2, orta + 32)], fill=(0, 0, 0, 255))
    im.save(yol)
    return yol


def _sure(yol):
    p = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", yol],
                       capture_output=True, text=True, check=True)
    return float(p.stdout.strip())


def ig_varyant_komutu(girdi, katman, cikti, sure, cagri_sn=IG_CAGRI_SN):
    bas = max(sure - cagri_sn, 0.0)
    filtre = (f"[1:v]format=rgba,fade=t=in:st={bas:.2f}:d=0.3:alpha=1[c];"
              f"[0:v][c]overlay=0:0:enable='gte(t,{bas:.2f})'[v]")
    return ["ffmpeg", "-y", "-v", "error", "-i", girdi, "-framerate", "30", "-loop", "1",
            "-t", f"{sure:.2f}", "-i", katman, "-filter_complex", filtre, "-map", "[v]", "-map", "0:a?",
            "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
            "-profile:v", "high", "-level", "4.1", "-c:a", "copy", "-movflags", "+faststart", cikti]


def ig_varyant_uret(girdi, cikti, calisma):
    katman = cagri_katmani(os.path.join(calisma, "ig-cagri.png"))
    subprocess.run(ig_varyant_komutu(girdi, katman, cikti, _sure(girdi)), check=True)
    return cikti


# --------------------------------------------------------------------------- #
# Akışlar
# --------------------------------------------------------------------------- #

def kapali_mi(ortam=None):
    ortam = os.environ if ortam is None else ortam
    return tr_kucuk((ortam.get("SOSYAL_YAYIN") or "").strip()) in ("kapali", "kapalı", "0", "false", "off")


def kuru_mu(ortam=None):
    ortam = os.environ if ortam is None else ortam
    return (ortam.get("SOSYAL_KURU") or "").strip() == "1"


def paylas(rapor, video, ortam=None, buffer=None, release=None, bildir=None, simdi=None,
           durum_yolu=DURUM_DOSYASI, ig_uret=ig_varyant_uret, erisim=url_erisilebilir, ig_cikti=None):
    """Sosyal zamanlama. -> {platform: post_id}. Asla fırlatmaz."""
    ortam = os.environ if ortam is None else ortam
    kuru = kuru_mu(ortam)
    bildir = bildir or (lambda m: telegram_bildir(m, ortam, kuru=kuru))
    sonuc, sorunlar = {}, []
    try:
        if kapali_mi(ortam):
            log("[sosyal] SOSYAL_YAYIN=kapali — sosyal paylaşım atlandı.")
            return sonuc
        anahtar = (ortam.get("BUFFER_API_KEY") or "").strip()
        if not anahtar and not kuru:
            aktions_uyari("BUFFER_API_KEY tanımlı değil — sosyal paylaşım atlandı.")
            return sonuc
        if not (video and os.path.isfile(video)):
            log("[sosyal] video dosyası yok — sosyal paylaşım atlandı.")
            return sonuc
        gun = rapor["id"]
        buffer = buffer or Buffer(anahtar, kuru=kuru)
        release = release or Release(depo_adi(ortam), kuru=kuru)

        bekleyen = [p for p in KANALLAR if p not in durumda_gonderilmis(gun, durum_yolu)]
        if bekleyen:
            try:
                zaten = buffer.bugun_zamanlanmis(gun)
            except Exception as e:            # noqa: BLE001
                sorunlar.append(f"Buffer gönderi kontrolü yapılamadı, güvenli tarafta kalındı: {gizle(e)}")
                zaten = set(bekleyen)
            bekleyen = [p for p in bekleyen if p not in zaten]
        if not bekleyen:
            log(f"[sosyal] {gun} için gönderiler zaten zamanlanmış — atlandı (çift gönderi koruması).")
            if sorunlar:
                bildir("⚠️ Sosyal medya atlandı:\n" + "\n".join(sorunlar))
            return sonuc

        metinler = {"instagram": "", "x": x_metni(rapor), "tiktok": tiktok_metni(rapor)}
        # IG hikâyesinin metni boş ama videoda aynı başlıklar var: başlıklar
        # filtreye takılırsa hikâye de gönderilmez.
        denetlenen = dict(metinler, instagram="\n".join(basliklar(rapor, 3)))
        for p in list(bekleyen):
            supheli = supheli_kelimeler(denetlenen[p])
            if supheli:
                bekleyen.remove(p)
                sorunlar.append(f"{PLATFORM_AD[p]} gönderilmedi — şüpheli ifade: {', '.join(supheli)}")

        with tempfile.TemporaryDirectory(prefix="sosyal-") as calisma:
            ad, ig_ad = asset_adlari(gun)
            yuklenecek = {}
            if any(p in bekleyen for p in ("x", "tiktok")):
                kopya = os.path.join(calisma, ad)
                shutil.copyfile(video, kopya)
                yuklenecek[ad] = kopya
            if "instagram" in bekleyen:
                try:
                    ig_yol = ig_uret(video, os.path.join(calisma, ig_ad), calisma)
                    yuklenecek[ig_ad] = ig_yol
                    if ig_cikti:
                        shutil.copyfile(ig_yol, ig_cikti)
                except Exception as e:        # noqa: BLE001
                    bekleyen.remove("instagram")
                    sorunlar.append(f"Instagram varyantı üretilemedi: {gizle(e)[:200]}")
            if not bekleyen:
                bildir("⚠️ Sosyal medya: hiçbir platforma gönderilmedi.\n" + "\n".join(sorunlar))
                return sonuc

            mevcut = release.hazirla()
            release.yukle(list(yuklenecek.values()))
            silinen = release.temizle(mevcut, gun)
            if silinen:
                log(f"[sosyal] eski assetler silindi: {', '.join(silinen)}")

            depo = release.depo
            urller = {"instagram": asset_url(depo, ig_ad), "x": asset_url(depo, ad), "tiktok": asset_url(depo, ad)}
            if not kuru:
                for u in sorted({urller[p] for p in bekleyen}):
                    if not erisim(u):
                        raise RuntimeError(f"video URL'i erişilebilir değil: {u}")

            due, yerel = due_at(simdi, gecikme_dk(ortam))
            for p in bekleyen:
                try:
                    pid = buffer.gonderi_olustur(p, urller[p], metinler[p], due)
                    sonuc[p] = pid
                    if not kuru:
                        durum_yaz(gun, p, pid, durum_yolu)
                except Exception as e:        # noqa: BLE001
                    sorunlar.append(f"{PLATFORM_AD[p]} zamanlanamadı: {gizle(e)[:300]}")

        if sonuc:
            satirlar = [f"Sosyal medya: {yerel:%H:%M}'de yayınlanacak "
                        f"({', '.join(PLATFORM_AD[p] for p in sonuc)}). İptal için Buffer'dan sil."]
            satirlar += [f"{PLATFORM_AD[p]}: {pid}" for p, pid in sonuc.items()]
            if sorunlar:
                satirlar += ["", "⚠️ Sorunlar:"] + sorunlar
            bildir("\n".join(satirlar))
        elif sorunlar:
            bildir("⚠️ Sosyal medya: hiçbir platforma gönderilmedi.\n" + "\n".join(sorunlar))
    except Exception as e:                    # noqa: BLE001
        m = f"Sosyal medya adımı başarısız: {type(e).__name__}: {gizle(e)[:400]}"
        log("[uyarı] " + m)
        bildir("⚠️ " + m + ("\n" + "\n".join(sorunlar) if sorunlar else ""))
    return sonuc


def manychat(rapor, ortam=None, http=None, bildir=None):
    """bugun_ozet alanını günceller. -> metin ya da None. Asla fırlatmaz."""
    ortam = os.environ if ortam is None else ortam
    kuru = kuru_mu(ortam)
    bildir = bildir or (lambda m: telegram_bildir(m, ortam, kuru=kuru))
    anahtar = (ortam.get("MANYCHAT_API_KEY") or "").strip()
    if not anahtar and not kuru:
        aktions_uyari("MANYCHAT_API_KEY tanımlı değil — ManyChat güncellemesi atlandı.")
        return None
    try:
        metin = manychat_guncelle(rapor, anahtar, http=http, kuru=kuru)
        log("[manychat] bugun_ozet güncellendi.")
        return metin
    except Exception as e:                    # noqa: BLE001
        m = f"ManyChat bugun_ozet güncellenemedi: {gizle(e)[:300]}"
        log("[uyarı] " + m)
        bildir("⚠️ " + m)
        return None


def main(argv=None):
    ap = argparse.ArgumentParser(description="Sosyal medya zamanlama + ManyChat")
    alt = ap.add_subparsers(dest="komut", required=True)
    m = alt.add_parser("manychat")
    m.add_argument("--rapor", required=True)
    p = alt.add_parser("paylas")
    p.add_argument("--rapor", required=True)
    p.add_argument("--video", required=True)
    p.add_argument("--ig-cikti", default=None, help="IG varyantının bir kopyasını buraya yaz (deneme)")
    a = ap.parse_args(argv)
    try:
        with open(a.rapor, encoding="utf-8") as f:
            rapor = json.load(f)
        if a.komut == "manychat":
            manychat(rapor)
        else:
            paylas(rapor, a.video, ig_cikti=a.ig_cikti)
    except Exception as e:                    # noqa: BLE001
        log(f"[uyarı] sosyal adımı atlandı: {type(e).__name__}: {gizle(e)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
