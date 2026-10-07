# -*- coding: utf-8 -*-
"""sosyal.py birim testleri (ağ, secret, gh veya ffmpeg GEREKTİRMEZ)."""
import json
import os
import tempfile
import unittest
from unittest import mock
from datetime import datetime, timezone
from types import SimpleNamespace

import sosyal as s

RAPOR = {
    "id": "2026-10-08",
    "brief": {"criticalEvents": [{"timeTr": "15:30", "title": "PCE enflasyon verisi"}]},
    "sections": {"agenda": [
        {"title": "CFTC kripto piyasası için kural teklifine gitti"},
        {"title": "ISM hizmet PMI beklentinin altında kaldı"},
        {"title": "BTC ETF'leri 3. haftada girişte, ETH'de çıkış"},
        {"title": "Dördüncü başlık burada"},
    ]},
}


class SahteYanit:
    def __init__(self, veri, kod=200):
        self.veri, self.status_code = veri, kod

    def json(self):
        return self.veri


class SahteHttp:
    def __init__(self, *yanitlar):
        self.yanitlar = list(yanitlar)
        self.cagrilar = []

    def post(self, url, json=None, headers=None, timeout=None):
        self.cagrilar.append({"url": url, "json": json, "headers": headers})
        return SahteYanit(self.yanitlar.pop(0) if self.yanitlar else {})


class SahteBuffer:
    def __init__(self, zaten=(), hata=None):
        self.zaten, self.hata = set(zaten), hata
        self.olusturulan = []

    def bugun_zamanlanmis(self, gun):
        if self.hata:
            raise self.hata
        return self.zaten

    def gonderi_olustur(self, platform, url, metin, due):
        self.olusturulan.append((platform, url, metin, due))
        return f"id-{platform}"


class SahteRelease:
    depo = "xDoko00/crypto-daily-report"

    def __init__(self, mevcut=()):
        self.mevcut = list(mevcut)
        self.yuklenen = []
        self.silinen = []

    def hazirla(self):
        return self.mevcut

    def yukle(self, yollar):
        self.yuklenen.extend(os.path.basename(y) for y in yollar)

    def temizle(self, adlar, bugun):
        self.silinen = s.silinecek_assetler(adlar, bugun)
        return self.silinen


def sahte_ig(girdi, cikti, calisma):
    with open(cikti, "wb") as f:
        f.write(b"ig")
    return cikti


