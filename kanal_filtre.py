"""Kanal çıkış filtresi: kanala gidecek metnin son kapısı (model değil, kod).

Neden var: 24 Tem, 9 Ağu ve 17 Ağu 2026'da (kanal gönderileri 1884, 1941,
1948) modelin kendi iç notu ("Confirmed Friday matches the template...",
"Rapor hazır. İşte...", "Karakter sayımı için bash izni alınamadı...")
raporun önüne yapışıp kanala gitti. Bu modül kanala giden HER metni
göndermeden önce denetler; şüpheli metin kanala gitmez, sebep loga yazılır.

Kurallar (Doğukan, 10 Kas 2026):
  - boş metin, '[SILENT]' gitmez
  - iç işaretler gitmez: hata/error/Traceback/cron/ajan/Alpha/Beta/Omega/
    brif/kart/pano/skill/job, dosya yolu (/Users/, ~/.hermes, /home/runner)
  - modelin üst konuşması gitmez (İngilizce ön söz, "rapor hazır", "bash izni")
  - kâr vaadi / al-sat sinyali gitmez
  - metin GÜNAYDIN brief kalıbına uymalı
  - em tire (—) kanalda kullanılmaz: gönderim öncesi '·' ya da '-' olur

Log dosyasına metnin kendisi YAZILMAZ (repo herkese açık): yalnız tarih,
sebep, uzunluk ve özet (sha256 ilk 12 hane). Tam metin admin'e özelden gider.
"""

import hashlib
import json
import os
import re
from datetime import datetime, timezone

KOK = os.path.dirname(os.path.abspath(__file__))
LOG_YOL = os.path.join(KOK, "state", "kanal-filtre-log.jsonl")

# Kök + en çok 4 harf Türkçe ek (ajanı, hatası, kartı, panoya...).
_TR_HARF = "a-zA-ZçğıöşüÇĞİÖŞÜâîû"
_KOKLER = ("hata", "ajan", "brif", "kart", "pano", "cron", "skill", "job",
           "error", "traceback")
# Kök ile başlayan ama iç işaret OLMAYAN gerçek kelimeler (haber dilinde geçer).
_ISTISNA_ON_EK = ("hatay", "ajans", "ajanda", "kartel", "kartal", "kartvizit",
                  "panora", "jobs report")
_KOK_RE = re.compile(
    r"(?<![" + _TR_HARF + r"])(" + "|".join(_KOKLER) + r")[" + _TR_HARF + r"]{0,4}(?![" + _TR_HARF + r"])",
    re.IGNORECASE)
# Ajan/ekip adları: tam kelime (Alpha'ya, Beta'nın kesmesi ile de yakalanır).
_AD_RE = re.compile(r"(?<![" + _TR_HARF + r"])(alpha|beta|omega)(?![" + _TR_HARF + r"])",
                    re.IGNORECASE)
_YOL_RE = re.compile(r"(/Users/|~/\.hermes|\.hermes/|/home/runner|[A-Z]:\\|\.py\b|\.sh\b|\.json\b)")
# Modelin üst konuşması / iç not izleri.
_META_RE = re.compile(
    r"(\[SILENT\]|here'?s the|here is|the report|confirmed|template|i'?ll\b|let me|"
    r"\bbash\b|izni alınamadı|karakter sayımı|rapor hazır|raporu doğrudan|"
    r"\bprompt\b|\bclaude\b|\bsession\b|\bjson\b|\bTODO\b|\[TEST\])",
    re.IGNORECASE)
# Kâr vaadi / sinyal.
_SINYAL_RE = re.compile(
    r"((al|sat|alım|satış|long|short)\s+sinyal|kesin kazanç|garantili|kâr garanti|kar garanti|"
    r"fiyat hedefi|hedef fiyat|para kazan|\bx\d+\s*kazan|yatırım tavsiyesidir)",
    re.IGNORECASE)

# Brief kalıbı (render.brief_html): sabit satır başları.
_KALIP_ZORUNLU = ("📊 <b>GÜNAYDIN", "⚡ <b>60 SANİYE</b>", "🌡️ Hava:", "₿ BTC",
                  "🔑 <b>Neden:</b>", "⏰ <b>Kritik:</b>", "⚠️ <b>Risk:</b>")


