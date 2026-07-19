#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KURULUM SİHİRBAZI — tek komutla her şeyi ayarlar
=================================================

Senin elle yapacağın işi minimuma indirir. Şunları OTOMATİK yapar:
  1. Bot token'ını doğrular (getMe)
  2. Kanalın ve senin (admin) chat_id'ni OTOMATİK bulur — JSON okuman gerekmez
  3. Her ikisine test mesajı atıp çalıştığını kanıtlar
  4. .env dosyasını yazar
  5. (gh CLI varsa) GitHub reposunu oluşturur, dosyaları push'lar ve 4 secret'ı
     senin yerine ekler — GitHub arayüzünde tık tık uğraşmazsın

Kullanım:
  python setup.py

Sana kalan tek manuel iş (sihirbaz seni yönlendirir):
  - @BotFather'dan bot oluşturup token'ı yapıştırmak
  - Kanala bir mesaj atmak ve kendi botuna /start yazmak
  - claude setup-token çıktısını yapıştırmak
"""

import os
import re
import sys
import time
import json
import subprocess
import shutil

import requests

HTTP_TIMEOUT = 30
ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")


# --------------------------------------------------------------------------- #
# Küçük yardımcılar
# --------------------------------------------------------------------------- #

def sor(mesaj, gizli=False):
    """Kullanıcıdan girdi alır (boşlukları temizler)."""
    try:
        return input(mesaj).strip()
    except (EOFError, KeyboardInterrupt):
        print("\nİptal edildi.")
        sys.exit(1)


def baslik(metin):
    print("\n" + "=" * 60)
    print(metin)
    print("=" * 60)


def api(token, method, **params):
    """Telegram Bot API çağrısı; (ok, sonuç) döndürür."""
    url = f"https://api.telegram.org/bot{token}/{method}"
    r = requests.post(url, json=params, timeout=HTTP_TIMEOUT)
    data = r.json()
    return data.get("ok", False), data


# --------------------------------------------------------------------------- #
# 1) Bot token doğrulama
# --------------------------------------------------------------------------- #

def token_al_ve_dogrula():
    baslik("ADIM 1 — Telegram bot token'ı")
    print("@BotFather'dan aldığın token'ı yapıştır (123456:ABC-... biçiminde).")
    print("Henüz bot oluşturmadıysan: Telegram'da @BotFather → /newbot → token'ı kopyala.\n")

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if token:
        print("(Ortam değişkeninden token bulundu, onu kullanıyorum.)")
    while True:
        if not token:
            token = sor("Bot token: ")
        ok, data = api(token, "getMe")
        if ok:
            bot = data["result"]
            print(f"✓ Bot doğrulandı: @{bot.get('username')} ({bot.get('first_name')})")
            return token, bot.get("username")
        print(f"✗ Token geçersiz görünüyor: {data.get('description')}. Tekrar dene.\n")
        token = ""


# --------------------------------------------------------------------------- #
# 2) chat_id otomatik keşif
# --------------------------------------------------------------------------- #

def sohbetleri_topla(token):
    """
    getUpdates'i okuyup botun gördüğü sohbetleri türüne göre ayırır.
    Döndürür: {"channel": {...}, "private": {...}, "group": {...}}
    Her biri chat_id -> görünen ad eşlemesi.
    """
    ok, data = api(token, "getUpdates", timeout=0, allowed_updates=[])
    kanallar, ozel, gruplar = {}, {}, {}
    if not ok:
        return kanallar, ozel, gruplar

    for upd in data.get("result", []):
        # Kanal gönderileri channel_post; özel/grup mesajları message içinde
        for anahtar in ("message", "channel_post", "my_chat_member"):
            obj = upd.get(anahtar)
            if not obj:
                continue
            chat = obj.get("chat", {})
            cid = chat.get("id")
            if cid is None:
                continue
            ctype = chat.get("type")
            ad = chat.get("title") or (
                (chat.get("first_name", "") + " " + chat.get("last_name", "")).strip()
                or chat.get("username") or str(cid)
            )
            if ctype == "channel":
                kanallar[cid] = ad
            elif ctype == "private":
                ozel[cid] = ad
            elif ctype in ("group", "supergroup"):
                gruplar[cid] = ad
    return kanallar, ozel, gruplar


def sec_veya_bekle(token, tur, aciklama, ipucu):
    """
    Belirtilen türde (channel/private) sohbet bulunana kadar kullanıcıyı
    yönlendirir. Birden fazla varsa seçtirir, tek varsa otomatik seçer.
    """
    while True:
        kanallar, ozel, gruplar = sohbetleri_topla(token)
        secenek = kanallar if tur == "channel" else ozel

        if secenek:
            items = list(secenek.items())
            if len(items) == 1:
                cid, ad = items[0]
                print(f"✓ {aciklama} otomatik bulundu: {ad}  (id: {cid})")
                return cid
            print(f"\nBirden fazla {aciklama.lower()} bulundu, birini seç:")
            for i, (cid, ad) in enumerate(items, 1):
                print(f"  {i}) {ad}  (id: {cid})")
            sec = sor("Numara: ")
            try:
                cid = items[int(sec) - 1][0]
                return cid
            except (ValueError, IndexError):
                print("Geçersiz seçim, tekrar.")
                continue

        print(f"\n… Henüz {aciklama.lower()} görmedim.")
        print(f"   {ipucu}")
        sor("   Yaptıktan sonra ENTER'a bas (çıkmak için Ctrl+C)... ")


def chat_idleri_bul(token, bot_username):
    baslik("ADIM 2 — Kanal ve admin chat_id'leri (OTOMATİK)")

    print("Önce kanalı hazırla:")
    print("  • Raporun gideceği Telegram KANALINI oluştur (yoksa)")
    print(f"  • Kanala @{bot_username} botunu ADMIN yap (mesaj gönderme yetkisi yeterli)")
    print("  • Kanala herhangi bir mesaj at (botun görebilmesi için)\n")

    kanal_id = sec_veya_bekle(
        token, "channel", "Kanal",
        f"Kanalı oluştur, @{bot_username} botunu admin yap ve kanala bir mesaj at.",
    )

    print("\nŞimdi admin (senin özel) chat'in:")
    admin_id = sec_veya_bekle(
        token, "private", "Admin (senin özel chat'in)",
        f"Telegram'da @{bot_username} botunu aç ve /start yaz.",
    )

    return kanal_id, admin_id


# --------------------------------------------------------------------------- #
# 3) Test mesajı
# --------------------------------------------------------------------------- #

def test_mesaji_at(token, kanal_id, admin_id):
    baslik("ADIM 3 — Test mesajları")
    ok1, d1 = api(token, "sendMessage", chat_id=admin_id,
                  text="✅ Kurulum testi: bot sana özel mesaj atabiliyor.")
    print("✓ Admin'e test mesajı gönderildi." if ok1
          else f"✗ Admin'e mesaj başarısız: {d1.get('description')}")

    ok2, d2 = api(token, "sendMessage", chat_id=kanal_id,
                  text="✅ Kurulum testi: bot bu kanala rapor atabiliyor.")
    print("✓ Kanala test mesajı gönderildi." if ok2
          else f"✗ Kanala mesaj başarısız: {d2.get('description')} "
               "(bot kanalda admin mi?)")
    return ok1 and ok2


# --------------------------------------------------------------------------- #
# 4) claude token + .env yaz
# --------------------------------------------------------------------------- #

def claude_token_al():
    baslik("ADIM 4 — Claude token'ı")
    mevcut = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "")
    if mevcut:
        print("(Ortam değişkeninden Claude token'ı bulundu.)")
        return mevcut
    print("Terminalde şu komutu çalıştır ve çıkan token'ı yapıştır:")
    print("  claude setup-token")
    print("(Pro/Max aboneliği yeterli, ek ücret yok. Boş bırakıp ENTER'a basarak")
    print(" bu adımı sonraya erteleyebilirsin.)\n")
    return sor("Claude token (opsiyonel): ")


def env_yaz(bot_token, kanal_id, admin_id, claude_token):
    satirlar = [
        f"CLAUDE_CODE_OAUTH_TOKEN={claude_token}",
        f"TELEGRAM_BOT_TOKEN={bot_token}",
        f"TELEGRAM_CHAT_ID={kanal_id}",
        f"TELEGRAM_ADMIN_CHAT_ID={admin_id}",
        "",
    ]
    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(satirlar))
    print(f"\n✓ .env dosyası yazıldı: {ENV_PATH}")
    print("  (.gitignore ile korunuyor; asla commit'lenmez.)")


# --------------------------------------------------------------------------- #
# 5) GitHub otomasyonu (gh CLI varsa)
# --------------------------------------------------------------------------- #

def gh_bin():
    """gh çalıştırılabilirini bulur. PATH'te yoksa Windows'taki standart kurulum
    yolunu da dener (winget kurulumu sonrası açık terminaller PATH'i görmeyebilir)."""
    yol = shutil.which("gh")
    if yol:
        return yol
    if os.name == "nt":
        aday = os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"),
                            "GitHub CLI", "gh.exe")
        if os.path.exists(aday):
            return aday
    return None


