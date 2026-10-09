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


IG_ID, X_ID, TT_ID = "6ac732776a5c39ccb64cfdb6", "6ac5fcb16a5c39ccb63d823e", "6ac5fc7f6a5c39ccb63d7f09"
TEST_KANALLARI = {"instagram": IG_ID, "x": X_ID, "tiktok": TT_ID}
KANAL_LISTESI = [
    {"id": IG_ID, "service": "instagram", "name": "dogukanlive", "isDisconnected": False, "isLocked": False},
    {"id": X_ID, "service": "twitter", "name": "DogukanDogan", "isDisconnected": False, "isLocked": False},
    {"id": TT_ID, "service": "tiktok", "name": "gercekdogukandogan", "isDisconnected": False, "isLocked": False},
]


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
    def __init__(self, zaten=(), hata=None, kanal_sorunlari=(), kanal_hatasi=None, kopuk=()):
        self.zaten, self.hata = set(zaten), hata
        self.kanal_sorunlari, self.kanal_hatasi, self.kopuk = list(kanal_sorunlari), kanal_hatasi, set(kopuk)
        self.olusturulan = []

    def kanallari_bul(self):
        if self.kanal_hatasi:
            raise self.kanal_hatasi
        return {p: i for p, i in TEST_KANALLARI.items() if p not in self.kopuk}, self.kanal_sorunlari

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
        self.assertTrue(t.endswith("Yatırım tavsiyesi değildir."))
        self.assertLessEqual(len(t), 280)
        self.assertEqual(t.count("• "), 3)

    def test_x_ana_metinde_url_yok(self):
        t = s.x_metni(RAPOR)
        self.assertNotIn("dogukanlive", t)
        self.assertNotRegex(t, r"https?://|www\.|\.com")
        self.assertEqual(s.X_YANIT, "Detaylı rapor ve grafikler: https://dogukanlive.com/bugun/")

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
        self.assertEqual(etiketler, ["#günaydın", "#gündem", "#ekonomi", "#haber"])
        for e in etiketler:
            self.assertNotRegex(s.tr_kucuk(e), r"kripto|crypto|bitcoin|btc|coin")
        self.assertIn("Günaydın Kripto", t)              # metin aynı; yalnız etiketler nötr
        self.assertIn("Yatırım tavsiyesi değildir.", t)

    def test_tiktok_etiket_filtresi(self):
        girdi = ["#günaydın", "#Kripto", "#KRİPTOPARA", "#bitcoin", "#BTC", "#altcoin", "#Crypto", "#haber"]
        self.assertEqual(s.guvenli_etiketler(girdi), ["#günaydın", "#haber"])
        with mock.patch.object(s, "TIKTOK_ETIKETLER", ["#gündem", "#kriptohaber", "#günaydınkripto"]):
            t = s.tiktok_metni(RAPOR)
        self.assertEqual([k for k in t.split() if k.startswith("#")], ["#gündem"])

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
        g = s.Buffer("k", kanallar=TEST_KANALLARI).gonderi_girdisi("instagram", "https://u/ig.mp4", "", "2026-10-08T05:30:00.000Z")
        self.assertEqual(g["channelId"], IG_ID)
        self.assertEqual(g["metadata"], {"instagram": {"type": "story", "shouldShareToFeed": False}})
        self.assertEqual(g["assets"], [{"video": {"url": "https://u/ig.mp4"}}])
        self.assertEqual((g["mode"], g["schedulingType"]), ("customScheduled", "automatic"))
        self.assertNotIn("text", g)

    def test_x_tiktok_girdisi(self):
        for p, kanal in (("x", "6ac5fcb16a5c39ccb63d823e"), ("tiktok", "6ac5fc7f6a5c39ccb63d7f09")):
            g = s.Buffer("k", kanallar=TEST_KANALLARI).gonderi_girdisi(p, "https://u/v.mp4", "metin", "D")
            self.assertEqual((g["channelId"], g["text"], g["dueAt"]), (kanal, "metin", "D"))
        self.assertNotIn("metadata", s.Buffer("k", kanallar=TEST_KANALLARI).gonderi_girdisi("tiktok", "u", "m", "D"))

    def test_x_thread_girdisi(self):
        g = s.Buffer("k", kanallar=TEST_KANALLARI).gonderi_girdisi("x", "https://u/v.mp4", "ana metin", "D")
        thread = g["metadata"]["twitter"]["thread"]
        self.assertEqual(thread, [
            {"text": "ana metin", "assets": [{"video": {"url": "https://u/v.mp4"}}]},
            {"text": "Detaylı rapor ve grafikler: https://dogukanlive.com/bugun/", "assets": []}])
        self.assertEqual(g["text"], thread[0]["text"])          # üst text = ilk parça (Buffer kuralı)
        self.assertEqual(list(g["metadata"]), ["twitter"])

    def test_buffer_istek_ve_yanit(self):
        http = SahteHttp({"data": {"createPost": {"post": {"id": "p1"}}}})
        pid = s.Buffer("GIZLI", http=http, kanallar=TEST_KANALLARI).gonderi_olustur("x", "https://u/v.mp4", "m", "D")
        self.assertEqual(pid, "p1")
        c = http.cagrilar[0]
        self.assertEqual(c["url"], "https://api.buffer.com")
        self.assertEqual(c["headers"]["Authorization"], "Bearer GIZLI")
        self.assertIn("createPost", c["json"]["query"])
        self.assertEqual(c["json"]["variables"]["input"]["channelId"], "6ac5fcb16a5c39ccb63d823e")

    def test_buffer_mutation_hatasi(self):
        http = SahteHttp({"data": {"createPost": {"message": "Invalid"}}})
        with self.assertRaises(RuntimeError):
            s.Buffer("k", http=http, kanallar=TEST_KANALLARI).gonderi_olustur("x", "u", "m", "D")

    def test_buffer_bugun_yalniz_api(self):
        http = SahteHttp({"data": {"posts": {"edges": [
            {"node": {"channelId": "6ac5fcb16a5c39ccb63d823e", "via": "api", "status": "scheduled"}},
            {"node": {"channelId": "6ac5fc7f6a5c39ccb63d7f09", "via": "network", "status": "sent"}},
            {"node": {"channelId": "eski-kanal", "via": "api", "status": "sent"}}]}}})
        self.assertEqual(s.Buffer("k", http=http, kanallar=TEST_KANALLARI).bugun_zamanlanmis("2026-10-08"), {"x"})
        http = SahteHttp({"data": {"posts": {"edges": [   # API gönderileri yanıtta via=buffer geliyor
            {"node": {"channelId": IG_ID, "via": "buffer", "status": "sent"}}]}}})
        self.assertEqual(s.Buffer("k", http=http, kanallar=TEST_KANALLARI).bugun_zamanlanmis("2026-10-08"),
                         {"instagram"})
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
            self.assertEqual(s.Buffer("GIZLI", http=http, kuru=True, kanallar=TEST_KANALLARI).gonderi_olustur("x", "u", "m", "D"), "KURU")
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
        if "channels(" in json["query"]:
            return SahteYanit({"data": {"channels": KANAL_LISTESI}})
        if "createPost" in json["query"]:
            i = g["input"]
            n = {"id": f"p{len(self.postlar) + 1}", "channelId": i["channelId"], "via": "api",
                 "dueAt": i.get("dueAt"), "status": "draft" if i.get("saveToDraft") else "scheduled"}
            self.postlar.append(n)
            return SahteYanit({"data": {"createPost": {"post": n}}})
        durumlar = g["input"]["filter"].get("status") or [n["status"] for n in self.postlar]
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
        g = s.Buffer("k", taslak=True, kanallar=TEST_KANALLARI).gonderi_girdisi("x", "https://u/v.mp4", "m", "D")
        self.assertIs(g["saveToDraft"], True)
        self.assertEqual(g["dueAt"], "D")
        self.assertNotIn("saveToDraft", s.Buffer("k", kanallar=TEST_KANALLARI).gonderi_girdisi("x", "u", "m", "D"))

    def test_taslak_ortamdan_ve_istek(self):
        api = SahteBufferApi()
        b = s.Buffer("k", http=api, taslak=s.taslak_mi({"SOSYAL_TASLAK": "1"}), kanallar=TEST_KANALLARI)
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
        for p in s.PLATFORMLAR:
            s.durum_yaz("2026-10-08", p, "gercek", self.durum)
        b = SahteBuffer(zaten=set(s.PLATFORMLAR))
        self.assertEqual(set(self._paylas(b, {"BUFFER_API_KEY": "k", "SOSYAL_TASLAK": "1"})), set(s.PLATFORMLAR))

    def test_taslaklar_gercek_calismayi_engellemez(self):
        api = SahteBufferApi()
        self._paylas(s.Buffer("k", http=api, taslak=True), {"BUFFER_API_KEY": "k", "SOSYAL_TASLAK": "1"})
        sonuc = self._paylas(s.Buffer("k", http=api), {"BUFFER_API_KEY": "k"})
        self.assertEqual(set(sonuc), {"instagram", "x", "tiktok"})
        self.assertEqual([n["status"] for n in api.postlar], ["draft"] * 3 + ["scheduled"] * 3)
        self.assertEqual(set(s.durum_oku(self.durum)["gonderiler"]), set(s.PLATFORMLAR))
        # gerçek gönderiler bundan sonra yine çift gönderiyi engeller
        self.assertEqual(self._paylas(s.Buffer("k", http=api), {"BUFFER_API_KEY": "k"}), {})

    def test_bugun_kontrolu_draft_saymaz(self):
        http = SahteHttp({"data": {"posts": {"edges": [
            {"node": {"channelId": "6ac5fcb16a5c39ccb63d823e", "via": "api", "status": "draft"}},
            {"node": {"channelId": IG_ID, "via": "buffer", "status": "error"}},
            {"node": {"channelId": "6ac5fc7f6a5c39ccb63d7f09", "via": "api", "status": "scheduled"}}]}}})
        self.assertEqual(s.Buffer("k", http=http, kanallar=TEST_KANALLARI).bugun_zamanlanmis("2026-10-08"), {"tiktok"})
        # Buffer çoklu status filtresinde boş dönüyor: süzgeç istemcide
        self.assertNotIn("status", http.cagrilar[0]["json"]["variables"]["input"]["filter"])

    def test_temizlik_test_assetlerini_kapsar(self):
        adlar = ["gunaydin-2026-09-30-test.mp4", "gunaydin-2026-09-30-test-ig.mp4",
                 "gunaydin-2026-10-07-test.mp4", "gunaydin-2026-09-30-ig-test.mp4"]
        self.assertEqual(s.silinecek_assetler(adlar, "2026-10-08"),
                         ["gunaydin-2026-09-30-test-ig.mp4", "gunaydin-2026-09-30-test.mp4"])
        self.assertEqual(s.asset_adlari("2026-10-08", test=True),
                         ("gunaydin-2026-10-08-test.mp4", "gunaydin-2026-10-08-test-ig.mp4"))


