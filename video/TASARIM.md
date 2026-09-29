> **Depo notu (crypto-daily-report/video):** Bu belge ~/gunaydin-video'daki onaylı tasarımın kopyasıdır. Depoda yollar `video/` altındadır; b-roll 720x1280 CRF 23 sessiz kopyalar (`haric` klipler dahil edilmedi), döndürme durumu `state/video-son-kullanim.json`. Higgsfield üretimi ve `--broll-uret` burada yok. Günlük çalıştırma: `report.py` → `video.calistir` (VIDEO_OZET=1, VIDEO_HEDEF=admin).

# Günaydın Kripto — dikey kısa video tasarımı

Yüzsüz, 1080x1920, ~60 sn, sabah haber özeti. Kaynak: `crypto-daily-report`
kanonik JSON'u (`reports/latest.json`). Yayın/gönderim yok, yerel mp4 üretir.

## Çalıştırma

```bash
cd ~/gunaydin-video
python3 gunaydin.py --sadece-metin                 # senaryoyu gör (API yok)
env -u ELEVENLABS_API_KEY python3 gunaydin.py      # güncel raporu GitHub raw'dan okur
python3 gunaydin.py --rapor ~/crypto-daily-report/reports/latest.json --broll-uret
python3 -m unittest test_senaryo
```

Çıktı: `cikti/gunaydin-<tarih>.mp4`, `cikti/kareler/*.jpg` (sahne başı bir kare),
`cikti/metin.txt`; ara dosyalar ve maliyet özeti `calisma/<tarih>/ozet.json`.

| Dosya | Görev |
|---|---|
| `senaryo.py` | Rapor → sahneler + etiketli konuşma metni (kurallı, LLM yok). Tüm değiştirilebilir metinler dosyanın başında. |
| `kutuphane.py` | B-roll kütüphanesi: katalog, tema içi döndürme (`sec`). `kutuphane_uret.py`: toplu üretim. |
| `servisler.py` | ElevenLabs `/with-timestamps` (+ Scribe yedeği), Higgsfield Kling 3.0 std (curl). |
| `cizim.py` | Pillow grafikleri: kartlar, gösterge, altyazı, ilerleme çubuğu. Renkler/güvenli alan burada. |
| `gunaydin.py` | Boru hattı: ses → kelime zamanları → sahne zamanları → b-roll → miks → kare kare kodlama. |

## Sahne akışı (29 Eylül 2026 örneği)

| # | Sahne | Süre | İçerik | B-roll |
|---|---|---|---|---|
| 1 | Kanca | 0–8,2 | Tarih çipi + "PİYASA TEMKİNLİ" + "Saldırı gölgesi, enflasyon bekleyişi" | sabah şehir |
| 2 | Fiyat | 8,2–15,4 | BTC/ETH/SOL/BNB/XRP fiyat + %24s (yeşil/kırmızı ▲▼), toplam piyasa, BTC dominansı | altın parçacıklar |
| 3 | Duygu | 15,4–20,0 | Korku-açgözlülük göstergesi (ibre animasyonlu), dün/geçen hafta | altın parçacıklar |
| 4 | Haber 1 | 20,0–28,2 | KRİTİK çip, "$387,5 milyon" vurgusu, başlık, kaynak | sunucu odası |
| 5 | Haber 2 | 28,2–32,8 | ÖNEMLİ çip, HYPE kilit açılımı | kasa kapısı |
| 6 | Ana risk | 32,8–41,4 | Kırmızı şeritli risk kartı | fırtına bulutları |
| 7 | Takip et | 41,4–51,2 | Saat çipli 3 madde (saatsiz: "GÜN İÇİ") | masa/takvim |
| 8 | Kapanış | 51,2–59,7 | Uyarı + dogukanlive.com + Akademi + "Bay bay." | sabah şehir (ters yarı) |

Sahne sınırları seste o sahnenin ilk kelimesinden 0,12 sn önce; kesme sesle senkron.

## Kararlar ve gerekçeler

