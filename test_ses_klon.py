# -*- coding: utf-8 -*-
"""ses_klon (ElevenLabs klon sesli özet) birim testleri — ağ/anahtar GEREKTİRMEZ."""
import copy
import os
import shutil
import subprocess
import tempfile
import unittest

import ses_klon as sk
import telaffuz

RAPOR = {
    "id": "2026-09-29",
    "title": "29 Eylül 2026, Salı",
    "market": {
        "coins": {
            "BTC": {"priceUsd": 83589, "change24h": 0.458},
            "ETH": {"priceUsd": 2681.71, "change24h": 1.0198},
        },
        "fearGreed": {"value": 73, "label": "Açgözlülük", "previousValue": 74},
    },
    "brief": {
        "mood": "Temkinli",
        "why": ("Fiyatlar dar bir bantta yatay seyrediyor; piyasa Bitget'teki 387,5 milyon "
                "dolarlık hackin ardından THORChain'in saldırgana ait fonları engellemeyi "
                "reddetmesinin güven üzerindeki etkisini ve yarınki ABD PCE enflasyon verisini bekliyor."),
        "criticalEvents": [
            {"timeTr": "11:00", "title": "Bitget ETH çekimleri açılışı"},
            {"timeTr": "17:00", "title": "ABD JOLTS verisi"},
            {"timeTr": None, "title": "HYPE token kilidi açılışı"},
            {"timeTr": "21:00", "title": "Dördüncü olay"},
        ],
        "mainRisk": ("THORChain üzerinden nakde çevrilen çalıntı fonlar ve HYPE unlock kaynaklı "
                     "olası satış baskısı kısa vadeli oynaklığı artırabilir."),
    },
    "sections": {"today": []},
}


def rapor():
    return copy.deepcopy(RAPOR)


class Bicimler(unittest.TestCase):
    def test_usd_konusma(self):
        self.assertEqual(sk.usd_konusma(83589), "83 bin 600")
        self.assertEqual(sk.usd_konusma(2681.71), "2 bin 680")
        self.assertEqual(sk.usd_konusma(105432), "105 bin")
        self.assertEqual(sk.usd_konusma(1234), "bin 230")
        self.assertEqual(sk.usd_konusma(387.5e6), "387 milyon")
        self.assertEqual(sk.usd_konusma(2.87e12), "2870 milyar")
        self.assertEqual(sk.usd_konusma(118.51), "119")

    def test_yuzde_konusma(self):
        self.assertEqual(sk.yuzde_konusma(1.0198), "bir")
        self.assertEqual(sk.yuzde_konusma(-2.345), "2,3")
        self.assertEqual(sk.yuzde_konusma(12.04), "12")

    def test_saat_konusma(self):
        self.assertEqual(sk.saat_konusma("11:00"), "saat on birde")
        self.assertEqual(sk.saat_konusma("17:00"), "saat on yedide")
        self.assertEqual(sk.saat_konusma("15:30"), "saat on beş otuzda")
        self.assertEqual(sk.saat_konusma("14:00"), "saat on dörtte")
        self.assertEqual(sk.saat_konusma("10:00"), "saat onda")
        self.assertEqual(sk.saat_konusma("09:05"), "saat dokuz sıfır beşte")
        self.assertEqual(sk.saat_konusma("20:40"), "saat yirmi kırkta")
        self.assertIsNone(sk.saat_konusma("25:00"))
        self.assertIsNone(sk.saat_konusma(""))


