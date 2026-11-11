"""Kanal mesajı site tarihli sayfası hazır olunca gider (Doğukan, 11 Kas 2026).

Bekleme mantığı (200 hemen, 404 sonra 200, tavan dolması) ve çift gönderi
koruması. Ağ, Telegram, git ve disk yazımı sahte; gerçek gönderi YOK."""
import copy
import os
import sys
import unittest
from unittest import mock

import report
import sema
import test_report as tr


class _Yanit:
    def __init__(self, kod, metin=""):
        self.status_code = kod
        self.text = metin


GUN = "2026-11-12"
SAYFA_TAM = (f'<link rel="canonical" href="https://dogukanlive.com/gunluk-raporlar/{GUN}/">'
             f'<audio src="/ses/{GUN}.mp3"></audio>')
SAYFA_SESSIZ = f'<link rel="canonical" href="https://dogukanlive.com/gunluk-raporlar/{GUN}/">'


class SaatSahte:
    """time.monotonic + time.sleep yerine: uyudukça saat ilerler."""
    def __init__(self):
        self.t = 1000.0
        self.uykular = []

    def saat(self):
        return self.t

    def uyu(self, sn):
        self.uykular.append(sn)
        self.t += sn


class SayfaKontrol(unittest.TestCase):
    def test_200_tarih_ve_ses_var(self):
        get = mock.Mock(return_value=_Yanit(200, SAYFA_TAM))
        self.assertEqual(report.site_sayfasi_hazir_mi(GUN, True, get=get), (True, "hazir"))
        self.assertEqual(get.call_args[0][0], f"https://dogukanlive.com/gunluk-raporlar/{GUN}/")

    def test_404_hazir_degil(self):
        get = mock.Mock(return_value=_Yanit(404, "Sayfa yok"))
        self.assertEqual(report.site_sayfasi_hazir_mi(GUN, False, get=get), (False, "http 404"))

    def test_200_ama_baska_gun(self):
        get = mock.Mock(return_value=_Yanit(200, SAYFA_TAM.replace(GUN, "2026-11-11")))
        ok, durum = report.site_sayfasi_hazir_mi(GUN, False, get=get)
        self.assertFalse(ok)
        self.assertEqual(durum, "http 200, tarih yok")

    def test_ses_bekleniyorsa_ses_referansi_sart(self):
        get = mock.Mock(return_value=_Yanit(200, SAYFA_SESSIZ))
        self.assertEqual(report.site_sayfasi_hazir_mi(GUN, True, get=get)[0], False)
        self.assertEqual(report.site_sayfasi_hazir_mi(GUN, False, get=get)[0], True)

    def test_ag_hatasi_firlatmaz(self):
        get = mock.Mock(side_effect=OSError("baglanti"))
        ok, durum = report.site_sayfasi_hazir_mi(GUN, False, get=get)
        self.assertFalse(ok)
        self.assertIn("ag hatasi", durum)