- **Kanca ilk kareden görünür.** Kanca öğeleri animasyonsuz; 0. kare aynı zamanda
  kapak (thumbnail). Kısa videoda izleyici ilk 1-2 sn'de kalır ya da kaydırır; tarih +
  günün tek cümlelik yargısı "bu bugünün özeti" sinyalini hemen verir. Başlık
  kurallı: `Piyasa <mood>` + `why` metnindeki temalar (hack → saldırı gölgesi, PCE/CPI →
  enflasyon bekleyişi, Fed, ETF, kilit açılımı…).
- **Sahne başı tek fikir, 4-8 sn.** Uzun paragraf yok; her kart tek bilgi taşır.
  Üstte hikâye tarzı bölümlü ilerleme çubuğu: kalan süreyi gösterir, bitirmeyi özendirir.
- **Kelime kelime altyazı.** Sesin çoğu sessiz izlendiği için şart. En fazla 3 kelime /
  16 harf, noktalamada kırılır; o an söylenen kelime sarı (aksan), diğerleri beyaz,
  kalın büyük harf (TR büyük harf dönüşümü: i→İ), siyah kontur + gölge. Zamanlama
  ElevenLabs karakter hizalamasından (difflib ile metne eşlenir; yoksa Scribe STT).
- **Güvenli alan.** İçerik x 64–900 (sağ 180 px Shorts/Reels/TikTok butonlarına boş),
  üst 220 px ilerleme + etiket, alt %20 (y>1536) tamamen boş; altyazı merkezi y=1430.
- **Rakam kuralı.** Tüm sayılar JSON'dan birebir; ekranda TR biçimi (`$83.589`,
  `$2.681,71`, `+%0,46`, `−%0,61`, `$2,87 trilyon`), seste konuşma diliyle yuvarlanmış
  (`83 bin 600 dolar`) — `ses_klon.py`'nin yardımcıları yeniden kullanılır.
