# -*- coding: utf-8 -*-
"""video/ paketi testleri — ağ çağrıları sahte, ffmpeg gerekmez.
Çalıştır: python -m unittest video.test_video"""
import json
import os
import subprocess
import tempfile
import unittest
from unittest import mock

from video import senaryo as s
from video import kutuphane as ku
from video import calistir as vc
from video import servisler as sv

RAPOR = {
    "id": "2026-09-29", "disclaimer": "Bilgilendirme amaçlıdır, yatırım tavsiyesi değildir.",
    "market": {"coins": {"BTC": {"priceUsd": 83589, "change24h": 0.458},
                         "ETH": {"priceUsd": 2681.71, "change24h": 1.0198}},
               "fearGreed": {"value": 73, "label": "Açgözlülük", "previousValue": 74}},
    "brief": {"mood": "Temkinli", "why": "Piyasa Bitget'teki hackin ardından ABD PCE enflasyon verisini bekliyor.",
              "criticalEvents": [{"timeTr": "17:00", "title": "ABD JOLTS verisi"},
                                 {"timeTr": None, "title": "HYPE token kilidi açılışı"}],
              "mainRisk": "HYPE unlock kaynaklı satış baskısı."},
    "sections": {"agenda": [
        {"importance": "kritik", "title": "THORChain, Bitget hackerinin fonlarını engellemeyi reddetti",
         "summary": "387,5 milyon dolarlık hack; saldırgana ait fonların bir kısmı bitcoin'e çevrildi."},
        {"importance": "onemli", "title": "Bitget aşamalı çekimlere başladı", "summary": "ETH ağları 29 Eylül'de."},
        {"importance": "onemli", "title": "HYPE'ta 904 milyon dolarlık kilit açılışı", "summary": "x"}]},
}