def _kanal(i, servis, ad, kopuk=False, kilitli=False):
    return {"id": i, "service": servis, "name": ad, "isDisconnected": kopuk, "isLocked": kilitli}


class KanalTestleri(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.video = os.path.join(self.d, "v.mp4")
        with open(self.video, "wb") as f:
            f.write(b"v")
        self.durum = os.path.join(self.d, "state", "sosyal-son.json")
        self.bildirim = []

    def _paylas(self, buffer):
        return s.paylas(RAPOR, self.video, ortam={"BUFFER_API_KEY": "k"}, buffer=buffer, release=SahteRelease(),
                        bildir=self.bildirim.append, simdi=datetime(2026, 10, 8, 5, 0, tzinfo=timezone.utc),
                        durum_yolu=self.durum, ig_uret=sahte_ig, erisim=lambda u: True)

    def test_servise_gore_eslesir(self):
        http = SahteHttp({"data": {"channels": KANAL_LISTESI}})
        b = s.Buffer("k", http=http)
        self.assertEqual(b.kanallari_bul(), (TEST_KANALLARI, []))
        self.assertEqual(http.cagrilar[0]["json"]["variables"]["input"]["organizationId"], s.ORG_ID)
        self.assertEqual(b.gonderi_girdisi("instagram", "u", "", "D")["channelId"], IG_ID)

    def test_birden_fazla_eslesmede_ada_ve_baglantiya_gore(self):
        liste = [_kanal("eski", "instagram", "dogukanlive", kopuk=True), _kanal("baska", "instagram", "baskahesap"),
                 _kanal("yeni", "instagram", "DogukanLive"), KANAL_LISTESI[1], KANAL_LISTESI[2]]
        kanallar, sorunlar = s.Buffer("k", http=SahteHttp({"data": {"channels": liste}})).kanallari_bul()
        self.assertEqual((kanallar["instagram"], sorunlar), ("yeni", []))

    def test_kopuk_ve_eksik_kanal_atlanir(self):
        liste = [_kanal(IG_ID, "instagram", "dogukanlive", kopuk=True), _kanal(X_ID, "twitter", "DogukanDogan",
                                                                             kilitli=True)]
        kanallar, sorunlar = s.Buffer("k", http=SahteHttp({"data": {"channels": liste}})).kanallari_bul()
        self.assertEqual(kanallar, {})
        self.assertIn("Instagram hikâye (dogukanlive) bağlantısı kopmuş, yeniden bağla", sorunlar[0])
        self.assertIn("X (DogukanDogan) kanalı kilitli", sorunlar[1])
        self.assertIn("TikTok kanalı bulunamadı", sorunlar[2])

    def test_kopuk_kanal_paylasimda_atlanir_ve_uyarilir(self):
        api = SahteBufferApi()
        liste = [_kanal(IG_ID, "instagram", "dogukanlive", kopuk=True)] + KANAL_LISTESI[1:]
        api_post = api.post

        def post(url, json=None, headers=None, timeout=None):
            if "channels(" in json["query"]:
                api.cagrilar.append(json)
                return SahteYanit({"data": {"channels": liste}})
            return api_post(url, json=json, headers=headers, timeout=timeout)
        api.post = post
        sonuc = self._paylas(s.Buffer("k", http=api))
        self.assertEqual(set(sonuc), {"x", "tiktok"})
        self.assertNotIn(IG_ID, {n["channelId"] for n in api.postlar})
        self.assertIn("Instagram hikâye (dogukanlive) bağlantısı kopmuş, yeniden bağla", self.bildirim[0])
        self.assertNotIn("instagram", s.durum_oku(self.durum)["gonderiler"])
        # posts kontrolü yalnız dinamik id'lerle
        postlar = [c for c in api.cagrilar if "posts(" in c["query"]][0]
        self.assertEqual(postlar["variables"]["input"]["filter"]["channelIds"], [X_ID, TT_ID])

    def test_kanal_sorgusu_hatasinda_hic_gondermez(self):
        b = SahteBuffer(kanal_hatasi=RuntimeError("Buffer hatası: ağ"))
        self.assertEqual(self._paylas(b), {})
        self.assertEqual(b.olusturulan, [])
        self.assertIn("Buffer kanal listesi alınamadı, hiçbir platforma gönderilmedi", self.bildirim[0])

    def test_graphql_hatasinda_hic_gondermez(self):
        http = SahteHttp({"errors": [{"message": "Actor can not access", "extensions": {"code": "FORBIDDEN"}}]})
        self.assertEqual(self._paylas(s.Buffer("k", http=http)), {})
        self.assertEqual(len(http.cagrilar), 1)
        self.assertIn("Actor can not access [FORBIDDEN]", self.bildirim[0])

    def test_tum_kanallar_kopuksa_uyarir(self):
        b = SahteBuffer(kopuk=set(s.PLATFORMLAR), kanal_sorunlari=["Buffer'da X bağlantısı kopmuş, yeniden bağla"])
        self.assertEqual(self._paylas(b), {})
        self.assertTrue(self.bildirim[0].startswith("⚠️ Sosyal medya: hiçbir platforma gönderilmedi."))
        self.assertIn("• Buffer'da X bağlantısı kopmuş", self.bildirim[0])

    def test_kuru_yer_tutucu_kanal(self):
        b = s.Buffer("k", http=SahteHttp(), kuru=True)
        with mock.patch("sys.stderr"):
            kanallar, sorunlar = b.kanallari_bul()
        self.assertEqual((set(kanallar), sorunlar), (set(s.PLATFORMLAR), []))

    def test_create_post_mutation_hatasi_acik_yazilir(self):
        http = SahteHttp({"data": {"createPost": {"__typename": "PostChannelNotFoundError",
                                                  "message": "Channel not found"}}})
        with self.assertRaisesRegex(RuntimeError, r"Buffer reddetti \(PostChannelNotFoundError\): Channel not found"):
            s.Buffer("k", http=http, kanallar=TEST_KANALLARI).gonderi_olustur("instagram", "u", "", "D")

    def test_create_post_hata_durumu(self):
        http = SahteHttp({"data": {"createPost": {"post": {"id": "p9", "status": "error",
                                                           "error": {"message": "Token expired"}}}}})
        with self.assertRaisesRegex(RuntimeError, r"hatalı işaretledi \(id p9, durum error\): Token expired"):
            s.Buffer("k", http=http, kanallar=TEST_KANALLARI).gonderi_olustur("instagram", "u", "", "D")

    def test_platform_hatasi_mesajda_net(self):
        class IgRed(SahteBuffer):
            def gonderi_olustur(self, platform, url, metin, due):
                if platform == "instagram":
                    raise RuntimeError("Buffer reddetti (PostChannelNotFoundError): yok")
                return super().gonderi_olustur(platform, url, metin, due)
        self._paylas(IgRed())
        self.assertIn("⚠️ Sorunlar:\n• Instagram hikâye zamanlanamadı: Buffer reddetti (PostChannelNotFoundError)",
                      self.bildirim[0])


class IgSureTestleri(unittest.TestCase):
    """IG hikâyesi Buffer'da ≤1 dk olmalı (9 Eki 2026: 63,8 sn reddedildi)."""

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.video = os.path.join(self.d, "v.mp4")
        with open(self.video, "wb") as f:
            f.write(b"v")
        self.durum = os.path.join(self.d, "state", "sosyal-son.json")
        self.bildirim = []

    def _paylas(self, buffer, ig_uret=sahte_ig):
        with mock.patch("sys.stdout", new_callable=__import__("io").StringIO) as out, \
                mock.patch("sys.stderr", new_callable=__import__("io").StringIO):
            sonuc = s.paylas(RAPOR, self.video, ortam={"BUFFER_API_KEY": "k"}, buffer=buffer,
                             release=SahteRelease(), bildir=self.bildirim.append,
                             simdi=datetime(2026, 10, 9, 5, 0, tzinfo=timezone.utc), durum_yolu=self.durum,
                             ig_uret=ig_uret, erisim=lambda u: True)
        return sonuc, out.getvalue()

    def test_katsayi(self):
        self.assertIsNone(s.ig_hiz_katsayisi(45.0))
        self.assertIsNone(s.ig_hiz_katsayisi(59.5))
        k = s.ig_hiz_katsayisi(63.8)
        self.assertAlmostEqual(k, 1.0814, places=3)
        self.assertLessEqual(63.8 / k, 59.5)
        self.assertAlmostEqual(s.ig_hiz_katsayisi(67.8), 67.8 / 59.0)   # sınırın hemen altı
        with self.assertRaises(s.IgCokUzun):
            s.ig_hiz_katsayisi(75.0)

    def test_hizlandir_komutu(self):
        k = s.ig_hizlandir_komutu("in.mp4", "out.mp4", 63.8 / 59.0)
        filtre = k[k.index("-filter_complex") + 1]
        self.assertEqual(filtre, "[0:v]setpts=PTS/1.0814[v];[0:a]atempo=1.0814[a]")
        self.assertEqual(k[-1], "out.mp4")
        sessiz = s.ig_hizlandir_komutu("in.mp4", "out.mp4", 1.08, ses=False)
        self.assertNotIn("atempo", sessiz[sessiz.index("-filter_complex") + 1])
        self.assertNotIn("[a]", sessiz)

    def _uret(self, sure_girdi, sure_cikti):
        """ig_varyant_uret: ffmpeg/ffprobe mock'lu. -> (komutlar, hata)."""
        komutlar = []
        sureler = iter([sure_girdi, sure_cikti])

        def calistir(k, **kw):
            komutlar.append(k)
            return SimpleNamespace(returncode=0, stdout="0\n", stderr="")
        with mock.patch.object(s, "_sure", side_effect=lambda y: next(sureler)), \
                mock.patch.object(s.subprocess, "run", side_effect=calistir), \
                mock.patch.object(s, "kucuk_hap", side_effect=lambda y: y), \
                mock.patch.object(s, "cagri_katmani", side_effect=lambda y: y), \
                mock.patch("sys.stderr", new_callable=__import__("io").StringIO):
            try:
                s.ig_varyant_uret("in.mp4", os.path.join(self.d, "out.mp4"), self.d)
                return komutlar, None
            except Exception as e:      # noqa: BLE001
                return komutlar, e

    def test_uzun_video_hizlanir(self):
        komutlar, hata = self._uret(63.8, 59.0)
        self.assertIsNone(hata)
        hiz = [k for k in komutlar if "-filter_complex" in k and "setpts" in k[k.index("-filter_complex") + 1]]
        self.assertEqual(len(hiz), 1)
        self.assertIn("atempo=1.0814", hiz[0][hiz[0].index("-filter_complex") + 1])
        self.assertEqual(hiz[0][-1], os.path.join(self.d, "out.mp4"))
        # hızlandırma, varyant (hap + son çağrı) üretildikten SONRA, orijinal süreyle
        varyant = komutlar[0]
        self.assertIn("enable='gte(t,60.80)'", varyant[varyant.index("-filter_complex") + 1])

    def test_kisa_video_hizlanmaz(self):
        komutlar, hata = self._uret(45.0, None)
        self.assertIsNone(hata)
        self.assertEqual(len(komutlar), 1)
        self.assertEqual(komutlar[0][-1], os.path.join(self.d, "out.mp4"))

    def test_hizlanmis_hala_uzunsa_hata(self):
        _, hata = self._uret(63.8, 60.2)
        self.assertIsInstance(hata, RuntimeError)

    def test_cok_uzun_ig_atlanir_uyari(self):
        def uzun(girdi, cikti, calisma):
            raise s.IgCokUzun(75.0)
        b = SahteBuffer()
        sonuc, out = self._paylas(b, ig_uret=uzun)
        self.assertEqual(set(sonuc), {"x", "tiktok"})
        self.assertNotIn("instagram", [p for p, *_ in b.olusturulan])
        self.assertIn("IG hikâyesi için video çok uzun: 75.0 sn", self.bildirim[0])
        self.assertIn("::warning::", out)
        self.assertIn("video çok uzun", out)

    def test_mutation_hatasi_net_uyari(self):
        http = SahteHttp({"data": {"createPost": {
            "__typename": "InvalidInputError",
            "message": "Invalid post: Video must be no longer than 1 minute for Instagram Stories."}}})
        with self.assertRaises(s.BufferReddi) as c:
            s.Buffer("k", http=http, kanallar=TEST_KANALLARI).gonderi_olustur("instagram", "u", "", "D")
        self.assertEqual(c.exception.tur, "InvalidInputError")

        class Reddeden(SahteBuffer):
            def gonderi_olustur(self, platform, url, metin, due):
                if platform == "instagram":
                    raise s.BufferReddi("InvalidInputError", "Invalid post: Video must be no longer than "
                                                             "1 minute for Instagram Stories.")
                return super().gonderi_olustur(platform, url, metin, due)
        sonuc, out = self._paylas(Reddeden())
        self.assertEqual(set(sonuc), {"x", "tiktok"})
        beklenen = ("Instagram hikâye GÖNDERİLEMEDİ: Invalid post: Video must be no longer than "
                    "1 minute for Instagram Stories.")
        self.assertTrue(self.bildirim[0].startswith("⚠️ " + beklenen))
        self.assertIn("::warning::[sosyal] " + beklenen, out)


class IgGercekFfmpegTesti(unittest.TestCase):
    """Gerçek ffmpeg ile sentetik 62 sn video (ffmpeg yoksa atlanır)."""

    @unittest.skipUnless(__import__("shutil").which("ffmpeg") and __import__("shutil").which("ffprobe")
                         and os.environ.get("IG_FFMPEG_TESTI") == "1",
                         "IG_FFMPEG_TESTI=1 ve ffmpeg gerekli")
    def test_62_sn_hizlanir(self):
        import subprocess
        d = tempfile.mkdtemp()
        girdi, cikti = os.path.join(d, "in.mp4"), os.path.join(d, "out.mp4")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=s=1080x1920:r=30:d=62",
                        "-f", "lavfi", "-i", "sine=f=440:d=62", "-c:v", "libx264", "-preset", "ultrafast",
                        "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", girdi], check=True)
        s.ig_varyant_uret(girdi, cikti, d)
        sure = s._sure(cikti)
        self.assertLessEqual(sure, s.IG_MAX_SN)
        self.assertGreater(sure, 58.5)
        self.assertTrue(s._ses_var_mi(cikti))


