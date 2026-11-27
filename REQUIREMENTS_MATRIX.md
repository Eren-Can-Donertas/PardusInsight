# Gereksinim İzlenebilirlik Matrisi

**Kaynaklar:**
- **A1** = `BIL461_PardusInsight.pdf` (Aşama 1 önerisi, üç kişilik son sürüm)
- **A2** = `BIL461-Proje-Asama2.pdf` (hocanın nihai teslim yönergesi)
- **G** = ekibin Aşama 2 görev tanımı

`~/Downloads/BIL461_PardusInsight_SON.pdf` iki kişilik eski bir taslaktır (16 Ekim 2026), bu
yüzden referans alınmadı. Hocanın Aşama 1 geri bildirimi çalışma ortamında bulunamadı; geri
bildirim varmış gibi davranılmadı.

**Sonuç değerleri:**
- **PASS:** Geliştirme makinesinde (Ubuntu 24.04.4, Python 3.12.3, PySide6 6.12.0, psutil
  7.2.2) gerçekten çalıştırılan test veya ölçümle doğrulandı.
- **NOT TESTED:** Doğrulanmadı.
- **FAIL:** Karşılanmadı.

Pardus'a özgü maddeler Pardus'ta doğrulanmadıkça PASS sayılmaz. Tarih: 27 Kasım 2026.

## 1. İşlevsel gereksinimler

