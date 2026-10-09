# -*- coding: utf-8 -*-
"""Türkçe yazım denetimi: model çıktısı Türkçe karakterleri yitirmiş mi?

Model (claude -p) zaman zaman metni ASCII'ye yakın yazıyor ("Hurmuz Bogazi",
"tuketici guveni"). Kodda metni ASCII'leştiren bir adım yok; sorun üretimde.
Bu modül yalnız modelin yazdığı metin alanlarına bakar (kaynak başlığı /
yayıncı adı gibi İngilizce olabilecek alanlara bakmaz) ve iki işarete dayanır:

  1) Türkçe harf oranı (ğ, ı, ş, ö, ü, İ ve büyükleri) — normal raporda harflerin
     ~%8-13'ü, ASCII'leşmiş raporda %0-2. "ç" bilerek sayılmaz: ASCII'leşmiş
     raporlarda bile sık sık kalıyor.
  2) Sık Türkçe kelimelerin ASCII hâli ("icin", "degil", "buyuk"...). Liste,
     ASCII hâli başka bir Türkçe/İngilizce kelimeye denk gelmeyen kelimelerden
     seçildi; yine de tek eşleşme sorun sayılmaz (özel ad olabilir).
"""
import re

TR_HARFLER = set("ğışöüİĞŞÖÜ")

# Oran yalnız yeterince uzun metinde anlamlı; kısa metinde kelime işaretine bakılır.
ORAN_MIN_HARF = 300
ORAN_ESIK = 0.03
KELIME_ESIK = 2

# Kelimenin ASCII'leşmiş başı → doğru yazım (yalnız okunurluk için).
# Eşleşme kelime başından yapılır: "guven" → "guveni", "guvenini" de yakalanır.
# Her kök, ASCII hâli doğru bir Türkçe ya da yaygın İngilizce kelime başı
# OLMAYACAK biçimde seçildi.
ASCII_KOKLER = {
    "icin": "için", "degil": "değil", "gore": "göre", "buyuk": "büyük",
    "kucuk": "küçük", "dusus": "düşüş", "dustu": "düştü", "dusuk": "düşük",
    "yukselis": "yükseliş", "yukseldi": "yükseldi", "yuksek": "yüksek",
    "guven": "güven", "bogaz": "boğaz", "onemli": "önemli", "uzerinde": "üzerinde",
    "uzerine": "üzerine", "artis": "artış", "yuzde": "yüzde", "degisim": "değişim",
    "tuketici": "tüketici", "oncu": "öncü", "oncesi": "öncesi", "sonrasi": "sonrası",
    "piyasasi": "piyasası", "yatirim": "yatırım", "cikis": "çıkış", "giris": "giriş",
    "baski": "baskı", "kisa": "kısa", "gunluk": "günlük", "haftalik": "haftalık",
    "yillik": "yıllık", "isaret": "işaret", "gerginlig": "gerginliğ",
    "aciklama": "açıklama", "toplanti": "toplantı", "artirim": "artırım",
    "gelisme": "gelişme", "dolarlik": "dolarlık", "konusma": "konuşma",
}
# Kökle başlayan ama ASCII'leşmiş Türkçe olmayan İngilizce kelimeler.
INGILIZCE_ISTISNA = ("artist", "artisan")

_KELIME = re.compile(r"[^\W\d_]+", re.UNICODE)


def llm_metinleri(veri):
    """Modelin yazdığı Türkçe metin alanlarını tek listede toplar.
    `veri` hem model çıktısı hem kanonik rapor olabilir (aynı alan adları)."""
    b = veri.get("brief") or {}
    s = veri.get("sections") or {}
    out = [b.get("why"), b.get("mainRisk")]
    out += [e.get("title") for e in b.get("criticalEvents") or []]
    for y in s.get("yesterday") or []:
        out += [y.get("item"), y.get("outcome")]
    for a in s.get("agenda") or []:
        out += [a.get("title"), a.get("summary")]
    for a in (s.get("turkey") or {}).get("items") or []:
        out += [a.get("title"), a.get("summary")]
    out += [t.get("title") for t in s.get("today") or []]
    out += list(s.get("risks") or [])
    out += list(veri.get("followUps") or [])
    return [m for m in out if isinstance(m, str) and m]


def _kucuk(k):
    return k.replace("I", "ı").replace("İ", "i").lower()


def ascii_kelimeler(metin):
    """Metindeki ASCII'leşmiş Türkçe kelimeler (tekil, sıralı)."""
    bulunan = set()
    for k in _KELIME.findall(metin):
        if k[0].isupper():
            continue                        # özel ad olabilir (Boğaziçi/"Bogazici", Gore)
        k = _kucuk(k)
        if any(c in TR_HARFLER for c in k):
            continue
        # "çikis" gibi ç kalıp ı/ş gitmiş kelimeler de yakalansın; ama doğru
        # yazımı yalnız ç içeren kelime ("için", "içinde") sorun sayılmasın.
        katlanmis = k.replace("ç", "c")
        if katlanmis.startswith(INGILIZCE_ISTISNA):
            continue
        for kok, dogru in ASCII_KOKLER.items():
            if katlanmis.startswith(kok) and not k.startswith(dogru):
                bulunan.add(k)
                break
    return sorted(bulunan)


def turkce_sorunu(veri):
    """Sorun yoksa None; varsa kısa açıklama (log/admin uyarısı için)."""
    metin = " ".join(llm_metinleri(veri))
    harf = sum(c.isalpha() for c in metin)
    tr = sum(c in TR_HARFLER for c in metin)
    kelimeler = ascii_kelimeler(metin)
    nedenler = []
    if harf >= ORAN_MIN_HARF and tr / harf < ORAN_ESIK:
        nedenler.append(f"Türkçe harf oranı %{100 * tr / harf:.1f} (beklenen ≥%{100 * ORAN_ESIK:.0f})")
    if len(kelimeler) >= KELIME_ESIK:
        nedenler.append("ASCII yazılmış kelimeler: " + ", ".join(kelimeler[:8]))
    return "; ".join(nedenler) or None


YAZIM_UYARISI = (
    "ÖNCEKİ DENEMENDE Türkçe karakterler eksikti ({sorun}). Aynı içeriği "
    "Türkçe karakterleri (ç, ğ, ı, İ, ö, ş, ü) eksiksiz kullanarak yeniden yaz; "
    "ör. \"icin\" değil \"için\", \"Hurmuz Bogazi\" değil \"Hürmüz Boğazı\". "
    "SADECE geçerli JSON döndür."
)
