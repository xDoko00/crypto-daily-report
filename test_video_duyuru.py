"""video_duyuru / duyuru_filtre / youtube_rss / haftanın videosu satırı testleri.
Ağ YOK: Telegram ve RSS sahte."""

import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

import duyuru_filtre
import kanal_filtre
import report
import video_duyuru as vd
import youtube_rss

RSS = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015" xmlns:media="http://search.yahoo.com/mrss/" xmlns="http://www.w3.org/2005/Atom">
 <title>Doğukan Doğan</title>
 <entry><yt:videoId>iIaKZM0HyP0</yt:videoId><title>Bu Kadın Gerçek Değil! Sıfırdan Yapay Zekâ Influencer Yaptım</title>
  <link rel="alternate" href="https://www.youtube.com/watch?v=iIaKZM0HyP0"/>
  <published>2026-11-09T17:00:02+00:00</published>
  <media:group><media:description>Yapay zekayla sıfırdan bir influencer oluşturdum. Linkler: https://x.com/a</media:description></media:group></entry>
 <entry><yt:videoId>m7EKVXQoesY</yt:videoId><title>Kaybı Önlemek</title>
  <link rel="alternate" href="https://www.youtube.com/shorts/m7EKVXQoesY"/>
  <published>2026-11-08T15:00:58+00:00</published></entry>
 <entry><yt:videoId>7qKNJhtmeCM</yt:videoId><title>Yapay Zekayla Dikey Dizi Nasıl Yapılır?</title>
  <link rel="alternate" href="https://www.youtube.com/watch?v=7qKNJhtmeCM"/>
  <published>2026-11-02T17:06:15+00:00</published></entry>