class Test(unittest.TestCase):
    def test_bicimler(self):
        self.assertEqual(s.fiyat_tr(83589), "$83.589")
        self.assertEqual(s.fiyat_tr(2681.71), "$2.681,71")
        self.assertEqual(s.fiyat_tr(1.5), "$1,50")
        self.assertEqual(s.yuzde_tr(0.4582), "+%0,46")
        self.assertEqual(s.yuzde_tr(-0.613), "−%0,61")
        self.assertEqual(s.buyuk_usd_tr(2869656860666), "$2,87 trilyon")

    def test_konusma_turkcelestirme(self):
        self.assertEqual(s.konusma("HYPE'ta kilit açılışı", RAPOR), "Hayp tokeninde kilit açılımı")
        self.assertIn("açık iş pozisyonları", s.konusma("ABD JOLTS verisi", RAPOR))
        self.assertIn("bugün", s.konusma("ETH ağları 29 Eylül'de devreye girdi", RAPOR))
        self.assertIn("yarın", s.konusma("30 Eylül'de açıklanacak", RAPOR))

    def test_sahneler(self):
        L = s.sahneler(RAPOR)
        turler = [x["tur"] for x in L]
        self.assertEqual(turler, ["kanca", "fiyat", "duygu", "haber", "haber", "risk", "takip", "kapanis"])
        haberler = [x for x in L if x["tur"] == "haber"]
        self.assertTrue(haberler[1]["baslik"].startswith("HYPE"))      # Bitget tekrarı atlandı
        self.assertEqual(haberler[0]["tema"], "hack-guvenlik")
        self.assertEqual(haberler[1]["tema"], "kilit")
        temalar = {x["tur"]: x["tema"] for x in L}
        self.assertEqual(temalar["kanca"], "kanca-sabah")          # sabah-sehir ∪ istanbul-sabah
        self.assertEqual(temalar["fiyat"], "sakin-yatay")          # BTC +%0,46 < eşik
        self.assertEqual(temalar["kapanis"], "kapanis")
        self.assertEqual(temalar["takip"], "takvim-veri")
        self.assertEqual(haberler[0]["vurgu"], "$387,5 milyon")
        self.assertEqual(haberler[1]["vurgu"], "")                     # rakam başlıkta zaten var
        self.assertTrue(s.tam_metin(L).endswith("[warm] Bay bay."))
        self.assertNotIn("'", s.etiketsiz(s.tam_metin(L)).replace("ABD'", ""))
        metin = s.tam_metin(L)
        self.assertIn("Doğukan Live nokta com", metin)
        self.assertNotIn("dogukanlive", metin)
        self.assertNotIn("yapay zekâ", metin)
        self.assertEqual(L[-1]["site"], "dogukanlive.com")
        self.assertFalse(L[-1]["not"])

    def test_tema_eslemesi(self):
        self.assertEqual(s.tema_bul("SEC, Coinbase davasında karar verdi"), "regulasyon-hukuk")
        self.assertEqual(s.tema_bul("Spot bitcoin ETF'lerine 500 milyon dolar giriş"), "etf-kurumsal")
        self.assertEqual(s.tema_bul("Powell faiz kararını açıkladı"), "fed-makro")
        self.assertEqual(s.tema_bul("Tether yeni USDT bastı"), "stablecoin-dolar")
        self.assertEqual(s.tema_bul("Bitcoin madencileri hashrate rekoru kırdı"), "bitcoin-madencilik")
        self.assertEqual(s.tema_bul("Binance yeni vadeli işlem çifti listeledi"), "borsa-islem-masasi")
        self.assertEqual(s.tema_bul("Solana memecoin çılgınlığı sürüyor"), "altcoin-cesitlilik")
        self.assertEqual(s.tema_bul("Piyasa sakin bir hafta geçirdi"), s.YEDEK_TEMA)
        self.assertEqual(s.tema_bul("İran-İsrail gerilimi petrolü yükseltti"), "jeopolitik")
        self.assertEqual(s.tema_bul("Rusya'ya yeni yaptırım paketi"), "jeopolitik")
        self.assertEqual(s.tema_bul("ETH staking getirisi arttı"), "ethereum-defi")
        self.assertEqual(s.tema_bul("Ethereum Layer 2 ağlarında likidite rekoru"), "ethereum-defi")
        self.assertEqual(s.tema_bul("Tether piyasaya 1 milyar yeni dolar bastı"), "stablecoin-dolar")  # "tether" ≠ eth
        self.assertEqual(s.tema_bul("Nvidia yapay zekâ çipi satışları patladı"), "yapay-zeka-teknoloji")
        self.assertEqual(s.tema_bul("Bu cüzdan balinaya ait"), s.YEDEK_TEMA)    # " ai" ≠ "ait"
        for tema, _ in s.TEMA_ANAHTARLARI:
            self.assertIn(tema, s.BROLL_PROMPTLARI)

    def test_piyasa_temasi(self):
        def r(ch):
            return {"market": {"coins": {"BTC": {"change24h": ch}}}}
        self.assertEqual(s.piyasa_temasi(r(2.1)), "piyasa-yukselis")
        self.assertEqual(s.piyasa_temasi(r(-1.3)), "piyasa-dusus")
        self.assertEqual(s.piyasa_temasi(r(0.2)), "sakin-yatay")
        self.assertEqual(s.piyasa_temasi({}), "sakin-yatay")

    def test_kutuphane_dondurme(self):
        with tempfile.TemporaryDirectory() as d:
            kat, dur = os.path.join(d, "kutuphane.json"), os.path.join(d, "son.json")
            for _ in range(3):
                dosya = ku.yeni_dosya("sabah-sehir", d)
                open(os.path.join(d, dosya), "wb").close()
                ku.ekle({"tema": "sabah-sehir", "dosya": dosya}, kat)
            self.assertEqual(ku.klipler("sabah-sehir", d, kat)[-1], "sabah-sehir/sabah-sehir-03.mp4")
            sec = lambda gun, n=1: [os.path.basename(x) for x in ku.sec("sabah-sehir", gun, n, d, kat, dur)]
            g1 = sec("2026-09-30")
            self.assertEqual(sec("2026-09-30"), g1)                    # aynı gün: aynı seçim
            g2, g3, g4 = sec("2026-10-01"), sec("2026-10-02"), sec("2026-10-03")
            self.assertEqual([g1, g2, g3, g4], [["sabah-sehir-01.mp4"], ["sabah-sehir-02.mp4"],
                                                ["sabah-sehir-03.mp4"], ["sabah-sehir-01.mp4"]])
            self.assertEqual(sec("2026-10-04", 2), ["sabah-sehir-02.mp4", "sabah-sehir-03.mp4"])
            self.assertEqual(sec("2026-10-05"), ["sabah-sehir-01.mp4"])  # dünün sonuncusu tekrar etmez
            self.assertEqual(ku.sec("yok", "2026-10-05", 1, d, kat, dur), [])
            ku.ekle({"tema": "sabah-sehir", "dosya": "sabah-sehir/sabah-sehir-02.mp4", "haric": True}, kat)
            self.assertNotIn("sabah-sehir/sabah-sehir-02.mp4", ku.klipler("sabah-sehir", d, kat))
            for _ in range(2):
                dosya = ku.yeni_dosya("istanbul-sabah", d)
                open(os.path.join(d, dosya), "wb").close()
                ku.ekle({"tema": "istanbul-sabah", "dosya": dosya}, kat)
            birlesik = [os.path.basename(x) for x in ku.klipler("kanca-sabah", d, kat)]
            self.assertEqual(birlesik, ["sabah-sehir-01.mp4", "istanbul-sabah-01.mp4",
                                        "sabah-sehir-03.mp4", "istanbul-sabah-02.mp4"])
            k1 = [os.path.basename(x) for x in ku.sec("kanca-sabah", "2026-10-06", 1, d, kat, dur)]
            k2 = [os.path.basename(x) for x in ku.sec("kanca-sabah", "2026-10-07", 1, d, kat, dur)]
            self.assertNotEqual(k1[0].split("-")[0], k2[0].split("-")[0])   # günden güne dönüşümlü

    def test_cizim_tum_sahneler(self):
        """Her sahne grafiği ve altyazı hatasız çizilir (ffmpeg gerekmez)."""
        from video import gunaydin as g
        from video import cizim as cz
        sira = 0
        for x in s.sahneler(RAPOR):
            ogeler, _ = g.sahne_ogeleri(x, sira)
            sira += x["tur"] == "haber"
            self.assertTrue(ogeler, x["tur"])
        self.assertGreater(cz.altyazi(["BİTCOİN", "YÜZDE"], 1).width, 0)

    def test_adres_birlestir(self):
        from video import gunaydin as g
        kel = [[("için:", 1.0, 1.2), ("Doğukan", 1.3, 1.6), ("Live", 1.6, 1.8), ("nokta", 1.8, 2.0),
                ("com.", 2.0, 2.3), ("Bay", 2.5, 2.7)]]
        self.assertEqual(g.adres_birlestir(kel)[0][1], ("dogukanlive.com.", 1.3, 2.3))


    def test_altyazi_orijinal_yazim(self):
        from video import gunaydin as g
        rapor = dict(RAPOR, brief={"mood": "Temkinli", "mainRisk": "SEC'in Coinbase davası ve AI."})
        sahne = next(x for x in s.sahneler(rapor) if x["tur"] == "risk")
        konusulan = s.etiketsiz(sahne["konusma"])
        self.assertIn("Es-İ-Si'nin Koinbeys", konusulan)
        harfler = list(konusulan)
        tts = {"alignment": {"characters": harfler,
                             "character_start_times_seconds": [i * 0.05 for i in range(len(harfler))],
                             "character_end_times_seconds": [(i + 1) * 0.05 for i in range(len(harfler))]}}
        kel = g.kelime_zamanlari([sahne], tts, None)[0]
        yazi = [k[0] for k in kel]
        self.assertEqual(yazi[yazi.index("SEC'in") + 1], "Coinbase")
        self.assertIn("AI.", yazi)
        self.assertNotIn("Koinbeys", " ".join(yazi))
        for (_, a1, b1), (_, a2, b2) in zip(kel, kel[1:]):
            self.assertLess(a1, b1)
            self.assertLessEqual(b1, a2)
            self.assertLessEqual(a2 - b1, 0.05 + 1e-9)

    def _altyazi(self, sahne):
        from video import gunaydin as g
        h = list(s.etiketsiz(sahne["konusma"]))
        tts = {"alignment": {"characters": h,
                             "character_start_times_seconds": [i * 0.05 for i in range(len(h))],
                             "character_end_times_seconds": [(i + 1) * 0.05 for i in range(len(h))]}}
        return g.kelime_zamanlari([sahne], tts, None)[0]

    def test_altyazi_saat_ve_yuzde_rakamla(self):
        rapor = dict(RAPOR, brief=dict(RAPOR["brief"], criticalEvents=[
            {"timeTr": "15:30", "title": "ABD PCE verisi, beklenti %2,4"},
            {"timeTr": "20:05", "title": "Fed konuşması"}]))
        sahne = next(x for x in s.sahneler(rapor) if x["tur"] == "takip")
        self.assertIn("Saat on beş otuzda", sahne["konusma"])
        self.assertIn("yüzde 2,4", sahne["konusma"])
        kel = self._altyazi(sahne)
        yazi = " ".join(k[0] for k in kel)
        self.assertIn("Saat 15:30'da ABD PCE verisi, beklenti", yazi)
        self.assertIn("%2,4.", yazi)
        self.assertIn("Saat 20:05'te Fed", yazi)
        self.assertNotIn("otuz", yazi)
        # çok kelimelik okunuş tek belirteç: süre "on beş otuzda" boyunca
        konusulan = s.etiketsiz(sahne["konusma"])
        bas = konusulan.index("on beş otuzda") * 0.05
        son = (konusulan.index("on beş otuzda") + len("on beş otuzda")) * 0.05
        k = next(k for k in kel if k[0] == "15:30'da")
        self.assertAlmostEqual(k[1], bas)
        self.assertAlmostEqual(k[2], son)

    def test_altyazi_fiyat_rakamla(self):
        sahne = next(x for x in s.sahneler(RAPOR) if x["tur"] == "fiyat")
        self.assertIn("83 bin 600 dolar", sahne["konusma"])
        yazi = " ".join(k[0] for k in self._altyazi(sahne))
        self.assertIn("Bitcoin 83.600 dolar", yazi)
        self.assertIn("Ethereum %1 artıyla 2.680 dolarda.", yazi)

    def test_altyazi_cftc_ekli(self):
        rapor = dict(RAPOR, brief={"mood": "Temkinli", "mainRisk": "CFTC'nin kural teklifi."})
        sahne = next(x for x in s.sahneler(rapor) if x["tur"] == "risk")
        self.assertIn("Si-Ef-Ti-Si'nin kural", sahne["konusma"])
        yazi = [k[0] for k in self._altyazi(sahne)]
        self.assertIn("CFTC'nin", yazi)

    def test_altyazi_kesme_orijinal(self):
        rapor = dict(RAPOR, brief={"mood": "Temkinli",
                                   "mainRisk": "Fed'den sonra Bitcoin'in ve Ethena'nın 15:30'da düşüşü."})
        sahne = next(x for x in s.sahneler(rapor) if x["tur"] == "risk")
        self.assertIn("Fed'den sonra Bitcoinin ve Etinanın", sahne["konusma"])
        yazi = " ".join(k[0] for k in self._altyazi(sahne))
        self.assertIn("Fed'den sonra Bitcoin'in ve Ethena'nın 15:30'da", yazi)
        self.assertNotIn("Bitcoinin", yazi)

    def test_kanca_manset_ve_btc(self):
        rapor = dict(RAPOR, market=dict(RAPOR["market"], coins={"BTC": {"priceUsd": 82279, "change24h": -1.62}}),
                     sections={"agenda": [{"title": "Hürmüz Boğazı'nda tanker saldırıları petrolü sıçrattı"}]})
        k = s.sahneler(rapor)[0]
        self.assertEqual(s.etiketsiz(k["konusma"]), "Günaydın! Hürmüz Boğazında tanker saldırıları "
                         "petrolü sıçrattı. Bitcoin 82 bin dolar, günde yüzde 1,6 düşüş.")
        self.assertEqual(k["alt"], "Hürmüz Boğazı'nda tanker saldırıları petrolü sıçrattı")
        self.assertEqual(k["mood"], "Temkinli")
        yazi = " ".join(w[0] for w in self._altyazi(k))
        self.assertIn("Boğazı'nda", yazi)
        self.assertIn("%1,6 düşüş.", yazi)
        self.assertTrue(k["manset"])
        from video import cizim as cz
        self.assertEqual(len(cz.sahne_kanca(k)), 2)          # tarih + manşet; "PİYASA TEMKİNLİ" yok

    def test_kanca_kucuk_harekette_rakam_yok(self):
        rapor = dict(RAPOR, market=dict(RAPOR["market"], coins={"BTC": {"priceUsd": 82279, "change24h": -0.18}}))
        k = s.etiketsiz(s.sahneler(rapor)[0]["konusma"])
        self.assertEqual(k, "Günaydın! THORChain, Bitget saldırganının fonlarını engellemeyi reddetti.")
        self.assertNotIn("Piyasa", k)

    def test_kanca_manset_kisaltma(self):
        def m(baslik):
            return s.kanca_manseti({"sections": {"agenda": [{"title": baslik}]}})
        self.assertEqual(m("Zayıf istihdam verisi BTC'yi sıçrattı, tasfiye dalgası sonra geri çekti"),
                         "Zayıf istihdam verisi BTC'yi sıçrattı")
        uzun = m("Bir iki üç dört beş altı yedi ve dokuz on on bir")
        self.assertEqual(uzun, "Bir iki üç dört beş altı yedi")
        for b in ("Bir iki üç dört beş altı yedi ve dokuz on", "Kısa başlık."):
            self.assertLessEqual(len(m(b).split()), s.KANCA_MAKS_KELIME)
        self.assertEqual(m("Kısa başlık."), "Kısa başlık")

    def test_haber_mansetu_tekrar_etmez(self):
        haber = next(x for x in s.sahneler(RAPOR) if x["tur"] == "haber")
        self.assertTrue(haber["konusma"].startswith("[serious] Manşete dönelim: 387 milyon dolarlık"))
        self.assertNotIn("reddetti", haber["konusma"])
        self.assertIn("THORChain", haber["baslik"])            # ekranda başlık durur
        rapor = dict(RAPOR, sections={"agenda": [dict(RAPOR["sections"]["agenda"][0], summary="")]})
        haber = next(x for x in s.sahneler(rapor) if x["tur"] == "haber")
        self.assertTrue(haber["konusma"].startswith("[serious] Günün haberi: THORChain"))

    def test_kanca_mansetsiz_eski_davranis(self):
        rapor = dict(RAPOR, sections={"agenda": []})
        k = s.sahneler(rapor)[0]
        self.assertIn("Bugün 29 Eylül Salı. [calm] Piyasa temkinli", k["konusma"])
        self.assertFalse(k["manset"])
        from video import cizim as cz
        self.assertEqual(len(cz.sahne_kanca(dict(k, alt="Gündem"))), 3)   # eski ekran: tarih, ruh hâli, alt
        self.assertEqual(s.kanca_manseti({}), "")

    def test_orijinal_yazim_art_arda_kelimeler(self):
        from video import gunaydin as g
        import telaffuz
        konusulan, es = telaffuz.donustur_eslemeli("SEC ve ABD, AI. Binance'te ETH")
        kel = [(k, i * 1.0, i * 1.0 + 0.8) for i, k in enumerate(konusulan.split())]
        sonuc = g.orijinal_yazim(kel, es)
        self.assertEqual([k[0] for k in sonuc], ["SEC", "ve", "ABD,", "AI.", "Binance'te", "ETH"])
        self.assertEqual(sonuc[2], ("ABD,", 2.0, 2.8))
        self.assertEqual(sonuc[3], ("AI.", 3.0, 4.8))
        self.assertEqual(sonuc[4], ("Binance'te", 5.0, 5.8))

    def test_orijinal_yazim_bas_harf_ve_coklu_kelime(self):
        from video import gunaydin as g
        kel = [("Steyking", 0.0, 0.5), ("ve", 0.5, 0.6), ("yapay", 0.6, 0.9), ("zekâ,", 0.9, 1.3)]
        es = [(("steyking",), ("staking",)), (("yapay", "zekâ"), ("AI",))]
        self.assertEqual(g.orijinal_yazim(kel, es),
                         [("Staking", 0.0, 0.5), ("ve", 0.5, 0.6), ("AI,", 0.6, 1.3)])