def gh_girisli_mi(gh):
    """gh ile giriş yapılmış mı?"""
    return subprocess.run([gh, "auth", "status"], capture_output=True).returncode == 0


# --------------------------------------------------------------------------- #
# Güvenlik taraması — repo herkese açılmadan önce sızıntı kontrolü
# --------------------------------------------------------------------------- #

# Gerçek token'ları yakalar; .env.example ve dokümanlardaki yer tutucuları
# ("123456:ABC-DEF...", "sk-ant-oat...") kasıtlı olarak yakalamaz.
GIZLI_KALIPLAR = [
    ("Telegram bot token", r"[0-9]{8,10}:AA[A-Za-z0-9_\-]{30,}"),
    ("Claude OAuth token", r"sk-ant-[A-Za-z0-9_\-]{20,}"),
    ("GitHub token", r"gh[pousr]_[A-Za-z0-9]{36,}"),
    ("GitHub fine-grained token", r"github_pat_[A-Za-z0-9_]{40,}"),
]


def _taranacak_dosyalar():
    """Repoya gidecek dosyalar (gitignore'lananlar hariç)."""
    r = subprocess.run(["git", "ls-files", "-co", "--exclude-standard"],
                       capture_output=True, text=True)
    if r.returncode == 0 and r.stdout.strip():
        return [d for d in r.stdout.splitlines() if d.strip()]
    atla = {".git", "__pycache__", ".venv", "venv", "node_modules"}
    bulunan = []
    for kok, klasorler, dosyalar in os.walk("."):
        klasorler[:] = [k for k in klasorler if k not in atla]
        bulunan.extend(os.path.join(kok, d) for d in dosyalar)
    return bulunan