| # | Gereksinim | Kaynak | Gerçekleştirim | Kaynak dosya | Test yöntemi | Sonuç | Açıklama |
|---|---|---|---|---|---|---|---|
| F1 | Canlı toplam CPU, kullanıcı/çekirdek CPU | A1 §5, G 5A | `/proc/stat` farkı, psutil ile aynı tanım | `collectors/procfs.py`, `core/normalize.py` | `test_cpu_percent_from_deltas`, 10 örnekli karşılaştırma | PASS | /proc ile psutil arasındaki CPU % farkı ≤ 0,1 puan |
| F2 | Bellek toplam/kullanılan/kullanılabilir | A1 §5, G 5A | MemTotal, MemAvailable; kullanılan = toplam − kullanılabilir | `procfs.py`, `normalize.py` | `test_parse_meminfo_*`, karşılaştırma | PASS | MemTotal 10/10 eşit |
| F3 | Swap kullanımı ve giriş/çıkış etkinliği | A1 §5, G 5A | SwapTotal−SwapFree; pswpin/pswpout farkı | `procfs.py`, `normalize.py` | `test_swap_and_major_fault_rates` | PASS | |
| F4 | Major/minor page fault | A1 §1, G 5A | pgmajfault; minor = pgfault − pgmajfault | `normalize.py` | `test_minor_faults_and_cumulative_disk_bytes` | PASS | |
| F5 | Disk okuma/yazma baytları ve hızları | A1 §3, G 5A | diskstats sektör×512, kümülatif + hız, io_ticks | `procfs.py`, `normalize.py` | `test_disk_rates_*`, `test_parse_diskstats_*` | PASS | Fiziksel diskler; çift sayım önlenir |
| F6 | Süreç PID, ad, CPU, bellek | A1 §5, G 5A | psutil taraması | `collectors/processes.py` | `test_process_collector_*`, gerçek tarama | PASS | |
| F7 | Hız için fark + gerçek geçen süre; ilk ölçümde hız yok | G 5A | monotonik Δt; ilk örnekte `None` | `normalize.py` | `test_first_sample_has_gauges_but_no_rates` | PASS | |
| F8 | Sayaç sıfırlanması/taşması, süreç kaybolması güvenli | G 5A, A1 §4 | negatif yerine `None`; NoSuchProcess atlanır | `normalize.py`, `processes.py` | `test_counter_reset_*`, `test_vanished_*`, `test_real_scan_*` | PASS | |
| F9 | Varsayılan 2 sn örnekleme | A1 §5, G 5B | `AppSettings.sample_interval_s = 2.0` | `config.py`, `ui/worker.py` | Performans koşusu (30 tur/60 sn) | PASS | |
| F10 | Geçmiş 30 dk ile sınırlı, sınırsız büyüme yok | A1 §5, G 5B | yaş sınırı + sabit `deque` kapasitesi | `core/history.py` | `test_history_bounded_to_30_minutes_at_2s`, `test_history_hard_capacity_*`, `test_shorter_interval_*` | PASS | Uzun süreli gerçek koşu (35 dk) yapılmadı |
| F11 | CPU/RAM/swap geçmiş grafikleri | A1 §5, G 5D | QPainter zaman serisi grafiği | `ui/charts.py` | `test_window_updates_*`, `test_chart_handles_gaps_*`, ekran görüntüsü | PASS | Offscreen render |
| F12 | Süreç tablosu | G 5D | sıralama/filtre model içinde | `ui/process_model.py` | `test_process_model_sorts_*` | PASS | |
| F13 | Kural 1: bellek baskısı | A1 §3, G 5C | pencere medyanı + en az bir destek | `analysis/rules.py` | 6 pozitif/negatif + 4 sınır testi + 2 senaryo | PASS | |
| F14 | Kural 2: kalıcı CPU / süreç kaynaklı yoğunluk | A1 §3, G 5C | eşik üstü oranı, süreç grubu payı | `rules.py` | 5 pozitif/negatif + 2 sınır + 3 kaynak testi + 2 senaryo | PASS | |
| F15 | Kural 3: disk G/Ç anomalisi (gözlemsel) | A1 §3, G 5C | önceki 5 dk'ya göre medyan artışı veya meşguliyet | `rules.py` | 6 pozitif/negatif + 4 sınır testi + 2 senaryo | PASS | |
| F16 | Her uyarıda tetikleyici metrikler, eşikler, zaman aralığı, belirsizlik | A1 §3, G 5C | `Alert`/`Evidence`, HTML/metin açıklaması | `core/models.py`, `analysis/explain.py` | `test_alert_contains_full_explanation`, ekran görüntüsü | PASS | |
| F17 | En az iki ardışık pencere, olasılık dili | A1 §3 | `split_windows`, ortak belirsizlik cümlesi | `analysis/windows.py`, `rules.py` | `test_*_only_latest_window_*` | PASS | |
| F18 | Veri yetersizse sonuç üretmeme | G 5C | kapsama < %60 → "Yetersiz veri" | `rules.py` | `test_memory_insufficient_data_is_not_an_alert` | PASS | |
| F19 | Pozitif, negatif, eşik sınırı, yanlış alarm testleri (her kural) | A1 §5, G 5C | | `tests/test_rules.py`, `tests/test_scenarios_service.py` | 30 + 8 test | PASS | |
| F20 | CSV ve JSON raporu, tekrar okunabilir | A1 §5, G 5E | atomik yazım, geri okuma | `export/` | `test_samples_csv_roundtrip`, `test_json_report_roundtrip` | PASS | |
| F21 | Açık zaman damgası, tutarlı birim, eksik değer temsili | G 5E | ISO + epoch; `units`; boş hücre/`null` | `export/`, `core/models.py` | `test_csv_and_json_mark_data_source_and_units` | PASS | |
| F22 | Export yalnızca kullanıcı isteğiyle, uygulama dizinine kendiliğinden dosya yazılmaz | A1 §4, G 5E/8 | yalnızca düğme/bayrakla | `ui/main_window.py`, `cli.py` | `test_no_files_are_written_without_explicit_export` | PASS | |
| F23 | Demo modu: normal, bellek, CPU, disk (+ karşı-örnekler) | G 5F, A1 §8 | 8 senaryo, kayıtlı JSON dosyaları | `collectors/synthetic.py`, `scenarios/` | 8 senaryo testi | PASS | |
| F24 | Demo verisi gerçek ölçüm gibi gösterilmez | G 5F | şerit, `data_source`, `is_synthetic`, `[SENTETİK]` | `ui/main_window.py`, `cli.py`, `export/` | `test_demo_banner_*`, `test_synthetic_headless_output_*` | PASS | |
| F25 | Uygulama hakkında / metodoloji ekranı | G 5D | Hakkında penceresi + Metodoloji sekmesi | `analysis/methodology.py`, `ui/main_window.py` | `test_methodology_lists_*`, GUI smoke | PASS | |
| F26 | Türkçe arayüz | G 5D | tüm metinler Türkçe | `ui/` | Ekran görüntüleri | PASS | |
| F27 | Çevrimdışı çalışma | G 2 | ağ modülü yok | — | `test_no_dangerous_modules_are_imported` | PASS | |
| F28 | GUI'siz yedek arayüz | A1 §7 | `--headless` | `cli.py` | `test_cli_headless_*` | PASS | |

