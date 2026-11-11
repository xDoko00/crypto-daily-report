"""Kanal çıkış filtresi testleri (kuru çalışma; ağ/Telegram yok).

Sızıntı örnekleri kanaldaki gerçek gönderilerden: t.me/DogukanLive/1884,
/1941, /1948 (modelin iç notu raporun önüne yapışmış hâlde)."""

import json
import os
import tempfile
import unittest
from unittest import mock

import kanal_filtre
import render

GOVDE = (
    "📊 <b>GÜNAYDIN — {tarih}</b>\n"
    "\n"
    "⚡ <b>60 SANİYE</b>\n"
    "🌡️ Hava: Temkinli · F&amp;G 31 (dün 34)\n"
    "₿ BTC $63,462 (+0.63%) · Ξ ETH $1,901 (+1.09%)\n"
    "🔑 <b>Neden:</b> Hafta sonu altcoin türev piyasalarında yaşanan tasfiye dalgası ve "
    "BTC spot ETF'lerden süren net çıkışlar risk iştahını bastırıyor.\n"
    "⏰ <b>Kritik:</b> Wyoming Blockchain Symposium bugün başlıyor\n"
    "⚠️ <b>Risk:</b> $62.000 altına sarkma yeni bir tasfiye dalgasını tetikleyebilir."
)
NORMAL = GOVDE.format(tarih="17 Ağustos 2026, Pazartesi")

SIZINTI_1884 = "Confirmed Friday matches the template. Here's the report:\n\n" + GOVDE.format(
    tarih="24 Temmuz 2026, Cuma")
SIZINTI_1941 = "Rapor hazır. İşte 9 Ağustos 2026 için günlük kripto raporu:\n\n" + GOVDE.format(
    tarih="9 Ağustos 2026, Pazar")
SIZINTI_1948 = ("Karakter sayımı için bash izni alınamadı ama metin uzunluğu tahmini olarak "
                "aralık içinde (DETAY ~1900 karakter). Raporu doğrudan sunuyorum.\n\n"
                + GOVDE.format(tarih="17 Ağustos 2026, Pazartesi"))


def _govde_ile(neden):
    return NORMAL.replace(
        NORMAL.split("🔑 <b>Neden:</b> ")[1].split("\n")[0], neden)


class KanalFiltreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.log = os.path.join(self.tmp, "log.jsonl")

    def hazirla(self, metin):
        return kanal_filtre.hazirla(metin, log_yol=self.log)

    def test_normal_gecer_ve_em_tire_temizlenir(self):
        temiz, sebep = self.hazirla(NORMAL)
        assert temiz is not None, sebep
        self.assertNotIn("—", temiz)
        self.assertTrue(temiz.startswith("📊 <b>GÜNAYDIN · 17 Ağustos 2026"))
        self.assertFalse(os.path.exists(self.log))

    def test_gercek_sizintilar_engellenir(self):
        for ad, metin in (("1884", SIZINTI_1884), ("1941", SIZINTI_1941), ("1948", SIZINTI_1948)):
            with self.subTest(gonderi=ad):
                temiz, sebep = self.hazirla(metin)
                self.assertIsNone(temiz)
                self.assertIn("kalıp dışı", sebep)

    def test_bos_ve_silent(self):
        for metin in ("", "   ", None, "[SILENT]", "[SILENT] bugün gönderi yok"):
            with self.subTest(metin=metin):
                self.assertIsNone(self.hazirla(metin)[0])

    def test_govde_icindeki_ic_isaretler(self):
        ornekler = {
            "hata": "Veri kaynağında hata oluştu, rapor eksik.",
            "hatası": "CoinGecko hatası yüzünden fiyatlar eski.",
            "error": "Request error nedeniyle haber çekilemedi.",
            "Traceback": "Traceback (most recent call last) piyasa.",
            "cron": "Sabah cron gecikti, rapor geç hazırlandı.",
            "ajan": "Ajan notu: kaynaklar kontrol edildi.",
            "Alpha": "Alpha'ya iletilecek not: piyasa sakin.",
            "Beta": "Beta telefonu meşgul, piyasa sakin.",
            "Omega": "Omega ekibi raporu onayladı.",
            "brif": "Brif gereği kısa tutuldu.",
            "kart": "Kart üretilemedi, piyasa sakin.",
            "pano": "Pano güncellendi, piyasa sakin.",
            "yol": "Detay /Users/dogukandogan/notlar.md dosyasında.",
            "hermes": "Ayrıntı ~/.hermes/profiles altında.",
            "skill": "Skill yüklenemedi, piyasa sakin.",
            "job": "Job tamamlandı, piyasa sakin.",
            "bash": "Bash izni yoktu, piyasa sakin.",
        }
        for ad, neden in ornekler.items():
            with self.subTest(isaret=ad):
                temiz, sebep = self.hazirla(_govde_ile(neden))
                self.assertIsNone(temiz, f"{ad} geçmemeliydi")

    def test_kar_vaadi_sinyal(self):
        for neden in ("BTC için güçlü al sinyali oluştu.", "Bu hafta kesin kazanç fırsatı var.",
                      "Analistlerin fiyat hedefi 90 bin dolar."):
            with self.subTest(neden=neden):
                self.assertIsNone(self.hazirla(_govde_ile(neden))[0])

    def test_haber_dili_yanlis_alarm_vermez(self):
        for neden in ("Anadolu Ajansı'nın aktardığına göre Hatay'da yeni düzenleme konuşuluyor.",
                      "Fed'in şahin sinyali ve token kilit açılımları satış baskısı yarattı.",
                      "Piyasalar ABD istihdam verisine odaklandı; kartel soruşturması da gündemde."):
            with self.subTest(neden=neden):
                temiz, sebep = self.hazirla(_govde_ile(neden))
                self.assertIsNotNone(temiz, sebep)

    def test_log_metni_yazmaz_sebebi_yazar(self):
        self.hazirla(SIZINTI_1948)
        with open(self.log, encoding="utf-8") as f:
            satir = json.loads(f.read().strip())
        self.assertEqual(satir["karar"], "ENGELLENDI")
        self.assertIn("kalıp dışı", satir["sebep"])
        self.assertNotIn("bash", json.dumps(satir, ensure_ascii=False))
        self.assertEqual(len(satir["ozet"]), 12)

    def test_render_brief_kalibina_uyar(self):
        """Gerçek renderer çıktısı (son kanonik rapor) filtreden geçmeli."""
        yol = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports", "latest.json")
        if not os.path.exists(yol):
            self.skipTest("reports/latest.json yok")
        with open(yol, encoding="utf-8") as f:
            rapor = json.load(f)
        temiz, sebep = self.hazirla(render.brief_html(rapor))
        self.assertIsNotNone(temiz, sebep)


class KanalTekGonderiTest(unittest.TestCase):
    def test_tek_gonderi_varsayilan_acik(self):
        import report
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("KANAL_TEK_GONDERI", None)
            self.assertTrue(report.kanal_tek_gonderi_mi())
        with mock.patch.dict(os.environ, {"KANAL_TEK_GONDERI": "0"}):
            self.assertFalse(report.kanal_tek_gonderi_mi())

    def test_kanala_gonder_tek_cagri(self):
        import report
        with mock.patch.object(report, "foto_gonder") as foto, \
             mock.patch.object(report, "telegram_gonder") as metin, \
             mock.patch.object(report, "ses_gonder") as ses:
            report.kanala_gonder("t", "-100", b"png", NORMAL)
            self.assertEqual(foto.call_count, 1)
            self.assertEqual(metin.call_count + ses.call_count, 0)
            report.kanala_gonder("t", "-100", None, NORMAL)
            self.assertEqual(metin.call_count, 1)
            self.assertEqual(ses.call_count, 0)


LINK = ("📊 Detaylı haberler ve günlük grafik analizi burada 👉 "
        "https://dogukanlive.com/gunluk-raporlar/2026-08-17/")