def guvenlik_taramasi():
    """Repo public yapılmadan ÖNCE sızıntı kontrolü.

    Dört şeye bakar: (1) .env takip ediliyor mu, (2) .gitignore onu kapsıyor mu,
    (3) gönderilecek dosyalarda gerçek token var mı, (4) git geçmişinde var mı
    (silinmiş olsa bile geçmişte kalır ve public olunca herkes görebilir).

    (temiz_mi, [bulgular]) döndürür.
    """
    bulgular = []

    r = subprocess.run(["git", "ls-files", ".env"], capture_output=True, text=True)
    if r.stdout.strip():
        bulgular.append(".env dosyası git tarafından TAKİP EDİLİYOR (asla olmamalı)")

    try:
        with open(".gitignore", encoding="utf-8") as f:
            if ".env" not in f.read():
                bulgular.append(".gitignore içinde .env satırı yok")
    except OSError:
        bulgular.append(".gitignore bulunamadı")

    for yol in _taranacak_dosyalar():
        try:
            with open(yol, encoding="utf-8", errors="ignore") as f:
                icerik = f.read()
        except OSError:
            continue
        for ad, kalip in GIZLI_KALIPLAR:
            if re.search(kalip, icerik):
                bulgular.append("%s dosyasinda %s benzeri bir dize var" % (yol, ad))

    birlesik = "|".join(k for _, k in GIZLI_KALIPLAR)
    r = subprocess.run(["git", "rev-list", "--all"], capture_output=True, text=True)
    for commit in [c for c in r.stdout.split() if c][:100]:
        g = subprocess.run(["git", "grep", "-I", "-E", birlesik, commit],
                           capture_output=True, text=True)
        if g.stdout.strip():
            bulgular.append("git gecmisinde (%s) token benzeri bir dize var" % commit[:7])
            break

    return (not bulgular), bulgular


