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


if __name__ == "__main__":
    unittest.main(verbosity=2)