class MetinTestleri(unittest.TestCase):
    def test_basliklar_uc_tane_ve_tekrarsiz(self):
        r = json.loads(json.dumps(RAPOR))
        r["sections"]["agenda"].insert(1, {"title": "CFTC kripto piyasası için kural teklifine gitti."})
        self.assertEqual(len(s.basliklar(r)), 3)
        self.assertEqual(s.basliklar(r)[1], "ISM hizmet PMI beklentinin altında kaldı")

    def test_basliklar_eksikse_kritik_olay(self):
        r = {"id": "2026-10-08", "brief": RAPOR["brief"], "sections": {"agenda": RAPOR["sections"]["agenda"][:1]}}
        self.assertIn("PCE enflasyon verisi", s.basliklar(r))

    def test_x_metni(self):
        t = s.x_metni(RAPOR)
        self.assertTrue(t.startswith("Günaydın Kripto · 8 Ekim"))
        self.assertIn("dogukanlive.com/bugun", t)
        self.assertTrue(t.endswith("Yatırım tavsiyesi değildir."))
        self.assertLessEqual(len(t), 280)
        self.assertEqual(t.count("• "), 3)

    def test_x_uzun_basliklar_sinira_sigar(self):
        r = {"id": "2026-10-08", "sections": {"agenda": [{"title": ("Çok uzun başlık kelime " * 10)} for _ in range(3)]}}
        r["sections"]["agenda"] = [{"title": f"{i} " + "uzun başlık kelime " * 10} for i in range(3)]
        t = s.x_metni(r)
        self.assertLessEqual(len(t), 280)
        self.assertIn("Yatırım tavsiyesi değildir.", t)
        self.assertGreaterEqual(t.count("• "), 2)

    def test_tiktok_metni(self):
        t = s.tiktok_metni(RAPOR)
        self.assertLessEqual(len(t), 2200)
        etiketler = [k for k in t.split() if k.startswith("#")]
        self.assertTrue(4 <= len(etiketler) <= 6)
        self.assertIn("#günaydınkripto", etiketler)
        self.assertIn("Yatırım tavsiyesi değildir.", t)

    def test_manychat_metni(self):
        t = s.manychat_metni(RAPOR)
        self.assertEqual(t.split("\n")[0], "📅 8 Ekim")
        self.assertEqual(t.count("\n• "), 3)
        self.assertLess(len(t), 600)

    def test_filtre_yakalar(self):
        self.assertEqual(s.supheli_kelimeler("Şimdi AL, kesin yükselir"), ["al", "kesin"])
        self.assertIn("garanti", s.supheli_kelimeler("Garanti getiri"))
        self.assertIn("hedef fiyat", s.supheli_kelimeler("BTC için hedef fiyat 100 bin"))
        self.assertIn("satın al", s.supheli_kelimeler("Hemen satın al"))

    def test_filtre_haber_dilini_gecirir(self):
        for t in ("Strategy 1.000 BTC satın aldı", "ETF alımları sürdü", "satış baskısı arttı",
                  "kâr realizasyonu geldi", "SEC kararını aldı", "Kesinleşti: ETF onayı"):
            self.assertEqual(s.supheli_kelimeler(t), [], t)
        self.assertEqual(s.supheli_kelimeler(s.x_metni(RAPOR)), [])


class ZamanlamaTestleri(unittest.TestCase):
    def test_due_at(self):
        simdi = datetime(2026, 10, 8, 5, 0, 42, tzinfo=timezone.utc)   # 08:00:42 TSİ
        iso, yerel = s.due_at(simdi, 30)
        self.assertEqual(iso, "2026-10-08T05:30:00.000Z")
        self.assertEqual(yerel.strftime("%H:%M"), "08:30")

    def test_gecikme_ortamdan(self):
        self.assertEqual(s.gecikme_dk({}), 30)
        self.assertEqual(s.gecikme_dk({"SOSYAL_GECIKME_DK": "45"}), 45)
        self.assertEqual(s.gecikme_dk({"SOSYAL_GECIKME_DK": "abc"}), 30)

    def test_gun_araligi_tsi(self):
        self.assertEqual(s.gun_araligi("2026-10-08"), ("2026-10-07T21:00:00.000Z", "2026-10-08T21:00:00.000Z"))


