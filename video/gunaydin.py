# -*- coding: utf-8 -*-
"""Günaydın Kripto — yüzsüz dikey kısa haber videosu (1080x1920, ~60 sn).

Tasarım: video/TASARIM.md (onaylı; görsel/ses tasarımını değiştirme).
Günlük akışta report.py → video.calistir alt süreci bu modülün `uret`'ini çağırır.
Yerel deneme (Telegram'a GÖNDERMEZ):
  python3 -m video.gunaydin --rapor reports/latest.json
  python3 -m video.gunaydin --sadece-metin

Maliyet koruması: seslendirme <calisma>/tts.json'da önbelleklenir; metin aynıysa
ElevenLabs yeniden çağrılmaz. B-roll klipleri video/broll/<tema>/<tema>-NN.mp4
kütüphanesinde (video/broll/kutuphane.json); tema içinde günden güne döndürülür
(durum: state/video-son-kullanim.json).
"""
import argparse
import difflib
import json
import os
import re
import subprocess
import sys
import urllib.request

import numpy as np
from PIL import Image, ImageDraw

from . import senaryo as sn      # noqa: E402
from . import servisler as sv    # noqa: E402
from . import cizim as cz        # noqa: E402
from . import kutuphane as ku    # noqa: E402

KOK = os.path.dirname(os.path.abspath(__file__))
VARSAYILAN_RAPOR = "https://raw.githubusercontent.com/xDoko00/crypto-daily-report/main/reports/latest.json"
FPS = 30
ON_BOSLUK = 0.15          # ses başlamadan önce (sn)
KUYRUK = 1.2              # ses bittikten sonra kapanış karesi (sn)
SES_HIZI = 1.04           # atempo: perdeyi bozmadan %4 hızlandırma (~58 sn hedef)
HEDEF_LUFS = -14.0
MUZIK_LUFS = -36.0        # konuşmanın ~22 LU altı
GECIS_KARE = 5            # sahne geçişinde arka plan çapraz geçişi


def log(m):
    print(m, file=sys.stderr, flush=True)


def calistir(args, **kw):
    p = subprocess.run(args, capture_output=True, text=True, **kw)
    if p.returncode != 0:
        raise RuntimeError(f"{args[0]} hata: {p.stderr[-800:]}")
    return p


# --------------------------------------------------------------------------- #
# Rapor + ses
# --------------------------------------------------------------------------- #