## 2. Kalite ve performans gereksinimleri

| # | Gereksinim | Kaynak | Gerçekleştirim | Kaynak dosya | Test yöntemi | Sonuç | Açıklama |
|---|---|---|---|---|---|---|---|
| Q1 | GUI donmamalı, arka plan örnekleme | A1 §4, G 4 | QThread + QTimer worker | `ui/worker.py` | `test_background_sampling_keeps_gui_responsive`, perf_check | PASS | En uzun olay döngüsü aralığı 29 ms (Ubuntu, offscreen) |
| Q2 | 60 sn yanıt verebilirlik | A1 §5, G 5B | | | `perf_check.py --gui` | PASS (Ubuntu) / NOT TESTED (Pardus) | |
| Q3 | Ortalama CPU < %5 | A1 §5, G 5B | process_every, gizli sekmelerin güncellenmemesi | | perf_check | PASS (Ubuntu: %4,09) / NOT TESTED (Pardus VM) | Sınıra yakın |
| Q4 | RAM < 200 MiB | A1 §5, G 5B | | | perf_check | PASS (Ubuntu: 82 MiB) / NOT TESTED (Pardus VM) | |
| Q5 | Hata toleransı: eksik /proc alanı, izin hatası | A1 §7, G 4 | bölüm bazında okuma, psutil yedeği | `collectors/system.py` | `test_permission_error_*`, `test_system_collector_*` | PASS | |
| Q6 | En az 20 anlamlı otomatik test | A1 §5, G 6 | 136 test | `tests/` | pytest | PASS | 136/136 |
| Q7 | Testler gerçek sistem değerlerine bağlı değil | G 6 | sahte /proc, sahte psutil, sentetik kaynak | `tests/conftest.py` | `-m "not linux"`: 130/130 | PASS | Canlı testler `linux` işaretiyle ayrıldı |
| Q8 | GUI açılış/kapanış smoke testi | G 6 | | `tests/test_gui.py` | `test_gui_smoke_open_sample_and_close_cleanly` | PASS | |
| Q9 | /proc–psutil tutarlılığı, ≥ 10 örnek | A1 §5 | | `scripts/validate_metrics.py` | 10 örnek tablo | PASS (Ubuntu) / NOT TESTED (Pardus) | |
| Q10 | Tür açıklamaları, modülerlik, logging | G 8 | dataclass + typing; modül loggerları | tüm paket | mypy, ruff | PASS | mypy: 33 dosyada sorun yok; ruff E,F,W,B temiz |
| Q11 | Bağımlılık sürümleri belgeli | A2 2.1, G 8 | | `requirements*.txt`, README §3 | inceleme | PASS | |
| Q12 | Lisans uyumu ve atıflar | A1 §3, A2 §6 | | `THIRD_PARTY_NOTICES.md` | inceleme | PASS | Projenin kendi lisansı seçilmedi (ekip kararı) |
| Q13 | Debian 13 kütüphane sürümleriyle uyum | G 7 (dolaylı) | | | PySide6 6.8.2.1 + psutil 5.9.8 ile 136/136 | PASS | Pardus değildir |

## 3. Güvenlik gereksinimleri