class IstekGovdesiTestleri(unittest.TestCase):
    def test_instagram_hikaye_girdisi(self):
        g = s.Buffer("k").gonderi_girdisi("instagram", "https://u/ig.mp4", "", "2026-10-08T05:30:00.000Z")
        self.assertEqual(g["channelId"], "6ac5fc4c6a5c39ccb63d7b1c")
        self.assertEqual(g["metadata"], {"instagram": {"type": "story", "shouldShareToFeed": False}})
        self.assertEqual(g["assets"], [{"video": {"url": "https://u/ig.mp4"}}])
        self.assertEqual((g["mode"], g["schedulingType"]), ("customScheduled", "automatic"))
        self.assertNotIn("text", g)

    def test_x_tiktok_girdisi(self):
        for p, kanal in (("x", "6ac5fcb16a5c39ccb63d823e"), ("tiktok", "6ac5fc7f6a5c39ccb63d7f09")):
            g = s.Buffer("k").gonderi_girdisi(p, "https://u/v.mp4", "metin", "D")
            self.assertEqual((g["channelId"], g["text"], g["dueAt"]), (kanal, "metin", "D"))
            self.assertNotIn("metadata", g)

    def test_buffer_istek_ve_yanit(self):
        http = SahteHttp({"data": {"createPost": {"post": {"id": "p1"}}}})
        pid = s.Buffer("GIZLI", http=http).gonderi_olustur("x", "https://u/v.mp4", "m", "D")
        self.assertEqual(pid, "p1")
        c = http.cagrilar[0]
        self.assertEqual(c["url"], "https://api.buffer.com")
        self.assertEqual(c["headers"]["Authorization"], "Bearer GIZLI")
        self.assertIn("createPost", c["json"]["query"])
        self.assertEqual(c["json"]["variables"]["input"]["channelId"], "6ac5fcb16a5c39ccb63d823e")

    def test_buffer_mutation_hatasi(self):
        http = SahteHttp({"data": {"createPost": {"message": "Invalid"}}})
        with self.assertRaises(RuntimeError):
            s.Buffer("k", http=http).gonderi_olustur("x", "u", "m", "D")

    def test_buffer_bugun_yalniz_api(self):
        http = SahteHttp({"data": {"posts": {"edges": [
            {"node": {"channelId": "6ac5fcb16a5c39ccb63d823e", "via": "api"}},
            {"node": {"channelId": "6ac5fc7f6a5c39ccb63d7f09", "via": "network"}}]}}})
        self.assertEqual(s.Buffer("k", http=http).bugun_zamanlanmis("2026-10-08"), {"x"})
        f = http.cagrilar[0]["json"]["variables"]["input"]["filter"]
        self.assertEqual(f["dueAt"]["start"], "2026-10-07T21:00:00.000Z")

    def test_manychat_govdesi(self):
        http = SahteHttp({"status": "success"})
        metin = s.manychat_guncelle(RAPOR, "MK", http=http)
        c = http.cagrilar[0]
        self.assertEqual(c["url"], "https://api.manychat.com/fb/page/setBotField")
        self.assertEqual(c["json"], {"field_id": 5115106, "field_value": metin})
        self.assertEqual(c["headers"]["Authorization"], "Bearer MK")

    def test_manychat_hata_firlatmaz(self):
        bildirim = []
        http = SahteHttp({"status": "error", "message": "bad"})
        self.assertIsNone(s.manychat(RAPOR, ortam={"MANYCHAT_API_KEY": "k"}, http=http, bildir=bildirim.append))
        self.assertEqual(len(bildirim), 1)

    def test_manychat_anahtarsiz_atlanir(self):
        self.assertIsNone(s.manychat(RAPOR, ortam={}, http=SahteHttp(), bildir=lambda m: None))

    def test_kuru_istek_gondermez_ve_maskeler(self):
        http = SahteHttp()
        with mock.patch("sys.stderr") as err:
            self.assertEqual(s.Buffer("GIZLI", http=http, kuru=True).gonderi_olustur("x", "u", "m", "D"), "KURU")
            yazilan = "".join(c.args[0] for c in err.write.call_args_list)
        self.assertEqual(http.cagrilar, [])
        self.assertNotIn("GIZLI", yazilan)
        self.assertIn("Bearer ***", yazilan)

    def test_gizle(self):
        self.assertEqual(s.gizle("x Bearer abc123 y", {}), "x Bearer *** y")
        self.assertNotIn("SIR", s.gizle("hata SIR", {"BUFFER_API_KEY": "SIR"}))


