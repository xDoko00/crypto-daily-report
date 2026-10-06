# -*- coding: utf-8 -*-
"""Köşe maskotu: Doğan balonu (sağ alt, altyazının üstü).

Konuşurken `konusma`, susarken `bekleme` klibi (ikisi de ping-pong), "Bay bay"dan
~0.45 sn önce `kapanis` (el sallama). Geçişler ~0.17 sn (5 kare kutu süzgeci).
Klipler video/varliklar/dogan/ altında önceden işlenmiş hâlde (bkz. oradaki README).

Güvenlik: `hazirla` ve `Kose.bindir` hiçbir zaman exception fırlatmaz; sorun olursa
uyarı loglanır ve video Doğan'sız üretilir. Kapatma: DOGAN_KOSE=kapali.
"""
import os
import re
import subprocess
import sys

import numpy as np
from PIL import Image

KLASOR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "varliklar", "dogan")
BAYRAK = "DOGAN_KOSE"
KAPALI_DEGERLER = {"kapali", "kapalı", "0", "false", "off", "hayir", "hayır"}
D, IC = 232, 222                 # balon çapı / iç daire (5 px sarı kenarlık)
X, Y = 724, 1096                 # 1080x1920 videoda sol üst köşe
KLIP_FPS = 24
BIRLESME = 0.35                  # bundan kısa duraklamalar konuşma sayılır
PAY = 0.05                       # konuşma aralığına iki yandan eklenen pay
KAPANIS_ONDE = 0.45              # el sallama "Bay bay"dan bu kadar önce başlar
YUMUSATMA = 5                    # kare; 30 fps'te ~0.17 sn geçiş
KENAR = np.array([242, 183, 5], np.float32)


def log(m):
    print(m, file=sys.stderr, flush=True)


def aktif_mi(ortam=None):
    ortam = os.environ if ortam is None else ortam
    return (ortam.get(BAYRAK) or "").strip().lower() not in KAPALI_DEGERLER


def konusma_araliklari(ks, birlesme=BIRLESME):
    """ks: sahne başına [(kelime, bas, son)] (video zaman çizgisi) -> [[bas, son], ...]"""
    ar = sorted((w[1], w[2]) for kel in ks for w in kel)
    bir = []
    for a, b in ar:
        if bir and a - bir[-1][1] < birlesme:
            bir[-1][1] = max(bir[-1][1], b)
        else:
            bir.append([a, b])
    return bir


def _sade(k):
    return re.sub(r"[^\wçğıöşü]", "", k.lower())


def kapanis_zamani(ks, onde=KAPANIS_ONDE):
    """Son "Bay bay"ın başlangıcından `onde` sn önce; bulunamazsa son kelimeden."""
    kel = [w for s in ks for w in s]
    if not kel:
        return None
    for i in range(len(kel) - 2, -1, -1):
        if _sade(kel[i][0]) == "bay" and _sade(kel[i + 1][0]) == "bay":
            return max(0.0, kel[i][1] - onde)
    return max(0.0, kel[-1][1] - onde)


def agirliklar(n, fps, araliklar, kapanis):
    """-> (wa, wb, wc): kare başına konuşma / bekleme / kapanış karışım ağırlıkları."""
    t = np.arange(n) / fps
    kon = np.zeros(n, bool)
    for a, b in araliklar:
        kon[(t >= a - PAY) & (t < b + PAY)] = True
    c_on = (t >= kapanis).astype(float) if kapanis is not None else np.zeros(n)
    a_on = np.where(c_on > 0, 0, kon.astype(float))
    k = YUMUSATMA

    def yum(v):
        return np.convolve(np.pad(v, (k // 2, k // 2), mode="edge"), np.ones(k) / k, mode="valid")

    wc = yum(c_on)
    wa = yum(a_on) * (1 - wc)
    wb = 1 - wa - wc
    return wa, wb, wc


def pingpong_indis(n, sn):
    p = 2 * (n - 1)
    i = int(sn * KLIP_FPS) % p
    return i if i < n else p - i


def _kareler(ad):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", os.path.join(KLASOR, ad + ".mp4"),
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         capture_output=True, check=True, timeout=60).stdout
    F = np.frombuffer(raw, np.uint8).reshape(-1, IC, IC, 3)
    if len(F) < 2:
        raise ValueError(f"{ad}: kare yok")
    return F


class Kose:
    def __init__(self, ks, top, fps, kareler=None):
        self.fps = fps
        n = int(round(top * fps)) + 2
        self.kapanis = kapanis_zamani(ks)
        self.araliklar = konusma_araliklari(ks)
        self.wa, self.wb, self.wc = agirliklar(n, fps, self.araliklar, self.kapanis)
        self.A, self.B, self.C = kareler or (_kareler("konusma"), _kareler("bekleme"), _kareler("kapanis"))
        yy, xx = np.mgrid[0:D, 0:D] + 0.5
        r = np.hypot(xx - D / 2, yy - D / 2)
        self.dis = (np.clip(D / 2 - r, 0, 1) * 255).astype(np.uint8)
        o = (D - IC) // 2
        self.o = o
        self.ic = np.clip(IC / 2 - r, 0, 1)[o:o + IC, o:o + IC, None].astype(np.float32)

    def kare(self, i):
        """i. video karesi için 232x232 RGBA balon."""
        i = min(i, len(self.wa) - 1)
        ti = i / self.fps
        img = np.zeros((IC, IC, 3), np.float32)
        if self.wa[i] > 0:
            img += self.wa[i] * self.A[pingpong_indis(len(self.A), ti)]
        if self.wb[i] > 0:
            img += self.wb[i] * self.B[pingpong_indis(len(self.B), ti)]
        if self.wc[i] > 0:
            j = min(int(max(ti - self.kapanis, 0) * KLIP_FPS), len(self.C) - 1)
            img += self.wc[i] * self.C[j]
        tam = np.empty((D, D, 3), np.float32)
        tam[:] = KENAR
        o = self.o
        tam[o:o + IC, o:o + IC] = KENAR * (1 - self.ic) + img * self.ic
        return Image.fromarray(np.dstack([tam.clip(0, 255).astype(np.uint8), self.dis]))

    def bindir(self, im, i):
        """PIL RGBA kareye balonu yerleştirir. Hata -> False (çağıran bindirmeyi kapatır)."""
        try:
            im.alpha_composite(self.kare(i), (X, Y))
            return True
        except Exception as e:  # noqa: BLE001
            log(f"[dogan] UYARI: bindirme hatası, kalan kareler Doğan'sız: {e}")
            return False


def hazirla(ks, top, fps, ortam=None):
    """-> Kose ya da None (kapalı / hata). Asla exception fırlatmaz."""
    if not aktif_mi(ortam):
        log(f"[dogan] {BAYRAK}=kapali, köşe balonu atlandı")
        return None
    try:
        k = Kose(ks, top, fps)
        log(f"[dogan] köşe balonu açık ({len(k.araliklar)} konuşma aralığı, kapanış {k.kapanis:.2f} sn)")
        return k
    except Exception as e:  # noqa: BLE001
        log(f"[dogan] UYARI: köşe balonu hazırlanamadı, video Doğan'sız: {e}")
        return None