class IgFragmanTestleri(unittest.TestCase):
    """IG hikâyesine ~20 sn fragman; üretilemezse eski tam video varyantı."""

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.video = os.path.join(self.d, "v.mp4")
        with open(self.video, "wb") as f:
            f.write(b"v")
        self.cagri = []

    def fragman(self, rapor, cikti, calisma):
        self.cagri.append(("fragman", rapor["id"], cikti))
        with open(cikti, "wb") as f:
            f.write(b"fragman")
        return cikti

    def bozuk_fragman(self, rapor, cikti, calisma):
        self.cagri.append(("fragman", rapor["id"], cikti))
        raise RuntimeError("ElevenLabs HTTP 401")

    def eski(self, girdi, cikti, calisma):
        self.cagri.append(("eski", girdi, cikti))
        with open(cikti, "wb") as f:
            f.write(b"eski")
        return cikti

    def _hikaye(self, fragman, ortam=None):
        notlar = []
        cikti = os.path.join(self.d, "ig.mp4")
        with mock.patch("sys.stderr", new_callable=__import__("io").StringIO):
            yol = s.ig_hikaye_uret(RAPOR, self.video, cikti, self.d, fragman=fragman, eski=self.eski,
                                   ortam=ortam or {}, notlar=notlar)
        with open(yol, "rb") as f:
            return f.read(), notlar

    def test_fragman_secilir(self):
        icerik, notlar = self._hikaye(self.fragman)
        self.assertEqual(icerik, b"fragman")
        self.assertEqual([c[0] for c in self.cagri], ["fragman"])
        self.assertEqual(notlar, [])

    def test_fragman_hatasinda_eski_varyant(self):
        icerik, notlar = self._hikaye(self.bozuk_fragman)
        self.assertEqual(icerik, b"eski")
        self.assertEqual([c[0] for c in self.cagri], ["fragman", "eski"])
        self.assertEqual(self.cagri[1][1], self.video)                  # eski varyant tam videodan
        self.assertIn("IG fragmanı üretilemedi", notlar[0])
        self.assertIn("ElevenLabs HTTP 401", notlar[0])

    def test_bayrakla_kapatilir(self):
        icerik, _ = self._hikaye(self.fragman, ortam={"IG_FRAGMAN": "kapali"})
        self.assertEqual(icerik, b"eski")
        self.assertEqual([c[0] for c in self.cagri], ["eski"])

    def test_eski_varyant_ig_cok_uzun_korunur(self):
        def uzun(girdi, cikti, calisma):
            raise s.IgCokUzun(75.0)
        with mock.patch("sys.stderr", new_callable=__import__("io").StringIO):
            with self.assertRaises(s.IgCokUzun):
                s.ig_hikaye_uret(RAPOR, self.video, os.path.join(self.d, "ig.mp4"), self.d,
                                 fragman=self.bozuk_fragman, eski=uzun, ortam={})

    def _paylas(self, fragman):
        b, r = SahteBuffer(), SahteRelease()
        bildirim = []
        with mock.patch.object(s, "ig_fragman_uret", side_effect=fragman), \
                mock.patch.object(s, "ig_varyant_uret", side_effect=self.eski), \
                mock.patch("sys.stdout", new_callable=__import__("io").StringIO), \
                mock.patch("sys.stderr", new_callable=__import__("io").StringIO):
            sonuc = s.paylas(RAPOR, self.video, ortam={"BUFFER_API_KEY": "k"}, buffer=b, release=r,
                             bildir=bildirim.append, simdi=datetime(2026, 10, 9, 5, 0, tzinfo=timezone.utc),
                             durum_yolu=os.path.join(self.d, "state", "sosyal-son.json"),
                             erisim=lambda u: True)
        return sonuc, r, bildirim

    def test_paylas_varsayilan_ig_fragman(self):
        sonuc, r, _ = self._paylas(self.fragman)
        self.assertEqual(set(sonuc), {"instagram", "x", "tiktok"})
        self.assertEqual([c[0] for c in self.cagri], ["fragman"])
        self.assertTrue(self.cagri[0][2].endswith("gunaydin-2026-10-08-ig.mp4"))   # asset adı aynı
        self.assertIn("gunaydin-2026-10-08.mp4", r.yuklenen)                       # X/TikTok tam video

    def test_paylas_fragman_hatasinda_eski_ve_uyari(self):
        sonuc, _, bildirim = self._paylas(self.bozuk_fragman)
        self.assertEqual(set(sonuc), {"instagram", "x", "tiktok"})
        self.assertEqual([c[0] for c in self.cagri], ["fragman", "eski"])
        self.assertIn("IG fragmanı üretilemedi", bildirim[0])

    def test_x_tiktok_ig_fragmanindan_once_zamanlanir(self):
        b = SahteBuffer()
        gorulen = []

        def yavas_fragman(rapor, cikti, calisma):
            gorulen.append([p for p, *_ in b.olusturulan])
            raise s.FragmanZamanAsimi("IG fragmanı 240 sn içinde bitmedi, durduruldu")
        bildirim = []
        with mock.patch.object(s, "ig_fragman_uret", side_effect=yavas_fragman), \
                mock.patch.object(s, "ig_varyant_uret", side_effect=self.eski), \
                mock.patch("sys.stdout", new_callable=__import__("io").StringIO), \
                mock.patch("sys.stderr", new_callable=__import__("io").StringIO):
            sonuc = s.paylas(RAPOR, self.video, ortam={"BUFFER_API_KEY": "k"}, buffer=b, release=SahteRelease(),
                             bildir=bildirim.append, simdi=datetime(2026, 10, 9, 5, 0, tzinfo=timezone.utc),
                             durum_yolu=os.path.join(self.d, "state", "sosyal-son.json"), erisim=lambda u: True)
        self.assertEqual(gorulen, [["x", "tiktok"]])                    # fragman başlarken X/TikTok hazır
        self.assertEqual([p for p, *_ in b.olusturulan], ["x", "tiktok", "instagram"])
        self.assertEqual(list(sonuc), ["instagram", "x", "tiktok"])
        self.assertIn("240 sn içinde bitmedi", bildirim[0])              # admin uyarısı, eski varyant gitti

    def test_ig_tamamen_coker_x_tiktok_etkilenmez(self):
        def bozuk(girdi, cikti, calisma):
            raise RuntimeError("ffmpeg yok")
        b = SahteBuffer()
        bildirim = []
        with mock.patch("sys.stdout", new_callable=__import__("io").StringIO), \
                mock.patch("sys.stderr", new_callable=__import__("io").StringIO):
            sonuc = s.paylas(RAPOR, self.video, ortam={"BUFFER_API_KEY": "k"}, buffer=b, release=SahteRelease(),
                             bildir=bildirim.append, simdi=datetime(2026, 10, 9, 5, 0, tzinfo=timezone.utc),
                             durum_yolu=os.path.join(self.d, "state", "sosyal-son.json"),
                             ig_uret=bozuk, erisim=lambda u: True)
        self.assertEqual(set(sonuc), {"x", "tiktok"})
        self.assertIn("Instagram hikâye GÖNDERİLEMEDİ: ffmpeg yok", bildirim[0])

    def test_fragman_alt_sureci_zaman_siniri(self):
        class Takilan:
            pid = 0

            def wait(self, timeout=None):
                raise s.subprocess.TimeoutExpired("python", timeout)
        komutlar = []

        def popen(k, **kw):
            komutlar.append((k, kw))
            return Takilan()
        with mock.patch("video.calistir._oldur") as oldur:
            with self.assertRaises(s.FragmanZamanAsimi):
                s.ig_fragman_uret(RAPOR, os.path.join(self.d, "ig.mp4"), self.d, sure_siniri=5, popen=popen)
        oldur.assert_called_once()
        k, kw = komutlar[0]
        self.assertEqual(k[1:3], ["-m", "video.fragman"])
        self.assertTrue(kw.get("start_new_session") or os.name == "nt")
        with open(os.path.join(self.d, "fragman-rapor.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["id"], RAPOR["id"])

    def test_fragman_alt_sureci_hata_kodu(self):
        class Biten:
            pid = 0

            def wait(self, timeout=None):
                return 1
        with self.assertRaises(RuntimeError):
            s.ig_fragman_uret(RAPOR, os.path.join(self.d, "ig.mp4"), self.d, popen=lambda k, **kw: Biten())
        self.assertEqual(s.IG_FRAGMAN_SURE_SN, 240)


if __name__ == "__main__":
    unittest.main()