class _Yanit:
    def __init__(self, veri, kod=200, basliklar=None):
        self._veri, self.status_code, self.headers, self.text = veri, kod, basliklar or {}, ""

    def json(self):
        return self._veri


class _Http:
    def __init__(self, yanitlar):
        self.yanitlar, self.cagrilar = list(yanitlar), []

    def post(self, url, **kw):
        self.cagrilar.append((url, kw))
        y = self.yanitlar.pop(0)
        if isinstance(y, Exception):
            raise y
        return y


class _Surec:
    def __init__(self, kod=0, zaman_asimi=False):
        self.kod, self.zaman_asimi, self.pid, self.args = kod, zaman_asimi, 999999, None

    def wait(self, timeout=None):
        if self.zaman_asimi and timeout is not None and timeout < 60:
            self.zaman_asimi = False
            raise subprocess.TimeoutExpired("video", timeout)
        return self.kod


class TestKutuphaneDepo(unittest.TestCase):
    def test_katalog_klipleri_var(self):
        kat = ku.yukle()["klipler"]
        self.assertGreater(len(kat), 30)
        for k in kat:
            self.assertFalse(k.get("haric"), k["dosya"])
            self.assertTrue(os.path.exists(os.path.join(ku.KLASOR, k["dosya"])), k["dosya"])
        for tema in [x for x, _ in s.TEMA_ANAHTARLARI] + [s.RISK_TEMA, s.TAKIP_TEMA, s.KAPANIS_TEMA,
                                                           s.SABAH_TEMA, s.YEDEK_TEMA]:
            self.assertTrue(ku.klipler(tema), tema)

    def test_durum_state_altinda(self):
        self.assertEqual(os.path.relpath(ku.DURUM, s.DEPO_KOKU),
                         os.path.join("state", "video-son-kullanim.json"))

    def test_font_depoda(self):
        from video import cizim as cz
        self.assertTrue(os.path.exists(cz._FONT_ADAYLARI[0]))
        self.assertTrue(os.path.exists(os.path.join(os.path.dirname(cz._FONT_ADAYLARI[0]), "OFL.txt")))