class BeklemeDongusu(unittest.TestCase):
    def _bekle(self, sonuclar, tavan_dk=45):
        s = SaatSahte()
        sira = list(sonuclar)
        kontrol = mock.Mock(side_effect=lambda *a: sira.pop(0) if len(sira) > 1 else sira[0])
        with mock.patch.object(report, "_actions_uyari") as uyari:
            sonuc = report.site_hazir_bekle(GUN, True, tavan_dk=tavan_dk, kontrol=kontrol,
                                            uyu=s.uyu, saat=s.saat)
        return sonuc, kontrol, s, uyari

    def test_200_hemen_gonderir(self):
        sonuc, kontrol, s, uyari = self._bekle([(True, "hazir")])
        self.assertTrue(sonuc)
        self.assertEqual(kontrol.call_count, 1)
        self.assertEqual(s.uykular, [])
        uyari.assert_not_called()

    def test_404_sonra_200(self):
        sonuc, kontrol, s, uyari = self._bekle([(False, "http 404"), (False, "http 404"),
                                                (True, "hazir")])
        self.assertTrue(sonuc)
        self.assertEqual(kontrol.call_count, 3)
        self.assertEqual(s.uykular, [60, 60])
        uyari.assert_not_called()

    def test_tavan_dolar_false_doner_ve_uyarir(self):
        sonuc, kontrol, s, uyari = self._bekle([(False, "http 404")], tavan_dk=45)
        self.assertFalse(sonuc)
        self.assertLessEqual(sum(s.uykular), 45 * 60)
        self.assertGreaterEqual(sum(s.uykular), 44 * 60)
        self.assertEqual(kontrol.call_count, len(s.uykular) + 1)
        uyari.assert_called_once()
        # Loga yalnız durum gider, rapor metni gitmez.
        self.assertIn("http 404", uyari.call_args[0][1])

    def test_kontrol_hatasi_beklemeyi_bozmaz(self):
        sira = [OSError("x"), (True, "hazir")]

        def kontrol(*a):
            v = sira.pop(0)
            if isinstance(v, Exception):
                raise v
            return v
        s = SaatSahte()
        self.assertTrue(report.site_hazir_bekle(GUN, False, tavan_dk=5, kontrol=kontrol,
                                                uyu=s.uyu, saat=s.saat))

    def test_env_tavan(self):
        for deger, beklenen in (("", 45), ("10", 10.0), ("0", 0.0), ("abc", 45), ("-3", 0.0)):
            with mock.patch.dict(os.environ, {"KANAL_SITE_BEKLE_DK": deger}):
                self.assertEqual(report.site_bekle_dk(), beklenen, deger)

    def test_aktiflik(self):
        with mock.patch.dict(os.environ, {"GITHUB_ACTIONS": "true", "KANAL_SITE_BEKLE_DK": "45",
                                          "KANAL_RAPOR_LINKI": "1"}):
            self.assertTrue(report.site_bekleme_aktif_mi())
            with mock.patch.dict(os.environ, {"KANAL_SITE_BEKLE_DK": "0"}):
                self.assertFalse(report.site_bekleme_aktif_mi())
            with mock.patch.dict(os.environ, {"KANAL_RAPOR_LINKI": "0"}):
                self.assertFalse(report.site_bekleme_aktif_mi())
        with mock.patch.dict(os.environ, {"GITHUB_ACTIONS": ""}):
            self.assertFalse(report.site_bekleme_aktif_mi())

    def test_on_yayin_actions_disinda_git_calistirmaz(self):
        with mock.patch.dict(os.environ, {"GITHUB_ACTIONS": ""}), \
             mock.patch.object(report.subprocess, "run") as run:
            self.assertFalse(report.raporu_onden_yayinla(GUN))
            run.assert_not_called()

    def test_on_yayin_takip_json_push_etmez(self):
        cagrilar = []

        def run(arg, **kw):
            cagrilar.append(arg)
            r = mock.Mock()
            r.returncode = 1 if arg[-2:] == ["--cached", "--quiet"] else 0
            return r
        with mock.patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}), \
             mock.patch.object(report.subprocess, "run", side_effect=run):
            self.assertTrue(report.raporu_onden_yayinla(GUN))
        eklenen = [a for a in cagrilar if "add" in a]
        self.assertEqual(len(eklenen), 1)
        self.assertEqual(eklenen[0][-1], "reports")
        self.assertFalse(any("state/takip.json" in " ".join(a) for a in cagrilar))
        self.assertTrue(any(a[-3:] == ["push", "origin", "HEAD:main"] for a in cagrilar))


