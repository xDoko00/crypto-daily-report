# -*- coding: utf-8 -*-
"""Günlük video adımı: üret + Telegram'a `sendVideo`.

İki taraf:
  * `izole_calistir(rapor)` — report.py'den, rapor ve sesli özet GÖNDERİLDİKTEN
    sonra çağrılır. Yalnız stdlib kullanır; videoyu ayrı bir alt süreçte üretir,
    toplam süreyi `UST_SINIR_SN` ile sınırlar. HİÇBİR durumda exception fırlatmaz;
    hata/zaman aşımı loglanır, rapor akışı etkilenmez.
  * `python -m video.calistir --rapor x.json` — alt süreç: üretir ve gönderir.

Bayraklar (ortam):
  VIDEO_OZET=1         açık (varsayılan kapalı)
  VIDEO_HEDEF=admin    varsayılan; TELEGRAM_ADMIN_CHAT_ID'ye gider.
                       "kanal" kod yolu hazır ama KANAL_ACIK=False iken gönderilmez.
"""
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import time

BAYRAK = "VIDEO_OZET"
HEDEF_DEGISKENI = "VIDEO_HEDEF"
VARSAYILAN_HEDEF = "admin"
KANAL_ACIK = False                       # kanala gönderim bu aşamada kapalı
UST_SINIR_SN = 8 * 60                    # üretim + gönderim toplam üst sınırı
TELEGRAM_SINIR = 50 * 1024 * 1024        # Bot API yükleme sınırı
HEDEF_BOYUT = 48 * 1024 * 1024           # aşılırsa bu boyuta göre yeniden kodla
W, H = 1080, 1920
ACIKLAMA = {"admin": "Günaydın Kripto video önizleme (sadece sana)",
            "kanal": "Günaydın Kripto — günün 60 saniyelik özeti"}
MAX_DENEME = 3
DEPO_KOKU = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def log(m):
    print(m, file=sys.stderr, flush=True)


def _gizle(s):
    s = str(s)
    tok = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if tok:
        s = s.replace(tok, "***")
    return re.sub(r"bot\d{6,12}:[A-Za-z0-9_-]{10,}", "bot***", s)


def aktif_mi(ortam=None):
    ortam = os.environ if ortam is None else ortam
    return (ortam.get(BAYRAK) or "").strip() == "1"


def hedef_sohbet(ortam=None):
    """-> (hedef adı, chat_id) ya da (ad, None) gönderilmeyecekse."""
    ortam = os.environ if ortam is None else ortam
    hedef = (ortam.get(HEDEF_DEGISKENI) or VARSAYILAN_HEDEF).strip().lower()
    if hedef == "admin":
        return hedef, (ortam.get("TELEGRAM_ADMIN_CHAT_ID") or "").strip() or None
    if hedef == "kanal":
        if not KANAL_ACIK:
            log("[video] VIDEO_HEDEF=kanal henüz kapalı (KANAL_ACIK=False) — gönderilmedi.")
            return hedef, None
        return hedef, (ortam.get("TELEGRAM_CHAT_ID") or "").strip() or None
    log(f"[video] bilinmeyen VIDEO_HEDEF={hedef!r} — gönderilmedi.")
    return hedef, None


# --------------------------------------------------------------------------- #
# Rapor süreci tarafı (yalnız stdlib)
# --------------------------------------------------------------------------- #

def _oldur(p):
    try:
        if os.name != "nt":
            os.killpg(p.pid, signal.SIGKILL)   # ffmpeg torunları dahil
        else:
            p.kill()
    except Exception:                         # noqa: BLE001
        pass
    try:
        p.wait(timeout=10)
    except Exception:                         # noqa: BLE001
        pass


def izole_calistir(rapor, ust_sinir=UST_SINIR_SN, ortam=None, popen=subprocess.Popen):
    """Video alt sürecini çalıştırır. -> True (gönderildi/üretildi) / False. Asla fırlatmaz."""
    try:
        if not aktif_mi(ortam):
            log(f"[video] {BAYRAK} kapalı — video atlandı.")
            return False
        with tempfile.TemporaryDirectory(prefix="gunaydin-video-") as d:
            yol = os.path.join(d, "rapor.json")
            with open(yol, "w", encoding="utf-8") as f:
                json.dump(rapor, f, ensure_ascii=False)
            bas = time.time()
            p = popen([sys.executable, "-m", "video.calistir", "--rapor", yol, "--calisma", d],
                      cwd=DEPO_KOKU, start_new_session=(os.name != "nt"))
            try:
                kod = p.wait(timeout=ust_sinir)
            except subprocess.TimeoutExpired:
                _oldur(p)
                log(f"[uyarı] Video adımı {ust_sinir} sn üst sınırını aştı — durduruldu, rapor etkilenmedi.")
                return False
            if kod != 0:
                log(f"[uyarı] Video adımı başarısız (çıkış {kod}) — rapor etkilenmedi.")
                return False
            log(f"[video] tamam ({time.time() - bas:.0f} sn).")
            return True
    except Exception as e:                    # noqa: BLE001
        log(f"[uyarı] Video adımı atlandı: {type(e).__name__}: {_gizle(e)}")
        return False