class Telaffuz(unittest.TestCase):
    def test_borsa_kesmesi(self):
        self.assertEqual(sk.telaffuz_duzelt("Bitget'teki hack"), "Bitget borsasındaki hack")
        self.assertEqual(sk.telaffuz_duzelt("Binance'ten çıkış"), "Baynens borsasından çıkış")
        self.assertEqual(sk.telaffuz_duzelt("Coinbase'in hissesi"), "Koinbeys borsasının hissesi")

    def test_ag_kesmesi(self):
        self.assertEqual(sk.telaffuz_duzelt("THORChain'in kararı"), "THORChain ağının kararı")

    def test_bilinmeyen_ad_ve_kisaltma(self):
        self.assertEqual(sk.telaffuz_duzelt("Bitcoin'in"), "Bitcoinin")
        self.assertEqual(sk.telaffuz_duzelt("ABD'nin verisi"), "A-Be-De'nin verisi")

    def test_kisa_adda_kesme_kalir(self):
        self.assertEqual(sk.telaffuz_duzelt("Fed'den sonra"), "Fed'den sonra")
        self.assertEqual(sk.telaffuz_duzelt("Nasdaq'ta"), "Nasdaqta")

    def test_saatten_sonra_yuzde(self):
        es = []
        t = sk.telaffuz_duzelt("saat 15:30'da %2,5 düştü", eslemeler=es)
        self.assertEqual(t, "saat on beş otuzda yüzde 2,5 düştü")
        self.assertEqual(es, [(("on", "beş", "otuzda"), ("15:30'da",)), (("yüzde", "2,5"), ("%2,5",))])
        self.assertEqual(sk.telaffuz_duzelt("2.5% arttı"), "yüzde 2,5 arttı")

    def test_kesme_eslemesi_metin_sirasiyla(self):
        es = []
        t = sk.telaffuz_duzelt("Bitcoin'in fiyatı 15:30'da Ethereum'un Fed'den önce",
                               fonetik=False, eslemeler=es)
        self.assertEqual(t, "Bitcoinin fiyatı saat on beş otuzda Ethereumun Fed'den önce")
        self.assertEqual(es, [(("Bitcoinin",), ("Bitcoin'in",)),
                              (("saat", "on", "beş", "otuzda"), ("15:30'da",)),
                              (("Ethereumun",), ("Ethereum'un",))])

    def test_sayilar_ve_yuzde(self):
        self.assertEqual(sk.telaffuz_duzelt("387,5 milyon dolarlık"), "387 milyon dolarlık")
        self.assertEqual(sk.telaffuz_duzelt("$387,5 milyon"), "387 milyon dolar")
        self.assertEqual(sk.telaffuz_duzelt("1,5 milyar"), "1,5 milyar")
        self.assertEqual(sk.telaffuz_duzelt("$83,600"), "83 bin 600 dolar")
        self.assertEqual(sk.telaffuz_duzelt("83.600 dolar"), "83 bin 600 dolar")
        self.assertEqual(sk.telaffuz_duzelt("%2,5 arttı"), "yüzde 2,5 arttı")
        self.assertEqual(sk.telaffuz_duzelt("2.5% arttı"), "yüzde 2,5 arttı")

    def test_saat_metin_icinde(self):
        self.assertEqual(sk.telaffuz_duzelt("TÜFE saat 15:30'da (TSİ)."), "TÜFE saat on beş otuzda.")
        self.assertEqual(sk.telaffuz_duzelt("11:00 açılış"), "saat on birde açılış")

    def test_btc_eth_acilir_html_emoji_temizlenir(self):
        self.assertEqual(sk.telaffuz_duzelt("<b>BTC</b> ⚡ ve ETH"), "Bitcoin ve Ethereum")


