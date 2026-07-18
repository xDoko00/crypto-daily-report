# -*- coding: utf-8 -*-
"""report.py için basit birim testleri (ağ veya secret GEREKTİRMEZ)."""
import unittest

import report

NL = chr(10)


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


if __name__ == "__main__":
    unittest.main()
