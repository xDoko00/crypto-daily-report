# 📊 Günlük Kripto Raporu → Telegram Botu

Her sabah **07:00 (Türkiye saati)** otomatik olarak güncel kripto piyasa raporu üretip Telegram kanalına gönderen sistem. Bilgisayarın **kapalıyken de çalışır**, çünkü GitHub'ın ücretsiz sunucularında (GitHub Actions) zamanlanmış görev olarak koşar.

## Nasıl çalışır? (3 adım)

1. **Sabit veriler** — BTC, ETH, SOL, BNB, XRP fiyatları, piyasa değeri, hacim, dominans ve Fear & Greed endeksi doğrudan ücretsiz API'lerden çekilir. Bu sayılar yapay zekâya **uydurtulmaz**, olduğu gibi rapora girer.
2. **Haber & analiz** — Headless Claude Code web araması yaparak son 24 saatin gelişmelerini araştırır ve Türkçe raporu yazar. (Claude aboneliğinden düşer, **ek API ücreti yok**.)
3. **Gönderim** — Rapor Telegram'a HTML formatında, 4096 karakter limitine uyacak şekilde bölünerek gönderilir.

> ⚠️ **Yatırım tavsiyesi değildir.** Bu bot bilgilendirme amaçlıdır; al/sat önerisi vermez.

---

## 🤖 En kolay yol: kurulumu Claude Code yapsın

Teknik bilgin yoksa hiç uğraşma. Şunu yap:

1. Bu repoyu indir/klonla (yeşil **Code** → **Download ZIP**, veya `git clone`).
2. Klasörde **[Claude Code](https://claude.com/claude-code)**'u aç.
3. Şunu yaz: **"Bu repoyu kurmak istiyorum, beni baştan sona yönlendir."**

Claude Code repodaki `CLAUDE.md` talimatlarını okuyup seni adım adım kurar: Telegram botu, kanal, chat_id bulma, token'lar ve GitHub'ı **senin yerine** halleder. Sana kalan sadece birkaç token'ı yapıştırmak ve bir kez tarayıcı girişi yapmak.

> Aşağıdaki manuel adımlar, kendin kurmak istersen diye duruyor.

---

## ⚡ Hızlı kurulum (manuel)

Zor ve teknik kısımları (chat_id bulma, test mesajı, GitHub reposu + secret'lar) **`setup.py` sihirbazı** senin yerine yapıyor. Sana kalan sadece hesap oluşturma ve token yapıştırma:

### 1) Telegram botu oluştur
Telegram'da **@BotFather** → `/newbot` → bota isim ver → çıkan **token'ı kopyala** (`123456:ABC-...`).

### 2) Kanalı hazırla
- Raporun gideceği **kanalı** oluştur (yoksa).
- Kanal → **Yöneticiler** → **Yönetici Ekle** → botunu ekle ("Mesaj Gönderme" yetkisi yeterli).
- Kanala **herhangi bir mesaj at** (botun kanalı "görebilmesi" için gerekli).
- Ayrıca Telegram'da **kendi botuna** bir kez **/start** yaz (botun sana özel mesaj atabilmesi için).

### 3) Claude token'ı üret
Terminalde:
```bash
claude setup-token
```
Çıkan token'ı kopyala. (Pro/Max aboneliği yeterli, ek ücret yok; günde 1 rapor limiti zorlamaz. Token ~1 yıl geçerli.)

### 4) Sihirbazı çalıştır — gerisi TEK KOMUTLA otomatik
```bash
pip install -r requirements.txt
python setup.py
```
Sihirbaz senden sadece **iki token** (bot + Claude) isteyecek, **kalan her şeyi kendi yapacak**:
- ✅ Kanalın ve senin chat_id'ni **otomatik bulur** (JSON okuman gerekmez)
- ✅ Her ikisine **test mesajı** atıp çalıştığını kanıtlar
- ✅ `.env` dosyasını yazar
- ✅ **GitHub girişini kendisi başlatır** — tarayıcı açılır, tek kullanımlık kodu girersin (GitHub hesabın yoksa önce [github.com](https://github.com)'dan ücretsiz aç)
- ✅ **GitHub reposunu oluşturur, dosyaları yükler ve 4 secret'ı senin yerine ekler**

> GitHub CLI (`gh`) makinene **önceden kuruldu**; ayrıca bir şey yüklemene gerek yok.

**Bitti.** Artık her sabah 07:00'de kanala otomatik rapor gelir. 🎉

> **Not:** GitHub adımını atlamak istersen sihirbaz yine `.env`'i hazırlar ve yerel test (`python report.py --test`) çalışır. GitHub'ı sonra manuel kurmak istersen aşağıdaki adımlar var.

---

## Test etme

**Yerel (bilgisayarında):**
```bash
python report.py --test
```
`--test` bayrağı raporu **kanala değil, sadece sana (admin)** gönderir — kanalı kirletmeden denersin. Bayrak olmadan (`python report.py`) rapor kanala gider.

**GitHub üzerinden:**
Repo → **Actions** → **Günlük Kripto Raporu** → **Run workflow** → "Test modu" kutusunu işaretle → **Run**. Rapor admin chat'ine düşer.

---

## Manuel GitHub kurulumu (sihirbaz kullanmazsan)

1. [github.com](https://github.com)'da yeni repo oluştur (private olabilir).
2. Dosyaları yükle:
   ```bash
   git add .
   git commit -m "İlk kurulum"
   git branch -M main
   git remote add origin https://github.com/KULLANICI/REPO.git
   git push -u origin main
   ```
3. Repo → **Settings → Secrets and variables → Actions → New repository secret**. Şu 4 secret'ı ekle (isimler birebir):

   | Secret adı | Değeri |
   |---|---|
   | `CLAUDE_CODE_OAUTH_TOKEN` | `claude setup-token` çıktısı |
   | `TELEGRAM_BOT_TOKEN` | BotFather token'ı |
   | `TELEGRAM_CHAT_ID` | Kanal id (`@kanal` veya `-100...`) |
   | `TELEGRAM_ADMIN_CHAT_ID` | Senin özel chat id'in |

   > chat_id'leri elle bulman gerekirse: `.env` dosyasında sihirbazın yazdığı değerler zaten var. Ya da `https://api.telegram.org/bot<TOKEN>/getUpdates` adresini tarayıcıda açıp `"chat":{"id":...}` satırına bak.

---

## Sık sorulanlar

**Saat neden 07:00?** Workflow `cron: "0 4 * * *"` (04:00 UTC = 07:00 TSİ). GitHub yoğun saatlerde birkaç dakika gecikebilir, normaldir.

**Rapor gelmedi?** Repo → **Actions** loglarına bak. Hata olduysa bot sana (admin) hata özetini de mesaj atar.

**Ücret?** Yok. GitHub Actions ücretsiz katmanı, kripto API'leri ücretsiz, rapor Claude aboneliğinden düşer.

**Token süresi doldu?** `claude setup-token`'ı tekrar çalıştır, GitHub'da `CLAUDE_CODE_OAUTH_TOKEN` secret'ını güncelle (ya da `python setup.py`'ı tekrar çalıştır).

---

## Dosya yapısı

```
.
├── report.py                           # Ana script (3 adım: veri → rapor → gönderim)
├── setup.py                            # Kurulum sihirbazı (chat_id, test, .env, GitHub)
├── requirements.txt                    # Python bağımlılığı (sadece requests)
├── .github/workflows/daily-report.yml  # GitHub Actions zamanlanmış görevi (07:00 TSİ)
├── .env.example                        # Ortam değişkeni şablonu
├── .gitignore
└── README.md
```
