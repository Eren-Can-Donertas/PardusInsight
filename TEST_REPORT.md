# Test Raporu

> **Kapsam uyarısı:** Bu rapordaki tüm sonuçlar **geliştirme makinesinde** elde edildi.
> **Pardus 25.1 XFCE üzerinde henüz hiçbir test çalıştırılmadı.** Pardus sonuçları
> [PARDUS_DOGRULAMA.md](PARDUS_DOGRULAMA.md) uygulandıkça bu rapora ayrı bir bölüm olarak eklenmelidir.

**Geliştirme ortamı:** Ubuntu 24.04.4 LTS · Linux 7.0.0-42-generic · x86-64, 16 mantıksal CPU,
15,3 GiB RAM, 4 GiB swap, PSI etkin · Python 3.12.3 · psutil 7.2.2 · PySide6 6.12.0 ·
pytest 9.2.0 · GUI testleri `QT_QPA_PLATFORM=offscreen` ile (gerçek pencere yöneticisi olmadan).
Tarih: 2026-11-23.

## 1. Otomatik testler

```bash
.venv/bin/python -m pytest -q
# 116 passed in ~13 s
```

İkinci koşu, psutil ve PySide6 **kurulu olmayan** sistem Python'uyla (`python3 -m pytest -q`)
yapıldı: **103 passed, 7 skipped**. Atlanan testler canlı /proc–psutil karşılaştırması (5),
gerçek süreç taraması (1) ve GUI test modülüdür. Bu sonuç, Linux dışındaki veya eksik kurulu
geliştirme ortamlarında çekirdek mantığın ve sentetik verinin test edilebildiğini gösterir.

| Dosya | Test | Kapsam |
|---|---|---|
| `test_procfs.py` | 13 | `/proc` ayrıştırıcıları (meminfo, stat, vmstat, diskstats, pressure), eski çekirdek biçimleri, fiziksel disk filtresi, sahte /proc ağacı, **dosyaların yalnızca "r" kipinde açıldığı** |
| `test_collectors.py` | 11 | /proc → psutil yedeği, kaynak yokken çökmeme, süreç CPU normalizasyonu, **kaybolan süreç (NoSuchProcess)**, **AccessDenied**, G/Ç hızı ve PID yeniden kullanımı, yarıda kesilen tarama, gerçek sistemde sonlanan çocuk süreçler |
| `test_normalize_history.py` | 12 | Fark tabanlı CPU/swap/disk hızları, sayaç sıfırlanması, saat geri alınması, **30 dk sınırı (2000 örnek → 901)**, sabit kapasite, eşzamanlı okuma/yazma |
| `test_rules.py` | 17 | **Her kural için pozitif ve negatif sentetik testler** (aşağıdaki tablo) |
| `test_engine.py` | 8 | Uyarı yaşam döngüsü, dalgalanma koruması, hatalı kuralın yalıtımı, günlük sınırı, deterministik yeniden analiz, açıklama içeriği, ayar doğrulama |
| `test_scenarios_service.py` | 17 | 8 sentetik senaryonun uçtan uca beklenen uyarıları, tohum belirlenimciliği, hatalı kaynakta `tick()`'in çökmemesi, süreç listesi sıklığı, kayıt yükleme/canlıya dönüş, ayar değişikliği |
| `test_export.py` | 12 | CSV/JSON gidiş-dönüş (dosyanın tekrar okunabilmesi), geçersiz rapor mesajları, atomik yazım, boş dışa aktarma, **raporda kullanıcı/makine adı bulunmaması** |
| `test_cli_safety.py` | 10 | Headless mod, kayıt analizi, hatalı argümanlar, **açık istek olmadan dosya yazılmaması**, AST ile yasak modül/çağrı taraması (subprocess, socket, kill, terminate, nice…), `open()` kiplerinin denetimi |
| `test_crosscheck_linux.py` | 5 | Gerçek /proc ile psutil karşılaştırması, her biri **10 örnek** |
| `test_gui.py` | 7 | Ana pencere güncellemesi, dışa aktarma, kayıt açma, **arka plan örneklemede GUI'nin donmaması**, grafik boşlukları, süreç tablosu sıralama/filtre, ayar penceresi |
| `test_formatting.py` | 4 | Türkçe sayı/bayt/süre biçimleri, sentetik kaynak sayaçları |
| **Toplam** | **116** | |

### Kural testleri (PDF: her kural için en az 1 pozitif + 1 negatif)

| Kural | Pozitif testler | Negatif (yanlış tetiklenme karşı-örneği) testler |
|---|---|---|
| Bellek baskısı | düşük MemAvailable + swap · kritik (3 destek) · yalnızca PSI ile (swap yok) · `memory` senaryosu | destekleyici gösterge yok · yalnızca son pencere düşük · yetersiz veri · `memory_low_quiet` senaryosu |
| Kalıcı CPU | %95 sabit yük + süreç bağlamı · eşik ayarı · kullanıcı penceresi · `cpu` senaryosu | kısa sıçramalar · yalnızca son pencere yüksek · eşik altı · `cpu_spikes` senaryosu |
| Disk G/Ç | önceki döneme göre artış · tabansız meşguliyet · `disk` senaryosu | sabit yüksek etkinlik · mutlak alt sınır altında 10× artış · taban döneminde de meşgul · tek kısa sıçrama · `disk_steady` senaryosu |

Uçtan uca senaryo sonuçları (`scripts/generate_scenarios.py`, tohum 461, 2 sn aralık):