class TelaffuzSozlugu(unittest.TestCase):
    def d(self, metin):
        return sk.telaffuz_duzelt(metin)

    def test_harf_harf_kisaltmalar_ve_ek_uyumu(self):
        self.assertEqual(self.d("SEC'in kararı"), "Es-İ-Si'nin kararı")
        self.assertEqual(self.d("spot ETF'leri"), "spot İtief'leri")
        self.assertEqual(self.d("ETF'in akışı"), "İtief'in akışı")
        self.assertEqual(self.d("FOMC'nin toplantısı"), "Ef-O-Em-Si'nin toplantısı")
        self.assertEqual(self.d("ISM hizmet sektörü PMI"), "Ay-Es-Em hizmet sektörü Piemay")
        self.assertEqual(self.d("PMI'ı bekliyor"), "Piemay'ı bekliyor")
        self.assertEqual(self.d("CPI ve PCE verisi"), "Si-Pi-Ay ve Pi-Si-İ verisi")
        self.assertEqual(self.d("DCA yap, OTC'den al"), "Decea yap, Otisi'den al")
        self.assertEqual(self.d("NFT, TVL, ATH, KYC"), "Enefti, Ti-Vi-El, Atehaş, Key-Vay-Si")
        self.assertEqual(self.d("ATH'a yaklaştı"), "Atehaş'a yaklaştı")
        self.assertEqual(self.d("ABD'de"), "A-Be-De'de")
        self.assertEqual(self.d("AI'ın etkisi"), "yapay zekânın etkisi")

    def test_coin_sembolleri_ve_ek_uyumu(self):
        self.assertEqual(self.d("ENA'nın arzı"), "Ena'nın arzı")
        self.assertEqual(self.d("SOL'ü aldı"), "Solana'yı aldı")
        self.assertEqual(self.d("HYPE'lık"), "Hayp'lık")
        self.assertEqual(self.d("ETF'ten çıkış"), "İtief'ten çıkış")
        self.assertEqual(self.d("CFTC'nin raporu"), "Si-Ef-Ti-Si'nin raporu")
        self.assertEqual(self.d("XRP, ADA, AVAX, DOGE, BNB"),
                         "Ripıl, Kardano, Avaks, Doge, Bi-En-Bi")

    def test_cftc_ekli_ve_bagimsiz(self):
        self.assertEqual(telaffuz.donustur("CFTC'ye başvurdu"), "Si-Ef-Ti-Si'ye başvurdu")
        self.assertEqual(self.d("ABD CFTC kural teklifi"), "A-Be-De Si-Ef-Ti-Si kural teklifi")
        self.assertEqual(self.d("Komisyonu (CFTC), kural"), "Komisyonu (Si-Ef-Ti-Si), kural")
        self.assertNotIn("Si-Ef", self.d("cftc küçük harf"))

    def test_sayi_eslemeleri_altyazi_icin(self):
        es = []
        sonuc = sk.telaffuz_duzelt("Saat 15:30'da CPI %2,4 bekleniyor, BTC 83.600 dolar.", eslemeler=es)
        self.assertEqual(sonuc, "Saat saat on beş otuzda Si-Pi-Ay yüzde 2,4 bekleniyor, Bitcoin 83 bin 600 dolar.")
        self.assertEqual(es, [(("saat", "on", "beş", "otuzda"), ("15:30'da",)),
                              (("yüzde", "2,4"), ("%2,4",)),
                              (("83", "bin", "600"), ("83.600",))])
        es = []
        sk.telaffuz_duzelt("$387,5 milyon ve 2.5% ile 2025 yılı", eslemeler=es)
        self.assertEqual(es, [(("387", "milyon", "dolar"), ("$387,5", "milyon")),
                              (("yüzde", "2,5"), ("2.5%",))])

    def test_ingilizce_terimler_ekleriyle(self):
        self.assertEqual(self.d("Stakingde altcoinler"), "Steykingde altkoinler")
        self.assertEqual(self.d("airdrop ve stablecoin"), "erdrop ve steybılkoin")
        self.assertEqual(self.d("DeFi'de layer 2"), "difayde layer 2")
        self.assertEqual(self.d("Hyperliquid'in hacmi"), "Hayperlikuid ağının hacmi")
        self.assertEqual(self.d("BlackRock ve Binance"), "BlackRock ve Baynens")
        self.assertEqual(telaffuz.donustur("Binance'te Coinbase'e"), "Baynens'te Koinbeys'e")

    def test_yanlis_eslesme_yok(self):
        self.assertEqual(self.d("Bitcoin ve link"), "Bitcoin ve link")
        self.assertEqual(self.d("LINK yükseldi"), "Çeynlink yükseldi")
        self.assertEqual(self.d("defin ve sol kanat"), "defin ve sol kanat")
        self.assertEqual(self.d("Fed ve Nasdaq"), "Fed ve Nasdaq")
        self.assertEqual(self.d("OpenAI ve ETFS"), "OpenAI ve ETFS")

    def test_ek_uyumla(self):
        self.assertEqual(telaffuz.ek_uyumla("Es-İ-Si", "in"), "nin")
        self.assertEqual(telaffuz.ek_uyumla("Solana", "ü"), "yı")
        self.assertEqual(telaffuz.ek_uyumla("Hayp", "de"), "ta")
        self.assertEqual(telaffuz.ek_uyumla("İtief", "le"), "le")
        self.assertEqual(telaffuz.ek_uyumla("Ena", "nın"), "nın")
        self.assertEqual(telaffuz.ek_uyumla("Kardano", "dan"), "dan")