def rapor_oku(kaynak):
    if re.match(r"https?://", kaynak):
        req = urllib.request.Request(kaynak, headers={"User-Agent": "gunaydin-video/1.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    with open(os.path.expanduser(kaynak), encoding="utf-8") as f:
        return json.load(f)


def ses_al(metin, klasor):
    """Aynı metin için önbellekteki sesi kullanır; yoksa tek ElevenLabs çağrısı."""
    mp3, js = os.path.join(klasor, "ses.mp3"), os.path.join(klasor, "tts.json")
    if os.path.exists(js) and os.path.exists(mp3):
        d = json.load(open(js, encoding="utf-8"))
        if d.get("metin") == metin:
            log("[ses] önbellekten (ElevenLabs çağrılmadı, maliyet 0)")
            d["onbellek"] = True
            return mp3, d
    d = sv.seslendir_zamanli(metin, mp3, log)
    d["metin"] = metin
    json.dump(d, open(js, "w", encoding="utf-8"), ensure_ascii=False)
    return mp3, d


def kelime_zamanlari(sahneler, tts, mp3):
    """Her sahne için [(kelime, bas, son)] — ElevenLabs karakter hizalamasından."""
    segler = [sn.etiketsiz(s["konusma"]) for s in sahneler]
    S = " ".join(segler)
    hiz = tts.get("alignment") or tts.get("normalized_alignment")
    sonuc, taban = [], 0
    if hiz and hiz.get("characters"):
        A = "".join(hiz["characters"])
        bas_t, son_t = hiz["character_start_times_seconds"], hiz["character_end_times_seconds"]
        es = [None] * len(S)
        for blok in difflib.SequenceMatcher(None, S, A, autojunk=False).get_matching_blocks():
            for k in range(blok.size):
                es[blok.a + k] = blok.b + k
        bilinen = [i for i, v in enumerate(es) if v is not None]

        def zaman(i, dizi):
            if es[i] is None:                      # en yakın eşleşen karakter
                j = min(bilinen, key=lambda x: abs(x - i))
                return dizi[es[j]]
            return dizi[es[i]]

        for seg in segler:
            kel = []
            for m in re.finditer(r"\S+", seg):
                a, b = taban + m.start(), taban + m.end() - 1
                kel.append((m.group(0), zaman(a, bas_t), zaman(b, son_t)))
            sonuc.append(kel)
            taban += len(seg) + 1
        return sonuc
    # Yedek: Scribe STT kelime zamanları, sırayla eşlenir
    log("[ses] hizalama yok, Scribe STT yedeği")
    stt = sv.scribe_kelimeler(mp3)
    i = 0
    for seg in segler:
        kel = []
        for k in seg.split():
            w = stt[min(i, len(stt) - 1)]
            kel.append((k, w[1], w[2]))
            i += 1
        sonuc.append(kel)
    return sonuc


# --------------------------------------------------------------------------- #
# Zaman çizelgesi + altyazı parçaları
# --------------------------------------------------------------------------- #

def adres_birlestir(kelimeler):
    """Fonetik 'Doğukan Live nokta com' kelimelerini altyazıda tek 'dogukanlive.com' yapar."""
    hedef = sn.SITE_KONUSMA.split()
    n = len(hedef)
    sonuc = []
    for kel in kelimeler:
        yeni, i = [], 0
        while i < len(kel):
            parca = [re.sub(r"[.,;:!?]+$", "", w[0]) for w in kel[i:i + n]]
            if parca == hedef:
                son = kel[i + n - 1]
                nokta = re.search(r"[.,;:!?]+$", son[0])
                yeni.append((sn.SITE + (nokta.group(0) if nokta else ""), kel[i][1], son[2]))
                i += n
            else:
                yeni.append(kel[i])
                i += 1
        sonuc.append(yeni)
    return sonuc


def zaman_cizelgesi(sahneler, kelimeler, ses_suresi):
    top = ON_BOSLUK + ses_suresi / SES_HIZI + KUYRUK
    ks = [[(k, ON_BOSLUK + a / SES_HIZI, ON_BOSLUK + b / SES_HIZI) for k, a, b in kel] for kel in kelimeler]
    baslar = [0.0] + [max(0.0, kel[0][1] - 0.12) for kel in ks[1:]]
    araliklar = [(baslar[i], baslar[i + 1] if i + 1 < len(baslar) else top) for i in range(len(baslar))]
    return top, ks, araliklar


def altyazi_parcalari(ks, araliklar, maks_kelime=3, maks_harf=16):
    parcalar = []
    for si, kel in enumerate(ks):
        grup = []
        for i, w in enumerate(kel):
            grup.append(w)
            harf = sum(len(x[0]) for x in grup)
            if (re.search(r"[.,;:!?]$", w[0]) or len(grup) >= maks_kelime or harf >= maks_harf
                    or i == len(kel) - 1):
                parcalar.append({"sahne": si, "kel": grup})
                grup = []
    for i, p in enumerate(parcalar):
        bas = p["kel"][0][1]
        son_kelime = p["kel"][-1][2]
        sonraki = parcalar[i + 1]["kel"][0][1] if i + 1 < len(parcalar) else None
        sahne_son = araliklar[p["sahne"]][1]
        son = min(sonraki if sonraki is not None else sahne_son, son_kelime + 0.7, sahne_son)
        p["bas"], p["son"] = bas - 0.05, max(son, son_kelime)
        p["yazi"] = [re.sub(r"[.,;:]+$", "", w[0]) for w in p["kel"]]
    return parcalar


# --------------------------------------------------------------------------- #
# B-roll
# --------------------------------------------------------------------------- #

def broll_hazirla(sahneler, gun, durum=ku.DURUM):
    """Her sahneye kütüphaneden klip atar (tema içinde günden güne döner, bkz.
    kutuphane.sec). Klibi olmayan tema YEDEK_TEMA'ya düşer."""
    adet = {}
    for s in sahneler:
        adet[s["tema"]] = adet.get(s["tema"], 0) + 1
    eksik = [t for t in adet if not ku.klipler(t)]
    if eksik:
        log(f"[broll] boş temalar yedeğe düşüyor: {eksik}")
    for t in eksik:
        adet[sn.YEDEK_TEMA] = adet.get(sn.YEDEK_TEMA, 0) + adet.pop(t)
    secim = {t: ku.sec(t, gun, n, durum=durum) for t, n in adet.items()}
    for s in sahneler:
        t = s["tema"] if s["tema"] in secim else sn.YEDEK_TEMA
        s["klip"] = secim[t].pop(0) if secim.get(t) else None


def pingpong(klip, klasor):
    """İleri+geri birleştirilmiş, 1080x1920/30fps ön ölçekli döngü (kesintisiz loop)."""
    hedef = os.path.join(klasor, "pp-" + os.path.basename(klip))
    if os.path.exists(hedef) and os.path.getmtime(hedef) > os.path.getmtime(klip):
        return hedef
    calistir(["ffmpeg", "-y", "-v", "error", "-i", klip, "-filter_complex",
              "[0:v]scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,crop=1080:1920,"
              "setsar=1,fps=30,split[a][b];[b]reverse[r];[a][r]concat=n=2:v=1:a=0[v]",
              "-map", "[v]", "-an", "-c:v", "libx264", "-crf", "14", "-preset", "fast", hedef])
    return hedef


class ArkaPlan:
    """Sahne için ham RGB kare akışı (ffmpeg), karartma maskesiyle."""

    def __init__(self, pp, ofs, kare):
        self.kare = kare
        self.p = None
        if pp:
            self.p = subprocess.Popen(
                ["ffmpeg", "-v", "error", "-stream_loop", "-1", "-ss", f"{ofs:.2f}", "-i", pp,
                 "-frames:v", str(kare), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                stdout=subprocess.PIPE)
        self.son = None

    def oku(self):
        if self.p:
            b = self.p.stdout.read(cz.W * cz.H * 3)
            if len(b) == cz.W * cz.H * 3:
                self.son = np.frombuffer(b, np.uint8).reshape(cz.H, cz.W, 3)
        if self.son is None:
            self.son = _duz_zemin()
        return self.son

    def kapat(self):
        if self.p:
            self.p.stdout.close()
            self.p.wait()


_ZEMIN = None


def _duz_zemin():
    global _ZEMIN
    if _ZEMIN is None:
        y = np.linspace(0, 1, cz.H)[:, None, None]
        ust = np.array([28, 24, 12])
        alt = np.array(cz.BG)
        _ZEMIN = (ust * (1 - y) + alt * y).repeat(cz.W, axis=1).astype(np.uint8)
    return _ZEMIN


def karartma_maskesi():
    """Genel %50 karartma; üstte ve altyazı bandında daha koyu (okunurluk)."""
    y = np.arange(cz.H, dtype=np.float32)
    m = np.full(cz.H, 0.50, np.float32)
    m = np.where(y < 300, 0.26 + 0.24 * (y / 300), m)
    alt = np.clip((y - 1150) / 500, 0, 1)
    m = m * (1 - 0.55 * alt)
    return (m * 256).astype(np.uint16)[:, None, None]


# --------------------------------------------------------------------------- #
# Ses miksajı
# --------------------------------------------------------------------------- #

def _loudness(yol):
    p = subprocess.run(["ffmpeg", "-hide_banner", "-i", yol, "-af", "loudnorm=print_format=json",
                        "-f", "null", "-"], capture_output=True, text=True)
    js = p.stderr[p.stderr.rfind("{"):p.stderr.rfind("}") + 1]
    return json.loads(js)


def ses_miksaji(mp3, top, klasor):
    ham = os.path.join(klasor, "konusma.wav")
    calistir(["ffmpeg", "-y", "-v", "error", "-i", mp3, "-af",
              f"atempo={SES_HIZI},adelay={int(ON_BOSLUK * 1000)}:all=1,apad,atrim=0:{top:.3f}",
              "-ac", "2", "-ar", "48000", ham])
    kaz_k = HEDEF_LUFS - float(_loudness(ham)["input_i"])
    # Telifsiz, yerelde sentezlenen yumuşak pad (La majör add9), yavaş nefes alan LFO'lar
    notalar = [(110.0, .30, .05), (164.81, .22, .07), (220.0, .20, .04), (277.18, .12, .06),
               (329.63, .10, .05), (493.88, .05, .08)]
    ifade = "+".join(f"{a}*sin(2*PI*{f}*t)*(0.65+0.35*sin(2*PI*{l}*t+{i}))"
                     for i, (f, a, l) in enumerate(notalar))
    muzik = os.path.join(klasor, "muzik.wav")
    calistir(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
              f"aevalsrc='{ifade}':s=48000:d={top:.3f}", "-af",
              f"lowpass=f=900,aecho=0.8:0.7:120|240:0.25|0.15,afade=t=in:d=1.5,"
              f"afade=t=out:st={max(top - 2.0, 0):.2f}:d=2", "-ac", "2", muzik])
    kaz_m = MUZIK_LUFS - float(_loudness(muzik)["input_i"])
    cikis = os.path.join(klasor, "miks.wav")
    calistir(["ffmpeg", "-y", "-v", "error", "-i", ham, "-i", muzik, "-filter_complex",
              f"[0:a]volume={kaz_k:.2f}dB[k];[1:a]volume={kaz_m:.2f}dB[m];"
              f"[k][m]amix=inputs=2:normalize=0:duration=first,alimiter=limit=0.84:level=false[o]",
              "-map", "[o]", "-ar", "48000", cikis])
    return cikis


# --------------------------------------------------------------------------- #
# Kare üretimi
# --------------------------------------------------------------------------- #

def _yumusak(x):
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def sahne_ogeleri(s, sira_haber):
    t = s["tur"]
    if t == "kanca":
        return cz.sahne_kanca(s), None
    if t == "fiyat":
        return cz.sahne_fiyat(s), None
    if t == "duygu":
        return cz.sahne_duygu(s)
    if t == "haber":
        return cz.sahne_haber(s, sira_haber), None
    if t == "risk":
        return cz.sahne_risk(s), None
    if t == "takip":
        return cz.sahne_takip(s), None
    return cz.sahne_kapanis(s), None


def render(sahneler, araliklar, parcalar, top, ses, cikti, kare_klasoru, calisma):
    toplam_kare = int(round(top * FPS))
    kodlayici = subprocess.Popen(
        ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{cz.W}x{cz.H}",
         "-r", str(FPS), "-i", "-", "-i", ses, "-map", "0:v", "-map", "1:a",
         "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
         "-profile:v", "high", "-level", "4.1", "-g", "60",
         "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-shortest", "-movflags", "+faststart", cikti],
        stdin=subprocess.PIPE)
    maske = karartma_maskesi()
    etiket = cz.ust_etiket(sn.UST_ETIKET)
    ay_onbellek = {}
    kullanilan_tema = {}
    kare = 0
    haber_sira = 0
    onceki_son = None
    if kare_klasoru:
        os.makedirs(kare_klasoru, exist_ok=True)
    for si, s in enumerate(sahneler):
        bas, son = araliklar[si]
        n = int(round(son * FPS)) - int(round(bas * FPS))
        ofs = 0.0
        if s.get("klip"):
            anahtar = s["klip"]
            ofs = 5.0 * kullanilan_tema.get(anahtar, 0)        # aynı klip 2. kez: ters yarıdan
            kullanilan_tema[anahtar] = kullanilan_tema.get(anahtar, 0) + 1
        ap = ArkaPlan(pingpong(s["klip"], calisma) if s.get("klip") else None, ofs, n)
        ogeler, gosterge = sahne_ogeleri(s, haber_sira)
        if s["tur"] == "haber":
            haber_sira += 1
        orta = n // 2 if s["tur"] != "kanca" else int(1.2 * FPS)
        gosterge_son = None
        for i in range(n):
            t = (kare + i) / FPS
            tl = t - bas
            ham = ap.oku()
            if i < GECIS_KARE and onceki_son is not None:
                o = (i + 1) / (GECIS_KARE + 1)
                ham = (ham.astype(np.float32) * o + onceki_son.astype(np.float32) * (1 - o)).astype(np.uint8)
            koyu = ((ham.astype(np.uint16) * maske) >> 8).astype(np.uint8)
            im = Image.fromarray(koyu).convert("RGBA")
            im.alpha_composite(etiket, (cz.SOL, 116))
            if gosterge is not None:
                e = _yumusak((tl - 0.1) / 1.0)
                if gosterge_son is None or e < 1.0:
                    gosterge_son = cz.gosterge(gosterge["deger"], gosterge["deger"] * e, "")
                g_al = _yumusak(tl / 0.35)
                g_img = gosterge_son if g_al >= 1 else _alfa(gosterge_son, g_al)
                im.alpha_composite(g_img, (cz.SOL, gosterge["y"]))
            for og in ogeler:
                d = tl - og.giris
                if not og.anim or d >= 0.35:
                    im.alpha_composite(og.img, (int(og.x), int(og.y)))
                elif d > 0:
                    e = _yumusak(d / 0.35)
                    im.alpha_composite(_alfa(og.img, e), (int(og.x), int(og.y + (1 - e) * 40)))
            # altyazı
            for pi, p in enumerate(parcalar):
                if p["bas"] <= t < p["son"]:
                    aktif = 0
                    for j, w in enumerate(p["kel"]):
                        if t >= w[1] - 0.03:
                            aktif = j
                    k = (pi, aktif)
                    if k not in ay_onbellek:
                        ay_onbellek[k] = cz.altyazi(p["yazi"], aktif)
                    a = ay_onbellek[k]
                    im.alpha_composite(a, (0, int(cz.ALTYAZI_Y - a.height / 2)))
                    break
            d = ImageDraw.Draw(im)
            cz.ilerleme(d, araliklar, t)
            rgb = im.convert("RGB")
            if kare_klasoru and i == orta:
                rgb.save(os.path.join(kare_klasoru, f"{si + 1:02d}-{s['tur']}.jpg"), quality=88)
            kodlayici.stdin.write(rgb.tobytes())
        onceki_son = ap.son
        ap.kapat()
        kare += n
        log(f"[video] sahne {si + 1}/{len(sahneler)} ({s['tur']}) {n} kare")
    kodlayici.stdin.close()
    if kodlayici.wait() != 0:
        raise RuntimeError("kodlayıcı hata verdi")
    return kare


def _alfa(img, oran):
    a = img.getchannel("A").point(lambda v: int(v * oran))
    c = img.copy()
    c.putalpha(a)
    return c


# --------------------------------------------------------------------------- #

def uret(rapor, calisma, cikti, kare_klasoru=None, durum=ku.DURUM):
    """Rapor nesnesinden mp4 üretir -> özet dict (yol, süre, maliyet...)."""
    sahneler = sn.sahneler(rapor)
    metin = sn.tam_metin(sahneler)
    gun = rapor["id"]
    os.makedirs(calisma, exist_ok=True)
    os.makedirs(os.path.dirname(os.path.abspath(cikti)), exist_ok=True)

    mp3, tts = ses_al(metin, calisma)
    ses_suresi = float(calistir(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                 "-of", "csv=p=0", mp3]).stdout.strip())
    kelimeler = adres_birlestir(kelime_zamanlari(sahneler, tts, mp3))
    top, ks, araliklar = zaman_cizelgesi(sahneler, kelimeler, ses_suresi)
    parcalar = altyazi_parcalari(ks, araliklar)
    broll_hazirla(sahneler, gun, durum)
    miks = ses_miksaji(mp3, top, calisma)
    render(sahneler, araliklar, parcalar, top, miks, cikti, kare_klasoru, calisma)

    with open(os.path.join(calisma, "metin.txt"), "w", encoding="utf-8") as f:
        f.write(f"# Günaydın Kripto — {gun} — konuşma metni (ElevenLabs'e giden, etiketli)\n\n")
        f.write(metin + "\n\n# Sahneler (başlangıç–bitiş sn)\n\n")
        for s, (b, e) in zip(sahneler, araliklar):
            f.write(f"{b:5.1f}–{e:5.1f}  {s['tur']:8} [{s['tema']}] {sn.etiketsiz(s['konusma'])}\n")
    ozet = {"tarih": gun, "yol": cikti, "sure": round(top, 2), "sahneler": [
        {"tur": s["tur"], "tema": s["tema"], "bas": round(b, 2), "son": round(e, 2),
         "klip": os.path.basename(s["klip"]) if s.get("klip") else None}
        for s, (b, e) in zip(sahneler, araliklar)],
        "elevenlabs_karakter": 0 if tts.get("onbellek") else tts.get("maliyet")}
    json.dump(ozet, open(os.path.join(calisma, "ozet.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    log(f"[video] bitti: {os.path.basename(cikti)} ({ozet['sure']} sn, "
        f"ElevenLabs karakter: {ozet['elevenlabs_karakter']})")
    return ozet


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rapor", default=VARSAYILAN_RAPOR, help="latest.json yolu veya URL")
    ap.add_argument("--cikti", default=os.path.join(KOK, "cikti"))
    ap.add_argument("--calisma", default=None, help="ara dosyalar + TTS önbelleği (vars. <cikti>/calisma-<tarih>)")
    ap.add_argument("--durum", default=ku.DURUM, help="b-roll döndürme durumu dosyası")
    ap.add_argument("--sadece-metin", action="store_true")
    a = ap.parse_args()

    rapor = rapor_oku(a.rapor)
    if a.sadece_metin:
        sahneler = sn.sahneler(rapor)
        for s in sahneler:
            print(f"{s['tur']:8} {s['tema']:18} {s['konusma']}")
        print(f"\n{len(sn.tam_metin(sahneler))} karakter")
        return
    gun = rapor["id"]
    uret(rapor, a.calisma or os.path.join(a.cikti, "calisma-" + gun),
         os.path.join(a.cikti, f"gunaydin-{gun}.mp4"), os.path.join(a.cikti, "kareler"), a.durum)


if __name__ == "__main__":
    main()
