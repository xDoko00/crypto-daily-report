# -*- coding: utf-8 -*-
"""B-roll klip kütüphanesi: broll/<tema>/<tema>-NN.mp4 + broll/kutuphane.json.

Her temada birden çok klip olabilir; `sec` aynı tema içinde klipleri sırayla
döndürür ve son kullanılanı depo kökündeki state/video-son-kullanim.json'da
hatırlar (günlük iş commit'ler → kalıcı): ertesi gün
aynı tema bir sonraki klipten başlar (klip ≥ 2 ise art arda günlerde tekrar yok).
Aynı gün yeniden çalıştırmada aynı seçim döner (video tekrar üretilebilir).
"""
import json
import os
import re

KOK = os.path.dirname(os.path.abspath(__file__))
KLASOR = os.path.join(KOK, "broll")
KATALOG = os.path.join(KLASOR, "kutuphane.json")
DURUM = os.path.join(os.path.dirname(KOK), "state", "video-son-kullanim.json")
# Birleşik (sanal) temalar: kendi klasörü yok, üye temaların kliplerini kullanır
BIRLESIK = {"kanca-sabah": ["sabah-sehir", "istanbul-sabah"]}


def _oku(yol, varsayilan):
    try:
        with open(yol, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return varsayilan


def _yaz(yol, veri):
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    gecici = yol + ".tmp"
    with open(gecici, "w", encoding="utf-8") as f:
        json.dump(veri, f, ensure_ascii=False, indent=1)
    os.replace(gecici, yol)


def yukle(katalog=KATALOG):
    return _oku(katalog, {"klipler": []})


def ekle(kayit, katalog=KATALOG):
    """kayit: {tema, dosya (broll/'a göreli), prompt, request_id, tarih, ...}"""
    v = yukle(katalog)
    v["klipler"] = [k for k in v["klipler"] if k["dosya"] != kayit["dosya"]] + [kayit]
    _yaz(katalog, v)


def temalar(katalog=KATALOG):
    return sorted({k["tema"] for k in yukle(katalog)["klipler"]})


def klipler(tema, klasor=KLASOR, katalog=KATALOG):
    """Temanın diskte var olan klipleri (broll/'a göreli, sıralı). Katalogda
    "haric": true olan (kusurlu) klip seçime girmez; dosya silinmez.
    Birleşik tema (BIRLESIK): üye temaların klipleri sırayla harmanlanır
    (a1, b1, a2, b2, ...) → döndürmede üyeler günden güne dönüşümlü gelir."""
    if tema in BIRLESIK:
        listeler = [klipler(t, klasor, katalog) for t in BIRLESIK[tema]]
        return [x for i in range(max(map(len, listeler), default=0)) for L in listeler if i < len(L)
                for x in [L[i]]]
    return sorted(k["dosya"] for k in yukle(katalog)["klipler"]
                  if k["tema"] == tema and not k.get("haric")
                  and os.path.exists(os.path.join(klasor, k["dosya"])))


def yeni_dosya(tema, klasor=KLASOR):
    """Temada sıradaki boş ad: '<tema>/<tema>-NN.mp4' (broll/'a göreli)."""
    os.makedirs(os.path.join(klasor, tema), exist_ok=True)
    nolar = [int(m.group(1)) for a in os.listdir(os.path.join(klasor, tema))
             for m in [re.fullmatch(re.escape(tema) + r"-(\d+)\.mp4", a)] if m]
    return f"{tema}/{tema}-{max(nolar, default=0) + 1:02d}.mp4"


def sec(tema, gun, adet=1, klasor=KLASOR, katalog=KATALOG, durum=DURUM):
    """Tema için `adet` klip (mutlak yol) döndürür; tema boşsa []."""
    L = klipler(tema, klasor, katalog)
    if not L:
        return []
    d_hepsi = _oku(durum, {})
    d = d_hepsi.get(tema) or {}
    if d.get("gun") == gun:
        onceki = d.get("onceki")
        if len(d.get("secilen") or []) >= adet and all(x in L for x in d["secilen"]):
            return [os.path.join(klasor, x) for x in d["secilen"][:adet]]
    else:
        onceki = (d.get("secilen") or [None])[-1]
    bas = (L.index(onceki) + 1) % len(L) if onceki in L else 0
    secilen = [L[(bas + i) % len(L)] for i in range(adet)]
    d_hepsi[tema] = {"gun": gun, "onceki": onceki, "secilen": secilen}
    _yaz(durum, d_hepsi)
    return [os.path.join(klasor, x) for x in secilen]