| # | Gereksinim | Kaynak | Gerçekleştirim | Test yöntemi | Sonuç |
|---|---|---|---|---|---|
| S1 | Root istenmemeli | A1 §2, G 8 | root ile başlatılırsa yalnızca bilgi uyarısı | `test_root_warning_is_informational`, kod incelemesi | PASS |
| S2 | Sistem yapılandırması değiştirilmemeli, sistem dosyasına yazılmamalı | A1 §2, G 8 | `open(..., "r")` | AST taraması + çalışma zamanı kip izleme | PASS |
| S3 | Süreçlere sinyal yok, sonlandırma yok | A1 §2, G 8 | | `test_no_process_control_or_destructive_calls` | PASS |
| S4 | Bilinmeyen shell komutu yok | G 8 | uygulama paketinde subprocess yok | `test_no_dangerous_modules_are_imported` | PASS |
| S5 | Gereksiz ağ bağlantısı yok, veri dışarı gönderilmez | A1 §4, G 8 | | AST taraması | PASS (kod) / NOT TESTED (Pardus'ta `ss` kontrolü) |
| S6 | Export yalnızca kullanıcının seçtiği konuma | G 8 | | `test_no_files_are_written_*` | PASS |
| S7 | Kernel modülü, stres testi, otomatik onarım yok | A1 §2, G 2 | sentetik senaryolar | AST taraması (`modprobe`, `insmod` dizgileri) | PASS |

## 4. Pardus ve teslim gereksinimleri

| # | Gereksinim | Kaynak | Gerçekleştirim | Test yöntemi | Sonuç | Açıklama |
|---|---|---|---|---|---|---|
| P1 | Çözüm Pardus üzerinde test edilmeli | A2 §1, G 7 | `PARDUS_VALIDATION.md`, `scripts/pardus_validate.sh` | Pardus 25.1 XFCE VM | **NOT TESTED** | Ortamda Pardus yok; Docker imajı indirme izni reddedildi |
| P2 | Temiz kurulum, bağımlılıklar | A1 §5, G 7 | Debian 13 paket adları | VM'de apt kurulumu | **NOT TESTED** | |
| P3 | Normal kullanıcıyla çalışma, GUI açılışı, canlı metrikler, grafikler | G 7 | | VM | **NOT TESTED** | Ubuntu'da PASS |
| P4 | Pardus'ta CPU/RAM ölçümü, 60 sn yanıt | A1 §5, G 7 | `perf_check.py` | VM | **NOT TESTED** | |
| P5 | Temiz kapanış | G 7 | `shutdown()` | VM | **NOT TESTED** | Ubuntu'da smoke testi PASS |
| T1 | Kaynak kod + yapılandırma + bağımlılık listesi | A2 2.1 | `source_code/` | ZIP denetimi | PASS | |
| T2 | Geçici dosya, derleme çıktısı, büyük veri yok | A2 2.1, G 12 | `git ls-files` + yasak kalıp denetimi | `build_submission.py` denetimi | PASS | Bkz. TEST_REPORT.md §6 |
| T3 | README: hedef sürüm, gereksinimler, kurulum, komutlar, kullanım, örnek senaryo | A2 2.2, G 10 | `README.md` §2–§9 | İnceleme + ZIP'ten temiz kurulum testi | PASS (Ubuntu) / NOT TESTED (Pardus) | |
| T4 | Teknik rapor, tüm başlıklar | A2 2.3, G 9 | `technical_report.pdf` (18 bölüm) | İnceleme | PASS | Üye katkıları ekip tarafından doldurulacak |
| T5 | Demo videosu 8–10 dk, `VIDEO_LINK.txt` | A2 2.4, G 11 | `VIDEO_PLAN.md`, `VIDEO_LINK.txt` = `VIDEO_LINK_PENDING` | — | **NOT TESTED** (video yok) | Ekip çekecek |
| T6 | ZIP yapısı: source_code/, README.md, technical_report.pdf, VIDEO_LINK.txt | A2 §3, G 12 | `scripts/build_submission.py` | Arşivi açarak denetim | PASS | Ön teslim (video bekleniyor) |
| T7 | Grup üyelerinin görev ve sorumlulukları somut | A2 §1, 2.3 | `docs/GOREV_DAGILIMI.md`, rapor §15 | — | **NOT TESTED** | Plan yazıldı; gerçekleşen katkıyı ekip doğrulamalı |
| T8 | Yapay zekâ kullanımı açıklanmalı | A2 §6 | README §16, rapor §18 | İnceleme | PASS | |
| T9 | Her üye kodu açıklayabilmeli | A2 §4/§6 | `ORAL_EXAM_PREP.md` | Ekip çalışması | **NOT TESTED** | |
| T10 | UZAK'a yükleme (7 Aralık 2026) | A2 §4 | — | — | **NOT TESTED** | Ekip yükleyecek |
| T11 | GNOME uyumluluğu (ek hedef) | A1 §5 | — | — | NOT TESTED | İsteğe bağlı |

## 5. Özet

- İşlevsel, kalite ve güvenlik gereksinimleri geliştirme makinesinde karşılandı. Hiçbir
  gereksinim FAIL değil.
- **Açık kalanlar:** Pardus doğrulaması (P1–P5), demo videosu (T5), gerçekleşen üye
  katkılarının kaydı (T7), sözlü sunum hazırlığı (T9) ve UZAK'a yükleme (T10).
- Video ve Pardus testi olmadan teslim durumu: **PARTIALLY READY (ön teslim)**.