class KonusmaMetni(unittest.TestCase):
    def test_sablon_sirasi_ve_icerik(self):
        m = sk.konusma_metni(rapor())
        self.assertTrue(m.startswith("[cheerful] Günaydın, 29 Eylül Salı."))
        self.assertIn("[calm] Piyasanın havası bugün temkinli.", m)
        self.assertIn("Bitcoin 83 bin 600 dolar civarında, dar bir bantta yatay gidiyor.", m)
        self.assertIn("Ethereum yüzde bir artıyla 2 bin 680 dolarda.", m)
        self.assertIn("[curious] Neden bu sessizlik?", m)
        self.assertIn("Bitget borsasındaki 387 milyon dolarlık", m)
        self.assertIn("saat on birde", m)
        self.assertIn("[serious] Ana risk şu: [short pause]", m)
        self.assertIn("Korku ve açgözlülük endeksi 73, yani piyasa hâlâ açgözlü.", m)
        self.assertIn("Bilgilendirme amaçlıdır, yatırım tavsiyesi değildir.", m)
        sira = [m.index(x) for x in ("Günaydın", "havası", "Bitcoin 83", "Ethereum yüzde",
                                     "Neden", "takip edeceklerimiz", "Ana risk", "Korku", "Bilgilendirme")]
        self.assertEqual(sira, sorted(sira))

    def test_kapanis_bay_bay(self):
        self.assertTrue(sk.konusma_metni(rapor()).endswith("[warm] Bay bay."))

    def test_en_fazla_uc_takip(self):
        m = sk.konusma_metni(rapor(), maks=5000)
        self.assertNotIn("Dördüncü olay", m)
        self.assertIn("A-Be-De JOLTS verisi ve Hayp token kilidi açılışı.", m)

    def test_fiyat_tekrari_neden_kismindan_atilir(self):
        self.assertNotIn("Fiyatlar dar bir bantta", sk.konusma_metni(rapor()))

    def test_dusus_ve_yukselis_ifadesi(self):
        r = rapor()
        r["market"]["coins"]["BTC"]["change24h"] = -2.34
        m = sk.konusma_metni(r)
        self.assertIn("Bitcoin yüzde 2,3 düşüşle 83 bin 600 dolarda.", m)
        self.assertIn("Peki bu düşüş neden?", m)

    def test_uzunluk_siniri_kisaltir_kesmez(self):
        r = rapor()
        r["brief"]["why"] = " ".join(["Uzun bir gerekçe cümlesi burada yer alıyor ve devam ediyor."] * 12)
        r["brief"]["mainRisk"] = "Risk cümlesi çok uzun. " * 20
        r["brief"]["criticalEvents"] = [{"timeTr": "12:00", "title": "Çok uzun olay başlığı " * 8}] * 3
        m = sk.konusma_metni(r)
        self.assertLessEqual(len(m), sk.MAKS_KARAKTER)
        self.assertTrue(m.endswith("[warm] Bay bay."))
        self.assertIn("Bitcoin 83 bin 600", m)

    def test_bugunku_rapor_sinirda(self):
        self.assertLessEqual(len(sk.konusma_metni(rapor())), sk.MAKS_KARAKTER)

    def test_eksik_fiyat_ve_fng(self):
        r = rapor()
        r["market"]["coins"]["BTC"] = {"priceUsd": None, "change24h": None}
        r["market"]["fearGreed"] = None
        m = sk.konusma_metni(r)
        self.assertNotIn("Bitcoin 83", m)
        self.assertNotIn("Korku ve", m)
        self.assertTrue(m.endswith("[warm] Bay bay."))


class SahteYanit:
    def __init__(self, kod, icerik=b"", metin="", basliklar=None):
        self.status_code, self.content, self.text = kod, icerik, metin
        self.headers = basliklar or {}


class SahteHttp:
    def __init__(self, yanitlar):
        self.yanitlar, self.cagrilar = list(yanitlar), []

    def post(self, url, **kw):
        self.cagrilar.append((url, kw))
        y = self.yanitlar.pop(0)
        if isinstance(y, Exception):
            raise y
        return y


