# Mimari

## Veri akışı

```
              ┌──────────────── arka plan QThread (SamplerWorker, QTimer 2 sn) ───────────────┐
 /proc, /sys  │ LinuxSystemCollector ──RawSnapshot──┐                                         │
 psutil ──────│ ProcessCollector ──ProcessSnapshot──┴─► Normalizer ─SystemSample─► HistoryBuffer│
              │                                                                      │        │
              │                                          RuleEngine ◄──── son 7 dk ──┘        │
              │                                              │ EngineUpdate (yeni/çözülen/aktif)│
              └──────────────────────── TickResult (Qt sinyali, kuyruklu) ─────────────────────┘
                                                             ▼
                         GUI iş parçacığı: kutucuklar, grafikler, süreç tablosu, uyarı paneli
                                                             │ (yalnızca kullanıcı isterse)
                                                             ▼
                                               CSV / JSON raporu (atomik yazım)
```

## Katmanlar ve sorumluluklar

| Katman | Modül | Görev | Sorumlu (PDF) |
|---|---|---|---|
| 1–2 | `collectors/procfs.py` | `/proc/stat`, `meminfo`, `vmstat`, `diskstats`, `loadavg`, `pressure/*` için saf ayrıştırıcılar; `/sys/block` ile fiziksel disk seçimi | Eren |
| 1–2 | `collectors/system.py` | Bölüm bazında /proc okuma; başarısız bölüm için psutil yedeği; hatalar `errors` alanında | Eren |
| 1–2 | `collectors/processes.py` | psutil ile süreç taraması; `NoSuchProcess`/`AccessDenied` toleransı; süreç G/Ç hızları; PID yeniden kullanımına karşı `(pid, create_time)` anahtarı | Eren |
| 1–2 | `collectors/synthetic.py` | Evre tabanlı deterministik senaryolar (stres testi yerine) | Oğuz |
| 3 | `core/normalize.py` | Kümülatif sayaç → hız/yüzde; sayaç sıfırlanmasında negatif yerine `None`; monotonik zaman damgası | Eren |
| 3 | `core/history.py` | 30 dk yaş sınırı + sabit `deque(maxlen)` kapasitesi; kilitli anlık kopya | Eren |
| 3 | `core/service.py` | `MonitorService.tick()`: topla → normalize → tampon → analiz; asla istisna fırlatmaz | Eren / Oğuz |
| 4 | `analysis/windows.py`, `rules.py` | Ardışık pencereler, 3 kural, kanıt/belirsizlik üretimi | Oğuz |
| 4 | `analysis/engine.py` | Uyarı yaşam döngüsü (yeni → güncel → çözüldü, bekleme süreli), kural hatası yalıtımı, kayıt yeniden analizi | Oğuz |
| 4–5 | `analysis/explain.py` | Uyarının metin/HTML açıklaması (Qt'den bağımsız) | Oğuz / Yusuf |
| 5 | `export/` | CSV (örnek + uyarı), JSON rapor, geri okuma, atomik yazım | Yusuf |
| 5 | `ui/` | Ana pencere, QPainter grafikleri, süreç tablosu, uyarı paneli, ayarlar, worker | Yusuf |
| — | `cli.py` | GUI / headless / sentetik / kayıt modu girişleri | Oğuz |

## Önemli tasarım kararları

1. **Qt'den bağımsız çekirdek.** Toplama, normalizasyon, tampon ve kurallar saf Python'dur.
   Testler ekran olmadan çalışır. PySide6 kurulamayan bir ortamda `--headless` modu aynı
   analizi komut satırında sunar (PDF'deki risk planı).
2. **Arka plan örnekleme.** `/proc` okuma ve süreç taraması (yaklaşık 500 süreçte 40–60 ms)
   `QThread` içinde yapılır. Zamanlayıcı worker iş parçacığında yaşadığı için uzun bir tur
   sonraki turla çakışmaz, yalnızca gecikir. GUI'ye yalnızca değişmez (frozen) veri nesneleri
   sinyalle iletilir.
3. **Sınırlı bellek.** `HistoryBuffer` iki sınır uygular: yaş (varsayılan 30 dk) ve sabit
   kapasite (`ceil(30 dk / 1 sn) + 1`). Kural motoru yalnızca son
   `2 × 30 sn + 300 sn + 30 sn` veriye bakar. Uyarı günlüğü en fazla 200 kayıt tutar.
4. **Fark tabanlı ölçüm.** CPU yüzdesi `/proc/stat` farklarından psutil ile aynı tanımla
   hesaplanır (meşgul = toplam − idle − iowait). Swap/page-fault/disk hızları sayaç
   farkı / monotonik süre farkıdır. İlk örnekte hızlar bilinmez (`None`).
5. **Saat değişikliklerine dayanıklılık.** Örnek zaman damgası `ilk duvar saati + (monotonik − ilk monotonik)`
   olarak hesaplanır. NTP veya elle yapılan saat değişikliği pencereleri bozmaz.
6. **Özellik algılama.** PSI (`/proc/pressure`) yoksa ilgili kanıt "ölçülemedi" olarak işaretlenir
   ve kural diğer göstergelerle çalışır. `MemAvailable` yoksa (çok eski çekirdek) tahmini değer
   kullanılır ve bu durum işaretlenir.
7. **Çift sayımı önleme.** Disk toplamına yalnızca `/sys/block` altındaki fiziksel diskler girer.
   `loop`, `dm-*`, `md*`, `zram`, `sr` ve bölümler dışlanır.
8. **Hafif grafikler.** QtCharts yerine QPainter ile yazılmış bir grafik kullanılır, böylece ek paket
   gerekmez. Her piksel sütunu için min/maks noktaları tutularak seyreltme yapılır.

## İş parçacığı modeli

| Nesne | Yaşadığı iş parçacığı | Paylaşım |
|---|---|---|
| `MonitorService`, kolektörler, `RuleEngine` | worker | Yalnızca worker çağırır |
| `HistoryBuffer` | worker yazar, GUI okur | `threading.Lock` + kopya döndürme |
| `TickResult`, `Alert`, `SystemSample` | — | Değişmez dataclass'lar, sinyalle taşınır |
| Ayar/duraklatma/kayıt yükleme istekleri | GUI → worker | Kuyruklu Qt sinyalleri |

Kapanışta zamanlayıcı `BlockingQueuedConnection` ile worker iş parçacığında durdurulur, ardından
iş parçacığının bitmesi beklenir.
