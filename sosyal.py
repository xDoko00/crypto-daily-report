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
  SOSYAL_TASLAK=1                     taslak testi: Buffer'da TASLAK (saveToDraft) oluşturur,
                                      yayınlamaz; çift gönderi kilidi okunmaz/yazılmaz,
                                      release asset adları `-test` ekli
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
# Kanal kimlikleri sabit DEĞİL: hesap Buffer'a yeniden bağlanınca id değişir
# (8 Eki 2026'da IG hikâyesi böyle kayboldu). Her çalışmada `channels`
# sorgusuyla servis (+ hesap adı) eşleşmesinden bulunur.
PLATFORMLAR = ("instagram", "x", "tiktok")       # sıra = gönderim sırası
BUFFER_SERVIS = {"instagram": "instagram", "x": "twitter", "tiktok": "tiktok"}
BEKLENEN_HESAP = {"instagram": "dogukanlive", "x": "DogukanDogan", "tiktok": "gercekdogukandogan"}
VIA_BUFFER = ("api", "buffer")
CANLI_DURUMLAR = ("scheduled", "sending", "sent", "needs_approval")
PLATFORM_AD = {"instagram": "Instagram hikâye", "x": "X", "tiktok": "TikTok"}
VARSAYILAN_GECIKME_DK = 30

MANYCHAT_API = "https://api.manychat.com/fb/page/setBotField"
MANYCHAT_ALAN_ID = 5115106        # bugun_ozet