class ReleaseTestleri(unittest.TestCase):
    def test_asset_adlari(self):
        self.assertEqual(s.asset_adlari("2026-10-08"), ("gunaydin-2026-10-08.mp4", "gunaydin-2026-10-08-ig.mp4"))
        self.assertEqual(s.asset_url("a/b", "gunaydin-2026-10-08.mp4"),
                         "https://github.com/a/b/releases/download/gunluk-video/gunaydin-2026-10-08.mp4")

    def test_temizleme_7_gun(self):
        adlar = ["gunaydin-2026-09-30.mp4", "gunaydin-2026-09-30-ig.mp4", "gunaydin-2026-10-01.mp4",
                 "gunaydin-2026-10-07-ig.mp4", "baska.mp4", "gunaydin-x.mp4"]
        self.assertEqual(s.silinecek_assetler(adlar, "2026-10-08"),
                         ["gunaydin-2026-09-30-ig.mp4", "gunaydin-2026-09-30.mp4"])

    def test_release_komutlari(self):
        komutlar = []

        def calistir(a):
            komutlar.append(a)
            if a[2] == "view":
                return SimpleNamespace(returncode=0, stdout=json.dumps(
                    {"assets": [{"name": "gunaydin-2026-09-01.mp4"}]}), stderr="")
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        r = s.Release("a/b", calistir=calistir)
        mevcut = r.hazirla()
        r.yukle(["/t/gunaydin-2026-10-08.mp4"])
        self.assertEqual(r.temizle(mevcut, "2026-10-08"), ["gunaydin-2026-09-01.mp4"])
        self.assertEqual(komutlar[1][:3], ["gh", "release", "upload"])
        self.assertIn("--clobber", komutlar[1])
        self.assertEqual(komutlar[2][2:5], ["delete-asset", "gunluk-video", "gunaydin-2026-09-01.mp4"])
        self.assertEqual(komutlar[2][-2:], ["--repo", "a/b"])

    def test_release_yoksa_olusturur(self):
        komutlar = []

        def calistir(a):
            komutlar.append(a)
            return SimpleNamespace(returncode=1 if a[2] == "view" else 0, stdout="", stderr="not found")
        self.assertEqual(s.Release("a/b", calistir=calistir).hazirla(), [])
        self.assertEqual(komutlar[1][2:4], ["create", "gunluk-video"])
        self.assertIn("--prerelease", komutlar[1])

    def test_ig_varyant_komutu(self):
        k = s.ig_varyant_komutu("in.mp4", "hap.png", "cagri.png", "out.mp4", 50.0)
        filtre = k[k.index("-filter_complex") + 1]
        self.assertIn("enable='lt(t,47.00)'", filtre)           # küçük hap son 3 sn'ye kadar
        self.assertIn("enable='gte(t,47.00)'", filtre)          # büyük çağrı son 3 sn
        self.assertIn("eval=frame", filtre)                     # nabız
        self.assertIn("x='540-w/2':y='1610-h/2'", filtre)       # nabızda merkez sabit
        self.assertEqual([k[i + 1] for i, v in enumerate(k) if v == "-i"], ["in.mp4", "hap.png", "cagri.png"])
        self.assertEqual(k[-1], "out.mp4")
        sabit = s.ig_varyant_komutu("in.mp4", "hap.png", "cagri.png", "out.mp4", 50.0, nabiz=False)
        self.assertNotIn("eval=frame", sabit[sabit.index("-filter_complex") + 1])

    def test_nabiz_zamanlamasi(self):
        self.assertEqual(s.nabiz_olcegi(2.0), 1.0)              # ilk 5 sn nabız yok
        self.assertAlmostEqual(s.nabiz_olcegi(5.25), 1.12)      # 5. sn tepe
        self.assertEqual(s.nabiz_olcegi(5.6), 1.0)              # 0,5 sn sonra biter
        self.assertAlmostEqual(s.nabiz_olcegi(10.25), 1.12)     # her 5 sn

    def test_hap_guvenli_bantta(self):
        y0 = s.IG_HAP_MERKEZ[1] - s.IG_HAP_YUKSEKLIK * (1 + s.IG_NABIZ_GENLIK) / 2
        y1 = s.IG_HAP_MERKEZ[1] + s.IG_HAP_YUKSEKLIK * (1 + s.IG_NABIZ_GENLIK) / 2
        self.assertGreater(y0, 1500)                            # altyazı altı
        self.assertLess(y1, 1920 - 200)                         # IG yanıt kutusu üstü
        self.assertLess(s.IG_CAGRI_Y + s.IG_CAGRI_YUKSEKLIK, 1920 - 200)


