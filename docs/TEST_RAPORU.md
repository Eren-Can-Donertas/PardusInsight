# Test Raporu

> **Kapsam:** Otomatik testler her push'ta GitHub Actions'ta beş ortamda çalışır: Ubuntu
> (Python 3.9 ve 3.13), Windows ve **resmî Pardus 25.1 ve 25.2 kapsayıcıları**. Pardus
> kapsayıcısında bağımlılıklar Pardus deposundan kurulur ve testler root olmayan bir kullanıcıyla
> çalışır. Kapsayıcı Pardus'un kullanıcı alanını sağlar ama çekirdek GitHub sunucusunundur ve
> masaüstü oturumu yoktur. XFCE oturumu gerektiren kontroller
> [PARDUS_DOGRULAMA.md](PARDUS_DOGRULAMA.md)'de, VM'de tek komutla çalışacak biçimde
> listelenmiştir.

Tarih: 2026-11-26 · Sürüm: 0.1.0 · CI: `.github/workflows/ci.yml`, `uzun-kosu.yml`

## 0. Test planı ve izlenebilirlik (PDF bölüm 5)

| PDF ölçütü | Doğrulama | Durum |
|---|---|---|
| CPU, RAM, swap ve süreç gözlemi; "/proc veya psutil ile tutarlılık, en az 10 örnek" | `test_crosscheck_linux.py` (5 test × 10 örnek), `scripts/validate_metrics.py` tablosu (bölüm 2) | ✅ Pardus 25.1 kapsayıcısında |
| 3 açıklanabilir uyarı kuralı; "her kural için en az 1 pozitif + 1 negatif sentetik test" | `test_rules.py` (40), `test_engine.py` (18), `test_windows.py` (19), `test_scenarios_service.py` (31), mutasyon denemesi (bölüm 1.3) | ✅ her kural için 4+ pozitif, 6+ negatif |
| Zaman pencereli grafik ve CSV/JSON; "örnek sayısı/alanlar, dosyanın tekrar okunabilmesi" | `test_export.py`, `test_gui.py`, `test_cli_safety.py` (uzun kayıtların eksiksiz yazılması dahil) | ✅ |
| Root gerektirmeyen salt-okunur çalışma; "tehlikeli yazma/sonlandırma API yokluğu kod incelemesi" | `test_cli_safety.py`: AST taraması (bölüm 1.4), Pardus kapsayıcısında tüm takım `ogrenci` kullanıcısıyla | ✅ |
| Pardus 25.1 XFCE kurulum ve demo; "temiz VM'de yönergelerle başlatma" | `.deb` paketi Pardus kapsayıcısında apt ile kurulup çalıştırılıyor, GUI xvfb/xcb altında açılıyor (bölüm 4); XFCE VM: `scripts/pardus_kabul.py` | Kapsayıcıda ✅, VM'de ☐ |
| Performans: 2 sn periyot, CPU < %5, RAM < 200 MiB, 60 sn yanıt veren arayüz | `scripts/perf_check.py` (bölüm 3), `test_gui.py::test_background_sampling_keeps_gui_responsive` | ✅ Pardus 25.1 kapsayıcısında |
| 30 dk geçmiş, sınırsız bellek büyümesi olmaması | `test_normalize_history.py`, `test_scenarios_service.py`; gerçek zamanlı 35 dk: `uzun-kosu.yml` | ✅ birim; uzun koşu: bölüm 3 |
| En az 20 otomatik test; 3 kural için yanlış tetiklenme karşı-örnekleri | 316 test (bölüm 1) | ✅ |

## 1. Otomatik testler

