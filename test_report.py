# -*- coding: utf-8 -*-
"""report/sema/render için birim testleri (ağ veya secret GEREKTİRMEZ)."""
import copy
import json
import unittest

import eposta
import render
import report
import sema

NL = chr(10)


# --------------------------------------------------------------------------- #
# Test verisi — gerçek bir günün küçültülmüş hali
# --------------------------------------------------------------------------- #

MARKET = {
    "asOf": "2026-08-19T07:52:00+03:00",
    "coins": {
        "BTC": {"priceUsd": 64335.0, "change24h": -0.8},
        "ETH": {"priceUsd": 1921.0, "change24h": 1.2},
        "SOL": {"priceUsd": 88.4, "change24h": -2.15},
        "BNB": {"priceUsd": 512.0, "change24h": 0.4},
        "XRP": {"priceUsd": 0.5123, "change24h": -1.1},
    },
    "btcDominance": 58.2,
    "ethDominance": 11.4,
    "totalMarketCapUsd": 2.3e12,
    "volume24hUsd": 9.2e10,
    "fearGreed": {"value": 46, "label": "Nötr", "previousValue": 43, "weekAgoValue": 51},
}

LLM_CIKTISI = {
    "brief": {
        "mood": "Temkinli",
        "why": "Fed tutanakları şahin algılandı, risk iştahı gün boyu baskı altında kaldı.",
        "criticalEvents": [
            {"timeTr": "15:30", "title": "ABD TÜFE verisi"},
            {"timeTr": None, "title": "Beyaz Saray kripto zirvesi"},
        ],
        "mainRisk": "TÜFE beklenti üstü gelirse sert satış görülebilir.",
    },
    "sections": {
        "yesterday": [
            {"item": "BTC 64.000 desteğini korudu mu",
             "outcome": "Korudu; gün içi dip 63.800 seviyesinde kaldı."},
        ],
        "agenda": [
            {"importance": "kritik", "title": "SEC kripto ETF kararını erteledi",
             "summary": "Kurul kararı 30 gün öteledi. Onay beklentisi fiyatlanmıştı.",
             "source": {"url": "https://www.sec.gov/news/press-release/2026-118?utm_source=x",
                        "title": "SEC press release", "publisher": "SEC"}},
            {"importance": "onemli", "title": "Ethereum ağ ücretleri geriledi",
             "summary": "Ortalama işlem ücreti son üç ayın en düşüğüne indi.",
             "source": {"url": "https://www.reuters.com/technology/eth-fees",
                        "title": "ETH fees drop", "publisher": "Reuters"}},
        ],
        "today": [{"timeTr": "14:00", "title": "Almanya ZEW endeksi"}],
        "turkey": {"hasNews": False, "items": []},
        "risks": ["TÜFE sürprizi risk iştahını bozabilir."],
    },
    "followUps": ["ABD TÜFE verisi beklentiyi aştı mı", "SEC yeni tarih açıkladı mı"],
}


def ornek_rapor():
    return sema.rapor_kur(
        market=copy.deepcopy(MARKET),
        llm_ciktisi=copy.deepcopy(LLM_CIKTISI),
        tarih_id="2026-08-19",
        baslik="19 Ağustos 2026, Çarşamba",
        simdi_iso="2026-08-19T08:00:00+03:00",
    )


# --------------------------------------------------------------------------- #
# Mevcut davranış — bozulmadığını doğrula
# --------------------------------------------------------------------------- #

class MesajBolme(unittest.TestCase):
    def test_kisa_metin_tek_parca(self):
        self.assertEqual(report.mesaji_bol("kısa mesaj"), ["kısa mesaj"])

    def test_uzun_metin_limiti_asmaz(self):
        bloklar = [f"<b>Bölüm {i}</b>" + NL + ("satır " * 60) for i in range(40)]
        metin = (NL * 2).join(bloklar)
        parcalar = report.mesaji_bol(metin)
        self.assertGreater(len(parcalar), 1)
        for p in parcalar:
            self.assertLessEqual(len(p), report.SAFE_LIMIT)


class HtmlTemizle(unittest.TestCase):
    def test_etiketleri_kaldirir(self):
        self.assertEqual(
            report._html_temizle('<b>Merhaba</b> <a href="x">link</a>'),
            "Merhaba link")

    def test_entityleri_cevirir(self):
        self.assertEqual(report._html_temizle("5 &lt; 10 &amp; 3"), "5 < 10 & 3")