class PaylasTestleri(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.video = os.path.join(self.d, "v.mp4")
        with open(self.video, "wb") as f:
            f.write(b"v")
        self.durum = os.path.join(self.d, "state", "sosyal-son.json")
        self.ortam = {"BUFFER_API_KEY": "k"}
        self.bildirim = []

    def _paylas(self, buffer, release=None, ortam=None):
        return s.paylas(RAPOR, self.video, ortam=self.ortam if ortam is None else ortam, buffer=buffer,
                        release=release or SahteRelease(), bildir=self.bildirim.append,
                        simdi=datetime(2026, 10, 8, 5, 0, tzinfo=timezone.utc), durum_yolu=self.durum,
                        ig_uret=sahte_ig, erisim=lambda u: True)

    def test_uc_platform_zamanlanir(self):
        b, r = SahteBuffer(), SahteRelease(mevcut=["gunaydin-2026-09-20.mp4"])
        sonuc = self._paylas(b, r)
        self.assertEqual(sonuc, {"instagram": "id-instagram", "x": "id-x", "tiktok": "id-tiktok"})
        self.assertEqual(sorted(r.yuklenen), ["gunaydin-2026-10-08-ig.mp4", "gunaydin-2026-10-08.mp4"])
        self.assertEqual(r.silinen, ["gunaydin-2026-09-20.mp4"])
        urller = {p: u for p, u, _, _ in b.olusturulan}
        self.assertTrue(urller["instagram"].endswith("/gunaydin-2026-10-08-ig.mp4"))
        self.assertTrue(urller["x"].endswith("/gunaydin-2026-10-08.mp4"))
        self.assertEqual({d for *_, d in b.olusturulan}, {"2026-10-08T05:30:00.000Z"})
        self.assertIn("Sosyal medya: 08:30'de yayınlanacak (Instagram hikâye, X, TikTok). "
                      "İptal için Buffer'dan sil.", self.bildirim[0])
        self.assertIn("id-tiktok", self.bildirim[0])
        self.assertEqual(s.durum_oku(self.durum)["gonderiler"]["x"], "id-x")

    def test_ikinci_calisma_atlanir(self):
        self._paylas(SahteBuffer())
        b2 = SahteBuffer()
        self.assertEqual(self._paylas(b2), {})
        self.assertEqual(b2.olusturulan, [])

    def test_buffer_kontrolu_cift_gonderiyi_engeller(self):
        b = SahteBuffer(zaten={"x", "tiktok"})
        self.assertEqual(set(self._paylas(b)), {"instagram"})

    def test_buffer_kontrolu_hata_verirse_gondermez(self):
        b = SahteBuffer(hata=RuntimeError("ağ"))
        self.assertEqual(self._paylas(b), {})
        self.assertEqual(b.olusturulan, [])
        self.assertTrue(self.bildirim)

    def test_dunku_durum_bugunu_engellemez(self):
        s.durum_yaz("2026-10-07", "x", "eski", self.durum)
        self.assertIn("x", self._paylas(SahteBuffer()))

    def test_kapali(self):
        b = SahteBuffer()
        self.assertEqual(self._paylas(b, ortam={"BUFFER_API_KEY": "k", "SOSYAL_YAYIN": "kapali"}), {})
        self.assertEqual(b.olusturulan, [])

    def test_anahtarsiz_atlanir(self):
        b = SahteBuffer()
        self.assertEqual(self._paylas(b, ortam={}), {})
        self.assertEqual(b.olusturulan, [])

    def test_supheli_metin_o_platforma_gitmez(self):
        r = json.loads(json.dumps(RAPOR))
        r["sections"]["agenda"][0]["title"] = "Bitcoin kesin yükselecek"
        b = SahteBuffer()
        sonuc = s.paylas(r, self.video, ortam=self.ortam, buffer=b, release=SahteRelease(),
                         bildir=self.bildirim.append, durum_yolu=self.durum, ig_uret=sahte_ig,
                         erisim=lambda u: True)
        self.assertEqual(sonuc, {})                       # IG videosunda da aynı başlık var
        self.assertEqual(b.olusturulan, [])
        for ad in ("Instagram hikâye gönderilmedi", "X gönderilmedi", "TikTok gönderilmedi"):
            self.assertIn(ad, self.bildirim[0])
        self.assertIn("şüpheli ifade: kesin", self.bildirim[0])

    def test_platform_hatasi_digerlerini_durdurmaz(self):
        class Yarim(SahteBuffer):
            def gonderi_olustur(self, platform, url, metin, due):
                if platform == "x":
                    raise RuntimeError("X reddetti")
                return super().gonderi_olustur(platform, url, metin, due)
        sonuc = self._paylas(Yarim())
        self.assertEqual(set(sonuc), {"instagram", "tiktok"})
        self.assertIn("X zamanlanamadı", self.bildirim[0])
        self.assertNotIn("x", s.durum_oku(self.durum)["gonderiler"])

    def test_url_erisilemezse_gondermez(self):
        b = SahteBuffer()
        sonuc = s.paylas(RAPOR, self.video, ortam=self.ortam, buffer=b, release=SahteRelease(),
                         bildir=self.bildirim.append, durum_yolu=self.durum, ig_uret=sahte_ig,
                         erisim=lambda u: False)
        self.assertEqual((sonuc, b.olusturulan), ({}, []))
        self.assertIn("erişilebilir değil", self.bildirim[0])

    def test_kuru_durum_yazmaz(self):
        b = SahteBuffer()
        self._paylas(b, ortam={"SOSYAL_KURU": "1"})
        self.assertFalse(os.path.exists(self.durum))


class SahteBufferApi:
    """Buffer GraphQL'i taklit eder: oluşturulanı saklar, posts sorgusunda status filtresini uygular."""
    def __init__(self):
        self.postlar = []
        self.cagrilar = []

    def post(self, url, json=None, headers=None, timeout=None):
        self.cagrilar.append(json)
        g = json["variables"]
        if "createPost" in json["query"]:
            i = g["input"]
            n = {"id": f"p{len(self.postlar) + 1}", "channelId": i["channelId"], "via": "api",
                 "dueAt": i.get("dueAt"), "status": "draft" if i.get("saveToDraft") else "scheduled"}
            self.postlar.append(n)
            return SahteYanit({"data": {"createPost": {"post": n}}})
        durumlar = g["input"]["filter"]["status"]
        return SahteYanit({"data": {"posts": {"edges": [
            {"node": n} for n in self.postlar if n["status"] in durumlar]}}})


class TaslakTestleri(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.video = os.path.join(self.d, "v.mp4")
        with open(self.video, "wb") as f:
            f.write(b"v")
        self.durum = os.path.join(self.d, "state", "sosyal-son.json")
        self.bildirim = []

    def _paylas(self, buffer, ortam, release=None):
        return s.paylas(RAPOR, self.video, ortam=ortam, buffer=buffer, release=release or SahteRelease(),
                        bildir=self.bildirim.append, simdi=datetime(2026, 10, 8, 5, 0, tzinfo=timezone.utc),
                        durum_yolu=self.durum, ig_uret=sahte_ig, erisim=lambda u: True)

    def test_taslak_bayragi_govdeye_girer(self):
        g = s.Buffer("k", taslak=True).gonderi_girdisi("x", "https://u/v.mp4", "m", "D")
        self.assertIs(g["saveToDraft"], True)
        self.assertEqual(g["dueAt"], "D")
        self.assertNotIn("saveToDraft", s.Buffer("k").gonderi_girdisi("x", "u", "m", "D"))

    def test_taslak_ortamdan_ve_istek(self):
        api = SahteBufferApi()
        b = s.Buffer("k", http=api, taslak=s.taslak_mi({"SOSYAL_TASLAK": "1"}))
        b.gonderi_olustur("tiktok", "u", "m", "D")
        self.assertIs(api.cagrilar[0]["variables"]["input"]["saveToDraft"], True)
        self.assertFalse(s.taslak_mi({}))

    def test_taslak_kilit_yazmaz_test_asset_adi_ve_mesaj(self):
        r = SahteRelease()
        api = SahteBufferApi()
        b = s.Buffer("k", http=api, taslak=True)
        sonuc = self._paylas(b, {"BUFFER_API_KEY": "k", "SOSYAL_TASLAK": "1"}, r)
        self.assertEqual(set(sonuc), {"instagram", "x", "tiktok"})
        self.assertEqual({n["status"] for n in api.postlar}, {"draft"})
        self.assertFalse(os.path.exists(self.durum))
        self.assertEqual(sorted(r.yuklenen), ["gunaydin-2026-10-08-test-ig.mp4", "gunaydin-2026-10-08-test.mp4"])
        self.assertTrue(self.bildirim[0].startswith(
            "TEST: Buffer'da 3 taslak oluşturuldu (Instagram hikâye, X, TikTok). Kontrol edip silebilirsin."))

    def test_taslak_kilidi_okumaz(self):
        for p in s.KANALLAR:
            s.durum_yaz("2026-10-08", p, "gercek", self.durum)
        b = SahteBuffer(zaten=set(s.KANALLAR))
        self.assertEqual(set(self._paylas(b, {"BUFFER_API_KEY": "k", "SOSYAL_TASLAK": "1"})), set(s.KANALLAR))

    def test_taslaklar_gercek_calismayi_engellemez(self):
        api = SahteBufferApi()
        self._paylas(s.Buffer("k", http=api, taslak=True), {"BUFFER_API_KEY": "k", "SOSYAL_TASLAK": "1"})
        sonuc = self._paylas(s.Buffer("k", http=api), {"BUFFER_API_KEY": "k"})
        self.assertEqual(set(sonuc), {"instagram", "x", "tiktok"})
        self.assertEqual([n["status"] for n in api.postlar], ["draft"] * 3 + ["scheduled"] * 3)
        self.assertEqual(set(s.durum_oku(self.durum)["gonderiler"]), set(s.KANALLAR))
        # gerçek gönderiler bundan sonra yine çift gönderiyi engeller
        self.assertEqual(self._paylas(s.Buffer("k", http=api), {"BUFFER_API_KEY": "k"}), {})

    def test_bugun_kontrolu_draft_saymaz(self):
        http = SahteHttp({"data": {"posts": {"edges": [
            {"node": {"channelId": "6ac5fcb16a5c39ccb63d823e", "via": "api", "status": "draft"}},
            {"node": {"channelId": "6ac5fc7f6a5c39ccb63d7f09", "via": "api", "status": "scheduled"}}]}}})
        self.assertEqual(s.Buffer("k", http=http).bugun_zamanlanmis("2026-10-08"), {"tiktok"})
        self.assertNotIn("draft", http.cagrilar[0]["json"]["variables"]["input"]["filter"]["status"])

    def test_temizlik_test_assetlerini_kapsar(self):
        adlar = ["gunaydin-2026-09-30-test.mp4", "gunaydin-2026-09-30-test-ig.mp4",
                 "gunaydin-2026-10-07-test.mp4", "gunaydin-2026-09-30-ig-test.mp4"]
        self.assertEqual(s.silinecek_assetler(adlar, "2026-10-08"),
                         ["gunaydin-2026-09-30-test-ig.mp4", "gunaydin-2026-09-30-test.mp4"])
        self.assertEqual(s.asset_adlari("2026-10-08", test=True),
                         ("gunaydin-2026-10-08-test.mp4", "gunaydin-2026-10-08-test-ig.mp4"))


if __name__ == "__main__":
    unittest.main()