| Senaryo | Simülasyon süresi | Beklenen | Üretilen uyarı |
|---|---|---|---|
| `demo` | 500 sn | CPU, bellek, disk | sustained_cpu, memory_pressure, disk_io_anomaly |
| `cpu` | 420 sn | CPU | sustained_cpu |
| `memory` | 420 sn | bellek | memory_pressure |
| `disk` | 660 sn | disk | disk_io_anomaly |
| `cpu_spikes` | ~660 sn | yok | yok |
| `memory_low_quiet` | 360 sn | yok | yok |
| `disk_steady` | 900 sn | yok | yok |
| `normal` | 1200 sn (ilk 20 dk) | yok | yok |

## 2. /proc – psutil doğrulama tablosu (10 örnek)

`python3 scripts/validate_metrics.py --rounds 10 --interval 1` (geliştirme makinesi):

| # | MemTotal eşit | MemAvailable farkı (MiB) | SwapTotal eşit | Swap kullanılan farkı (MiB) | CPU user farkı (sn) | CPU % (/proc) | CPU % (psutil) | Disk okuma farkı (MiB) |
|---|---|---|---|---|---|---|---|---|
| 1 | evet | 0.00 | evet | 0.00 | 0.00 | 20.1 | 20.2 | 0.00 |
| 2 | evet | 0.00 | evet | 0.00 | 0.00 | 16.7 | 16.8 | 0.00 |
| 3 | evet | 0.00 | evet | 0.00 | 0.00 | 11.5 | 11.4 | 0.00 |
| 4 | evet | 0.00 | evet | 0.00 | 0.00 | 14.1 | 14.1 | 0.00 |
| 5 | evet | 0.00 | evet | 0.00 | 0.00 | 16.8 | 16.8 | 0.00 |
| 6 | evet | 0.00 | evet | 0.00 | 0.00 | 18.3 | 18.3 | 0.00 |
| 7 | evet | 0.00 | evet | 0.00 | 0.00 | 16.1 | 16.2 | 0.00 |
| 8 | evet | 1.27 | evet | 0.00 | 0.00 | 15.3 | 15.2 | 0.00 |
| 9 | evet | 0.00 | evet | 0.00 | 0.00 | 16.2 | 16.2 | 0.00 |
| 10 | evet | 0.00 | evet | 0.00 | 0.00 | 14.3 | 14.4 | 0.00 |

En büyük farklar: MemAvailable 1,27 MiB (iki okuma arasındaki gerçek değişim), CPU % 0,1 puan.
CPU yüzdesi psutil ile aynı tanım (meşgul = toplam − idle − iowait) kullanılarak hesaplandığı
için farklar yalnızca okuma anlarının kaymasından gelir.

## 3. Performans (PDF hedefleri)

`scripts/perf_check.py`, 2 sn örnekleme, canlı sistem (~494 süreç), 60 sn:

| Mod | Ortalama CPU (tek çekirdek = %100) | Toplam kapasiteye göre | RSS (en yüksek) | Tur süresi (medyan / en yüksek) | GUI olay döngüsü |
|---|---|---|---|---|---|
| GUI'siz (`--headless`) | %2,07 | %0,13 | 19,3 MiB | 38,5 / 59,8 ms | — |
| GUI + arka plan worker (offscreen) | %4,65 | %0,29 | 81,3 MiB | 47,7 / 117,3 ms | en uzun aralık 33 ms; 3022 kalp atışının 0'ı 100 ms'yi aştı |

- **CPU < %5:** Bu makinede sağlandı, ancak GUI modunda sınıra yakın. GUI ölçümüne ölçüm
  betiğinin kendi 50 Hz kalp atışı zamanlayıcısı da dahildir. Maliyetin büyük kısmı süreç
  taramasıdır (~500 süreçte tur başına 40–60 ms). Gerekirse **Ayarlar → Süreç listesi sıklığı = 2**
  bu maliyeti yarıya indirir.
- **RAM < 200 MiB:** Sağlandı (81 MiB). 60 sn içinde büyüme yok. 30 dk sınırı birim testleriyle
  doğrulandı. Uzun süreli (35 dk+) gerçek ölçüm Pardus'ta yapılmalı.
- **Donmayan GUI:** Örnekleme `QThread` içinde yapılır. Yapay olarak 300 ms süren ölçüm
  turlarında bile GUI olay döngüsü 250 ms'den uzun bloklanmadı (`test_gui.py`).

**Yapılan optimizasyon:** İlk ölçümde GUI modu %5,04 çıktı. Profil, `QSortFilterProxyModel`'in
~500 satırı her turda sıralarken Python `data()` metodunu ~6000 kez çağırdığını gösterdi.
Sıralama ve filtreleme model içinde tek bir `sorted()` çağrısına taşındı. Süreç tablosu da
yalnızca sekme görünürken güncelleniyor. GUI güncelleme maliyeti tur başına 17–32 ms'den
3–9 ms'ye indi.

## 4. Doğrulanmayanlar / açık riskler

| Konu | Durum |
|---|---|
| Pardus 25.1 XFCE'de kurulum ve çalışma | **Doğrulanmadı.** Paket adları Debian 13 deposuna göre yazıldı |
| Pardus çekirdeğinde PSI desteği | Bilinmiyor. PSI yoksa bellek kuralı swap/page-fault ile çalışır |
| XFCE gerçek pencere yöneticisinde görünüm, tema, yüksek DPI | Yalnızca offscreen ekran görüntüleriyle (açık/koyu palet) kontrol edildi |
| Eşik kalibrasyonu | Yapılmadı. Varsayılanlar sentetik senaryolara göre seçildi |
| Düşük kaynaklı VM'de (2 vCPU) performans | Ölçülmedi |
| Uzun süreli (≥ 35 dk) çalışma | Bellek sınırı birim testiyle doğrulandı, gerçek uzun koşu yapılmadı |
| GNOME/Wayland uyumluluğu | Ölçülmedi (ek hedef) |