class HedefZaman(unittest.TestCase):
    def test_saat_ve_dakika(self):
        dt = report._hedef_zaman_ist("08:00")
        self.assertEqual((dt.hour, dt.minute), (8, 0))


# --------------------------------------------------------------------------- #
# Şema
# --------------------------------------------------------------------------- #

class SemaDogrulama(unittest.TestCase):
    def test_ornek_rapor_gecerli(self):
        self.assertTrue(sema.dogrula(ornek_rapor()))

    def test_llm_ciktisi_gecerli(self):
        self.assertTrue(sema.dogrula_llm_ciktisi(copy.deepcopy(LLM_CIKTISI)))

    def test_kaynaksiz_gundem_maddesi_reddedilir(self):
        bozuk = copy.deepcopy(LLM_CIKTISI)
        del bozuk["sections"]["agenda"][0]["source"]
        with self.assertRaises(sema.RaporSemaHatasi):
            sema.dogrula_llm_ciktisi(bozuk)

    def test_http_kaynak_reddedilir(self):
        """https dışı kaynak yayına girmemeli."""
        bozuk = copy.deepcopy(LLM_CIKTISI)
        bozuk["sections"]["agenda"][0]["source"]["url"] = "http://ornek.com/haber"
        with self.assertRaises(sema.RaporSemaHatasi):
            sema.dogrula_llm_ciktisi(bozuk)

    def test_uzun_kritik_olay_basligi_reddedilir(self):
        """Brief satırı okunabilir kalsın diye kritik olay başlığı kısa olmalı."""
        bozuk = copy.deepcopy(LLM_CIKTISI)
        bozuk["brief"]["criticalEvents"][0]["title"] = "A" * 61
        with self.assertRaises(sema.RaporSemaHatasi):
            sema.dogrula_llm_ciktisi(bozuk)

    def test_gecersiz_mood_reddedilir(self):
        bozuk = copy.deepcopy(LLM_CIKTISI)
        bozuk["brief"]["mood"] = "Coşkulu"
        with self.assertRaises(sema.RaporSemaHatasi):
            sema.dogrula_llm_ciktisi(bozuk)

    def test_llm_piyasa_sayisi_ekleyemez(self):
        """Model şemada olmayan bir alan uydurursa çıktı reddedilmeli."""
        bozuk = copy.deepcopy(LLM_CIKTISI)
        bozuk["market"] = {"btc": 999999}
        with self.assertRaises(sema.RaporSemaHatasi):
            sema.dogrula_llm_ciktisi(bozuk)

    def test_kaynak_listesi_eksikse_reddedilir(self):
        rapor = ornek_rapor()
        rapor["sources"] = []
        with self.assertRaises(sema.RaporSemaHatasi):
            sema.dogrula(rapor)

    def test_tarih_tutarsizligi_reddedilir(self):
        rapor = ornek_rapor()
        rapor["publishedAt"] = "2026-08-18T08:00:00+03:00"
        with self.assertRaises(sema.RaporSemaHatasi):
            sema.dogrula(rapor)

    def test_turkiye_celiskisi_reddedilir(self):
        rapor = ornek_rapor()
        rapor["sections"]["turkey"]["hasNews"] = True
        with self.assertRaises(sema.RaporSemaHatasi):
            sema.dogrula(rapor)


class KaynakVeUrl(unittest.TestCase):
    def test_utm_temizlenir(self):
        self.assertEqual(
            sema.url_temizle("https://a.com/x?utm_source=x&id=5&fbclid=9"),
            "https://a.com/x?id=5")

    def test_fragment_atilir(self):
        self.assertEqual(sema.url_temizle("https://a.com/x#bolum"), "https://a.com/x")

    def test_kaynaklar_toplanir_ve_temizlenir(self):
        rapor = ornek_rapor()
        urller = [k["url"] for k in rapor["sources"]]
        self.assertEqual(len(urller), 2)
        self.assertIn("https://www.sec.gov/news/press-release/2026-118", urller)

    def test_ayni_kaynak_iki_kez_listelenmez(self):
        llm = copy.deepcopy(LLM_CIKTISI)
        llm["sections"]["agenda"][1]["source"] = copy.deepcopy(
            llm["sections"]["agenda"][0]["source"])
        rapor = sema.rapor_kur(market=copy.deepcopy(MARKET), llm_ciktisi=llm,
                               tarih_id="2026-08-19", baslik="test",
                               simdi_iso="2026-08-19T08:00:00+03:00")
        self.assertEqual(len(rapor["sources"]), 1)