| Ortam | Python | PySide6 | psutil | Sonuç |
|---|---|---|---|---|
| Pardus 25.1 kapsayıcısı (CI, `ogrenci` kullanıcısı) | 3.13.5 | 6.8.2.1 | 7.0.0 | ✅ 316/316 geçti (Linux'a özgü testler dahil, hiçbiri atlanmadı) |
| Pardus 25.2 kapsayıcısı (CI) | 3.13.5 | 6.8.2.1 | 7.0.0 | ✅ 316/316 geçti |
| Ubuntu 24.04 (CI, pip) | 3.9 / 3.13 | pip | pip | ✅ tümü geçti (Linux'a özgü testler dahil) |
| Windows (CI, pip) | 3.13 | pip | pip | ✅ geçti; Linux/POSIX'e özgü 9 test atlanır |
| Windows 10 (geliştirme makinesi) | 3.14.3 | 6.12.0 | 7.2.2 | ✅ 307 geçti, 9 atlandı (Linux/POSIX'e özgü) |

GUI testleri `QT_QPA_PLATFORM=offscreen` ile çalışır. Kabul betiği ayrıca Pardus kapsayıcısında
gerçek ortamda çalıştırılır (bölüm 5).

| Dosya | Test | Kapsam |
|---|---|---|
| `test_procfs.py` | 13 | `/proc` ayrıştırıcıları, eski çekirdek biçimleri, fiziksel disk filtresi, dosyaların yalnızca "r" kipinde açılması |
| `test_collectors.py` | 11 | psutil yedeği, kaybolan süreç, AccessDenied, G/Ç hızı ve PID yeniden kullanımı |
| `test_crosscheck_linux.py` | 5 | Gerçek /proc ile psutil karşılaştırması, her biri 10 örnek (yalnızca Linux) |
| `test_normalize_history.py` | 12 | Fark tabanlı hızlar, sayaç sıfırlanması, 30 dk sınırı, eşzamanlı erişim |
| `test_rules.py` | 40 | Her kural için pozitif/negatif testler, **eşik sınır değerleri**, önem/güven kuralları, açıklama metinleri |
| `test_engine.py` | 18 | Uyarı yaşam döngüsü, **yetersiz veride uyarının açık kalması**, **gözlenen örnekleme aralığı**, önem derecesinin güncel kanıtı izlemesi, günlük sınırı |
| `test_windows.py` | 19 | **Zaman pencereleri**: sınır örnekleri, düzensiz aralık, boşluk, veri yeterliliği, motorun geçmiş seçimi |
| `test_config.py` | 24 | JSON ayar dosyası tür dönüşümü, aralık denetimleri, analiz dönemi/geçmiş uyumu |
| `test_calibration.py` | 11 | Eşik kalibrasyonu: yanlış pozitifte eşik yükseltme, kaçırılan yoğun kayıtta düşürme, monotonluk |
| `test_scenarios_service.py` | 31 | 8 senaryonun uçtan uca uyarıları, **kayıtlı senaryo dosyalarının güncelliği**, tohumdan bağımsızlık, kaba aralıkta örtüşme olmaması |
| `test_export.py` | 12 | CSV/JSON gidiş-dönüş, atomik yazım, raporda kullanıcı/makine adı olmaması |
| `test_cli_safety.py` | 40 | Headless/kayıt modları, **dışa aktarma hatalarının erken bildirilmesi**, genişletilmiş AST güvenlik denetimi ve denetleyicinin kendi testleri |
| `test_packaging.py` | 14 | `.deb` yapısı, md5sums, izinler, yeniden üretilebilirlik, paketten çıkarılan başlatıcının çalışması |
| `test_pardus_kabul.py` | 55 | Kabul betiğinin ayrıştırıcıları, gizlilik temizliği, rapor biçimi, platformdan bağımsız kontroller |
| `test_gui.py` | 7 | Ana pencere, dışa aktarma, kayıt açma, arka plan örneklemede donmama |
| `test_formatting.py` | 4 | Türkçe biçimlendirme, sentetik sayaçlar |
| **Toplam** | **316** | İlk sürümde 116 |

### 1.1 Kural testleri (PDF: her kural için en az 1 pozitif + 1 negatif)

| Kural | Pozitif | Negatif (yanlış tetiklenme karşı-örneği) |
|---|---|---|
| Bellek baskısı | düşük MemAvailable + swap · kritik (3 destek) · yalnızca PSI · yalnızca major fault · eşiğin hemen altı (%9,99) · `memory` senaryosu | destekleyici gösterge yok · yalnızca son pencere düşük · tam eşikte (%10,0) · yetersiz veri · `memory_low_quiet` senaryosu |
| Kalıcı CPU | %95 sabit yük · tam sınırda (%85, oran %80) · eşik ayarı · kullanıcı penceresi · `cpu` senaryosu | kısa sıçramalar · ortalaması yüksek (%88) ama oranı düşük · yalnızca son pencere · eşik altı · `cpu_spikes` senaryosu (2 sn ve 30 sn aralıkta) |
| Disk G/Ç | önceki döneme göre artış (orta güven) · yalnızca oran koşulu (SSD, düşük güven) · tabansız meşguliyet · tam sınırlar (5 MiB/sn, %80) · `disk` senaryosu | sabit yüksek etkinlik · alt sınır altında 10× artış · tabanda da meşgul · tek kısa sıçrama · her pencerede kısa sıçramalar · yalnızca son pencere · `disk_steady` senaryosu |

### 1.2 Kod incelemesinde bulunan ve düzeltilen hatalar

Oğuz'un modülleri dört bağımsız inceleyiciyle tarandı. Her bulgu kod çalıştırılarak yeniden
üretildi, sonra ayrı bir doğrulayıcı tarafından kontrol edildi (38 bulgudan 37'si doğrulandı; bazıları farklı inceleyicilerce ayrı ayrı bulundu).
Her düzeltme, eski kodda başarısız olan regresyon testiyle commit'lendi. Başlıcaları:

| Bulgu | Etki | Düzeltme |
|---|---|---|
| Veri yetersizken (duraklatma, boşluk, ayar değişikliği) uyarı "çözüldü" sayılıyordu | Tek bir yük için birden çok uyarı, sahte çözülme | Yetersiz veri "bilinmiyor" olarak ele alınıyor |
| Kurallar gereken örnek sayısını ayardaki aralıktan hesaplıyordu | `--replay demo.json --interval 1` veya GUI'de aralık değişince **0 uyarı** | Gözlenen örnekleme aralığı kullanılıyor |
| JSON ayarlarında `2.0` gibi tam sayılar | Her turda tüm kurallar TypeError veriyordu | Tür dönüşümü ve açıklayıcı hata |
| Dışa aktarma klasörü yokken uzun kayıt | 30 dk kayıt sonunda traceback, veri kaybı | İzlemeden önce denetim |
| Sentetik kaynakta kaba aralıkta örtüşme | `cpu_spikes` karşı-örneği yanlış uyarı üretiyordu | Evre karışımı süre ağırlıklı |
| Önem derecesi hiç düşmüyordu | "Kritik" etiketi uyarı düzeyindeki kanıtla | Güncel kanıtı izliyor |
| Açıklama metinleri | %9,97 değeri "%10,0" görünüyordu, "%50'i" gibi ek hataları | Düzeltildi |

Başka üyelerin modüllerinde bulunan ve onlara bildirilen konular: `core/service.py`
(`load_recording` 1 sn altı kayıtları kesiyor, `apply_settings` kayıt analizini yeniden
çalıştırmıyor), `ui/settings_dialog.py` (iletişim kutusu aralıkları CLI'dan dar).

### 1.3 Mutasyon denemesi

Testlerin gerçekten kural mantığını sınadığını göstermek için kural, motor ve pencere kodunda 23
bilinçli hata (mutant) tek tek oluşturuldu. **23'ünün hepsi** en az bir testi düşürüyor. İlk
sürümde "her pencerede → herhangi bir pencerede", "medyan → ortalama", "oran → ortalama",
"< → <=" gibi değişikliklerin hiçbiri test düşürmüyordu.

| Mutant örnekleri | Yakalayan test |
|---|---|
| Bellek: her pencere → herhangi; `<` → `<=`; kritik için 2 destek → 1 | `test_memory_negative_only_latest_window_low`, `test_memory_available_threshold_is_strict`, `test_memory_single_support_stays_warning_even_when_very_low` |
| CPU: oran → ortalama; `>=` → `>` | `test_cpu_high_average_without_sustained_fraction_does_not_trigger`, `test_cpu_fraction_and_threshold_are_inclusive` |
| Disk: medyan → ortalama; oran koşulu kapalı; mutlak alt sınır yok | `test_disk_periodic_short_bursts_do_not_trigger`, `test_disk_ratio_condition_alone_triggers_with_low_confidence`, `test_disk_negative_large_ratio_but_below_absolute_floor` |
| Motor: bekleme süresi yok; günlük aktif uyarıyı atıyor; yetersiz veride bekletme yok | `test_short_dip_does_not_flap_alert`, `test_log_bound_keeps_every_active_alert`, `test_pause_in_sampling_does_not_resolve_and_reopen_alert` |

### 1.4 Salt-okunur güvenlik denetimi

`test_cli_safety.py`, paketin tüm kaynağını AST ile tarar. Süreç denetimi (kill, nice, exec*,
`from os import kill`, `getattr(p, "kill")()`), ağ (socket, urllib, PySide6.QtNetwork),
dosya yazma (`open(..., "w")`, `Path.write_text`, `io.open`, `os.open`, geçici dosyalar),
kalıcı ayar (`QSettings`) ve yetki yükseltme dizgileri yasaktır. Tek istisna, kullanıcının seçtiği
yola rapor yazan `export/atomic.py`'dir. Denetleyicinin kendisi 15 ihlal ve 7 izinli örnekle
sınanır.

## 2. /proc – psutil doğrulama tablosu (10 örnek)

`python3 scripts/validate_metrics.py --rounds 10 --interval 1`, resmî Pardus 25.1 kapsayıcısında
standart kullanıcıyla:

Ortam satırı: `Ortam: Pardus GNU/Linux 25 (yirmibes) · çekirdek 7.0.0-1017-azure · Python 3.13.5 · psutil 7.0.0 · 4 mantıksal CPU`

| # | MemTotal eşit | MemAvailable farkı (MiB) | SwapTotal eşit | Swap kullanılan farkı (MiB) | CPU user farkı (sn) | CPU % (/proc) | CPU % (psutil) | Disk okuma farkı (MiB) |
|---|---|---|---|---|---|---|---|---|
| 1 | evet | 0.00 | evet | 0.00 | 0.00 | 2.0 | 2.0 | 0.00 |
| 2 | evet | 0.00 | evet | 0.00 | 0.00 | 0.5 | 0.5 | 0.00 |
| 3 | evet | 0.00 | evet | 0.00 | 0.00 | 0.0 | 0.0 | 0.00 |
| 4 | evet | 0.00 | evet | 0.00 | 0.00 | 0.8 | 0.7 | 0.00 |
| 5 | evet | 0.00 | evet | 0.00 | 0.00 | 0.2 | 0.3 | 0.00 |
| 6 | evet | 0.00 | evet | 0.00 | 0.00 | 0.2 | 0.2 | 0.00 |
| 7 | evet | 0.00 | evet | 0.00 | 0.00 | 0.2 | 0.2 | 0.00 |
| 8 | evet | 0.00 | evet | 0.00 | 0.00 | 0.8 | 0.7 | 0.00 |
| 9 | evet | 0.00 | evet | 0.00 | 0.00 | 0.2 | 0.2 | 0.00 |
| 10 | evet | 0.00 | evet | 0.00 | 0.00 | 0.2 | 0.3 | 0.00 |

En büyük farklar: MemAvailable 0.00 MiB, swap 0.00 MiB, CPU user 0.00 sn, CPU % 0.1 puan, disk okuma 0.00 MiB.

İlk sürümde geliştirme makinesinde (Ubuntu 24.04) alınan tabloda da en büyük farklar
MemAvailable 1,27 MiB (iki okuma arasındaki gerçek değişim) ve CPU % 0,1 puandı.

## 3. Performans (PDF hedefleri)

`scripts/perf_check.py`, 2 sn örnekleme, 60 sn, resmî Pardus 25.1 kapsayıcısında standart
kullanıcıyla (GitHub sunucusu, 4 vCPU):

| Mod | Ortalama CPU (tek çekirdek = %100) | 4 çekirdek kapasitesine göre | RSS (en yüksek) | Tur süresi (medyan / en yüksek) | GUI olay döngüsü |
|---|---|---|---|---|---|
| GUI'siz (`--headless`) | %0,08 | %0,02 | 18,2 MiB | 1,7 / 2,0 ms | — |
| GUI + arka plan worker (offscreen) | %0,53 | %0,13 | 74,9 MiB | 1,5 / 2,6 ms | en uzun aralık 21 ms; 3008 kalp atışının 0'ı 100 ms'yi aştı → YANIT VERİYOR |

Her iki modda hedefler (CPU < %5, RAM < 200 MiB, yanıt veren arayüz) sağlandı.

- **Uzun koşu (35 dk, gerçek zamanlı):** ✅ Resmî Pardus 25.1 kapsayıcısında standart kullanıcıyla 35 dk gerçek zamanlı canlı izleme (`uzun-kosu.yml`): tampon en çok 900 örneğe ulaştı (kapasite 1801) ve son 5 dk boyunca 900'de sabit kaldı; tamponda tutulan süre 29 dk 58 sn (30 dk sınırı). Süreç belleği 31. dakikada 52,5 MiB, 35. dakikada 52,6 MiB (artış 84 KiB; sınır 10 MiB). Sınırsız bellek büyümesi yok.
- İlk sürümde geliştirme makinesinde (Ubuntu 24.04, ~494 süreç): GUI'siz %2,07, GUI %4,65 CPU,
  RSS en çok 81,3 MiB. Kapsayıcıdaki süreç sayısı çok az olduğundan oradaki CPU değerleri
  daha düşüktür. Gerçek masaüstünde ölçüm VM'de `pardus_kabul.py --gui` ile yapılmalıdır.

## 4. Paket testleri (`.deb`)

| Kontrol | Sonuç |
|---|---|
| Yapı (ar üyeleri, control, md5sums, izinler, LF, zaman damgasız gzip, yeniden üretilebilirlik) | ✅ `test_packaging.py`, her platformda |
| `dpkg-deb --info/--contents`, `desktop-file-validate` | ✅ Pardus 25.1 ve 25.2 |
| `lintian --fail-on error` | ✅ hata ve uyarı yok |
| `apt install ./pardusinsight_0.1.0_all.deb` (bağımlılıklar Pardus deposundan) | ✅ |
| Kurulu `pardusinsight` standart kullanıcıyla: `--version`, canlı izleme, `demo.json` analizi (3 uyarı) | ✅ |
| GUI gerçek X11 `xcb` eklentisiyle (xvfb) 20 sn | ✅ çökmeden çalıştı |
| `apt purge` sonrası artık dosya | ✅ yok |

## 5. Kabul betiği (Pardus 25.1 kapsayıcısı)

`scripts/pardus_kabul.py`, kapsayıcıda `.deb` paketi kurulduktan sonra standart kullanıcıyla
çalıştırılır:

| Sonuç | Pardus 25.1 | Pardus 25.2 |
|---|---|---|
| ✅ GEÇTİ | 19 | 19 |
| ❌ KALDI | 0 | 0 |
| ⏭ ATLANDI | 3 | 3 |
| ✋ MANUEL | 8 | 8 |
| ℹ BİLGİ | 1 | 1 |

- **GEÇTİ:**
  - Kurulum: 1.1 paketler Pardus deposunda, 1.2 kurulum, 1.4 `.deb` paketi ve menü kaydı
    (`desktop-file-validate` ile).
  - Güvenlik: 2.1–2.6. Ağ bağlantısı yok, ev dizininde dosya oluşmuyor, root süreçlerinin G/Ç
    alanları boş.
  - Ölçüm doğruluğu: 3.1–3.3. `free -b` ile MemTotal birebir eşit, MemAvailable farkı 0.
  - Performans ve işlevler: 4.1, 5.1–5.5 ve 5.8.
- **ATLANDI:** 4.1b ve 5.9 grafik oturum gerektirir. 4.2 bu işte `--uzun` olmadan çalıştı; ayrı
  uzun koşuda ✅.
- **MANUEL:** 1.3 (venv), 1.5 (XFCE menüsü), 3.3b (htop), 4.3, 5.3b (LibreOffice), 5.6, 5.7
  (koyu tema), 6 (kalibrasyon). Bunlar masaüstü oturumu veya gerçek kullanım gerektirir; VM'de
  aynı betikle yapılır.
- **BİLGİ:** 3.4 PSI. Kapsayıcıda GitHub çekirdeği kullanılır; Pardus çekirdeği VM'de görülür.

Kabul betiği de bağımsız bir incelemeden geçti. Gerçek Pardus koşusunun sonuçları
inceleyiciye verildi; bulunan 9 sorunun (1 orta, 8 düşük) hepsi düzeltildi.

## 6. Doğrulanmayanlar / açık riskler

| Konu | Durum |
|---|---|
| Pardus çekirdeğinde PSI | Kapsayıcı GitHub çekirdeğini kullanır. Debian çekirdeklerinde PSI varsayılan olarak kapalı olabilir; kural swap ve major fault ile çalışır. VM'de betik ortam tablosuna yazar |
| XFCE oturumunda görünüm, menü, koyu tema, yüksek DPI | VM'de elle (PARDUS_DOGRULAMA 1.5, 4.3, 5.7) |
| Gerçek kullanım verisiyle eşik kalibrasyonu | Araç hazır; 30 dk VM kaydı gerekir (`--kalibrasyon-suresi 1800`) |
| Düşük kaynaklı VM'de (2 vCPU) performans | VM'de `pardus_kabul.py --gui` |
| GNOME/Wayland uyumluluğu | Ölçülmedi (ek hedef) |