RELEASE_TAG = "gunluk-video"
ASSET_SAKLAMA_GUN = 7
_ASSET_RE = re.compile(r"^gunaydin-(\d{4}-\d{2}-\d{2})(-test)?(-ig)?\.mp4$")

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
                 "... on PostActionSuccess { post { id dueAt status channelId error { message } } } "
                 "... on MutationError { __typename message } } }")
    KANALLAR_Q = ("query Kanallar($input: ChannelsInput!) { channels(input: $input) "
                  "{ id service name isDisconnected isLocked } }")

    def __init__(self, anahtar, http=None, kuru=False, taslak=False, kanallar=None):
        self.anahtar = anahtar or ""
        self.http = http
        self.kuru = kuru
        self.taslak = taslak
        self.kanallar = dict(kanallar or {})      # platform -> kanal id (kanallari_bul doldurur)

    def kanallari_bul(self):
        """Buffer'daki kanallardan platform -> id eşlemesini kurar.

        -> (eşleme, sorunlar). Kopuk/kilitli ya da bulunamayan platform eşlemeye
        girmez, sorunlara yazılır. Sorgu başarısızsa fırlatır (çağıran hiçbir
        platforma göndermez)."""
        veri = self._istek(self.KANALLAR_Q, {"input": {"organizationId": ORG_ID}})
        if veri is None:                          # kuru deneme: yer tutucu id
            self.kanallar = {p: f"<{BUFFER_SERVIS[p]}-kanal>" for p in PLATFORMLAR}
            return dict(self.kanallar), []
        kanallar = veri.get("channels")
        if not isinstance(kanallar, list):
            raise RuntimeError("Buffer kanal listesi beklenmeyen biçimde")
        eslesme, sorunlar = {}, []
        for p in PLATFORMLAR:
            adaylar = [k for k in kanallar if (k.get("service") or "").lower() == BUFFER_SERVIS[p]]
            beklenen = BEKLENEN_HESAP[p].lower()
            if len(adaylar) > 1:
                adli = [k for k in adaylar if (k.get("name") or "").lower() == beklenen]
                adaylar = adli or adaylar
                # aynı ada birden çok kanal varsa bağlı olan önce
                adaylar.sort(key=lambda k: bool(k.get("isDisconnected") or k.get("isLocked")))
            if not adaylar:
                sorunlar.append(f"Buffer'da {PLATFORM_AD[p]} kanalı bulunamadı — "
                                f"{BEKLENEN_HESAP[p]} hesabını Buffer'a bağla.")
                continue
            k = adaylar[0]
            if (k.get("name") or "").lower() != beklenen:
                log(f"[sosyal] uyarı: {PLATFORM_AD[p]} kanal adı '{k.get('name')}' "
                    f"(beklenen '{BEKLENEN_HESAP[p]}') — yine de kullanılıyor.")
            if k.get("isDisconnected") or k.get("isLocked"):
                neden = "bağlantısı kopmuş" if k.get("isDisconnected") else "kanalı kilitli"
                sorunlar.append(f"Buffer'da {PLATFORM_AD[p]} ({k.get('name')}) {neden}, yeniden bağla — "
                                f"bugün {PLATFORM_AD[p]} gönderilmedi.")
                continue
            eslesme[p] = k["id"]
        self.kanallar = eslesme
        return dict(eslesme), sorunlar

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
            raise RuntimeError("Buffer hatası: " + gizle("; ".join(
                str(e.get("message")) + (f" [{c}]" if (c := (e.get("extensions") or {}).get("code")) else "")
                for e in d["errors"])))
        return d.get("data") or {}

    def bugun_zamanlanmis(self, gun):
        """O TSİ günü için Buffer üzerinden oluşturulmuş canlı gönderisi olan platformlar.

        API ile oluşturulan gönderiler yanıtta `via=buffer` geliyor (8 Eki 2026'da
        doğrulandı; `api` de kabul edilir). `network` = uygulamadan doğrudan
        paylaşım, sayılmaz. Buffer arayüzünden elle zamanlanan gönderi de
        sayılır: o gün o platforma ikinci kez gönderilmez.

        Yalnız canlı durumlar sayılır; taslak (draft) SAYILMAZ (taslak testi
        gerçek zamanlamayı engellememeli), `error` da sayılmaz. Durum süzgeci
        istemcide: Buffer `status` filtresine birden çok değer verilince boş
        dönüyor (8 Eki 2026'da doğrulandı)."""
        bas, son = gun_araligi(gun)
        if not self.kanallar:
            return set()
        ters = {v: k for k, v in self.kanallar.items()}
        veri = self._istek(self.POSTLAR_Q, {"first": 50, "input": {
            "organizationId": ORG_ID,
            "filter": {"channelIds": list(self.kanallar.values()),
                       "dueAt": {"start": bas, "end": son}}}})
        if veri is None:
            return set()
        bulunan = set()
        for e in (veri.get("posts") or {}).get("edges") or []:
            n = e.get("node") or {}
            if n.get("via") in VIA_BUFFER and n.get("channelId") in ters and n.get("status") in CANLI_DURUMLAR:
                bulunan.add(ters[n["channelId"]])
        return bulunan

    def gonderi_girdisi(self, platform, video_url, metin, due):
        if platform not in self.kanallar:
            raise RuntimeError(f"{PLATFORM_AD[platform]} için Buffer kanalı çözülmedi")
        girdi = {"channelId": self.kanallar[platform], "schedulingType": "automatic",
                 "mode": "customScheduled", "dueAt": due,
                 "assets": [{"video": {"url": video_url}}]}
        if platform == "instagram":
            girdi["metadata"] = {"instagram": {"type": "story", "shouldShareToFeed": False}}
        else:
            girdi["text"] = metin
        if self.taslak:
            girdi["saveToDraft"] = True       # yayınlanmaz; dueAt yalnız bilgi amaçlı kalır
        return girdi

    def gonderi_olustur(self, platform, video_url, metin, due):
        veri = self._istek(self.OLUSTUR_Q, {"input": self.gonderi_girdisi(platform, video_url, metin, due)})
        if veri is None:
            return "KURU"
        sonuc = veri.get("createPost") or {}
        post = sonuc.get("post") or {}
        if post.get("id"):
            hata = (post.get("error") or {}).get("message")
            if post.get("status") == "error" or hata:
                raise RuntimeError(f"Buffer gönderiyi oluşturdu ama hatalı işaretledi (id {post['id']}, "
                                   f"durum {post.get('status')}): " + gizle(hata or "ayrıntı yok"))
            return post["id"]
        tur = sonuc.get("__typename") or "MutationError"
        raise RuntimeError(f"Buffer reddetti ({tur}): " + gizle(sonuc.get("message") or "bilinmeyen yanıt"))


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