class TestServisler(unittest.TestCase):
    def test_zamanli_ses(self):
        import base64
        http = _Http([_Yanit({"audio_base64": base64.b64encode(b"mp3").decode(),
                              "alignment": {"characters": ["a"]}}, basliklar={"character-cost": "116"})])
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(sv, "anahtar_oku", return_value="k"):
            yol = os.path.join(d, "s.mp3")
            d2 = sv.seslendir_zamanli("[calm] Merhaba.", yol, log=lambda m: None, http=http)
            with open(yol, "rb") as f:
                self.assertEqual(f.read(), b"mp3")
        self.assertEqual(d2["maliyet"], 116)
        url, kw = http.cagrilar[0]
        self.assertTrue(url.endswith(f"/{sv.SES_ID}/with-timestamps"))
        self.assertEqual(kw["json"]["model_id"], "eleven_v4")

    def test_anahtar_yoksa_hata(self):
        with mock.patch.object(sv, "anahtar_oku", return_value=""):
            with self.assertRaises(sv.ServisHatasi):
                sv.seslendir_zamanli("x", "/nonexistent/x.mp3", http=_Http([]))


class TestCalistir(unittest.TestCase):
    def test_bayraklar(self):
        self.assertFalse(vc.aktif_mi({}))
        self.assertFalse(vc.aktif_mi({"VIDEO_OZET": "0"}))
        self.assertTrue(vc.aktif_mi({"VIDEO_OZET": "1"}))
        o = {"TELEGRAM_ADMIN_CHAT_ID": "42", "TELEGRAM_CHAT_ID": "-100"}
        self.assertEqual(vc.hedef_sohbet(o), ("admin", "42"))                  # varsayılan admin
        self.assertEqual(vc.hedef_sohbet({**o, "VIDEO_HEDEF": "admin"}), ("admin", "42"))
        with mock.patch.object(vc, "log"):
            self.assertEqual(vc.hedef_sohbet({**o, "VIDEO_HEDEF": "kanal"}), ("kanal", None))  # kapalı
            with mock.patch.object(vc, "KANAL_ACIK", True):
                self.assertEqual(vc.hedef_sohbet({**o, "VIDEO_HEDEF": "kanal"}), ("kanal", "-100"))
            self.assertEqual(vc.hedef_sohbet({**o, "VIDEO_HEDEF": "x"})[1], None)

    def test_izole_kapaliyken_calismaz(self):
        popen = mock.Mock()
        with mock.patch.object(vc, "log"):
            self.assertFalse(vc.izole_calistir({"id": "x"}, ortam={}, popen=popen))
        popen.assert_not_called()

    def test_izole_basari_ve_hata(self):
        with mock.patch.object(vc, "log"):
            p = _Surec(0)
            popen = mock.Mock(return_value=p)
            self.assertTrue(vc.izole_calistir({"id": "2026-09-29"}, ortam={"VIDEO_OZET": "1"}, popen=popen))
            args = popen.call_args[0][0]
            self.assertEqual(args[1:3], ["-m", "video.calistir"])
            self.assertFalse(vc.izole_calistir({"id": "x"}, ortam={"VIDEO_OZET": "1"},
                                               popen=mock.Mock(return_value=_Surec(1))))
            self.assertFalse(vc.izole_calistir({"id": "x"}, ortam={"VIDEO_OZET": "1"},
                                               popen=mock.Mock(side_effect=OSError("yok"))))

    def test_izole_zaman_asimi_durdurur(self):
        with mock.patch.object(vc, "log"), mock.patch.object(vc, "_oldur") as oldur:
            p = _Surec(0, zaman_asimi=True)
            self.assertFalse(vc.izole_calistir({"id": "x"}, ust_sinir=1, ortam={"VIDEO_OZET": "1"},
                                               popen=mock.Mock(return_value=p)))
            oldur.assert_called_once_with(p)

    def test_boyut_sigdir(self):
        cagri = mock.Mock()
        self.assertEqual(vc.boyut_sigdir("a.mp4", calistir=cagri, boyut=lambda y: 10), "a.mp4")
        cagri.assert_not_called()
        boyutlar = {"a.mp4": 60 * 2 ** 20, "a-kucuk.mp4": 40 * 2 ** 20}
        with mock.patch.object(vc, "log"):
            yeni = vc.boyut_sigdir("a.mp4", calistir=cagri, boyut=boyutlar.get, sure=lambda y: 60.0)
        self.assertEqual(yeni, "a-kucuk.mp4")
        komut = cagri.call_args[0][0]
        kbps = int(komut[komut.index("-b:v") + 1][:-1])
        self.assertLess((kbps + 128) * 1000 * 60 / 8, vc.TELEGRAM_SINIR)

    def test_video_gonder(self):
        http = _Http([OSError("ağ"), _Yanit({"ok": True})])
        with tempfile.NamedTemporaryFile(suffix=".mp4") as f, mock.patch.object(vc, "log"):
            vc.video_gonder("123456789:ABCDEFGHIJKLMNOP", "42", f.name, vc.ACIKLAMA["admin"], 59.7,
                            http=http, bekle=lambda s: None)
        url, kw = http.cagrilar[-1]
        self.assertTrue(url.endswith("/sendVideo"))
        self.assertEqual(kw["data"]["chat_id"], "42")
        self.assertEqual(kw["data"]["supports_streaming"], "true")
        self.assertEqual((kw["data"]["width"], kw["data"]["height"]), ("1080", "1920"))
        self.assertEqual(kw["data"]["duration"], "60")
        self.assertEqual(kw["data"]["caption"], "Günaydın Kripto video önizleme (sadece sana)")

    def test_video_gonder_hata_tokeni_gizler(self):
        tok = "123456789:ABCDEFGHIJKLMNOP"
        http = _Http([_Yanit({"ok": False, "description": "bad"})] * vc.MAX_DENEME)
        with tempfile.NamedTemporaryFile(suffix=".mp4") as f, mock.patch.object(vc, "log"), \
                mock.patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": tok}):
            with self.assertRaises(RuntimeError) as c:
                vc.video_gonder(tok, "42", f.name, "x", http=http, bekle=lambda s: None)
        self.assertNotIn(tok, str(c.exception))

    def test_main_hedef_yoksa_uretmez(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(vc, "log"), \
                mock.patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "", "TELEGRAM_ADMIN_CHAT_ID": ""}):
            yol = os.path.join(d, "r.json")
            with open(yol, "w") as f:
                json.dump({"id": "2026-09-29"}, f)
            with mock.patch("video.gunaydin.uret") as uret:
                self.assertEqual(vc.main(["--rapor", yol]), 0)
                uret.assert_not_called()

    def test_main_hata_cikis_1(self):
        with mock.patch.object(vc, "log"):
            self.assertEqual(vc.main(["--rapor", "/yok/r.json", "--gonderme"]), 1)