- **Doğal konuşma.** `ses_klon.py` metin üretici mantığı video için uyarlandı: kısa
  cümleler, haber başlıkları ayrı cümle, özetin `;` sonrası kısa yarısı ek cümle.
  İngilizce terimler Türkçeleştirilir (unlock → kilit açılımı, hack(er) → saldırı/
  saldırgan, JOLTS → açık iş pozisyonları). Kesme işaretli yabancı adlar baş isimle
  çözülür (Bitget'teki → Bitget borsasındaki, HYPE'ta → Hype tokeninde); tarihler
  göreli (29 Eylül'de → bugün). Aynı özel adı paylaşan ikinci haber atlanır (tekrar yok).
  Süre için ses %4 hızlandırılır (`atempo`, perde korunur).
- **Marka.** dogukanlive.com CSS değişkenleri: zemin `#0b0b0c`, metin `#ececec`,
  soluk `#8f8f99`, aksan `#f0b90b`, yükseliş `#2ee6a0`, düşüş `#ff5c6c`; font Archivo
  (siteyle aynı, değişken ağırlık). Küçük üst etiket "DOĞUKAN DOĞAN · GÜNAYDIN KRİPTO".
- **B-roll.** Higgsfield Kling 3.0 std, 9:16, 5 sn (720x1280); promptlarda insan/yüz/el/
  yazı/logo/rakam yok, ekranlar "abstract glowing charts, unreadable"; koyu zemin + amber
  vurgu (düşüş/hack'te kırmızı). Klipler **tema kütüphanesi**: `broll/<tema>/<tema>-NN.mp4`,
  katalog `broll/kutuphane.json` (tema, dosya, prompt, request_id, tarih). Sahne → tema:
  kanca `kanca-sabah` (birleşik: `sabah-sehir` ∪ `istanbul-sabah`, harmanlanıp günden güne
  dönüşümlü, `kutuphane.BIRLESIK`); fiyat+duygu BTC 24s yönüne göre `piyasa-yukselis`/`piyasa-dusus`/
  `sakin-yatay` (eşik `YATAY_ESIGI`); haber anahtar kelimeyle (`TEMA_ANAHTARLARI`:
  hack-guvenlik, kilit, etf-kurumsal, fed-makro, jeopolitik, regulasyon-hukuk, stablecoin-dolar,
  bitcoin-madencilik, yapay-zeka-teknoloji, borsa-islem-masasi, ethereum-defi, altcoin-cesitlilik; yedek `sakin-yatay`); risk
  `piyasa-dusus`; takip `takvim-veri`; kapanış `kapanis`. **Döndürme:** `kutuphane.sec`
  tema içinde sıradaki klibi verir, son kullanılanı `broll/son-kullanim.json`'da tutar →
  art arda günlerde aynı klip gelmez (temada ≥2 klip varsa); aynı gün yeniden çalıştırma
  aynı seçimi verir. Toplu üretim `kutuphane_uret.py` (4 paralel, sert tavan, gönderim
  sayacı POST'tan önce `calisma/kutuphane-uretim.json`'a yazılır). Döngü ileri+geri
  (ping-pong) birleştirildiği için dikişsiz; aynı klip ikinci kez ters yarıdan başlar.
  %50 karartma, üst ve altyazı bandında daha koyu; sahneler arası 5 karelik çapraz geçiş;
  kartların altında yarı saydam koyu zemin.
- **Şeffaflık notu: YOK (Doğukan'ın tercihi, 29 Eyl 2026).** Önceki sürümde kapanışta
  "yapay zekâ ile üretildi" notu vardı; Doğukan'ın isteğiyle hem ekrandan hem konuşmadan
  kaldırıldı (`senaryo.SEFFAFLIK_NOTU = ""`). Gerekirse metni yazmak yeterli. Platformların
  "sentetik içerik" kutusu yükleme sırasında ayrıca değerlendirilir.
- **Adres okunuşu.** Seste fonetik "Doğukan Live nokta com" (`SITE_KONUSMA`); ekranda ve
  altyazıda bu kelimeler tek `dogukanlive.com` olarak birleşir (`adres_birlestir`).
- **Ses.** Konuşma -14 LUFS'a (tek geçişli ölçüm + doğrusal kazanç), müzik -36 LUFS
  (~22 LU altında), limiter -1,5 dBTP. Müzik: ffmpeg `aevalsrc` ile yerelde
  sentezlenen La majör add9 pad (yavaş LFO, alçak geçiren, hafif eko) — telif riski sıfır.
- **Maliyet koruması.** Seslendirme `calisma/<tarih>/tts.json`'da önbellekli: metin
  değişirse `--ses-yeniden` verilmeden ElevenLabs çağrılmaz. Higgsfield istek kimliği
  gönderir göndermez kaydedilir (`--broll-uret`: `broll/<tema>/<ad>.json`); süreç çökerse ödenmiş klip
  yeniden gönderilmez. Anahtarlar loglanmaz; Higgsfield anahtarı curl'e 0600 geçici
  başlık dosyasıyla verilir (süreç listesinde görünmez).

## Bilinen kusurlar

- Kanca 8,2 sn (hedef 4-8): selamlama + tarih + başlık doğal hızda bu kadar sürüyor.
- Haber başlıkları ekranda raporun yazılı hâliyle (`HYPE'ta`, `hackerinin`); ses ve
  altyazı Türkçeleştirilmiş hâli söyler — ikisi birebir aynı değil.
- Tema anahtar kelimeleri basit alt dize eşlemesi; beklenmedik haberde yedek tema gelir.
- Kling bazen kadrajı 90° yan döndürüyor (dikey promptta bile). Yan dönük/kusurlu klipler katalogda
  `"haric": true` (dosya duruyor, seçime girmez): `kapanis-02`, `istanbul-sabah-03`, `jeopolitik-02`
  (yan dönük), `takvim-veri-03` (saatte okunur rakam). `yapay-zeka-teknoloji` tek klip.
- `regulasyon-hukuk-01` cephesinde bulanık yazıt benzeri oyma, `stablecoin-dolar-02` külçelerinde
  küçük damga izleri var (okunamaz; %50 karartma altında belirsiz).
- Render ~50 sn (Pillow, kare kare); 8 çekirdekte sorun değil.