class Idempotency(unittest.TestCase):
    def test_ayni_gun_ikinci_uretim_publishedat_korur(self):
        ilk = ornek_rapor()
        ikinci = sema.rapor_kur(
            market=copy.deepcopy(MARKET), llm_ciktisi=copy.deepcopy(LLM_CIKTISI),
            tarih_id="2026-08-19", baslik="19 Ağustos 2026, Çarşamba",
            simdi_iso="2026-08-19T11:30:00+03:00", onceki_rapor=ilk)
        self.assertEqual(ikinci["id"], ilk["id"])
        self.assertEqual(ikinci["publishedAt"], ilk["publishedAt"])
        self.assertNotEqual(ikinci["updatedAt"], ilk["updatedAt"])


# --------------------------------------------------------------------------- #
# Render
# --------------------------------------------------------------------------- #

class TelegramRender(unittest.TestCase):
    def setUp(self):
        self.rapor = ornek_rapor()

    def test_brief_iskeleti(self):
        b = render.brief_html(self.rapor)
        self.assertTrue(b.startswith("📊 <b>GÜNAYDIN — 19 Ağustos 2026, Çarşamba</b>"))
        for parca in ("⚡ <b>60 SANİYE</b>", "🌡️ Hava: Temkinli",
                      "🔑 <b>Neden:</b>", "⏰ <b>Kritik:</b>", "⚠️ <b>Risk:</b>"):
            self.assertIn(parca, b)

    def test_brief_fiyatlari_market_verisinden_alir(self):
        b = render.brief_html(self.rapor)
        self.assertIn("BTC $64,335 (-0.80%)", b)
        self.assertIn("ETH $1,921 (+1.20%)", b)
        self.assertIn("F&amp;G 46 (dün 43)", b)

    def test_brief_kart_altyazisina_sigar(self):
        """Kart + brief tek mesajda gitsin diye 1024 karakteri aşmamalı."""
        self.assertLessEqual(len(render.brief_html(self.rapor)), 1024)

    def test_detay_bolumleri(self):
        d = render.detay_html(self.rapor)
        for baslik in ("📈 <b>PİYASA</b>", "⏮️ <b>DÜNDEN</b>", "📰 <b>GÜNDEM</b>",
                       "⏰ <b>BUGÜN TAKİPTE</b>", "🇹🇷 <b>TÜRKİYE</b>",
                       "⚠️ <b>RİSKLER</b>"):
            self.assertIn(baslik, d)
        self.assertIn("Dominans: BTC %58.2 · ETH %11.4 — Hacim: $92.00B", d)
        self.assertIn("<i>Bilgilendirme amaçlıdır, yatırım tavsiyesi değildir.</i>", d)

    def test_gundem_maddesi_kaynak_linkli(self):
        d = render.detay_html(self.rapor)
        self.assertIn('<a href="https://www.sec.gov/news/press-release/2026-118">SEC</a>', d)
        self.assertIn("🔴 <b>SEC kripto ETF kararını erteledi</b>", d)

    def test_turkiye_haberi_yoksa_sabit_satir(self):
        self.assertIn("🇹🇷 <b>TÜRKİYE</b> — Yeni gelişme yok.",
                      render.detay_html(self.rapor))

    def test_html_kacisi_yapilir(self):
        """Model metnindeki & < > Telegram mesajını düşürmemeli."""
        rapor = ornek_rapor()
        rapor["brief"]["mainRisk"] = "Risk & <belirsizlik> arttı"
        b = render.brief_html(rapor)
        self.assertIn("Risk &amp; &lt;belirsizlik&gt; arttı", b)

    def test_dunden_bolumu_bos_ise_atlanir(self):
        rapor = ornek_rapor()
        rapor["sections"]["yesterday"] = []
        self.assertNotIn("⏮️ <b>DÜNDEN</b>", render.detay_html(rapor))

    def test_telegram_html_ayracla_bolunur(self):
        tam = render.telegram_html(self.rapor)
        parcalar = [p.strip() for p in tam.split(render.DETAY_AYRACI) if p.strip()]
        self.assertEqual(len(parcalar), 2)

    def test_saatsiz_kritik_olay_saat_yazmaz(self):
        b = render.brief_html(self.rapor)
        self.assertIn("⏰ <b>Kritik:</b> 15:30 ABD TÜFE verisi · Beyaz Saray kripto zirvesi", b)
        self.assertNotIn("None", b)

    def test_takvimde_saat_tireli_yazilir(self):
        self.assertIn("14:00 — Almanya ZEW endeksi", render.detay_html(self.rapor))

    def test_eksik_fiyat_dogrulanamadi_der(self):
        rapor = ornek_rapor()
        rapor["market"]["coins"]["BTC"] = {"priceUsd": None, "change24h": None}
        b = render.brief_html(rapor)
        self.assertIn("BTC doğrulanamadı (n/a)", b)