def asset_adlari(gun, test=False):
    ek = "-test" if test else ""
    return f"gunaydin-{gun}{ek}.mp4", f"gunaydin-{gun}{ek}-ig.mp4"


def silinecek_assetler(adlar, bugun, gun_sayisi=ASSET_SAKLAMA_GUN):
    """Adı `gunaydin-YYYY-MM-DD(-test)(-ig).mp4` olup `gun_sayisi` günden eski assetler."""
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
# Instagram varyantı: video boyunca küçük "DM'den BUGÜN yaz" hapı (her ~5 sn
# kısa nabız) + son ~3 sn'de büyük çağrı. X ve TikTok'a orijinal gider.
# --------------------------------------------------------------------------- #

IG_CAGRI_SN = 3.0
IG_CAGRI_METIN = "DM'den BUGÜN yaz"
# Yerleşim (1080x1920): kartlar/altyazı (merkez cizim.ALTYAZI_Y=1430, iki satırda
# alt kenar ~1500), Doğan balonu (y 1096-1328) ve ilerleme çubuğu (üst) dışında
# kalan boş bant y≈1540-1700. IG hikâye arayüzü üst ~250 px ve alt ~200 px'i
# (y>1720) kapattığı için ikisi de bu bandın içinde.
IG_CAGRI_Y = 1560                 # büyük çağrı: y 1560-1672, yatay ortalı
IG_CAGRI_YUKSEKLIK = 112
IG_HAP_MERKEZ = (540, 1610)       # küçük hap: ~494x76 (gölgesiz), x≈293-787, y≈1572-1648
IG_HAP_YUKSEKLIK = 76
IG_NABIZ_ARALIK = 5.0             # sn
IG_NABIZ_SURE = 0.5               # sn
IG_NABIZ_GENLIK = 0.12            # %12 büyüyüp küçülür