</feed>"""

NORMAL = ("📊 <b>GÜNAYDIN · 10 Kasım 2026</b>\n\n⚡ <b>60 SANİYE</b>\n"
          "🌡️ Hava: temkinli · F&amp;G 40 (dün 38)\n₿ BTC $74,894 (-1.19%) · Ξ ETH $2,139 (-4.25%)\n"
          "🔑 <b>Neden:</b> ABD enflasyon verisi öncesi piyasa bekliyor.\n"
          "⏰ <b>Kritik:</b> 15:30 TÜFE\n⚠️ <b>Risk:</b> Veri beklentiden yüksek gelirse satış baskısı.")


def _oku(yol):
    with open(yol, encoding="utf-8") as f:
        return json.load(f)


class SahteTG(vd.Telegram):
    def __init__(self, pinned=None, grup_hata=False):
        super().__init__("123456789:AAAAAAAAAAAAAAA", kuru=False)
        self.cagrilar = []
        self.pinned = pinned
        self.grup_hata = grup_hata
        self.n = 5000

    def cagir(self, yontem, **p):
        self.cagrilar.append((yontem, p))
        if yontem == "getChat":
            return {"pinned_message": {"message_id": self.pinned}} if self.pinned else {}
        if yontem == "sendMessage":
            if self.grup_hata and p["chat_id"] == "@DogukanLiveSohbet":
                raise RuntimeError("sendMessage hatası: Forbidden")
            self.n += 1
            return {"message_id": self.n}
        return True

    def hedefler(self, yontem="sendMessage"):
        return [p.get("chat_id") for y, p in self.cagrilar if y == yontem]


ENV = {"TELEGRAM_CHAT_ID": "-100KANAL", "TELEGRAM_ADMIN_CHAT_ID": "ADMIN",
       "TELEGRAM_SOHBET_ID": "", "VIDEO_DUYURU_AKTIF": "1", "DUYURU_MOD": "taslak",
       "DUYURU_REKLAM_VEREN": ""}


class RSSTest(unittest.TestCase):
    def test_ayristir_ve_pazartesi(self):
        v = youtube_rss.ayristir(RSS)
        self.assertEqual([x["id"] for x in v], ["iIaKZM0HyP0", "m7EKVXQoesY", "7qKNJhtmeCM"])
        self.assertTrue(v[1]["kisa"])
        simdi = datetime(2026, 11, 10, 8, 0, tzinfo=youtube_rss.IST)
        self.assertEqual(youtube_rss.son_pazartesi_videosu(v, simdi)["id"], "iIaKZM0HyP0")
        # 8 gün sonra: pencerede video yok
        self.assertIsNone(youtube_rss.son_pazartesi_videosu(v, simdi + timedelta(days=8)))


class HaftaninVideosuTest(unittest.TestCase):
    def setUp(self):
        self.v = youtube_rss.ayristir(RSS)
        self.simdi = datetime(2026, 11, 10, 8, 0, tzinfo=youtube_rss.IST)

    def test_satir_ve_filtre(self):
        s = report.haftanin_videosu_satiri(self.simdi, self.v)
        self.assertEqual(s, "🎬 Haftanın videosu: Bu Kadın Gerçek Değil! Sıfırdan Yapay Zekâ "
                            "Influencer Yaptım https://youtu.be/iIaKZM0HyP0")
        metin, sebep = report.kanal_brief_hazirla(NORMAL, s)
        self.assertEqual(sebep, "")
        self.assertTrue(metin.endswith("https://youtu.be/iIaKZM0HyP0"))
        self.assertEqual(len([x for x in metin.splitlines() if x.strip()]), 8)

    def test_kapali(self):
        with mock.patch.dict(os.environ, {"HAFTANIN_VIDEOSU": "0"}):
            self.assertEqual(report.haftanin_videosu_satiri(self.simdi, self.v), "")

    def test_yasakli_baslik_satiri_duser_rapor_gider(self):
        kotu = "🎬 Haftanın videosu: Garantili al sinyali https://youtu.be/iIaKZM0HyP0"
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(kanal_filtre, "LOG_YOL", os.path.join(d, "l.jsonl")):
                metin, sebep = report.kanal_brief_hazirla(NORMAL, kotu)
        self.assertIsNotNone(metin)
        self.assertNotIn("Haftanın videosu", metin)

    def test_bozuk_video_satiri_engel(self):
        ok, sebep = kanal_filtre.kontrol(NORMAL + "\n\n🎬 Haftanın videosu: x https://evil.com/a")
        self.assertFalse(ok)
        ok, _ = kanal_filtre.kontrol(NORMAL + "\nfazla satır")
        self.assertFalse(ok)

    def test_rss_hatasi_bos(self):
        with mock.patch.object(youtube_rss.requests, "get", side_effect=OSError("ağ")):
            self.assertEqual(report.haftanin_videosu_satiri(self.simdi), "")


class DuyuruFiltreTest(unittest.TestCase):
    V = "iIaKZM0HyP0"

    def k(self, m, **kw):
        return duyuru_filtre.kontrol(kanal_filtre.em_tire_temizle(m), self.V, **kw)

    def test_sablon_gecer(self):
        v = youtube_rss.ayristir(RSS)[0]
        ok, s = self.k(vd.metin_kur(v, "ilk"), sablon_zorunlu=True)
        self.assertTrue(ok, s)
        ok, s = self.k(vd.metin_kur(v, "ikinci"), sablon_zorunlu=True)
        self.assertTrue(ok, s)

    def test_engeller(self):
        L = f"https://youtu.be/{self.V}"
        for m in (f"Yeni video {L} binance kayıt https://accounts.binance.com/register?ref=X",
                  f"Garantili kazanç, risksiz! {L}",
                  f"Uyurken kazan {L}",
                  f"Rapor hazır, here is the post {L}",
                  f"/Users/dogukandogan/x.py {L}",
                  "Link yok",
                  f"Alpha'nın taslağı {L}"):
            ok, s = self.k(m)
            self.assertFalse(ok, m)

    def test_sponsor(self):
        L = f"https://youtu.be/{self.V}"
        ok, s = self.k(f"🎬 Yeni video yayında!\n\nX\n\n{L}", sponsor_izi=True)
        self.assertFalse(ok)
        self.assertIn("reklam veren", s)
        ok, s = self.k(f"Reklam: Shorts Studio\n\n🎬 Yeni video yayında!\n\nX\n\n{L}",
                       reklam_veren="Shorts Studio", sponsor_izi=True, sablon_zorunlu=True)
        self.assertTrue(ok, s)
        ok, s = self.k(f"🎬 Yeni video yayında!\n\nX\n\n{L}", reklam_veren="Shorts Studio")
        self.assertFalse(ok)

    def test_sablon_disi_sinifta_engel(self):
        ok, s = self.k(f"Bu kadın gerçek değil :D\n\nhttps://youtu.be/{self.V}", sablon_zorunlu=True)
        self.assertFalse(ok)
        ok, s = self.k(f"Bu kadın gerçek değil :D\n\nhttps://youtu.be/{self.V}")
        self.assertTrue(ok, s)


class AkisTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.yol = os.path.join(self.d.name, "durum.json")
        self.p = [mock.patch.dict(os.environ, ENV),
                  mock.patch.object(duyuru_filtre, "LOG_YOL", os.path.join(self.d.name, "f.jsonl"))]
        for x in self.p:
            x.start()
        self.v = youtube_rss.ayristir(RSS)
        self.t_yayin = datetime(2026, 11, 9, 17, 0, 2, tzinfo=timezone.utc)

    def tearDown(self):
        for x in self.p:
            x.stop()
        self.d.cleanup()

    def test_kapaliyken_hicbir_sey(self):
        tg = SahteTG()
        with mock.patch.dict(os.environ, {"VIDEO_DUYURU_AKTIF": "0"}):
            self.assertEqual(vd.calis(tg, self.t_yayin, self.v, self.yol), [])
        self.assertEqual(tg.cagrilar, [])

    def test_taslak_modu_kanala_gitmez(self):
        tg = SahteTG(pinned=2194)
        isler = vd.calis(tg, self.t_yayin + timedelta(minutes=10), self.v, self.yol)
        self.assertEqual(isler[0][:3], ("ilk", "iIaKZM0HyP0", "taslak"))
        self.assertEqual(tg.hedefler(), ["ADMIN"])
        self.assertIn("TASLAK", tg.cagrilar[0][1]["text"])
        # ikinci tur: aynı taslak tekrar gitmez
        tg2 = SahteTG()
        vd.calis(tg2, self.t_yayin + timedelta(minutes=20), self.v, self.yol)
        self.assertEqual(tg2.cagrilar, [])

    def test_sinif_modu_kanal_grup_sabit_ikinci(self):
        with mock.patch.dict(os.environ, {"DUYURU_MOD": "sinif",
                                          "TELEGRAM_SOHBET_ID": "@DogukanLiveSohbet"}):
            tg = SahteTG(pinned=2194)
            t1 = self.t_yayin + timedelta(minutes=10)
            vd.calis(tg, t1, self.v, self.yol)
            self.assertEqual(tg.hedefler(), ["-100KANAL", "@DogukanLiveSohbet", "ADMIN"])
            self.assertEqual(tg.hedefler("unpinChatMessage"), ["-100KANAL"])
            pin = [p for y, p in tg.cagrilar if y == "pinChatMessage"][0]
            self.assertEqual(pin["message_id"], 5001)
            self.assertTrue(pin["disable_notification"])
            unpin = [p for y, p in tg.cagrilar if y == "unpinChatMessage"][0]
            self.assertEqual(unpin["message_id"], 2194)
            # 23 saatte ikinci yok
            durum = _oku(self.yol)
            t_gonder = datetime.fromisoformat(durum["videolar"]["iIaKZM0HyP0"]["ilk"]["zaman"])
            tg2 = SahteTG()
            vd.calis(tg2, t_gonder + timedelta(hours=23), self.v, self.yol)
            self.assertEqual(tg2.cagrilar, [])
            # 24 saat: ikinci dokunuş yalnız kanala, sabit yok
            tg3 = SahteTG()
            vd.calis(tg3, t_gonder + timedelta(hours=24, minutes=5), self.v, self.yol)
            self.assertEqual(tg3.hedefler(), ["-100KANAL", "ADMIN"])
            self.assertFalse([y for y, _ in tg3.cagrilar if "pin" in y.lower()])
            metin = tg3.cagrilar[0][1]["text"]
            self.assertTrue(metin.startswith("⏰ Dünkü videoyu kaçırdıysan:"))
            self.assertIn("https://youtu.be/iIaKZM0HyP0", metin)
            # bir kez daha: tekrar gitmez
            tg4 = SahteTG()
            vd.calis(tg4, t_gonder + timedelta(hours=25), self.v, self.yol)
            self.assertEqual(tg4.cagrilar, [])

    def test_sinif_modu_sponsor_belirsiz_taslaga_duser(self):
        v = [dict(self.v[0], aciklama="Bu video Shorts Studio sponsorluğunda hazırlandı.")]
        with mock.patch.dict(os.environ, {"DUYURU_MOD": "sinif"}):
            tg = SahteTG()
            isler = vd.calis(tg, self.t_yayin + timedelta(minutes=10), v, self.yol)
        self.assertEqual(isler[0][2], "taslak")
        self.assertEqual(tg.hedefler(), ["ADMIN"])

    def test_unutulan_reklam_veren_sponsorsuz_videoya_eklenmez(self):
        with mock.patch.dict(os.environ, {"DUYURU_REKLAM_VEREN": "Shorts Studio"}):
            self.assertFalse(vd.metin_kur(self.v[0]).startswith("Reklam:"))
            v = dict(self.v[0], aciklama="Shorts Studio sponsorluğunda.")
            self.assertTrue(vd.metin_kur(v).startswith("Reklam: Shorts Studio\n"))

    def test_onayla_sonra_kanal(self):
        tg = SahteTG()
        vd.calis(tg, self.t_yayin + timedelta(minutes=10), self.v, self.yol)
        tg2 = SahteTG()
        vd.onayla(tg2, "iIaKZM0HyP0", "ilk", durum_yol=self.yol)
        self.assertEqual(tg2.hedefler()[0], "-100KANAL")
        self.assertIn("pinChatMessage", [y for y, _ in tg2.cagrilar])
        with self.assertRaises(SystemExit):
            vd.onayla(SahteTG(), "iIaKZM0HyP0", "ilk", durum_yol=self.yol)

    def test_grup_hatasi_kanali_bozmaz(self):
        with mock.patch.dict(os.environ, {"DUYURU_MOD": "sinif",
                                          "TELEGRAM_SOHBET_ID": "@DogukanLiveSohbet"}):
            tg = SahteTG(grup_hata=True)
            vd.calis(tg, self.t_yayin + timedelta(minutes=10), self.v, self.yol)
        durum = _oku(self.yol)["videolar"]["iIaKZM0HyP0"]["ilk"]
        self.assertEqual(durum["durum"], "gonderildi")
        self.assertTrue(any("sohbet grubuna" in n for n in durum["notlar"]))

    def test_shorts_ve_eski_video_duyurulmaz(self):
        tg = SahteTG()
        isler = vd.calis(tg, self.t_yayin + timedelta(days=2), self.v, self.yol)
        self.assertEqual(isler, [])
        self.assertEqual(tg.cagrilar, [])


if __name__ == "__main__":
    unittest.main()