class SesVeKart(unittest.TestCase):
    def setUp(self):
        self.rapor = ornek_rapor()

    def test_seslendirme_metni_fiyat_icermez(self):
        m = render.seslendirme_metni(self.rapor)
        self.assertIn("Piyasa havası Temkinli.", m)
        self.assertIn("Günün ana riski:", m)
        self.assertNotIn("64,335", m)
        self.assertNotIn("<", m)

    def test_kart_verisi_alanlari(self):
        k = render.kart_verisi(self.rapor)
        self.assertEqual(k["btc"], {"fiyat": 64335.0, "degisim": -0.8})
        self.assertEqual(k["fng_deger"], 46)
        self.assertEqual(k["fng_etiket"], "Nötr")
        self.assertEqual(k["btc_dom"], 58.2)


# --------------------------------------------------------------------------- #
# LLM çıktısını ayıklama
# --------------------------------------------------------------------------- #

class EpostaRender(unittest.TestCase):
    def setUp(self):
        self.rapor = ornek_rapor()

    def test_konu_hava_ve_btc_icerir(self):
        k = eposta.konu(self.rapor)
        self.assertIn("19 Ağustos 2026", k)
        self.assertIn("Temkinli", k)
        self.assertIn("$64,335", k)

    def test_govde_bolumleri(self):
        g = eposta.govde(self.rapor)
        for b in ("## 60 saniye", "## Piyasa", "## Dünden hesap",
                  "## Günün öne çıkan gelişmeleri", "## Bugün takipte",
                  "## Türkiye", "## Riskler", "## Yarın bunlara bakacağız"):
            self.assertIn(b, g)

    def test_govde_kaynak_baglantisi_verir(self):
        g = eposta.govde(self.rapor)
        self.assertIn("(https://www.sec.gov/news/press-release/2026-118)", g)

    def test_govde_fiyatlari_market_verisinden_alir(self):
        g = eposta.govde(self.rapor)
        self.assertIn("| BTC | $64,335 | +0.80% |".replace("+0.80", "-0.80"), g)

    def test_govde_rapor_sayfasina_baglar(self):
        self.assertIn("/gunluk-raporlar/2026-08-19/", eposta.govde(self.rapor))

    def test_govde_uyari_icerir(self):
        self.assertIn("yatırım tavsiyesi değildir",
                      eposta.govde(self.rapor).lower())

    def test_turkiye_haberi_yoksa_sabit_metin(self):
        self.assertIn("yeni bir gelişme yok", eposta.govde(self.rapor))

    def test_anahtar_yoksa_sessizce_atlar(self):
        """E-posta gönderilemezse rapor akışı durmamalı."""
        ok, mesaj = eposta.gonder(self.rapor, anahtar="")
        self.assertFalse(ok)
        self.assertIn("BUTTONDOWN_API_KEY", mesaj)


class JsonAyikla(unittest.TestCase):
    def test_duz_json(self):
        self.assertEqual(report.json_ayikla('{"a": 1}'), {"a": 1})

    def test_kod_citi_icinden(self):
        self.assertEqual(
            report.json_ayikla('```json\n{"a": 1}\n```'), {"a": 1})

    def test_on_metinli_cikti(self):
        """claude -p bazen JSON'un önüne cümle ekliyor; yine de ayıklanmalı."""
        self.assertEqual(
            report.json_ayikla('İşte rapor:\n{"a": 1}\nUmarım yardımcı olur.'),
            {"a": 1})

    def test_json_yoksa_hata(self):
        with self.assertRaises(ValueError):
            report.json_ayikla("hiç JSON yok")


# --------------------------------------------------------------------------- #
# Disk düzeni
# --------------------------------------------------------------------------- #

class RaporYollari(unittest.TestCase):
    def test_arsiv_yolu_yil_ay_kirilimli(self):
        arsiv, latest = sema.rapor_yollari("2026-08-19")
        self.assertTrue(arsiv.endswith("reports/2026/08/2026-08-19.json"))
        self.assertTrue(latest.endswith("reports/latest.json"))

    def test_sema_json_serilestirilebilir(self):
        json.dumps(sema.RAPOR_SEMASI)


if __name__ == "__main__":
    unittest.main()