def hap_ciz(yukseklik, yazi_boyut, ic, ok_gen, golge=True):
    """Kırpılmış RGBA hap: sarı zemin, siyah yazı + çizilmiş aşağı ok (emoji fontuna güvenmez)."""
    from PIL import Image, ImageDraw
    from video import cizim as cz
    f = cz.font(yazi_boyut, 800)
    yazi_gen = f.getlength(IG_CAGRI_METIN)
    bosluk = int(ok_gen * 0.55)
    gen = int(ic + yazi_gen + bosluk + ok_gen + ic)
    pay = 8 if golge else 0
    im = Image.new("RGBA", (gen + pay, yukseklik + pay), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    r = yukseklik // 2
    if golge:
        d.rounded_rectangle((4, 6, gen + 3, yukseklik + 5), radius=r, fill=(0, 0, 0, 110))
    d.rounded_rectangle((0, 0, gen - 1, yukseklik - 1), radius=r, fill=cz.ACCENT + (255,))
    orta = yukseklik // 2
    d.text((ic, orta), IG_CAGRI_METIN, font=f, fill=(0, 0, 0, 255), anchor="lm")
    ox = ic + yazi_gen + bosluk
    sap = max(ok_gen * 0.3, 4)
    u = ok_gen * 0.8
    d.rectangle((ox + ok_gen / 2 - sap / 2, orta - u * 0.95, ox + ok_gen / 2 + sap / 2, orta + u * 0.15),
                fill=(0, 0, 0, 255))
    d.polygon([(ox, orta + u * 0.05), (ox + ok_gen, orta + u * 0.05), (ox + ok_gen / 2, orta + u * 0.8)],
              fill=(0, 0, 0, 255))
    return im


def cagri_katmani(yol, w=1080, h=1920):
    """Son saniyelerin büyük çağrısı: saydam 1080x1920 PNG."""
    from PIL import Image
    hap = hap_ciz(IG_CAGRI_YUKSEKLIK, 58, 44, 40)
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    im.alpha_composite(hap, ((w - hap.width) // 2, IG_CAGRI_Y))
    im.save(yol)
    return yol


def kucuk_hap(yol):
    """Video boyunca duran küçük hap (kırpılmış PNG)."""
    hap_ciz(IG_HAP_YUKSEKLIK, 40, 30, 28).save(yol)
    return yol


def _sure(yol):
    p = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", yol],
                       capture_output=True, text=True, check=True)
    return float(p.stdout.strip())


def nabiz_olcegi(t, aralik=IG_NABIZ_ARALIK, sure=IG_NABIZ_SURE, genlik=IG_NABIZ_GENLIK):
    """Python karşılığı (test için): her `aralik` sn'de bir `sure` sn'lik yumuşak büyüme."""
    import math
    m = t % aralik
    return 1 + genlik * math.sin(math.pi * m / sure) if (t >= aralik and m < sure) else 1.0


def _nabiz_ifadesi():
    a, s_, g = IG_NABIZ_ARALIK, IG_NABIZ_SURE, IG_NABIZ_GENLIK
    return f"(1+{g}*sin(PI*mod(t,{a})/{s_})*lt(mod(t,{a}),{s_})*gte(t,{a}))"


def ig_varyant_komutu(girdi, kucuk, buyuk, cikti, sure, cagri_sn=IG_CAGRI_SN, nabiz=True):
    bas = max(sure - cagri_sn, 0.0)
    cx, cy = IG_HAP_MERKEZ
    if nabiz:
        olcek = _nabiz_ifadesi()
        hap = f"[1:v]format=rgba,scale=w='trunc(iw*{olcek}/2)*2':h='trunc(ih*{olcek}/2)*2':eval=frame[h];"
    else:
        hap = "[1:v]format=rgba[h];"
    filtre = (hap
              + f"[2:v]format=rgba,fade=t=in:st={bas:.2f}:d=0.3:alpha=1[c];"
              + f"[0:v][h]overlay=x='{cx}-w/2':y='{cy}-h/2':enable='lt(t,{bas:.2f})'[a];"
              + f"[a][c]overlay=0:0:enable='gte(t,{bas:.2f})'[v]")
    return ["ffmpeg", "-y", "-v", "error", "-i", girdi,
            "-framerate", "30", "-loop", "1", "-t", f"{sure:.2f}", "-i", kucuk,
            "-framerate", "30", "-loop", "1", "-t", f"{sure:.2f}", "-i", buyuk,
            "-filter_complex", filtre, "-map", "[v]", "-map", "0:a?",
            "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
            "-profile:v", "high", "-level", "4.1", "-c:a", "copy", "-movflags", "+faststart", cikti]


def ig_varyant_uret(girdi, cikti, calisma):
    kucuk = kucuk_hap(os.path.join(calisma, "ig-hap.png"))
    buyuk = cagri_katmani(os.path.join(calisma, "ig-cagri.png"))
    sure = _sure(girdi)
    try:
        subprocess.run(ig_varyant_komutu(girdi, kucuk, buyuk, cikti, sure), check=True)
    except subprocess.CalledProcessError:
        # Eski ffmpeg'de scale `t` değişkeni yok: nabızsız (sabit hap) üret.
        log("[sosyal] nabızlı IG varyantı üretilemedi, sabit hapla deneniyor")
        subprocess.run(ig_varyant_komutu(girdi, kucuk, buyuk, cikti, sure, nabiz=False), check=True)
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


def taslak_mi(ortam=None):
    ortam = os.environ if ortam is None else ortam
    return (ortam.get("SOSYAL_TASLAK") or "").strip() == "1"


def _maddeler(sorunlar):
    return "\n".join(f"• {m}" for m in sorunlar)


def paylas(rapor, video, ortam=None, buffer=None, release=None, bildir=None, simdi=None,
           durum_yolu=DURUM_DOSYASI, ig_uret=ig_varyant_uret, erisim=url_erisilebilir, ig_cikti=None):
    """Sosyal zamanlama. -> {platform: post_id}. Asla fırlatmaz."""
    ortam = os.environ if ortam is None else ortam
    kuru = kuru_mu(ortam)
    taslak = taslak_mi(ortam)
    bildir = bildir or (lambda m: telegram_bildir(m, ortam, kuru=kuru))
    if taslak:                                # test mesajları gerçeğiyle karışmasın
        _bildir = bildir
        bildir = lambda m: _bildir(m if m.startswith("TEST:") else "TEST: " + m)  # noqa: E731
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
        buffer = buffer or Buffer(anahtar, kuru=kuru, taslak=taslak)
        release = release or Release(depo_adi(ortam), kuru=kuru)

        # Taslak testi yayınlamadığı için çift gönderi riski yok: kilit okunmaz
        # (bugünün gerçek gönderileri testi engellemesin) ve aşağıda yazılmaz.
        bekleyen = list(PLATFORMLAR) if taslak else [p for p in PLATFORMLAR
                                                     if p not in durumda_gonderilmis(gun, durum_yolu)]
        if bekleyen:
            # Kanal id'leri her çalışmada Buffer'dan; sorgu başarısızsa hiçbir yere gönderme.
            try:
                kanallar, kanal_sorunlari = buffer.kanallari_bul()
            except Exception as e:            # noqa: BLE001
                m = f"Buffer kanal listesi alınamadı, hiçbir platforma gönderilmedi: {gizle(e)[:300]}"
                log("[uyarı] " + m)
                bildir("⚠️ Sosyal medya: " + m)
                return sonuc
            sorunlar += kanal_sorunlari
            bekleyen = [p for p in bekleyen if p in kanallar]
        if bekleyen and not taslak:
            try:
                zaten = buffer.bugun_zamanlanmis(gun)
            except Exception as e:            # noqa: BLE001
                sorunlar.append(f"Buffer gönderi kontrolü yapılamadı, güvenli tarafta kalındı: {gizle(e)}")
                zaten = set(bekleyen)
            bekleyen = [p for p in bekleyen if p not in zaten]
        if not bekleyen:
            log(f"[sosyal] {gun} için gönderilecek platform kalmadı (zaten zamanlanmış ya da kanal sorunu).")
            if sorunlar:
                bildir("⚠️ Sosyal medya: hiçbir platforma gönderilmedi.\n" + _maddeler(sorunlar))
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
            ad, ig_ad = asset_adlari(gun, test=taslak)
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
                bildir("⚠️ Sosyal medya: hiçbir platforma gönderilmedi.\n" + _maddeler(sorunlar))
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
                    if not (kuru or taslak):
                        durum_yaz(gun, p, pid, durum_yolu)
                except Exception as e:        # noqa: BLE001
                    sorunlar.append(f"{PLATFORM_AD[p]} zamanlanamadı: {gizle(e)[:300]}")

        if sonuc and taslak:
            satirlar = [f"TEST: Buffer'da {len(sonuc)} taslak oluşturuldu "
                        f"({', '.join(PLATFORM_AD[p] for p in sonuc)}). Kontrol edip silebilirsin."]
            satirlar += [f"{PLATFORM_AD[p]}: {pid}" for p, pid in sonuc.items()]
            if sorunlar:
                satirlar += ["", "⚠️ Sorunlar:", _maddeler(sorunlar)]
            bildir("\n".join(satirlar))
        elif sonuc:
            satirlar = [f"Sosyal medya: {yerel:%H:%M}'de yayınlanacak "
                        f"({', '.join(PLATFORM_AD[p] for p in sonuc)}). İptal için Buffer'dan sil."]
            satirlar += [f"{PLATFORM_AD[p]}: {pid}" for p, pid in sonuc.items()]
            if sorunlar:
                satirlar += ["", "⚠️ Sorunlar:", _maddeler(sorunlar)]
            bildir("\n".join(satirlar))
        elif sorunlar:
            bildir("⚠️ Sosyal medya: hiçbir platforma gönderilmedi.\n" + _maddeler(sorunlar))
    except Exception as e:                    # noqa: BLE001
        m = f"Sosyal medya adımı başarısız: {type(e).__name__}: {gizle(e)[:400]}"
        log("[uyarı] " + m)
        bildir("⚠️ " + m + ("\n" + _maddeler(sorunlar) if sorunlar else ""))
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