class ApiKatmani(unittest.TestCase):
    def test_istek_bicimi(self):
        http = SahteHttp([SahteYanit(200, b"MP3", basliklar={"character-cost": "812"})])
        ses, maliyet = sk.ElevenLabsIstemci("gizli-anahtar", http=http).seslendir("Merhaba dünya")
        self.assertEqual((ses, maliyet), (b"MP3", 812))
        url, kw = http.cagrilar[0]
        self.assertTrue(url.endswith("/v1/text-to-speech/l4Ygbni4CmTFHmTYdyhD"))
        self.assertEqual(kw["params"], {"output_format": "mp3_44100_128"})
        self.assertEqual(kw["json"], {"text": "Merhaba dünya", "model_id": "eleven_v4",
                                      "language_code": "tr"})
        self.assertEqual(kw["headers"]["xi-api-key"], "gizli-anahtar")

    def test_4xx_tekrar_denemez_anahtar_sizmaz(self):
        http = SahteHttp([SahteYanit(401, metin="quota_exceeded")])
        ist = sk.ElevenLabsIstemci("gizli-anahtar", http=http)
        with self.assertRaises(sk.SesHatasi) as h:
            ist.seslendir("x")
        self.assertEqual(len(http.cagrilar), 1)
        self.assertNotIn("gizli-anahtar", str(h.exception))
        self.assertNotIn("gizli-anahtar", repr(ist))

    def test_ag_hatasinda_tekrar_dener(self):
        http = SahteHttp([ConnectionError("x"), SahteYanit(200, b"OK")])
        ses, maliyet = sk.ElevenLabsIstemci("k", http=http).seslendir("abc")
        self.assertEqual((ses, maliyet), (b"OK", 3))

    def test_anahtar_yoksa_hata(self):
        with self.assertRaises(sk.SesHatasi):
            sk.ElevenLabsIstemci("")

    def test_anahtar_dosyadan(self):
        with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False) as f:
            f.write("# yorum\nexport ELEVENLABS_API_KEY=\"dosyadaki\"\n")
        try:
            self.assertEqual(sk.anahtar_al({}, f.name), "dosyadaki")
            self.assertEqual(sk.anahtar_al({"ELEVENLABS_API_KEY": "ortam"}, f.name), "ortam")
            self.assertEqual(sk.anahtar_al({}, "/yok/boyle/dosya"), "")
        finally:
            os.unlink(f.name)


class AkisDurmaz(unittest.TestCase):
    def test_bayrak_varsayilan_kapali(self):
        self.assertFalse(sk.aktif_mi({}))
        self.assertFalse(sk.aktif_mi({"SESLI_OZET_ELEVENLABS": "0"}))
        self.assertTrue(sk.aktif_mi({"SESLI_OZET_ELEVENLABS": "1"}))

    def test_api_hatasi_none_doner_ve_loglar(self):
        loglar = []
        http = SahteHttp([SahteYanit(429, metin="quota"), SahteYanit(500, metin="err")])
        ist = sk.ElevenLabsIstemci("gizli", http=http)
        self.assertIsNone(sk.ozet_ogg(rapor(), istemci=ist, log=loglar.append))
        self.assertIn("atlandı", loglar[0])
        self.assertNotIn("gizli", loglar[0])

    def test_donusum_hatasi_none(self):
        http = SahteHttp([SahteYanit(200, b"MP3")])

        def bozuk(_):
            raise OSError("ffmpeg yok")
        self.assertIsNone(sk.ozet_ogg(rapor(), istemci=sk.ElevenLabsIstemci("k", http=http),
                                      donustur=bozuk, log=lambda m: None))

    def test_basarili_akis(self):
        http = SahteHttp([SahteYanit(200, b"MP3")])
        ogg = sk.ozet_ogg(rapor(), istemci=sk.ElevenLabsIstemci("k", http=http),
                          donustur=lambda b: b"OGG:" + b, log=lambda m: None)
        self.assertEqual(ogg, b"OGG:MP3")
        self.assertTrue(http.cagrilar[0][1]["json"]["text"].endswith("[warm] Bay bay."))