def em_tire_temizle(metin):
    """Kanal kuralı: em tire yok. ' — ' -> ' · ', kalan '—' -> '-'."""
    return metin.replace(" — ", " · ").replace("—", "-")


def _duz(metin):
    return re.sub(r"<[^>]+>", " ", metin)


def kontrol(metin):
    """(gecer_mi, sebep). Sebep boşsa metin kanala gidebilir.

    Metin em_tire_temizle'den GEÇMİŞ hâliyle verilmeli."""
    if metin is None or not str(metin).strip():
        return False, "bos metin"
    m = str(metin).strip()
    duz = _duz(m)

    if "[SILENT]" in m.upper():
        return False, "[SILENT] işareti"
    if not m.startswith("📊 <b>GÜNAYDIN"):
        return False, "kalıp dışı: metin '📊 GÜNAYDIN' ile başlamıyor (önünde ek metin var)"
    eksik = [k for k in _KALIP_ZORUNLU if k not in m]
    if eksik:
        return False, "kalıp dışı: eksik satır " + ", ".join(eksik)
    satir = [s for s in m.splitlines() if s.strip()]
    if len(satir) != len(_KALIP_ZORUNLU):
        return False, f"kalıp dışı: {len(satir)} dolu satır (beklenen {len(_KALIP_ZORUNLU)})"
    if len(m) > 1024:
        return False, f"kalıp dışı: {len(m)} karakter (kart altyazısı en çok 1024)"
    if "—" in m:
        return False, "em tire var"

    for k in _KOK_RE.finditer(duz):
        # Not: tüm metni lower() yapıp indeksle bakma; 'İ'.lower() 2 karakter
        # olduğu için indeksler kayar. Eşleşmenin başından dilimle.
        devami = duz[k.start():k.start() + 20].lower()
        if any(devami.startswith(ist) for ist in _ISTISNA_ON_EK):
            continue
        return False, f"iç işaret: '{k.group(0)}'"
    a = _AD_RE.search(duz)
    if a:
        return False, f"iç işaret (ajan adı): '{a.group(0)}'"
    y = _YOL_RE.search(duz)
    if y:
        return False, f"dosya yolu/uzantı: '{y.group(0)}'"
    mt = _META_RE.search(duz)
    if mt:
        return False, f"model üst konuşması: '{mt.group(0)}'"
    s = _SINYAL_RE.search(duz)
    if s:
        return False, f"kâr vaadi/sinyal: '{s.group(0)}'"
    return True, ""


def logla(sebep, metin, karar="ENGELLENDI", log_yol=None):
    """Karar satırını JSONL loga ekler. Metnin kendisini yazmaz."""
    yol = log_yol or LOG_YOL
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    m = "" if metin is None else str(metin)
    kayit = {
        "zaman": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "karar": karar,
        "sebep": sebep,
        "uzunluk": len(m),
        "ozet": hashlib.sha256(m.encode("utf-8")).hexdigest()[:12],
    }
    with open(yol, "a", encoding="utf-8") as f:
        f.write(json.dumps(kayit, ensure_ascii=False) + "\n")
    return kayit


def hazirla(metin, log_yol=None):
    """Kanal metnini temizler + denetler. (temiz_metin | None, sebep).

    None dönerse kanala HİÇBİR ŞEY gönderilmez ve sebep loga yazılmıştır."""
    temiz = em_tire_temizle(metin or "")
    ok, sebep = kontrol(temiz)
    if not ok:
        logla(sebep, temiz, log_yol=log_yol)
        return None, sebep
    return temiz, ""


if __name__ == "__main__":
    # Kuru çalıştırma: python kanal_filtre.py dosya.txt  (gönderim YOK)
    import sys
    metin = open(sys.argv[1], encoding="utf-8").read() if len(sys.argv) > 1 else sys.stdin.read()
    temiz, sebep = hazirla(metin, log_yol=os.environ.get("KANAL_FILTRE_LOG"))
    print("GEÇER" if temiz else f"ENGELLENDİ: {sebep}")
    sys.exit(0 if temiz else 2)
