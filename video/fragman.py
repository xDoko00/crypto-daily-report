# -*- coding: utf-8 -*-
"""Instagram hikâyesi için ~18-20 sn'lik FRAGMAN (tam video X/TikTok'a gider).

Üç bölüm:
  1. Kanca — tam videonun kancası (senaryo.sahneler()[0]: "Günaydın!" + manşet [+ BTC]).
  2. Başlıklar — "Üç başlık var:" + kart; her başlık ≤ 7 kelime, ses ve ekran aynı
     kelimeler, kart satırı başlık okunurken girer. Kancada manşet okunduysa manşet
     tekrar edilmez: sıradaki başlıklar "Üç başlık daha:" ile okunur.
  3. Kapanış — "Haberler ve grafikler için bana BUGÜN yaz. Bay bay!" + BTC günlük
     grafik kartı (btc_grafik; veri yoksa grafiksiz, çağrı büyür).

Süre: hedef ≤ FRAGMAN_HEDEF_SN; tahmin aşarsa önce başlıklar kısaltılır (7→6→5
kelime, 7'nin altı yalnız anlamı bozmadan), sonra kancadaki BTC cümlesi düşer, en son
(manşet kancada okunduysa) "İki başlık daha"ya inilir — manşet + 2 = yine 3 haber.
Hiçbiri sığmazsa en kısa plan kabul edilir. Asla FRAGMAN_MAKS_SN'yi geçmez.
Seslendirme tek ek ElevenLabs çağrısı (~250 karakter, gunaydin.ses_al önbelleği).
Hiçbir koşulda tam videonun akışını etkilemez; hata çağırana (sosyal.py) fırlatılır,
o da eski IG varyantına düşer.

Yerel deneme (Telegram/Buffer'a GÖNDERMEZ):
  python3 -m video.fragman --rapor reports/latest.json --cikti /tmp/fragman.mp4 --calisma /tmp/fr
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys

from PIL import ImageDraw

from . import senaryo as sn
from . import gunaydin as gv
from . import cizim as cz
from . import dogan as dg
from . import kutuphane as ku
from . import btc_grafik as bg

FRAGMAN_HEDEF_SN = 20.0
FRAGMAN_MAKS_SN = 59.0          # Buffer IG hikâyesi 1 dk sınırı
KUYRUK = 0.9
KONUSMA_KARAKTER_SN = 12.0      # etiketsiz okunuş metni, ElevenLabs klon ses (9 Eki ölçümü)
BASLIK_ADET = 3
BASLIK_MAKS = 7                 # her koşulda üst sınır (kelime)
# (başlık hedef kelime, kancada BTC cümlesi) — süre tahmini aşarsa sıradakine geçilir.
# 7'nin altı yalnız anlamı bozmayan kısaltmalarla yapılır (ör. "İstanbul'da", "spot" atılır).
# (başlık hedef kelime, kancada BTC cümlesi, başlık adedi)
KISALTMA_PLANI = ((7, True, 3), (6, True, 3), (5, True, 3), (5, False, 3), (7, False, 2), (5, False, 2))
SAYILAR = {1: "Bir", 2: "İki", 3: "Üç"}
KAPANIS_SES = "[warm] Haberler ve grafikler için bana BUGÜN yaz. Bay bay!"
KAPANIS_UST = "Haberler ve grafikler"
KAPANIS_BUYUK = "BANA BUGÜN YAZ"
GRAFIK_GIRIS = 0.45
# Kısaltırken ilk atılan, bilgi taşımayan kelimeler
_ATILABILIR = {"spot", "tamamen", "resmen", "yeniden", "ilk", "kez"}
_BAGLACLAR = {"ama", "fakat", "ancak", "ve"}


def log(m):
    print(m, file=sys.stderr, flush=True)


# --------------------------------------------------------------------------- #
# Başlıklar
# --------------------------------------------------------------------------- #

def _kel_say(s):
    return len(s.split())


def baslik_kisalt(baslik, maks=BASLIK_MAKS):
    """Başlığı ≤ maks kelimeye indirmeye çalışır (kurallı, LLM yok), yalnız anlamı
    bozmayan adımlarla: ilk yan cümle -> parantez -> 'N yıllık/günlük' -> bilgi taşımayan
    kelimeler -> özel ad bulunma eki ('İstanbul'da') -> bağlaçtan önceki cümle.
    Kör kesme yok: sığmazsa sonuç maks'ı aşar (çağıran o başlığı atlar)."""
    b = re.sub(r"\s+", " ", (baslik or "")).strip().rstrip(" .;,:!?")
    if _kel_say(b) <= maks:
        return b
    ilk = sn.ilk_yan_cumle(b)
    if 3 <= _kel_say(ilk) <= maks:
        return ilk
    b = re.sub(r"\s*\([^)]*\)", "", b).strip()
    if _kel_say(b) > maks:
        b = re.sub(r"\b(?:[\d.,]+|iki|üç|dört|beş|altı|yedi|sekiz|dokuz|on) (?:yıllık|aylık|haftalık|günlük)\s+",
                   "", b).strip()
    kel = b.split()
    for k in list(kel):
        if len(kel) <= maks:
            break
        if sn.sk.tr_kucuk(k) in _ATILABILIR:
            kel.remove(k)
    for i in range(len(kel) - 2, 0, -1):          # ilk ve son kelime kalır
        if len(kel) <= maks:
            break
        if re.fullmatch(r"[A-ZÇĞİÖŞÜ][\wçğıöşü]*'(?:da|de|ta|te)", kel[i]):
            kel.pop(i)
    if len(kel) > maks:                           # bağlaçtan önceki cümle ("…çıktı ama piyasa…")
        for i, k in enumerate(kel):
            if 3 <= i <= maks and sn.sk.tr_kucuk(k) in _BAGLACLAR:
                kel = kel[:i]
                break
    return " ".join(kel).rstrip(",;:")


def baslik_adaylari(rapor, manset_var, adet=None):
    """Gündem başlıkları; kancada manşet okunduysa o (ve aynı özel adı paylaşan) atlanır."""
    gundem = (rapor.get("sections") or {}).get("agenda") or []
    sonuc, gorulen = [], set()
    for i, h in enumerate(gundem):
        t = (h or {}).get("title") or ""
        adlar = sn._anahtar_adlar(t)
        if i == 0 and manset_var:
            gorulen |= adlar
            continue
        if not t.strip() or adlar & gorulen:
            continue
        sonuc.append(t)
        gorulen |= adlar
        if len(sonuc) == adet:
            break
    return sonuc


def ekran_basligi(baslik, rapor, maks):
    """Ekranda yazan = seste okunan kelimeler: sesin kelime değişimleri (göreli tarih,
    terim Türkçeleştirme) ekrana da uygulanır; okunuş farkları altyazıda geri eşlenir.
    BASLIK_MAKS'a güvenle sığmıyorsa None (başlık atlanır, sıradaki gelir)."""
    t = sn.ekran(sn._terimler(sn._goreli_tarih(baslik, rapor), sn.SES_TERIMLERI))
    k = baslik_kisalt(t, maks)
    if _kel_say(k) > BASLIK_MAKS:
        k = baslik_kisalt(t, BASLIK_MAKS)
    return k if 0 < _kel_say(k) <= BASLIK_MAKS else None


def madde(baslik, rapor, maks):
    """-> (ses cümlesi, telaffuz eşlemeleri, rakam eşlemeleri, ekran metni).
    Ekran metni, ses cümlesinin altyazıdaki hâlidir (okunuşlar orijinal yazıma döner;
    "HYPE'ta" gibi seste yeniden kurulan ifadeler sesteki gibi yazılır) — ses ve ekran
    birebir aynı kelimeler. Yeniden kurulum kelime ekletirse kaynak bir kez daha kısaltılır;
    sığmazsa None (başlık atlanır)."""
    k = ekran_basligi(baslik, rapor, maks)
    if k is None:
        return None
    for _ in range(3):
        sn._ESLEMELER.clear()
        sn._RAKAMLAR.clear()
        ses = sn._cumle(sn.konusma(k, rapor))
        tel, rak = list(sn._ESLEMELER), list(sn._RAKAMLAR)
        sn._ESLEMELER.clear()
        sn._RAKAMLAR.clear()
        kel = [(w, 0.0, 0.0) for w in sn.etiketsiz(ses).split()]
        kel = gv.orijinal_yazim(gv.orijinal_yazim(kel, tel), rak)
        ekran = " ".join(w[0] for w in kel).rstrip(" .;,:!?")
        if _kel_say(ekran) <= BASLIK_MAKS:
            return ses, tel, rak, ekran
        yeni = baslik_kisalt(k, _kel_say(k) - (_kel_say(ekran) - BASLIK_MAKS))
        if yeni == k:
            break
        k = yeni
    return None


# --------------------------------------------------------------------------- #
# Sahneler
# --------------------------------------------------------------------------- #

def _ekle(liste, sahne):
    sahne["telaffuz"] = list(sn._ESLEMELER)
    sahne["rakam"] = list(sn._RAKAMLAR)
    sn._ESLEMELER.clear()
    sn._RAKAMLAR.clear()
    sahne["konusma"] = re.sub(r"\s+", " ", sahne["konusma"]).strip()
    liste.append(sahne)


def sahneler(rapor, maks=BASLIK_MAKS, btc=True, adet=BASLIK_ADET):
    """-> (gosterim, zamanlama). gosterim: [kanca, basliklar?, cagri] (render);
    zamanlama: başlıklar bölümü giriş + her başlık ayrı (kart giriş zamanları için).
    İkisinin tam metni aynıdır."""
    kanca = dict(sn.sahneler(rapor)[0])
    if not btc and kanca.get("manset"):
        sn._ESLEMELER.clear()
        sn._RAKAMLAR.clear()
        kanca["konusma"] = f"[cheerful] Günaydın! [calm] {sn._cumle(sn.konusma(sn.kanca_manseti(rapor), rapor))}"
        kanca["telaffuz"], kanca["rakam"] = list(sn._ESLEMELER), list(sn._RAKAMLAR)
    sn._ESLEMELER.clear()
    sn._RAKAMLAR.clear()
    zam = [kanca]
    gos = [kanca]
    adet = adet if kanca.get("manset") else BASLIK_ADET
    adaylar, hazir = [], []
    for b in baslik_adaylari(rapor, kanca.get("manset")):
        h = madde(b, rapor, maks)
        if h is not None:                        # güvenle kısalmayan başlık yerine sıradaki
            adaylar.append(b)
            hazir.append(h)
        if len(hazir) == adet:
            break
    if hazir:
        maddeler = [h[3] for h in hazir]
        daha = bool(kanca.get("manset"))
        giris = f"[calm] {SAYILAR[len(maddeler)]} başlık {'daha' if daha else 'var'}:"
        _ekle(zam, {"tur": "baslik-giris", "konusma": giris})
        for ses, tel, rak, _ in hazir:
            zam.append({"tur": "baslik-madde", "konusma": ses, "telaffuz": tel, "rakam": rak})
        parca = zam[1:]
        gos.append({"tur": "basliklar", "tema": sn.tema_bul(" ".join(adaylar), sn.YEDEK_TEMA),
                    "konusma": " ".join(x["konusma"] for x in parca),
                    "maddeler": maddeler, "tarih": sn.tarih_ekran(rapor),
                    "ust": (f"{len(maddeler)} BAŞLIK DAHA" if daha else f"BUGÜNÜN {len(maddeler)} BAŞLIĞI"),
                    "telaffuz": [e for x in parca for e in x["telaffuz"]],
                    "rakam": [e for x in parca for e in x["rakam"]],
                    "girisler": [0.1] * len(maddeler)})
    cagri = {"tur": "cagri", "tema": sn.KAPANIS_TEMA, "konusma": KAPANIS_SES, "telaffuz": [], "rakam": []}
    zam.append(cagri)
    gos.append(cagri)
    return gos, zam


def tahmini_sure(metin):
    """Etiketli metinden fragman süresi tahmini (sn): ön boşluk + konuşma/atempo + kuyruk."""
    return gv.ON_BOSLUK + len(sn.etiketsiz(metin)) / KONUSMA_KARAKTER_SN / gv.SES_HIZI + KUYRUK


def plan_sec(rapor, hedef=FRAGMAN_HEDEF_SN, plan=KISALTMA_PLANI):
    """Tahmini süresi hedefe sığan ilk plan -> (sira, gosterim, zamanlama, tahmin)."""
    for i, adim in enumerate(plan):
        gos, zam = sahneler(rapor, *adim)
        t = tahmini_sure(sn.tam_metin(gos))
        if t <= hedef or i == len(plan) - 1:
            return i, gos, zam, t


# --------------------------------------------------------------------------- #
# Çizim
# --------------------------------------------------------------------------- #

def sahne_basliklar(s):
    o, y = [], 360
    bas = cz._tuval(cz.GEN, 110)
    d = ImageDraw.Draw(bas)
    cz.aralikli(d, (0, 0), s["ust"], cz.font(46, 900), cz.ACCENT, 4)
    d.text((0, 62), s["tarih"], font=cz.font(32, 500), fill=cz.MUTED)
    o.append(cz.Oge(bas, cz.SOL, y, 0))
    y += 140
    for i, b in enumerate(s["maddeler"]):
        f = cz.font(52, 700)
        sol = 120
        sat = cz.sar(b, f, cz.GEN - sol - 50)
        lh = int(f.size * 1.2)
        h = max(130, lh * len(sat) + 56)
        k = cz.kart(cz.GEN, h, 22)
        d = ImageDraw.Draw(k)
        c = cz.cip(str(i + 1), cz.ACCENT, (0, 0, 0), 40, pad=(24, 10))
        k.alpha_composite(c, (28, (h - c.height) // 2))
        ty = (h - lh * len(sat)) // 2 - 4
        for j, x in enumerate(sat):
            d.text((sol + 20, ty + j * lh), x, font=f, fill=cz.INK)
        o.append(cz.Oge(k, cz.SOL, y, s["girisler"][i]))
        y += h + 22
    return o


def sahne_cagri(s):
    grafik = s.get("grafik")
    o = []
    if grafik is not None:
        y, f_ust, b_ust = 300, 56, 120
    else:                                      # grafik yok: çağrı ekranı kaplar
        y, f_ust, b_ust = 560, 72, 170
    im = cz._tuval(cz.GEN, int(f_ust * 1.4))
    ImageDraw.Draw(im).text((0, 0), KAPANIS_UST, font=cz.font(f_ust, 700), fill=cz.INK)
    o.append(cz.Oge(im, cz.SOL, y, 0))
    y += int(f_ust * 1.7)
    fb = cz.sigdir(KAPANIS_BUYUK, cz.GEN, b_ust, 900, 60)
    im = cz._tuval(cz.GEN, int(fb.size * 1.25))
    ImageDraw.Draw(im).text((0, 0), KAPANIS_BUYUK, font=fb, fill=cz.ACCENT)
    o.append(cz.Oge(im, cz.SOL - 4, y, 0.2))
    y += im.height + 16
    if grafik is not None:
        o.append(cz.Oge(grafik, cz.SOL, y, GRAFIK_GIRIS))
    return o


def sahne_ogeleri(s, sira):
    if s["tur"] == "basliklar":
        return sahne_basliklar(s), None
    if s["tur"] == "cagri":
        return sahne_cagri(s), None
    return gv.sahne_ogeleri(s, sira)


# --------------------------------------------------------------------------- #
# Üretim
# --------------------------------------------------------------------------- #

def _ses_ve_zaman(gos, zam, calisma):
    metin = sn.tam_metin(gos)
    mp3, tts = gv.ses_al(metin, calisma)
    ses_suresi = float(gv.calistir(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                    "-of", "csv=p=0", mp3]).stdout.strip())
    kel_z = gv.adres_birlestir(gv.kelime_zamanlari(zam, tts, mp3))
    top, ks_z, _ = gv.zaman_cizelgesi(zam, kel_z, ses_suresi, kuyruk=KUYRUK)
    return mp3, tts, ses_suresi, kel_z, top, ks_z


def uret(rapor, calisma, cikti, durum=None, grafik_verisi=None, kare_klasoru=None):
    """Ham fragman mp4'ü (IG katmanları yok) üretir -> özet dict. Hata fırlatabilir."""
    os.makedirs(calisma, exist_ok=True)
    sira, gos, zam, tahmin = plan_sec(rapor)
    log(f"[fragman] plan {KISALTMA_PLANI[sira]}, tahmini {tahmin:.1f} sn")
    mp3, tts, ses_suresi, kel_z, top, ks_z = _ses_ve_zaman(gos, zam, calisma)
    if top > FRAGMAN_HEDEF_SN + 1.0 and sira + 1 < len(KISALTMA_PLANI):
        sira += 1                                # tahmin tutmadı: bir kez daha kısa seslendir
        gos, zam = sahneler(rapor, *KISALTMA_PLANI[sira])
        log(f"[fragman] {top:.1f} sn uzun, plan {KISALTMA_PLANI[sira]} ile yeniden seslendiriliyor")
        mp3, tts, ses_suresi, kel_z, top, ks_z = _ses_ve_zaman(gos, zam, calisma)
    if top > FRAGMAN_MAKS_SN:
        raise RuntimeError(f"fragman çok uzun: {top:.1f} sn")

    # zamanlama sahneleri -> gösterim sahneleri (başlık giriş + maddeler tek bölüm)
    if len(gos) == 3:
        ks = [ks_z[0], [w for kel in ks_z[1:-1] for w in kel], ks_z[-1]]
    else:
        ks = [ks_z[0], ks_z[-1]]
    baslar = [0.0] + [max(0.0, kel[0][1] - 0.12) for kel in ks[1:]]
    ar = [(baslar[i], baslar[i + 1] if i + 1 < len(baslar) else top) for i in range(len(baslar))]
    if len(gos) == 3:
        b0 = ar[1][0]
        gos[1]["girisler"] = [max(0.1, kel[0][1] - b0 - 0.1) for kel in ks_z[2:-1]]
    gv_veri = grafik_verisi if grafik_verisi is not None else bg.veri_al()
    gos[-1]["grafik"] = bg.kart(gv_veri) if gv_veri else None

    parcalar = gv.altyazi_parcalari(ks, ar)
    if durum is None:                            # b-roll döndürme durumunu kirletme
        durum = os.path.join(calisma, "video-son-kullanim.json")
        if os.path.exists(ku.DURUM) and not os.path.exists(durum):
            shutil.copyfile(ku.DURUM, durum)
    gv.broll_hazirla(gos, rapor["id"], durum)
    miks = gv.ses_miksaji(mp3, top, calisma)
    kose = dg.hazirla(ks, top, gv.FPS)
    gv.render(gos, ar, parcalar, top, miks, cikti, kare_klasoru, calisma, kose, ogeler=sahne_ogeleri)
    ozet = {"yol": cikti, "sure": round(top, 2), "araliklar": [(round(a, 2), round(b, 2)) for a, b in ar],
            "basliklar": gos[1]["maddeler"] if len(gos) == 3 else [],
            "grafik": (gv_veri or {}).get("kaynak") if gos[-1]["grafik"] is not None else None,
            "cagri_bas": ar[-1][0], "plan": KISALTMA_PLANI[sira],
            "elevenlabs_karakter": 0 if tts.get("onbellek") else tts.get("maliyet"),
            "metin": sn.tam_metin(gos)}
    json.dump(ozet, open(os.path.join(calisma, "fragman-ozet.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    log(f"[fragman] bitti: {top:.2f} sn, bölümler {ozet['araliklar']}, grafik: {ozet['grafik']}")
    return ozet


# --------------------------------------------------------------------------- #
# IG katmanları: küçük nabızlı hap (bölüm 1-2) + büyük "📩 DM'den BUGÜN yaz" (kapanış)
# --------------------------------------------------------------------------- #

def cagri_katmani(yol, w=1080, h=1920):
    """Büyük çağrı: 📩 + DM'den BUGÜN yaz (sarı hap, sosyal.hap_ciz ölçüleri).
    Emoji fontu yoksa sosyal.cagri_katmani (çizilmiş ok)."""
    import sosyal
    from PIL import Image
    e = bg.emoji("\U0001F4E9", 64)
    if e is None:
        return sosyal.cagri_katmani(yol, w, h)
    Y, ic = sosyal.IG_CAGRI_YUKSEKLIK, 44
    f = cz.font(58, 800)
    tg = f.getlength(sosyal.IG_CAGRI_METIN)
    gen = int(ic + e.width + 22 + tg + ic)
    hap = Image.new("RGBA", (gen + 8, Y + 8), (0, 0, 0, 0))
    d = ImageDraw.Draw(hap)
    d.rounded_rectangle((4, 6, gen + 3, Y + 5), radius=Y // 2, fill=(0, 0, 0, 110))
    d.rounded_rectangle((0, 0, gen - 1, Y - 1), radius=Y // 2, fill=cz.ACCENT + (255,))
    hap.alpha_composite(e, (ic, (Y - e.height) // 2))
    d.text((ic + e.width + 22, Y // 2), sosyal.IG_CAGRI_METIN, font=f, fill=(0, 0, 0, 255), anchor="lm")
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    im.alpha_composite(hap, ((w - hap.width) // 2, sosyal.IG_CAGRI_Y))
    im.save(yol)
    return yol


def ig_fragman_uret(rapor, cikti, calisma, grafik_verisi=None):
    """Son IG hikâyesi mp4'ü: fragman + hap/çağrı katmanları. Hata fırlatabilir."""
    import sosyal
    is_klasoru = os.path.join(calisma, "fragman")
    os.makedirs(is_klasoru, exist_ok=True)
    ham = os.path.join(is_klasoru, "fragman-ham.mp4")
    oz = uret(rapor, is_klasoru, ham, grafik_verisi=grafik_verisi)
    kucuk = sosyal.kucuk_hap(os.path.join(is_klasoru, "ig-hap.png"))
    buyuk = cagri_katmani(os.path.join(is_klasoru, "ig-cagri.png"))
    top = oz["sure"]
    cagri_sn = top - oz["cagri_bas"]
    try:
        subprocess.run(sosyal.ig_varyant_komutu(ham, kucuk, buyuk, cikti, top, cagri_sn=cagri_sn), check=True)
    except subprocess.CalledProcessError:
        log("[fragman] nabızlı katman üretilemedi, sabit hapla deneniyor")
        subprocess.run(sosyal.ig_varyant_komutu(ham, kucuk, buyuk, cikti, top, cagri_sn=cagri_sn, nabiz=False),
                       check=True)
    sure = sosyal._sure(cikti)
    if sure > FRAGMAN_MAKS_SN:
        raise RuntimeError(f"fragman çok uzun: {sure:.1f} sn")
    log(f"[fragman] IG hikâyesi hazır: {sure:.2f} sn")
    return cikti


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rapor", default=gv.VARSAYILAN_RAPOR)
    ap.add_argument("--cikti", required=True)
    ap.add_argument("--calisma", required=True)
    ap.add_argument("--sadece-metin", action="store_true")
    a = ap.parse_args()
    rapor = gv.rapor_oku(a.rapor)
    if a.sadece_metin:
        i, gos, _, t = plan_sec(rapor)
        print(sn.tam_metin(gos))
        print(f"\nplan {KISALTMA_PLANI[i]}, tahmini {t:.1f} sn, {len(sn.etiketsiz(sn.tam_metin(gos)))} karakter")
        return
    ig_fragman_uret(rapor, a.cikti, a.calisma)


if __name__ == "__main__":
    main()