class WebSes(unittest.TestCase):
    """reports/ses/ web MP3'ü: yazılır, eskisi silinir, hata akışı durdurmaz."""

    def setUp(self):
        self._d = tempfile.TemporaryDirectory()
        self.dizin = os.path.join(self._d.name, "ses")

    def tearDown(self):
        self._d.cleanup()

    def dosyalar(self):
        return sorted(os.listdir(self.dizin)) if os.path.isdir(self.dizin) else []

    def test_ozet_sesleri_ogg_ve_ham_mp3_doner(self):
        http = SahteHttp([SahteYanit(200, b"MP3")])
        ogg, mp3 = sk.ozet_sesleri(rapor(), istemci=sk.ElevenLabsIstemci("k", http=http),
                                   donustur=lambda b: b"OGG:" + b, log=lambda m: None)
        self.assertEqual((ogg, mp3), (b"OGG:MP3", b"MP3"))
        self.assertEqual(len(http.cagrilar), 1)          # tek API çağrısı

    def test_ozet_sesleri_hata_none_none(self):
        http = SahteHttp([SahteYanit(401, metin="x")])
        self.assertEqual(sk.ozet_sesleri(rapor(), istemci=sk.ElevenLabsIstemci("k", http=http),
                                         log=lambda m: None), (None, None))

    def test_yazar_latest_ve_14_gunden_eskiyi_siler(self):
        os.makedirs(self.dizin)
        for g in ("2026-09-16", "2026-09-17", "2026-09-29"):
            with open(os.path.join(self.dizin, f"{g}.mp3"), "wb") as f:
                f.write(b"eski")
        with open(os.path.join(self.dizin, "notlar.txt"), "w") as f:
            f.write("dokunma")
        yol = sk.web_ses_yaz("2026-09-30", b"HAM", dizin=self.dizin,
                             donustur=lambda b: b"WEB:" + b, log=lambda m: None)
        self.assertEqual(yol, os.path.join(self.dizin, "2026-09-30.mp3"))
        # 30 Eylül dahil son 14 gün: 17 Eylül kalır, 16 Eylül silinir.
        self.assertEqual(self.dosyalar(), ["2026-09-17.mp3", "2026-09-29.mp3",
                                           "2026-09-30.mp3", "latest.mp3", "notlar.txt"])
        for ad in ("2026-09-30.mp3", "latest.mp3"):
            with open(os.path.join(self.dizin, ad), "rb") as f:
                self.assertEqual(f.read(), b"WEB:HAM")

    def test_buyuk_dosya_yazilmaz(self):
        loglar = []
        yol = sk.web_ses_yaz("2026-09-30", b"HAM", dizin=self.dizin,
                             donustur=lambda b: b"x" * (sk.WEB_MAKS_BAYT + 1), log=loglar.append)
        self.assertIsNone(yol)
        self.assertEqual(self.dosyalar(), [])
        self.assertIn("yazılmadı", loglar[0])

    def test_donusum_hatasi_dosya_yazmaz_firlatmaz(self):
        def bozuk(_):
            raise OSError("ffmpeg yok")
        self.assertIsNone(sk.web_ses_yaz("2026-09-30", b"HAM", dizin=self.dizin,
                                         donustur=bozuk, log=lambda m: None))
        self.assertEqual(self.dosyalar(), [])

    def test_bos_ses_ya_da_bozuk_tarih(self):
        self.assertIsNone(sk.web_ses_yaz("2026-09-30", None, dizin=self.dizin, log=lambda m: None))
        self.assertIsNone(sk.web_ses_yaz("../x", b"HAM", dizin=self.dizin,
                                         donustur=lambda b: b, log=lambda m: None))
        self.assertEqual(self.dosyalar(), [])

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg yok")
    def test_gercek_donusum_mono_ve_kucuk(self):
        with tempfile.TemporaryDirectory() as d:
            kaynak = os.path.join(d, "k.mp3")
            subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=60",
                            "-ac", "2", "-b:a", "128k", kaynak], capture_output=True, check=True)
            with open(kaynak, "rb") as f:
                ham = f.read()
        web = sk.mp3_web(ham)
        self.assertLess(len(web), sk.WEB_MAKS_BAYT)
        self.assertLess(len(web), len(ham))
        bilgi = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=channels",
                                "-of", "csv=p=0", "-"], input=web, capture_output=True).stdout
        self.assertEqual(bilgi.strip(), b"1")


if __name__ == "__main__":
    unittest.main()
