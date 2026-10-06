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


if __name__ == "__main__":
    unittest.main()