class TestDoganKose(unittest.TestCase):
    KS = [[("Günaydın!", 0.2, 0.9), ("Bugün", 1.0, 1.4), ("Salı.", 2.0, 2.6)],
          [("Bay", 10.0, 10.1), ("bay.", 10.2, 10.8)]]

    def _sahte_kareler(self):
        import numpy as np
        from video import dogan as dg
        F = lambda n, v: np.full((n, dg.IC, dg.IC, 3), v, np.uint8)  # noqa: E731
        return F(58, 200), F(69, 100), F(121, 50)

    def test_konusma_araliklari_birlesir(self):
        from video import dogan as dg
        # 0.9→1.0 (0.1 sn) birleşir; 1.4→2.0 (0.6 sn) ayrı; 10.1→10.2 birleşir
        self.assertEqual(dg.konusma_araliklari(self.KS), [[0.2, 1.4], [2.0, 2.6], [10.0, 10.8]])

    def test_kapanis_bay_bay_oncesi(self):
        from video import dogan as dg
        self.assertAlmostEqual(dg.kapanis_zamani(self.KS), 10.0 - dg.KAPANIS_ONDE)
        self.assertAlmostEqual(dg.kapanis_zamani([[("Hoşça", 3.0, 3.4), ("kalın.", 3.5, 4.0)]]),
                               3.5 - dg.KAPANIS_ONDE)
        self.assertIsNone(dg.kapanis_zamani([[]]))

    def test_agirliklar_gecis_ve_kapanis(self):
        from video import dogan as dg
        fps = 30
        wa, wb, wc = dg.agirliklar(360, fps, dg.konusma_araliklari(self.KS), dg.kapanis_zamani(self.KS))
        for i in range(360):
            self.assertAlmostEqual(wa[i] + wb[i] + wc[i], 1.0)
        self.assertEqual(wa[int(0.6 * fps)], 1.0)              # konuşma
        self.assertEqual(wb[int(5.0 * fps)], 1.0)              # bekleme
        self.assertEqual(wc[int(11.0 * fps)], 1.0)             # el sallama
        self.assertEqual(wc[int(9.4 * fps)], 0.0)
        k = 287                                                 # ilk t >= 9.55 karesi
        self.assertTrue(0 < wc[k] < 1)                          # yumuşak geçiş
        self.assertGreater(wc[k - 2], 0)
        self.assertEqual(wc[k - 3], 0)

    def test_kare_ve_bindirme(self):
        from PIL import Image
        from video import dogan as dg
        k = dg.Kose(self.KS, 12.0, 30, kareler=self._sahte_kareler())
        b = k.kare(int(0.6 * 30))
        self.assertEqual(b.size, (dg.D, dg.D))
        self.assertEqual(b.getpixel((dg.D // 2, dg.D // 2)), (200, 200, 200, 255))   # konuşma klibi
        self.assertEqual(b.getpixel((0, 0))[3], 0)                                    # daire dışı saydam
        self.assertEqual(b.getpixel((dg.D // 2, 2))[:3], (242, 183, 5))               # sarı kenar
        self.assertEqual(k.kare(int(11 * 30)).getpixel((dg.D // 2, dg.D // 2))[:3], (50, 50, 50))
        im = Image.new("RGBA", (1080, 1920), (0, 0, 0, 255))
        self.assertTrue(k.bindir(im, 10 ** 6))                 # taşan indis kırpılır
        self.assertEqual(im.getpixel((dg.X + dg.D // 2, dg.Y + dg.D // 2))[:3], (50, 50, 50))

    def test_hata_halinde_dogansiz_devam(self):
        from video import dogan as dg
        with mock.patch.object(dg, "log"), \
                mock.patch.object(dg, "_kareler", side_effect=FileNotFoundError("yok")):
            self.assertIsNone(dg.hazirla(self.KS, 12.0, 30, ortam={}))
        k = dg.Kose(self.KS, 12.0, 30, kareler=self._sahte_kareler())
        with mock.patch.object(dg, "log"), mock.patch.object(k, "kare", side_effect=ValueError("bozuk")):
            self.assertFalse(k.bindir(object(), 0))

    def test_kapatma_degiskeni(self):
        from video import dogan as dg
        self.assertTrue(dg.aktif_mi({}))
        for v in ("kapali", "KAPALI", "0", "false"):
            self.assertFalse(dg.aktif_mi({"DOGAN_KOSE": v}))
        with mock.patch.object(dg, "log"), mock.patch.object(dg, "_kareler") as kar:
            self.assertIsNone(dg.hazirla(self.KS, 12.0, 30, ortam={"DOGAN_KOSE": "kapali"}))
            kar.assert_not_called()

    def test_varliklar_depoda_ve_kucuk(self):
        from video import dogan as dg
        top = 0
        for ad in ("konusma", "bekleme", "kapanis"):
            yol = os.path.join(dg.KLASOR, ad + ".mp4")
            self.assertTrue(os.path.isfile(yol), yol)
            top += os.path.getsize(yol)
        self.assertLess(top, 3 * 1024 * 1024)


if __name__ == "__main__":
    unittest.main()


# --------------------------------------------------------------------------- #
# IG fragmanı (video/fragman.py + video/btc_grafik.py)
# --------------------------------------------------------------------------- #

from video import fragman as fr          # noqa: E402
from video import btc_grafik as bg       # noqa: E402
from video import gunaydin as gv         # noqa: E402

FRAGMAN_RAPOR = {
    "id": "2026-10-09", "disclaimer": "Bilgilendirme amaçlıdır.",
    "market": {"coins": {"BTC": {"priceUsd": 82279, "change24h": -2.4}}},
    "brief": {"mood": "Temkinli"},
    "sections": {"agenda": [
        {"title": "Hürmüz Boğazı'nda tanker saldırıları petrolü sıçrattı"},
        {"title": "ABD 10 yıllık tahvil getirisi 22 yılın zirvesine çıktı"},
        {"title": "Fed'den Waller'dan İstanbul'da şahin ama esnek mesaj"},
        {"title": "Hyperliquid ekibi 329 milyon dolarlık HYPE'ı OTC sattı"},
        {"title": "Bitcoin spot ETF'lerinden Haziran'dan beri en büyük çıkış"},
    ]},
}


def _noktalamasiz(kelimeler):
    import re
    return [re.sub(r"[.,;:!?]+$", "", w) for w in kelimeler]


class TestFragman(unittest.TestCase):
    def test_baslik_kisalt_en_fazla_yedi(self):
        ornekler = {
            "ABD 10 yıllık tahvil getirisi 22 yılın zirvesine çıktı": "ABD tahvil getirisi 22 yılın zirvesine çıktı",
            "Bitcoin spot ETF'lerinden Haziran'dan beri en büyük çıkış":
                "Bitcoin ETF'lerinden Haziran'dan beri en büyük çıkış",
            "Zayıf istihdam verisi BTC'yi sıçrattı, tasfiye dalgası geri çekti": "Zayıf istihdam verisi BTC'yi sıçrattı",
            "Fed'in Eylül tutanakları şahin çıktı ama piyasa omuz silkti": "Fed'in Eylül tutanakları şahin çıktı",
            "Grayscale'in Zcash ETF'i (ZCSH) 890 milyon dolara yaklaştı":
                "Grayscale'in Zcash ETF'i 890 milyon dolara yaklaştı",
            "Kısa başlık.": "Kısa başlık",
        }
        for girdi, beklenen in ornekler.items():
            self.assertEqual(fr.baslik_kisalt(girdi), beklenen)
        uzun = "Circle kurumsal müşterilere BTC teminatlı USDC borç verme hizmeti başlattı"
        self.assertLessEqual(len(fr.baslik_kisalt(uzun).split()), 7)
        # 7'nin altı yalnız güvenli adımlarla: anlam bozulacaksa olduğu gibi kalır
        self.assertEqual(fr.baslik_kisalt("Fed'den Waller'dan İstanbul'da şahin ama esnek mesaj", 6, zorla=False),
                         "Fed'den Waller'dan şahin ama esnek mesaj")
        self.assertEqual(len(fr.baslik_kisalt("Bir iki üç dört beş altı yedi", 5, zorla=False).split()), 7)

    def test_ses_ve_ekran_ayni_kelimeler(self):
        for adim in fr.KISALTMA_PLANI:
            gos, zam = fr.sahneler(FRAGMAN_RAPOR, *adim)
            self.assertEqual(sn_tam(gos), sn_tam(zam))
            maddeler = gos[1]["maddeler"]
            self.assertEqual(len(maddeler), adim[2])
            kel = [[(w, 0.0, 0.0) for w in s.etiketsiz(z["konusma"]).split()] for z in zam]
            altyazi = gv._orijinal_yazimlar(zam, kel)[2:-1]            # başlık maddeleri
            for m, k in zip(maddeler, altyazi):
                self.assertLessEqual(len(m.split()), fr.BASLIK_MAKS)
                self.assertEqual(_noktalamasiz([w[0] for w in k]), _noktalamasiz(m.split()))
        gos, _ = fr.sahneler(FRAGMAN_RAPOR, 7, True, 3)
        self.assertNotIn("Hürmüz", " ".join(gos[1]["maddeler"]))       # manşet kancada; tekrar yok
        self.assertIn("Üç başlık daha:", gos[1]["konusma"])
        self.assertEqual(gos[1]["ust"], "3 BAŞLIK DAHA")
        self.assertIn("HYPE tokenini", gos[1]["maddeler"][2])          # seste yeniden kurulan ifade ekranda da
        self.assertIn("Bitcoin 82 bin dolar", gos[0]["konusma"])
        self.assertNotIn("Bitcoin 82 bin", fr.sahneler(FRAGMAN_RAPOR, 7, False, 3)[0][0]["konusma"])
        self.assertEqual(gos[-1]["konusma"], "[warm] Haberler ve grafikler için bana BUGÜN yaz. Bay bay!")
        self.assertNotIn("Acele", gos[-1]["konusma"])

    def test_mansetsiz_kanca_bugunun_basliklari(self):
        r = dict(FRAGMAN_RAPOR, sections={"agenda": [{"title": ""}] + FRAGMAN_RAPOR["sections"]["agenda"][1:]})
        gos, _ = fr.sahneler(r)
        self.assertFalse(gos[0]["manset"])
        self.assertEqual(gos[1]["ust"], "BUGÜNÜN 3 BAŞLIĞI")
        self.assertIn("Üç başlık var:", gos[1]["konusma"])

    def test_sure_hedefe_gore_plan(self):
        self.assertAlmostEqual(fr.tahmini_sure("[calm] " + "a" * 120),
                               gv.ON_BOSLUK + 10.0 / gv.SES_HIZI + fr.KUYRUK)
        i, gos, _, t = fr.plan_sec(FRAGMAN_RAPOR)
        self.assertLessEqual(t, fr.FRAGMAN_HEDEF_SN)
        self.assertAlmostEqual(t, fr.tahmini_sure(sn_tam(gos)))
        for j in range(i):                      # önceki (daha uzun) planlar hedefi aşıyordu
            self.assertGreater(fr.tahmini_sure(sn_tam(fr.sahneler(FRAGMAN_RAPOR, *fr.KISALTMA_PLANI[j])[0])),
                               fr.FRAGMAN_HEDEF_SN)
        kisa = dict(FRAGMAN_RAPOR, market={"coins": {"BTC": {"priceUsd": 82279, "change24h": 0.1}}},
                    sections={"agenda": [{"title": "BTC yatay"}, {"title": "ETF girişi sürüyor"},
                                         {"title": "Solana ağı güncellendi"}, {"title": "XRP sakin"}]})
        self.assertEqual(fr.plan_sec(kisa)[0], 0)
        # hiçbiri sığmasa da en kısa plan döner; 59 sn sınırı uret()'te
        self.assertEqual(fr.plan_sec(FRAGMAN_RAPOR, hedef=1.0)[0], len(fr.KISALTMA_PLANI) - 1)

    def test_uzun_fragman_reddedilir(self):
        with mock.patch.object(fr, "_ses_ve_zaman", return_value=(None, {}, 60, [], 61.0, [])), \
                mock.patch("sys.stderr"):
            with self.assertRaises(RuntimeError):
                fr.uret(FRAGMAN_RAPOR, tempfile.mkdtemp(), "x.mp4", grafik_verisi={})


def sn_tam(sahneler):
    return s.tam_metin(sahneler)


def _mumlar(n=300):
    t0 = 1_700_000_000
    # Coinbase: [time, low, high, open, close, volume], yeniden eskiye
    return [[t0 + i * 86400, 100 + i - 2, 100 + i + 2, 100 + i, 100 + i + 1, 5] for i in reversed(range(n))]


class TestBtcGrafik(unittest.TestCase):
    def _getir(self, coinbase=None, coingecko=None):
        cagrilar = []

        def getir(url, params=None, headers=None):
            cagrilar.append(url)
            kaynak = coinbase if "coinbase" in url else coingecko
            if isinstance(kaynak, Exception):
                raise kaynak
            return kaynak
        return getir, cagrilar

    def test_coinbase_mumlari(self):
        getir, cagrilar = self._getir(coinbase=_mumlar())
        with mock.patch("sys.stderr"):
            v = bg.veri_al(getir)
        self.assertEqual((v["tur"], v["kaynak"], len(v["mumlar"])), ("mum", "Coinbase", 300))
        self.assertLess(v["zaman"][0], v["zaman"][-1])                  # eskiden yeniye
        self.assertEqual(v["mumlar"][-1][1:], (399.0, 401.0, 397.0, 400.0))   # (açılış, yüksek, düşük, kapanış)
        self.assertEqual(cagrilar, [bg.COINBASE_URL])
        o = bg.ozet(v)
        self.assertEqual(len(o["kapanis"]), bg.GORUNEN)
        self.assertNotIn(None, o["s200"])                                # 200g ortalama tüm pencerede
        self.assertEqual(o["yuksek30"], 401.0)
        self.assertEqual(o["dusuk30"], 100 + 270 - 2)

    def test_coinbase_hatasinda_coingecko_cizgi(self):
        fiyatlar = [[(1_700_000_000 + i * 86400) * 1000, 100.0 + i] for i in range(300)]
        getir, cagrilar = self._getir(coinbase=RuntimeError("451"), coingecko={"prices": fiyatlar})
        with mock.patch("sys.stderr"):
            v = bg.veri_al(getir)
        self.assertEqual((v["tur"], v["kaynak"]), ("cizgi", "CoinGecko"))
        self.assertEqual(cagrilar, [bg.COINBASE_URL, bg.COINGECKO_URL])
        self.assertEqual(v["kapanis"][-1], 399.0)

    def test_az_veri_de_hata_sayilir(self):
        getir, _ = self._getir(coinbase=_mumlar(10), coingecko={"prices": []})
        with mock.patch("sys.stderr"):
            self.assertIsNone(bg.veri_al(getir))

    def test_ikisi_de_yoksa_grafiksiz(self):
        getir, _ = self._getir(coinbase=RuntimeError("451"), coingecko=RuntimeError("429"))
        with mock.patch("sys.stderr"):
            self.assertIsNone(bg.veri_al(getir))
        # grafiksiz kapanış sahnesi çizilir (çağrı büyür)
        ogeler = fr.sahne_cagri({"grafik": None})
        self.assertEqual(len(ogeler), 2)

    def test_kart_cizer_bozuk_veride_none(self):
        getir, _ = self._getir(coinbase=_mumlar())
        with mock.patch("sys.stderr"):
            v = bg.veri_al(getir)
            k = bg.kart(v)
            self.assertEqual(k.size, (fr.cz.GEN, 520))
            self.assertEqual(len(fr.sahne_cagri({"grafik": k})), 3)
            self.assertIsNone(bg.kart({"tur": "mum", "kaynak": "x", "kapanis": [], "zaman": [], "mumlar": []}))
