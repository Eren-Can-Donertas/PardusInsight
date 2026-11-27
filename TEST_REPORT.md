# Test Raporu

> **Kapsam:** Bu rapordaki bütün sonuçlar **geliştirme makinesinde** gerçekten çalıştırılarak
> elde edildi. **Pardus 25.1 XFCE üzerinde hiçbir test çalıştırılmadı (NOT TESTED).** Pardus
> sonuçları [PARDUS_VALIDATION.md](PARDUS_VALIDATION.md) uygulandıkça bu dosyanın 8. bölümüne
> eklenmelidir.

**Ortam:** Ubuntu 24.04.4 LTS · Linux 7.0.0-43-generic · x86-64 · 16 mantıksal CPU · 15,3 GiB
RAM · 4 GiB swap · PSI etkin · Python 3.12.3. GUI testleri `QT_QPA_PLATFORM=offscreen` ile,
yani gerçek pencere yöneticisi olmadan çalıştırıldı. **Tarih:** 27 Kasım 2026 ·
**Dal:** `asama2-teslim`

## 1. Otomatik test koşuları

| # | Koşu | Ortam | Geçti | Başarısız | Atlandı | Süre |
|---|---|---|---|---|---|---|
| 1 | `python -m pytest -q` | PySide6 6.12.0, psutil 7.2.2, pytest 9.2.0 | **136** | 0 | 0 | ~13 sn |
| 2 | Aynı paket, Debian 13'teki PySide6 sürümüyle | PySide6 6.8.2.1, psutil 5.9.8, pytest 8.3.5 (ayrı sanal ortam) | **136** | 0 | 0 | ~13 sn |
| 3 | Bağımlılıksız Python (`python3 -m pytest -q`) | Sistem Python 3.12.3; psutil ve PySide6 yok | **121** | 0 | 7 | ~6 sn |
| 4 | Yalnız deterministik testler (`-m "not linux"`) | Koşu 1 ortamı | **130** | 0 | 6 seçilmedi | ~9 sn |
| 5 | **Teslim ZIP'inden temiz kurulum** (yeni venv, `pip install -r requirements-dev.txt`) | PySide6 6.12.0, psutil 7.2.2 | **136** | 0 | 0 | ~13 sn |

Koşu 3'te atlananlar şunlar: canlı /proc–psutil karşılaştırması (5), gerçek süreç taraması (1)
ve GUI test modülü (1 modül, 9 test). Bu koşu, Linux dışındaki veya eksik kurulu ortamlarda
çekirdek mantığın ve sentetik verinin test edilebildiğini gösterir.

### 1.1 Test envanteri