VIDEO = "🎬 Haftanın videosu: Bu Kadın Gerçek Değil https://youtu.be/iIaKZM0HyP0"


class RaporLinkiTest(unittest.TestCase):
    """Kanal mesajının en altındaki site rapor linki (Doğukan, 11 Kas 2026)."""

    def setUp(self):
        import report
        self.report = report
        self.tmp = tempfile.mkdtemp()
        self.log_yama = mock.patch.object(kanal_filtre, "LOG_YOL",
                                          os.path.join(self.tmp, "l.jsonl"))
        self.log_yama.start()
        self.addCleanup(self.log_yama.stop)

    def test_satir_tarihli_ve_utm_yok(self):
        os.environ.pop("KANAL_RAPOR_LINKI", None)
        s = self.report.rapor_linki_satiri("2026-08-17")
        self.assertEqual(s, LINK)
        self.assertNotIn("utm", s)
        self.assertNotIn("?", s)
        self.assertEqual(self.report.rapor_linki_satiri("bozuk"), "")
        with mock.patch.dict(os.environ, {"KANAL_RAPOR_LINKI": "0"}):
            self.assertEqual(self.report.rapor_linki_satiri("2026-08-17"), "")

    def test_filtre_link_satirini_gecirir(self):
        ok, sebep = kanal_filtre.kontrol(kanal_filtre.em_tire_temizle(NORMAL) + "\n\n" + LINK)
        self.assertTrue(ok, sebep)
        bugun = LINK.replace("gunluk-raporlar/2026-08-17/", "bugun/")
        ok, sebep = kanal_filtre.kontrol(kanal_filtre.em_tire_temizle(NORMAL) + "\n\n" + bugun)
        self.assertTrue(ok, sebep)

    def test_filtre_yabanci_link_ve_utm_engeller(self):
        temel = kanal_filtre.em_tire_temizle(NORMAL) + "\n\n"
        for kotu in (LINK.replace("dogukanlive.com", "evil.com"),
                     LINK + "?utm_source=telegram",
                     LINK.replace("2026-08-17/", "2026-08-17/../x"),
                     "📊 Detaylı haberler ve günlük grafik analizi burada 👉 http://dogukanlive.com/bugun/"):
            with self.subTest(kotu=kotu):
                ok, _ = kanal_filtre.kontrol(temel + kotu)
                self.assertFalse(ok)

    def test_link_en_altta_video_ustunde(self):
        metin, sebep = self.report.kanal_brief_hazirla(NORMAL, VIDEO, LINK)
        self.assertEqual(sebep, "")
        satirlar = [x for x in metin.splitlines() if x.strip()]
        self.assertEqual(satirlar[-1], LINK)
        self.assertEqual(satirlar[-2], VIDEO)
        self.assertEqual(len(satirlar), 9)

    def test_caption_siniri_link_her_zaman_kalir(self):
        uzun = _govde_ile("Piyasada temkinli bekleyiş sürüyor ve " * 25)
        self.assertGreater(len(uzun), 1024)
        metin, sebep = self.report.kanal_brief_hazirla(uzun, VIDEO, LINK)
        self.assertIsNotNone(metin, sebep)
        self.assertLessEqual(len(metin), 1024)
        self.assertTrue(metin.endswith(LINK))
        self.assertNotIn("Haftanın videosu", metin)
        self.assertIn("🔑 <b>Neden:</b> Piyasada", metin)
        self.assertIn("...", metin)

    def test_video_sigmazsa_duser_link_kalir(self):
        orta = _govde_ile("Piyasada temkinli bekleyiş sürüyor ve " * 15)
        self.assertLess(len(orta) + len(LINK) + 2, 1024)
        self.assertGreater(len(orta) + len(LINK) + len(VIDEO) + 4, 1024)
        metin, _ = self.report.kanal_brief_hazirla(orta, VIDEO, LINK)
        self.assertTrue(metin.endswith(LINK))
        self.assertNotIn("Haftanın videosu", metin)
        self.assertNotIn("...", metin)

    def test_sizinti_link_varken_de_engellenir(self):
        metin, sebep = self.report.kanal_brief_hazirla(SIZINTI_1948, "", LINK)
        self.assertIsNone(metin)

    def test_gercek_rapor_link_ile_1024_altinda(self):
        yol = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports", "latest.json")
        if not os.path.exists(yol):
            self.skipTest("reports/latest.json yok")
        with open(yol, encoding="utf-8") as f:
            rapor = json.load(f)
        os.environ.pop("KANAL_RAPOR_LINKI", None)
        metin, sebep = self.report.kanal_brief_hazirla(
            render.brief_html(rapor), VIDEO, self.report.rapor_linki_satiri(rapor["id"]))
        self.assertIsNotNone(metin, sebep)
        self.assertLessEqual(len(metin), 1024)
        self.assertTrue(metin.endswith(f"/gunluk-raporlar/{rapor['id']}/"))