# --------------------------------------------------------------------------- #
# Alt süreç tarafı
# --------------------------------------------------------------------------- #

def _sure(yol):
    p = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", yol], capture_output=True, text=True, check=True)
    return float(p.stdout.strip())


def boyut_sigdir(yol, sinir=TELEGRAM_SINIR, hedef=HEDEF_BOYUT, calistir=subprocess.run,
                 boyut=os.path.getsize, sure=_sure):
    """Dosya `sinir`'ı aşıyorsa bit hızını düşürüp yeniden kodlar -> gönderilecek yol."""
    if boyut(yol) <= sinir:
        return yol
    s = max(sure(yol), 1.0)
    ses_kbps = 128
    video_kbps = max(int(hedef * 8 / s / 1000 * 0.95) - ses_kbps, 500)
    yeni = yol[:-4] + "-kucuk.mp4"
    log(f"[video] {boyut(yol) / 1e6:.1f} MB > sınır; {video_kbps} kbps ile yeniden kodlanıyor")
    calistir(["ffmpeg", "-y", "-v", "error", "-i", yol, "-c:v", "libx264", "-preset", "medium",
              "-b:v", f"{video_kbps}k", "-maxrate", f"{int(video_kbps * 1.3)}k",
              "-bufsize", f"{video_kbps * 2}k", "-pix_fmt", "yuv420p",
              "-c:a", "aac", "-b:a", f"{ses_kbps}k", "-movflags", "+faststart", yeni], check=True)
    if boyut(yeni) > sinir:
        raise RuntimeError(f"yeniden kodlamadan sonra da {boyut(yeni) / 1e6:.1f} MB")
    return yeni


def video_gonder(bot_token, chat_id, yol, aciklama, sure=None, http=None, bekle=time.sleep):
    """Telegram sendVideo (supports_streaming, 1080x1920); ağ hatasında tekrar dener."""
    if http is None:
        import requests as http
    url = f"https://api.telegram.org/bot{bot_token}/sendVideo"
    veri = {"chat_id": chat_id, "caption": aciklama, "supports_streaming": "true",
            "width": str(W), "height": str(H)}
    if sure:
        veri["duration"] = str(int(round(sure)))
    son = None
    for deneme in range(1, MAX_DENEME + 1):
        try:
            with open(yol, "rb") as f:
                r = http.post(url, data=veri, files={"video": (os.path.basename(yol), f, "video/mp4")},
                              timeout=180)
            cevap = r.json()
            if not cevap.get("ok"):
                raise RuntimeError(f"sendVideo hatası: {cevap.get('description')}")
            return cevap
        except Exception as e:                # noqa: BLE001
            son = e
            log(f"[uyarı] Video gönderimi başarısız ({deneme}/{MAX_DENEME}): {_gizle(e)}")
            if deneme < MAX_DENEME:
                bekle(2 * deneme)
    raise RuntimeError(f"Video gönderimi {MAX_DENEME} denemede başarısız: {_gizle(son)}")


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="Günaydın Kripto videosu: üret + Telegram")
    ap.add_argument("--rapor", required=True, help="kanonik rapor JSON dosyası")
    ap.add_argument("--calisma", default=None, help="ara dosyalar (vars. geçici klasör)")
    ap.add_argument("--gonderme", action="store_true", help="yalnız üret, Telegram'a gönderme")
    a = ap.parse_args(argv)
    try:
        with open(a.rapor, encoding="utf-8") as f:
            rapor = json.load(f)
        hedef, chat_id = hedef_sohbet()
        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
        if not a.gonderme and not (chat_id and bot_token):
            log(f"[video] '{hedef}' hedefi için chat id / bot token yok — üretilmedi.")
            return 0
        from . import gunaydin
        calisma = a.calisma or tempfile.mkdtemp(prefix="gunaydin-video-")
        cikti = os.path.join(calisma, f"gunaydin-{rapor['id']}.mp4")
        ozet = gunaydin.uret(rapor, os.path.join(calisma, "is"), cikti)
        yol = boyut_sigdir(cikti)
        if a.gonderme:
            log(f"[video] üretildi (gönderilmedi): {yol}")
            return 0
        video_gonder(bot_token, chat_id, yol, ACIKLAMA.get(hedef, ACIKLAMA["admin"]), ozet.get("sure"))
        log(f"[başarılı] Video '{hedef}' hedefine gönderildi.")
        return 0
    except Exception as e:                    # noqa: BLE001
        log(f"[uyarı] Video üretilemedi/gönderilemedi: {type(e).__name__}: {_gizle(e)}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