| Dosya | Test | Kapsam |
|---|---|---|
| `test_procfs.py` | 13 | `/proc` ayrıştırıcıları, eski çekirdek biçimleri, eksik alanlar, fiziksel disk filtresi, dosyaların yalnızca `"r"` kipinde açılması |
| `test_collectors.py` | 12 | psutil yedeği, kaynaksız çalışma, **NoSuchProcess**, **AccessDenied**, **PermissionError**, PID yeniden kullanımı, yarıda kesilen tarama, gerçek sistemde sonlanan çocuk süreçler |
| `test_normalize_history.py` | 13 | CPU farkı, swap ve major/minor fault, disk hızları ve kümülatif baytlar, sayaç sıfırlanması, saat geri alınması, 30 dk sınırı, sabit kapasite, eşzamanlı erişim |
| `test_rules.py` | 30 | 3 kural × (pozitif, negatif, **eşik sınırı**, yanlış alarm karşı-örneği), CPU süreç kaynağı |
| `test_engine.py` | 8 | Uyarı yaşam döngüsü, dalgalanma koruması, kural hatası yalıtımı, günlük sınırı, deterministik yeniden analiz, açıklama içeriği, ayar doğrulama |
| `test_scenarios_service.py` | 17 | 8 sentetik senaryo uçtan uca, tohum belirlenimciliği, hatalı kaynakta `tick()`, süreç listesi sıklığı, kayıt yükleme ve canlıya dönüş, aralık değişince tampon kapasitesi |
| `test_export.py` | 13 | CSV/JSON gidiş-dönüş, geçersiz rapor mesajları, atomik yazım, boş dışa aktarma, kullanıcı/makine adı bulunmaması, `data_source` ve birimler |
| `test_cli_safety.py` | 12 | Headless mod, kayıt analizi, hatalı argümanlar, istek olmadan dosya yazılmaması, sentetik etiket, metodoloji, **AST ile yasak modül/çağrı taraması**, `open()` kip denetimi |
| `test_gui.py` | 9 | Pencere güncelleme, dışa aktarma, kayıt açma, **donmama** (300 ms'lik yavaş kaynakla), grafik boşlukları, süreç tablosu, ayarlar, demo şeridi, **açılış/kapanış smoke testi** |
| `test_crosscheck_linux.py` | 5 | Canlı /proc ile psutil karşılaştırması (10'ar örnek) |
| `test_formatting.py` | 4 | Türkçe biçimlendirme, sentetik sayaçlar |
| **Toplam** | **136** | |

### 1.2 Kural testleri

| Kural | Pozitif | Negatif / yanlış alarm karşı-örneği | Eşik sınırı |
|---|---|---|---|
| Bellek baskısı | düşük MemAvailable + swap; kritik (3 destek); yalnızca PSI (swap yok); `memory` senaryosu | destek yok; yalnızca son pencere düşük; yetersiz veri; `memory_low_quiet` | %10,0 → tetiklemez, %9,99 → tetikler; swap 100,0 → destek, 99,9 → değil |
| Kalıcı CPU | %95 sabit + süreç bağlamı; eşik ayarı; kullanıcı penceresi (2×20 sn); `cpu` senaryosu | kısa sıçramalar; yalnızca son pencere; eşik altı; `cpu_spikes` | 15 örnekten 12'si (%80) → tetikler, 11'i → tetiklemez |
| Disk G/Ç | önceki döneme göre artış; tabansız meşguliyet; `disk` senaryosu | sabit yüksek etkinlik; alt sınır altında 10× artış; taban döneminde de meşgul; tek kısa sıçrama; `disk_steady` | 5,00 MiB/sn → tetikler, 4,99 → tetiklemez; meşguliyet %80,0 → tetikler, %79,9 → tetiklemez |
| CPU süreç kaynağı | 3 × cc1plus → "cc1plus (3 süreç) kaynaklı" (%93,8) | 5 eşit süreç → "dağılmış"; süreç verisi yok → "belirlenemedi" | — |

### 1.3 Uçtan uca senaryolar (`scripts/generate_scenarios.py`, tohum 461, 2 sn aralık)

| Senaryo | Süre | Beklenen | Üretilen | Sonuç |
|---|---|---|---|---|
| demo | 500 sn | CPU, bellek, disk | sustained_cpu, memory_pressure, disk_io_anomaly | PASS |
| cpu | 420 sn | CPU | sustained_cpu | PASS |
| memory | 420 sn | bellek | memory_pressure | PASS |
| disk | 660 sn | disk | disk_io_anomaly | PASS |
| cpu_spikes | ~660 sn | yok | yok | PASS |
| memory_low_quiet | 360 sn | yok | yok | PASS |
| disk_steady | 900 sn | yok | yok | PASS |
| normal | 1200 sn | yok | yok | PASS |

## 2. Statik denetim

| Araç | Yapılandırma | Sonuç |
|---|---|---|
| ruff 0.15.17 | `E, F, W, B`, satır 100, hedef py39 (`pyproject.toml`) | **All checks passed** (`pardusinsight`, `tests`, `scripts`) |
| mypy 2.4.1 | `ignore_missing_imports`, `warn_unused_ignores` | **No issues found in 33 source files** |
| `sh -n` | `scripts/pardus_validate.sh`, `scripts/install_user.sh` | Sözdizimi geçerli |
| desktop-file-validate | `install_user.sh` çıktısı | Geçerli |
| shellcheck | — | **Yapılamadı** (bu makinede kurulu değil) |

İlk mypy koşusu 45 sorun buldu ve hepsi düzeltildi. Bunlardan biri gerçek bir kusurdu:
`MainWindow.thread` niteliği `QObject.thread()` metodunu gölgeliyordu. Ruff'ın pyupgrade (UP)
kuralları bilerek seçilmedi; seçilseydi `Optional[X]` → `X | None` gibi yalnızca tarzla ilgili
~400 öneri gelecekti ve kod Python 3.9 uyumunu korumak için `typing` yazımını kullanıyor.

## 3. /proc – psutil doğrulama tablosu (10 örnek)

`python scripts/validate_metrics.py --rounds 10 --interval 1` (Aşama 1: "en az 10 örnek karşılaştırma").

| # | MemTotal eşit | MemAvailable farkı (MiB) | SwapTotal eşit | Swap kullanılan farkı (MiB) | CPU user farkı (sn) | CPU % (/proc) | CPU % (psutil) | Disk okuma farkı (MiB) |
|---|---|---|---|---|---|---|---|---|
| 1 | evet | 0.00 | evet | 0.00 | 0.00 | 9.4 | 9.5 | 0.00 |
| 2 | evet | 0.00 | evet | 0.00 | 0.00 | 7.5 | 7.4 | 0.00 |
| 3 | evet | 0.00 | evet | 0.00 | 0.00 | 5.0 | 5.0 | 0.00 |
| 4 | evet | 0.00 | evet | 0.00 | 0.00 | 5.3 | 5.2 | 0.00 |
| 5 | evet | 0.00 | evet | 0.00 | 0.00 | 6.9 | 6.9 | 0.00 |
| 6 | evet | 0.00 | evet | 0.00 | 0.00 | 8.1 | 8.0 | 0.00 |
| 7 | evet | 0.00 | evet | 0.00 | 0.00 | 3.3 | 3.3 | 0.00 |
| 8 | evet | 0.00 | evet | 0.00 | 0.00 | 4.8 | 4.8 | 0.00 |
| 9 | evet | 0.00 | evet | 0.00 | 0.00 | 7.5 | 7.5 | 0.00 |
| 10 | evet | 0.00 | evet | 0.00 | 0.00 | 9.9 | 9.9 | 0.00 |

En büyük farklar: MemAvailable 0,00 MiB, swap 0,00 MiB, CPU user 0,00 sn, CPU % 0,1 puan, disk
okuma 0,00 MiB.

## 4. Performans (Aşama 1 hedefleri)

`scripts/perf_check.py`, canlı sistem (~500 süreç), 2 sn aralık, 60 sn.

| Mod | Ortalama CPU (tek çekirdek = %100) | Toplam kapasiteye göre | RSS en yüksek | Tur süresi medyan / maks | GUI olay döngüsü |
|---|---|---|---|---|---|
| GUI'siz | %2,03 | %0,13 | 19,6 MiB | 41,7 / 52,1 ms | — |
| GUI + worker (offscreen) | %4,09 | %0,26 | 82,1 MiB | 43,7 / 65,1 ms | En uzun aralık 29 ms; 2993 kalp atışından 0'ı 100 ms'yi aştı → **yanıt veriyor** |

| Hedef | Ubuntu (bu makine) | Pardus VM |
|---|---|---|
| 2 sn örnekleme | PASS | NOT TESTED |
| 30 dk sınırlı tampon, sınırsız büyüme yok | PASS (birim testi; 60 sn'de RSS sabit) | NOT TESTED (35 dk koşu gerekli) |
| 60 sn GUI yanıt verebilirliği | PASS | NOT TESTED |
| Ortalama CPU < %5 | PASS (%4,09; sınıra yakın) | NOT TESTED |
| RAM < 200 MiB | PASS (82 MiB) | NOT TESTED |

**Yapılan optimizasyonlar ve etkileri:**

| Adım | GUI CPU (60 sn) | Açıklama |
|---|---|---|
| İlk ölçüm | %5,04 | `QSortFilterProxyModel` 500 satırda her turda ~6000 Python `data()` çağrısı yapıyordu |
| Model içinde sıralama/filtre, süreç tablosu yalnızca görünürken | %4,65 | GUI turu 17–32 ms → 3–9 ms |
| Grafikler yalnızca Genel Bakış görünürken | %4,09 | Son ölçüm |

Ölçüme `perf_check.py`'nin kendi 50 Hz kalp atışı zamanlayıcısı da dahildir. Maliyetin büyük
kısmı süreç taramasıdır. Gerekirse *Ayarlar → Süreç listesi sıklığı = 2* ayarı bu maliyeti
yarıya indirir.

## 5. Güvenlik denetimi

| Kontrol | Yöntem | Sonuç |
|---|---|---|
| Yasak modüller (subprocess, socket, urllib, http, requests, ctypes, signal, shutil, multiprocessing…) | AST taraması, `pardusinsight/` | PASS (yok) |
| Süreç denetimi ve yıkıcı çağrılar (kill, terminate, suspend, send_signal, nice, ionice, cpu_affinity, remove, chmod…) | AST taraması | PASS (yok) |
| `open()` yalnızca `"r"`/`"rb"` (dışa aktarma modülü hariç) | AST + çalışma zamanı kip izleme | PASS |
| Yetki yükseltme dizgileri (sudo, pkexec, modprobe, insmod, sysctl -w, drop_caches) | Metin taraması | PASS (yok) |
| Açık istek olmadan dosya yazılmaması | Boş klasör/HOME ile 60 turluk koşu | PASS |
| Raporda kullanıcı/makine adı bulunmaması | JSON içerik testi | PASS |
| Root ile başlatma | Yalnızca bilgi uyarısı | PASS |

## 6. Teslim paketi (ZIP) denetimi

`python scripts/build_submission.py` → `dist/PardusInsight.zip`

| Kontrol | Sonuç |
|---|---|
| Kök yapısı: `source_code/`, `README.md`, `technical_report.pdf`, `VIDEO_LINK.txt` (A2 §3) | PASS |
| `.git/`, `.venv/`, `__pycache__/`, `.pytest_cache/`, `*.pyc`, log, `.env`/anahtar dosyası yok | PASS |
| Geliştirici belgeleri (bu dosya, matris, Pardus listesi, video planı, sözlü sınav, son kontrol) ZIP dışında | PASS |
| Kurs PDF'leri ve kişisel dosyalar dışarıda | PASS (yalnızca `git ls-files`) |
| 2 MiB'tan büyük dosya yok | PASS (en büyüğü `technical_report.pdf`, ~0,8 MiB) |
| Kök README'deki göreli bağlantılar `source_code/` içine çözülüyor; ZIP'te olmayan belgeler düz metin | PASS |
| `VIDEO_LINK.txt` ilk satırı `VIDEO_LINK_PENDING` (sahte URL yok) | PASS → **ön teslim** |
| Boyut | 73 dosya, ~850 KiB sıkıştırılmış |
| **Temiz kurulum:** ZIP yeni bir klasöre açıldı → `source_code/` içinde yeni sanal ortam → `pip install -r requirements-dev.txt` → `pytest` 136/136 → `--replay scenarios/demo.json` (3 uyarı, sentetik başlık) → 6 sn canlı headless + CSV/JSON (`data_source=linux`, `is_synthetic=false`) → `pip install .` → `pardusinsight --version` | PASS (Ubuntu) |

## 7. Doğrulanmayanlar ve açık riskler

| Konu | Durum |
|---|---|
| Pardus 25.1 XFCE'de kurulum, çalışma, performans | **NOT TESTED.** Ortamda Pardus yok. `pardus/yirmibes` Docker imajını indirme izni araç tarafından reddedildi |
| Pardus çekirdeğinde PSI desteği | Bilinmiyor |
| XFCE pencere yöneticisinde görünüm, tema, yüksek DPI | Yalnızca offscreen render. Gerçek XFCE ile denenmedi |
| Eşik kalibrasyonu ve olağan kullanımda yanlış pozitif oranı | Yapılmadı |
| Düşük kaynaklı VM (2 vCPU) ve uzun süreli (≥ 35 dk) koşu | Ölçülmedi |
| Python 3.9–3.11 ve 3.13 ile çalışma | Test edilmedi (yalnızca 3.12.3). Kod 3.9 sözdizimine göre yazıldı (ruff hedef py39) |
| GNOME/Wayland | Ölçülmedi (ek hedef) |
| shellcheck | Araç yok, çalıştırılmadı |

## 8. Pardus sonuçları

*(Ekip dolduracak: `sh scripts/pardus_validate.sh` çıktısındaki `ozet.txt` ve
PARDUS_VALIDATION.md kabul listesi buraya eklenecek. Konteyner testi yapılırsa
"kısmi — kullanıcı alanı" olarak ayrı etiketlenmelidir.)*
