# Bekleyen yayın

Yayına (main'e push) girmemiş işler. Yayınlanınca madde buradan silinir.
Ayrıntılı plan: `~/akademi/docs/gelistirme-plani.md`.

- **Aşama 2 (plan 5) — web sesli özet**, yerelde hazır, reviewer ve Doğukan onayı bekliyor:
  - `ses_klon.ozet_sesleri()` tek ElevenLabs çağrısından (OGG, ham MP3) döner; `ozet_ogg()` aynı kaldı,
    Telegram akışı değişmedi.
  - `report.py`: rapor diske yazıldıktan sonra `ses_klon.web_ses_yaz()` → `reports/ses/<gün>.mp3` +
    `reports/ses/latest.mp3` (mono 64 kbps, ≤1 MB, ~0,5 MB/dk); 14 günden eskiler silinir. Yalnız klon
    ses üretildiyse ve test/önizleme modu değilse. Hata olursa dosya yazılmaz, rapor etkilenmez.
  - İş akışı değişmedi (`git add reports` yeni dosyaları ve silmeleri kapsıyor); yalnız yorum güncellendi.
  - Dikkat: silinen ses dosyaları git geçmişinde kalır (~0,5 MB/gün). Geçmiş büyürse ayrı depolama düşünülür.
  - Site tarafı (dogukan-website) bu dosyayı `reports/ses/<rapor id>.mp3` adıyla arıyor.