class KartTest(unittest.TestCase):
    """Kart üretimi: her tasarım 1080x1350 PNG, eksik/uç veride çökmez."""

    VERI = {"btc": {"fiyat": 73711, "degisim": -1.18}, "eth": {"fiyat": 2066.31, "degisim": 2.4},
            "sol": {"fiyat": 83.0, "degisim": -3.2}, "bnb": {"fiyat": 681.18, "degisim": 0.0},
            "xrp": {"fiyat": 1.055, "degisim": -3.3}, "btc_dom": 59.7, "eth_dom": 10.2,
            "hacim": 8.1e10, "fng_deger": 29, "fng_etiket": "Korku", "fng_dun": 32}

    def _boyut(self, png):
        from PIL import Image
        import io
        im = Image.open(io.BytesIO(png))
        return im.format, im.size

    def test_tum_tasarimlar(self):
        import kart
        for ad in kart.TASARIMLAR:
            with self.subTest(tasarim=ad):
                png = kart.kart_olustur(self.VERI, "Temkinli", "Fed kararı oynaklık getirebilir.",
                                        "11 Kasım 2026, Çarşamba", tasarim=ad)
                self.assertEqual(self._boyut(png), ("PNG", (1080, 1350)))

    def test_varsayilan_ve_ortam_secimi(self):
        import kart
        os.environ.pop("KART_TASARIM", None)
        self.assertEqual(kart.tasarim_sec(), kart.VARSAYILAN_TASARIM)
        with mock.patch.dict(os.environ, {"KART_TASARIM": "klasik"}):
            self.assertEqual(kart.tasarim_sec(), "klasik")
        with mock.patch.dict(os.environ, {"KART_TASARIM": "yok-boyle"}):
            self.assertEqual(kart.tasarim_sec(), kart.VARSAYILAN_TASARIM)

    def test_eksik_ve_uc_veri(self):
        import kart
        uc = [{}, {"btc": {"fiyat": None, "degisim": None}, "fng_deger": None},
              dict(self.VERI, btc={"fiyat": 123456.0, "degisim": 12.5}, fng_deger=100),
              dict(self.VERI, fng_deger=0, xrp={"fiyat": 0.0042, "degisim": -0.01})]
        for ad in kart.TASARIMLAR:
            for i, veri in enumerate(uc):
                with self.subTest(tasarim=ad, ornek=i):
                    png = kart.kart_olustur(veri, "", "", "", tasarim=ad)
                    self.assertEqual(self._boyut(png)[1], (1080, 1350))

    def test_font_repoda_ve_turkce_karakter_var(self):
        import kart
        self.assertTrue(os.path.exists(kart.FONT_VF))
        fnt = kart._f(800, 40)
        for harf in "ĞÜŞİÖÇğüşıöç":
            self.assertGreater(fnt.getmask(harf).size[0], 0, harf)

    def test_tr_buyuk_harf(self):
        import kart
        self.assertEqual(kart._tr_buyuk("Temkinli"), "TEMKİNLİ")
        self.assertEqual(kart._tr_buyuk("Aşırı Korku"), "AŞIRI KORKU")


if __name__ == "__main__":
    unittest.main(verbosity=2)
