# Doğan köşe balonu klipleri

`video/dogan.py` bu üç klibi her karede 232 px'lik daireye (5 px sarı kenarlık)
bindirir; konum 1080x1920 videoda x=724, y=1096. Kapatmak için `DOGAN_KOSE=kapali`.

| Dosya | Kare | Kaynak (960x960, 24 fps) |
|---|---|---|
| `konusma.mp4` | 58 | `a-konusma-v2.mp4` kareler 63–120 (göz kırpmalar dışarıda); sol alttaki el 85. kareden yumuşak kenarlı (40 px) yamayla örtülü |
| `bekleme.mp4` | 69 | `b-bekleme-v2.mp4` kareler 0–68 (73–82'deki göz kırpma dışarıda) |
| `kapanis.mp4` | 121 | `c-kapanis.mp4` (el sallama), tamamı |

Hazırlama (kaynak klipler repoda değil):
1. Her kaynak: `pad=960:980:0:0:black,crop=960:960:0:10,scale=222:222:flags=lanczos`
   (daire merkezi (480,490), yarıçap 480 → 222 px iç daire).
2. Konuşma yaması: ölçek 222/960; maske `clip((430-x)/40,0,1)*clip((y-790)/40,0,1)`
   (x,y kaynak piksel; y'ye +10), maskeli bölge 85. kareyle değiştirilir.
3. Kodlama: 24 fps, `libx264 -preset veryslow -crf 12 -pix_fmt yuv444p -g 24`, ses yok.
   Daire maskesi ve kenarlık çalışma anında uygulanır (mp4 alfa taşımaz).

Ping-pong (konuşma/bekleme) ve geçişler (~0.17 sn) `video/dogan.py` içinde.