def github_kur(bot_token, kanal_id, admin_id, claude_token):
    baslik("ADIM 5 — GitHub (repo + secret'lar OTOMATİK)")

    gh = gh_bin()
    if not gh:
        print("GitHub CLI (gh) bulunamadı — bu adımı otomatik yapamıyorum.")
        print("Kur (Windows): winget install --id GitHub.cli")
        print("Sonra bu sihirbazı tekrar çalıştır. (Ya da README'deki manuel adımlar.)")
        return

    # Giriş yapılmamışsa, tarayıcı girişini sihirbaz BAŞLATIR — kullanıcı komut yazmaz.
    if not gh_girisli_mi(gh):
        print("GitHub'a henüz giriş yapılmamış. Tarayıcı girişini şimdi başlatıyorum.")
        print("Açılan sayfada / komutta: hesabını seç, çıkan tek kullanımlık kodu gir.\n")
        # Etkileşimli: stdio terminale bağlı; tarayıcı açılır, kod gösterilir.
        subprocess.run([gh, "auth", "login", "--hostname", "github.com",
                        "--git-protocol", "https", "--web"])
        if not gh_girisli_mi(gh):
            print("Giriş tamamlanamadı. `gh auth login` yapıp sihirbazı tekrar çalıştır.")
            return
        print("✓ GitHub girişi başarılı.")

    if sor("GitHub reposunu otomatik oluşturayım mı? (e/h, öneri e): ").lower() not in ("", "e", "evet", "y", "yes"):
        print("Atlandı. README'deki manuel adımları kullanabilirsin.")
        return

    repo_adi = sor("Repo adı (ör. crypto-daily-report): ") or "crypto-daily-report"

    # git identity yoksa ayarla (commit için gerekli)
    if not subprocess.run(["git", "config", "user.email"], capture_output=True).stdout.strip():
        subprocess.run(["git", "config", "user.email", "bot@example.com"])
        subprocess.run(["git", "config", "user.name", "Crypto Report Bot"])

    # İlk commit
    subprocess.run(["git", "add", "-A"])
    subprocess.run(["git", "commit", "-m", "Günlük kripto raporu botu kurulumu"],
                   capture_output=True)

    # Repo PUBLIC oluşturulur: public repolarda GitHub Actions süresi ücretsizdir,
    # böylece bot sabah erkenden uyanıp teslim saatini bekleyebilir (sabit 08:00).
    # Ama önce sızıntı taraması — temiz değilse otomatik private'a düşeriz.
    print("\nGüvenlik taraması yapılıyor (repo herkese açık olacak)...")
    temiz, bulgular = guvenlik_taramasi()
    if temiz:
        gorunurluk = "--public"
        print("✓ Tarama temiz — repo PUBLIC oluşturulacak.")
        print("  Sebep: public repoda Actions süresi sınırsız; rapor tam saatinde gider.")
        print("  Token'ların yine de gizli kalır — GitHub Secrets şifrelidir, kodda durmaz.")
    else:
        gorunurluk = "--private"
        print("⚠ GÜVENLİK UYARISI — repo PRIVATE oluşturulacak. Bulunanlar:")
        for b in bulgular:
            print("   • %s" % b)
        print("  Bunları temizlemeden repoyu public YAPMA.")
        print("  Private repoda rapor bazen birkaç saat kayabilir (Actions kotası yüzünden).")

    # Repo oluştur + push
    print("\nRepo oluşturuluyor ve push'lanıyor...")
    r = subprocess.run(
        [gh, "repo", "create", repo_adi, gorunurluk, "--source=.", "--push"],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        print(f"✗ Repo oluşturulamadı: {r.stderr.strip()}")
        return
    print("✓ Repo oluşturuldu ve dosyalar yüklendi.")

    # 4 secret'ı ekle
    print("Secret'lar ekleniyor...")
    secrets = {
        "CLAUDE_CODE_OAUTH_TOKEN": claude_token,
        "TELEGRAM_BOT_TOKEN": bot_token,
        "TELEGRAM_CHAT_ID": str(kanal_id),
        "TELEGRAM_ADMIN_CHAT_ID": str(admin_id),
    }
    for ad, deger in secrets.items():
        if not deger:
            print(f"  ⚠ {ad} boş, atlandı (sonra ekle).")
            continue
        rr = subprocess.run([gh, "secret", "set", ad, "--body", deger],
                            capture_output=True, text=True)
        print(f"  {'✓' if rr.returncode == 0 else '✗'} {ad}")

    print("\n✓ GitHub tamamen hazır! Actions sekmesinden 'Run workflow' ile test edebilirsin.")


# --------------------------------------------------------------------------- #
# Ana akış
# --------------------------------------------------------------------------- #

def main():
    print("╔" + "═" * 58 + "╗")
    print("║  Günlük Kripto Raporu — KURULUM SİHİRBAZI               ║")
    print("╚" + "═" * 58 + "╝")

    bot_token, bot_username = token_al_ve_dogrula()
    kanal_id, admin_id = chat_idleri_bul(bot_token, bot_username)
    if not test_mesaji_at(bot_token, kanal_id, admin_id):
        cevap = sor("Test mesajı başarısız. Yine de devam edeyim mi? (e/h): ")
        if cevap.lower() not in ("e", "evet", "y", "yes"):
            print("Durduruldu. Botun kanalda ADMIN olduğundan ve botuna /start "
                  "yazdığından emin ol, sonra tekrar çalıştır.")
            sys.exit(1)
    claude_token = claude_token_al()
    env_yaz(bot_token, kanal_id, admin_id, claude_token)
    github_kur(bot_token, kanal_id, admin_id, claude_token)

    baslik("BİTTİ 🎉")
    print("Yerel test için:  python report.py --test")
    print("Otomatik yayın:   her sabah 08:00'de GitHub Actions çalışır.")
    if not claude_token:
        print("\n⚠ Claude token'ını boş bıraktın. `claude setup-token` çalıştırıp")
        print("  .env'e ve GitHub secret'a eklemeyi unutma.")


if __name__ == "__main__":
    main()
