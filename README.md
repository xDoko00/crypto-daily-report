# 🌅 Günaydın Kripto — Telegram Sabah Botu

> Her sabah **08:00'de**, sen uyanmadan, piyasayı **1 dakikada** anlatan arkadaşın.

Bu bir "otomatik rapor" değil. Uyandığında tam ihtiyacın olan bilgiyi — gereksiz hiçbir şey olmadan — Telegram kanalına koyan bir sabah rutini. Bilgisayarın **kapalıyken de çalışır** (GitHub'ın ücretsiz sunucularında koşar).

> ⚠️ **Yatırım tavsiyesi değildir.** Bilgilendirme amaçlıdır; al/sat önerisi vermez.

---

## ✨ Her sabah kanalına ne düşer?

- 📊 **Kart + 60 saniyelik brief** (tek mesaj) — piyasa havası, BTC/ETH, **"piyasa neden hareket etti"**, günün kritik saatleri ve ana risk. Bir bakışta, bir dakikada okunur. Kartı **Instagram/WhatsApp'ta paylaşabilirsin**.
- 🎙️ **~45 saniyelik sesli özet** — yolda ya da hazırlanırken dinle. Ücretsiz Türkçe doğal ses.
- ⏮️ **Dünden hesap** — dün "dikkat" dediğimiz olayların bugünkü **sonucunu** gösterir. Sistem dünü hatırlar.
- 📄 **Detay** — piyasa tablosu, günün en önemli 3 gelişmesi (kaynak linkli), Türkiye mevzuatı, bugünün ekonomik takvimi (TSİ), riskler.

**Sayılar uydurma değildir:** Fiyat, dominans, hacim ve Fear & Greed doğrudan ücretsiz API'lerden gelir — yapay zekâya asla uydurtulmaz. Yalnızca haber/analiz kısmını Claude, canlı web araması yaparak yazar.

---

## 🔧 Perde arkası (4 adım)

1. **Sabit veriler** — CoinGecko + Alternative.me'den fiyatlar, dominans, hacim, Fear & Greed (LLM yok → halüsinasyon yok).
2. **Haber & analiz** — Headless Claude Code web araması yaparak son 24 saati **şemalı JSON** olarak üretir. (Claude aboneliğinden düşer, **ek API ücreti yok**.)
3. **Kanonik rapor** — İkisi birleşip `reports/` altına tek bir doğrulanmış JSON olarak yazılır.
4. **Gönderim** — Telegram mesajı, kart ve sesli özet **hep aynı JSON'dan** üretilir; saniyesi saniyesine **08:00'de** gider.

Kart görseli (Pillow) ve sesli özet (edge-tts) de dahil **her şey ücretsiz** — hiçbir ödemeli servis yok.

---

## 📦 Kanonik rapor: `reports/`

Rapor artık yalnızca Telegram'a gidip kaybolmuyor. Her gün şemaya uyan tek bir JSON üretiliyor ve repoda kalıyor:

```
reports/latest.json              # en son rapor — web sitesinin okuduğu dosya
reports/2026/08/2026-08-19.json  # tarihli arşiv (kalıcı)
```

Telegram mesajı, paylaşım kartı ve sesli özet bu dosyadan **türetilir** — yani dört kanal arasında tutarsızlık olamaz. Şemanın kendisi `schema/daily-report.schema.json` dosyasında; web tarafı da aynı şemayla doğrulama yapabilir.

**Şemanın dayattığı kurallar:**

| Kural | Nasıl zorlanıyor |
|---|---|
| Fiyat/dominans/hacim/F&G'yi LLM üretemez | Bu alanlar şemada modelin çıktısında **yok**; Python API'den doldurur |
| Her gündem maddesinde kaynak zorunlu | `source` alanı `required`; kaynaksız madde doğrulamadan geçmez |
| Kaynak `https://` olmalı | URL deseni; `http`/`javascript:` reddedilir |
| İzleme parametreleri yayınlanmaz | `utm_*`, `fbclid` vb. yazmadan önce temizlenir |
| Aynı gün iki kez üretim ikinci kayıt açmaz | Aynı `id`, `publishedAt` korunur, yalnız `updatedAt` tazelenir |
| "Türkiye'de gelişme var" deyip madde vermemek | Çelişki doğrulamada yakalanır |

Model şemayı tutturamazsa hata mesajı kendisine geri verilir ve düzeltmesi istenir; üç denemede olmazsa rapor gönderilmez ve admin'e bildirim gider. **Bozuk rapor asla diske yazılmaz.**

> Görsel ve ses dosyaları (PNG/OGG) bilerek repoda tutulmuyor — depo şişmesin diye yalnız Telegram'a gidiyorlar. JSON'daki `assets.cardUrl` / `assets.audioUrl` alanları, ileride obje depolama eklendiğinde dolacak.

---

## 🤖 En kolay kurulum: bırak Claude Code yapsın

Teknik bilgin yoksa hiç uğraşma:

1. Bu repoyu indir (yeşil **Code → Download ZIP**) veya klonla.
2. Klasörde **[Claude Code](https://claude.com/claude-code)**'u aç.
3. Şunu yaz: **"Bu repoyu kurmak istiyorum, beni baştan sona yönlendir."**

Claude Code, repodaki `CLAUDE.md` talimatlarını okuyup seni adım adım kurar: Telegram botu, kanal, chat_id bulma, token'lar ve GitHub'ı **senin yerine** halleder. Sana kalan sadece birkaç token yapıştırmak ve bir kez tarayıcı girişi.

---

## ⚡ Hızlı kurulum (manuel)

Zor kısımları (chat_id bulma, test, GitHub reposu + secret'lar) **`setup.py` sihirbazı** yapıyor. Sana kalan:

### 1) Telegram botu oluştur
**@BotFather** → `/newbot` → isim ver → **token'ı kopyala** (`123456:ABC-...`).

### 2) Kanalı hazırla
- Raporun gideceği **kanalı** oluştur.
- Kanal → **Yöneticiler → Yönetici Ekle** → botunu ekle ("Mesaj Gönderme" yetkisi yeter).
- Kanala **bir mesaj at** (bot kanalı görebilsin) ve **kendi botuna** bir kez **/start** yaz.

### 3) Claude token'ı üret
```bash
claude setup-token
```
Çıkan token'ı kopyala. (Pro/Max aboneliği yeter, ek ücret yok. Token ~1 yıl geçerli.)

### 4) Sihirbazı çalıştır — gerisi otomatik
```bash
pip install -r requirements.txt
python setup.py
```
Sihirbaz senden **iki token** (bot + Claude) ister, kalan her şeyi kendi yapar:
- ✅ Kanalın ve senin chat_id'ni **otomatik bulur**
- ✅ **Test mesajı** atıp çalıştığını kanıtlar
- ✅ `.env` dosyasını yazar
- ✅ **GitHub girişini başlatır** + repoyu oluşturur + dosyaları yükler + **4 secret'ı ekler**
- ✅ **Sızıntı taraması** yapıp repoyu **public** oluşturur — saatinde teslim için gerekli (aşağıda anlatılıyor). Tarama temiz değilse otomatik **private**'a düşer ve seni uyarır.

**Bitti.** Artık her sabah 08:00'de kanala tam rapor gelir. 🎉

---

## Test etme

**Yerel:**
```bash
python report.py --test    # rapor kanala DEĞİL, sadece sana (admin) gider
```

**GitHub üzerinden:** Repo → **Actions → Günlük Kripto Raporu → Run workflow** → **mode**: `test` (sadece sana), `both` (sana + kanala) ya da `normal` (kanala). `deliver_at` ile belirli bir saate de gönderebilirsin.

---

## Manuel GitHub kurulumu (sihirbaz kullanmazsan)

1. [github.com](https://github.com)'da yeni repo oluştur.
2. Dosyaları yükle (`git add . && git commit -m "kurulum" && git push`).
3. Repo → **Settings → Secrets and variables → Actions**. Şu 4 secret'ı ekle:

   | Secret | Değer |
   |---|---|
   | `CLAUDE_CODE_OAUTH_TOKEN` | `claude setup-token` çıktısı |
   | `TELEGRAM_BOT_TOKEN` | BotFather token'ı |
   | `TELEGRAM_CHAT_ID` | Kanal id (`@kanal` veya `-100...`) |
   | `TELEGRAM_ADMIN_CHAT_ID` | Senin özel chat id'in |

---

## Sık sorulanlar

**Rapor tam 08:00'de mi gelir?** Evet — ve bunun için özel bir düzenek var.

GitHub'ın ücretsiz zamanlayıcısı "best-effort"tur: alarmı bazen dakikalarca, nadiren **saatlerce** geç çalar. Tek alarma güvenmek bu yüzden yetmiyor. Çözüm iki katmanlı:

1. **Beş nöbetçi.** Workflow 04:07 / 07:10 / 07:25 / 07:40 / 07:55 TSİ'de ayrı ayrı uyanmayı dener. Hangisi vaktinde uyanırsa **tam 08:00'e kadar bekler**, öyle gönderir (`DELIVER_AT_TR`).
2. **Çift rapor koruması.** Rapor gidince `state/takip.json`'a günün tarihi yazılır. Geç uyanan nöbetçiler bunu görüp saniyeler içinde çıkar — ikinci rapor gitmez.

**Repo neden public?** Public repolarda GitHub Actions süresi ücretsiz ve sınırsızdır. Bu sayede en erken nöbetçi 04:07'de uyanıp saati bekleyebiliyor — yani GitHub **4 saat** geç kalsa bile rapor yine 08:00'de gider. Private repoda aylık 2.000 dakika sınırı olduğu için bu kadar bekleyemeyiz; orada erken nöbetçi otomatik atlanır ve pay ~50 dakikaya iner.

**Public olması güvenli mi?** Evet. Token'ların **kodda durmaz** — GitHub Secrets'ta şifreli tutulur ve Actions loglarında maskelenir. `.env` dosyası `.gitignore`'dadır, hiç yüklenmez. Ayrıca `setup.py` repoyu public yapmadan önce **sızıntı taraması** çalıştırır: `.env` takip ediliyor mu, dosyalarda veya **git geçmişinde** gerçek token kalıbı var mı diye bakar. En ufak şüphede repoyu public yapmaz, private oluşturur ve neyi bulduğunu sana söyler.

Saati değiştirmek için workflow'daki `DELIVER_AT_TR` değerini (ve istersen cron satırlarını) güncelle.

**Kart/ses gelmezse?** İkisi de "best-effort"; biri üretilemezse rapor yine gider. Rapor üretimi hata verirse sistem birkaç kez dener, yine olmazsa sana hata bildirimi gelir.

**Ücret?** Yok. GitHub Actions ücretsiz katmanı, kripto API'leri ücretsiz, kart/ses ücretsiz kütüphaneler, rapor Claude aboneliğinden düşer.

---

## Dosya yapısı

```
.
├── report.py            # Ana akış: veri → JSON rapor → kart + brief + ses + detay gönderimi
├── sema.py              # Kanonik rapor şeması, doğrulama, reports/ yazma
├── render.py            # JSON → Telegram HTML / sesli özet metni / kart verisi
├── kart.py              # Paylaşılabilir sabah kartı (Pillow)
├── ses.py               # 45 sn sesli özet (edge-tts + ffmpeg)
├── setup.py             # Kurulum sihirbazı (chat_id, test, .env, GitHub)
├── requirements.txt     # requests, Pillow, edge-tts, tzdata, jsonschema
├── reports/             # Kanonik raporlar: latest.json + YYYY/MM/ arşivi
├── schema/              # daily-report.schema.json (web tarafı da kullanabilir)
├── state/takip.json     # Nöbetçi kilidi + "dünden hesap" yedeği
├── .github/workflows/   # daily-report.yml (08:00 TSİ) + tests.yml
├── CLAUDE.md            # Claude Code'un otomatik kurulum rehberi
├── test_report.py       # Birim testler
├── LICENSE              # MIT
└── .env.example
```

---

## 🎁 Ücretsiz & topluluk için

Bu araç **DogukanLive** tarafından hazırlanıp topluluğa **ücretsiz** sunulmuştur. Satılık değildir — dilediğin gibi kur, kullan, kendine göre değiştir. Beğendiysen paylaş, bir arkadaşının sabahını da güzelleştir. ☕

<sub>Made with ❤️ by <b>DogukanLive</b> · <a href="https://youtube.com/@DogukanLive">youtube.com/@DogukanLive</a> · MIT License</sub>