class AnaAkis(unittest.TestCase):
    """report.main() Actions'taymış gibi; Telegram/ağ/git sahte."""

    def kos(self, site_sonuclari, uzak=(False, False), bugun_gonderildi=False, tavan="45"):
        olaylar = []
        s = SaatSahte()

        def post(url, json=None, data=None, files=None, timeout=None):
            govde = json or data or {}
            olaylar.append(("post", url.rsplit("/", 1)[-1], str(govde.get("chat_id")),
                            govde.get("caption") or govde.get("text") or ""))
            r = mock.Mock()
            r.json.return_value = {"ok": True, "result": {}}
            return r

        sira = list(site_sonuclari)

        def kontrol(rid, ses):
            olaylar.append(("yokla", rid, ses))
            return sira.pop(0) if len(sira) > 1 else sira[0]

        uzak_sira = list(uzak)
        ses_klon = mock.Mock(aktif_mi=mock.Mock(return_value=True),
                             ozet_sesleri=mock.Mock(return_value=(b"OGG", b"MP3")),
                             web_ses_yaz=mock.Mock(return_value="reports/ses/x.mp3"))
        env = {"TELEGRAM_BOT_TOKEN": "1:x", "TELEGRAM_CHAT_ID": "-100KANAL",
               "TELEGRAM_ADMIN_CHAT_ID": "ADMIN", "DELIVER_AT_TR": "", "KANAL_TEK_GONDERI": "1",
               "GITHUB_ACTIONS": "true", "KANAL_SITE_BEKLE_DK": tavan, "KANAL_RAPOR_LINKI": "1",
               "VIDEO_RAPOR_DOSYASI": os.devnull, "GITHUB_STEP_SUMMARY": ""}
        with mock.patch.dict(os.environ, env), \
             mock.patch.object(sys, "argv", ["report.py"]), \
             mock.patch.object(report.requests, "post", post), \
             mock.patch.object(report.requests, "get", side_effect=AssertionError("ag yok")), \
             mock.patch.object(report, "piyasa_verilerini_cek",
                               return_value=("veri", copy.deepcopy(tr.MARKET))), \
             mock.patch.object(report, "llm_ciktisi_uret",
                               return_value=copy.deepcopy(tr.LLM_CIKTISI)), \
             mock.patch.object(report, "haftanin_videosu_satiri", return_value=""), \
             mock.patch.object(report, "bugun_gonderildi_mi", return_value=bugun_gonderildi), \
             mock.patch.object(report, "_uzaktan_gonderilmis_mi",
                               side_effect=lambda: uzak_sira.pop(0)), \
             mock.patch.object(report, "raporu_onden_yayinla",
                               side_effect=lambda rid: olaylar.append(("on_yayin", rid))), \
             mock.patch.object(report, "site_sayfasi_hazir_mi", side_effect=kontrol), \
             mock.patch.object(report.time, "sleep", side_effect=s.uyu), \
             mock.patch.object(report.time, "monotonic", side_effect=s.saat), \
             mock.patch.object(report, "takip_yaz",
                               side_effect=lambda t: olaylar.append(("kilit",))), \
             mock.patch.object(report.kanal_filtre, "LOG_YOL", os.devnull), \
             mock.patch.object(sema, "rapor_yaz", return_value=("a", "b")), \
             mock.patch.object(sema, "rapor_oku", return_value=None), \
             mock.patch.dict(sys.modules, {
                 "eposta": mock.Mock(gonder=mock.Mock(return_value=(True, "ok"))),
                 "ses_klon": ses_klon,
                 "kart": mock.Mock(kart_olustur=mock.Mock(return_value=b"PNG"))}):
            report.main()
        return olaylar, s

    @staticmethod
    def kanal(olaylar):
        return [o for o in olaylar if o[0] == "post" and o[2] == "-100KANAL"]

    def test_404_sonra_200_tek_gonderi_bekleme_sonrasi(self):
        olaylar, s = self.kos([(False, "http 404"), (False, "http 404"), (True, "hazir")])
        kanal = self.kanal(olaylar)
        self.assertEqual(len(kanal), 1)
        self.assertEqual(kanal[0][1], "sendPhoto")
        adlar = [o[0] for o in olaylar]
        # Sıra: ön yayın -> yoklamalar -> kanal -> kilit
        self.assertEqual(adlar.index("on_yayin"), 0)
        son_yokla = max(i for i, a in enumerate(adlar) if a == "yokla")
        ilk_kanal = olaylar.index(kanal[0])
        self.assertLess(son_yokla, ilk_kanal)
        self.assertLess(ilk_kanal, adlar.index("kilit"))
        self.assertEqual(sum(1 for a in adlar if a == "yokla"), 3)
        # Web sesi yazıldığı için ses referansı da beklendi.
        self.assertTrue(all(o[2] is True for o in olaylar if o[0] == "yokla"))
        self.assertEqual(s.uykular[:2], [60, 60])
        # Link satırı tarihli adres, en altta.
        self.assertRegex(kanal[0][3].splitlines()[-1],
                         r"https://dogukanlive\.com/gunluk-raporlar/\d{4}-\d{2}-\d{2}/$")

    def test_tavan_dolarsa_yine_tarihli_linkle_gonderir(self):
        olaylar, s = self.kos([(False, "http 404")], tavan="45")
        kanal = self.kanal(olaylar)
        self.assertEqual(len(kanal), 1)
        son = kanal[0][3].splitlines()[-1]
        self.assertIn("/gunluk-raporlar/", son)
        self.assertNotIn("/bugun/", son)
        self.assertLessEqual(sum(u for u in s.uykular if u == 60), 45 * 60)
        self.assertIn(("kilit",), olaylar)

    def test_bekleme_sirasinda_baskasi_gonderdiyse_ikinci_gonderi_yok(self):
        olaylar, _ = self.kos([(False, "http 404"), (True, "hazir")], uzak=(False, True))
        self.assertEqual(self.kanal(olaylar), [])
        self.assertNotIn(("kilit",), olaylar)

    def test_kilitli_gunde_yedek_cron_hic_gondermez(self):
        olaylar, _ = self.kos([(True, "hazir")], bugun_gonderildi=True)
        self.assertEqual(olaylar, [])

    def test_iki_ardisik_kosu_tek_gonderi(self):
        """Concurrency grubu yedek cron'u ilk koşu bitene kadar sıraya alır; sıra
        gelince kilit (takip.json) bugünü gösterir -> ikinci gönderi yok."""
        ilk, _ = self.kos([(False, "http 404"), (True, "hazir")])
        ikinci, _ = self.kos([(True, "hazir")], bugun_gonderildi=("kilit",) in ilk)
        self.assertEqual(len(self.kanal(ilk)) + len(self.kanal(ikinci)), 1)

    def test_bekleme_kapaliysa_yoklama_yok(self):
        olaylar, _ = self.kos([(False, "http 404")], tavan="0")
        self.assertEqual(len(self.kanal(olaylar)), 1)
        self.assertFalse(any(o[0] in ("yokla", "on_yayin") for o in olaylar))


class WorkflowAyari(unittest.TestCase):
    def test_concurrency_ve_timeout(self):
        yol = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           ".github", "workflows", "daily-report.yml")
        with open(yol, encoding="utf-8") as f:
            metin = f.read()
        self.assertIn("group: daily-report", metin)
        self.assertIn("cancel-in-progress: false", metin)
        self.assertIn("KANAL_SITE_BEKLE_DK", metin)
        import re
        dk = int(re.search(r"timeout-minutes:\s*(\d+)", metin).group(1))
        # 04:07 erken nöbetçi -> 08:00 teslim (~233 dk) + 45 dk bekleme + ~30 dk video/sosyal
        self.assertGreaterEqual(dk, 233 + 45 + 30)


if __name__ == "__main__":
    unittest.main()
