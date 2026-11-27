# Gereksinim İzlenebilirlik Matrisi

**Kaynaklar:**
- **A1** = `BIL461_PardusInsight.pdf` (Aşama 1 önerisi, üç kişilik son sürüm)
- **A2** = `BIL461-Proje-Asama2.pdf` (hocanın nihai teslim yönergesi)
- **G** = ekibin Aşama 2 görev tanımı

`~/Downloads/BIL461_PardusInsight_SON.pdf` iki kişilik eski bir taslaktır (16 Ekim 2026) ve
referans alınmadı. Hocanın Aşama 1 geri bildirimi çalışma ortamında bulunamadı; geri bildirim
varmış gibi davranılmadı.

**Pardus kapsayıcısı kanıtı:** Bu dalın eklemeleri dahil birleşmiş kod (`4e5eb3b`) CI
45968920157'de Pardus 25.1/25.2 kapsayıcılarında 326/326 geçti. Son üç hata düzeltmesinin CI
sonucu PR #1'de görünür.

**Sonuç değerleri:**
- **PASS (P-kap):** Resmî Pardus 25.1 Docker imajında CI ile doğrulandı. CI iş günlükleri okunarak kontrol edildi.
- **PASS (dev):** Geliştirme makinesinde (Ubuntu 24.04, Python 3.12.3) çalıştırılan test/ölçümle doğrulandı.
- **NOT TESTED:** Doğrulanmadı.
- **FAIL:** Karşılanmadı.

"Pardus VM" temiz Pardus 25.1 XFCE sanal makinesi demektir ve **hiçbir maddede test edilmedi**.
Tarih: 27 Kasım 2026.

## 1. İşlevsel gereksinimler

| # | Gereksinim | Kaynak | Gerçekleştirim | Kaynak dosya | Test yöntemi | Sonuç | Açıklama |
|---|---|---|---|---|---|---|---|
| F1 | Canlı toplam CPU, kullanıcı/çekirdek CPU | A1 §5, G 5A | `/proc/stat` farkı, psutil ile aynı tanım | `collectors/procfs.py`, `core/normalize.py` | birim testleri, 10 örnekli karşılaştırma | PASS (P-kap, dev) | CPU % farkı ≤ 0,1 puan |
| F2 | Bellek toplam/kullanılan/kullanılabilir | A1 §5, G 5A | MemTotal, MemAvailable; kullanılan = toplam − kullanılabilir | `procfs.py`, `normalize.py` | birim + karşılaştırma + kabul 3.x (`free -b`) | PASS (P-kap, dev) | |
| F3 | Swap kullanımı ve giriş/çıkış | A1 §5, G 5A | SwapTotal−SwapFree; pswpin/pswpout farkı | `procfs.py`, `normalize.py` | birim | PASS (P-kap, dev) | |
| F4 | Major/minor page fault | A1 §1, G 5A | pgmajfault; minor = pgfault − pgmajfault | `normalize.py` | `test_minor_faults_and_cumulative_disk_bytes` | PASS (P-kap, dev) | |
| F5 | Disk okuma/yazma baytları ve hızları | A1 §3, G 5A | diskstats sektör×512; kümülatif + hız; io_ticks | `procfs.py`, `normalize.py` | birim | PASS (P-kap, dev) | Fiziksel diskler; çift sayım önlenir |
| F6 | Süreç PID, ad, CPU, bellek | A1 §5, G 5A | psutil taraması | `collectors/processes.py` | birim + gerçek tarama | PASS (P-kap, dev) | |
| F7 | Hız için fark + gerçek geçen süre; ilk ölçümde hız yok | G 5A | monotonik Δt; ilk örnekte boş | `normalize.py` | `test_first_sample_has_gauges_but_no_rates` | PASS (P-kap, dev) | |
| F8 | Sayaç sıfırlanması/taşması, süreç kaybolması | G 5A, A1 §4 | negatif yerine boş; NoSuchProcess atlanır | `normalize.py`, `processes.py` | birim + gerçek sistemde sonlanan çocuk süreçler | PASS (P-kap, dev) | |
| F9 | Varsayılan 2 sn örnekleme | A1 §5, G 5B | `sample_interval_s = 2.0` | `config.py`, `ui/worker.py` | performans koşuları (30 tur/60 sn) | PASS (P-kap, dev) | |
| F10 | Geçmiş 30 dk ile sınırlı, sınırsız büyüme yok | A1 §5, G 5B | yaş sınırı + sabit kapasite | `core/history.py` | birim + **35 dk uzun koşu** | PASS (P-kap, dev) | 35 dk: tampon ≤ 901, RSS 53,0 → 53,1 MiB |
| F11 | CPU/RAM/swap geçmiş grafikleri | A1 §5, G 5D | QPainter zaman serisi grafiği | `ui/charts.py` | GUI testleri, ekran görüntüleri | PASS (dev, offscreen) | XFCE'de görsel kontrol: VM |
| F12 | Süreç tablosu | G 5D | sıralama/filtre model içinde | `ui/process_model.py` | GUI testi | PASS (P-kap, dev) | |
| F13 | Kural 1: bellek baskısı | A1 §3, G 5C | pencere medyanı + en az bir destek | `analysis/rules.py` | pozitif, negatif, sınır, karşı-örnek, senaryo; mutasyon denemesi | PASS (P-kap, dev) | |
| F14 | Kural 2: kalıcı CPU / süreç kaynaklı yoğunluk | A1 §3, G 5C | eşik üstü oranı; süreç grubu payı | `rules.py` | aynı + süreç kaynağı testleri | PASS (P-kap, dev) | |
| F15 | Kural 3: disk G/Ç anomalisi (gözlem) | A1 §3, G 5C | önceki 5 dk'ya göre medyan artışı veya meşguliyet | `rules.py` | aynı | PASS (P-kap, dev) | |
| F16 | Uyarıda tetikleyici metrikler, eşikler, zaman aralığı, belirsizlik | A1 §3, G 5C | `Alert`/`Evidence`, açıklama metinleri | `core/models.py`, `analysis/explain.py` | `test_alert_contains_full_explanation`, açıklama metni testleri | PASS (P-kap, dev) | |
| F17 | En az iki ardışık pencere, olasılık dili | A1 §3 | `split_windows`, ortak belirsizlik cümlesi | `analysis/windows.py`, `rules.py` | `test_windows.py`, "yalnızca son pencere" testleri | PASS (P-kap, dev) | |
| F18 | Veri yetersizse sonuç üretmeme / uyarıyı yanlışlıkla kapatmama | G 5C | "yetersiz veri" sonucu; motor aktif uyarıyı açık tutar | `rules.py`, `engine.py` | `test_insufficient_*`, duraklama testleri | PASS (P-kap, dev) | |
| F19 | Pozitif, negatif, eşik sınırı, yanlış alarm testleri (her kural) | A1 §5, G 5C, G 6 | | `tests/test_rules.py`, `test_scenarios_service.py`, `test_windows.py` | 23 mutantın tamamı yakalanıyor (docs/TEST_RAPORU.md §1.3) | PASS (P-kap, dev) | |
| F20 | CSV ve JSON, tekrar okunabilir | A1 §5, G 5E | atomik yazım, geri okuma | `export/` | gidiş-dönüş testleri | PASS (P-kap, dev) | |
| F21 | Açık zaman damgası, tutarlı birim, eksik değer temsili | G 5E | ISO + epoch; `units`; boş hücre/`null` | `export/`, `core/models.py` | `test_csv_and_json_mark_data_source_and_units` | PASS (P-kap, dev) | |
| F22 | Export yalnızca kullanıcı isteğiyle; uygulama dizinine kendiliğinden yazmama | A1 §4, G 5E/8 | yalnızca düğme veya bayrakla | `ui/main_window.py`, `cli.py` | test + kabul 2.5 | PASS (P-kap, dev) | |
| F23 | Demo: normal, bellek, CPU, disk (+ karşı-örnekler) | G 5F, A1 §8 | 8 senaryo, 7 kayıtlı JSON | `collectors/synthetic.py`, `scenarios/` | senaryo testleri; kayıtlı dosyaların koda uygunluğu | PASS (P-kap, dev) | |
| F24 | Demo verisi gerçek ölçüm gibi gösterilmez | G 5F | şerit, `data_source`, `is_synthetic`, `[SENTETİK]` | `ui/main_window.py`, `cli.py`, `export/` | GUI, CLI, dışa aktarma testleri | PASS (P-kap, dev) | |
| F25 | Hakkında / metodoloji ekranı | G 5D | Hakkında penceresi + Metodoloji sekmesi | `analysis/methodology.py` | testler, ekran görüntüsü | PASS (P-kap, dev) | |
| F26 | Türkçe arayüz | G 5D | | `ui/` | ekran görüntüleri | PASS (dev) | |
| F27 | Çevrimdışı çalışma | G 2 | ağ modülü yok | — | AST taraması + kabul 2.4 (bağlantı yok) | PASS (P-kap, dev) | |
| F28 | GUI'siz yedek arayüz | A1 §7 | `--headless` | `cli.py` | CLI testleri, kabul 2.2 | PASS (P-kap, dev) | |

## 2. Kalite ve performans gereksinimleri

| # | Gereksinim | Kaynak | Test yöntemi | Sonuç | Açıklama |
|---|---|---|---|---|---|
| Q1 | GUI donmamalı, arka plan örnekleme | A1 §4, G 4 | donmama testi, `perf_check --gui` | PASS (P-kap, dev) | En uzun olay döngüsü aralığı 23 ms (kapsayıcı), 27 ms (dev) |
| Q2 | 60 sn yanıt verebilirlik | A1 §5, G 5B | `perf_check --gui` | PASS (P-kap, dev) / NOT TESTED (VM) | |
| Q3 | Ortalama CPU < %5 | A1 §5, G 5B | `perf_check` | PASS (P-kap: %0,93 GUI; dev: %3,15 GUI) / NOT TESTED (VM) | |
| Q4 | RAM < 200 MiB | A1 §5, G 5B | `perf_check` | PASS (P-kap: 75 MiB; dev: 82 MiB) / NOT TESTED (VM) | |
| Q5 | Hata toleransı: eksik /proc alanı, izin hatası | A1 §7, G 4 | birim testleri | PASS (P-kap, dev) | |
| Q6 | En az 20 anlamlı otomatik test | A1 §5, G 6 | pytest | PASS | 329 (dev, son kod); 326 (P-kap, birleşmiş dal `4e5eb3b`) |
| Q7 | Testler gerçek sistem değerlerine bağlı değil | G 6 | `-m "not linux"` | PASS (dev: 320) | Canlı testler `linux` işaretli |
| Q8 | GUI açılış/kapanış smoke testi | G 6 | `test_gui_smoke_open_sample_and_close_cleanly` | PASS (P-kap, dev) | |
| Q9 | /proc–psutil tutarlılığı, ≥ 10 örnek | A1 §5 | `validate_metrics.py` | PASS (P-kap, dev) / NOT TESTED (VM) | |
| Q10 | Tür açıklamaları, modülerlik, logging | G 8 | mypy, ruff | PASS (mypy 34 dosya temiz) | ruff: `main`'den gelen dosyalarda 10 biçim bulgusu (TEST_REPORT §2) |
| Q11 | Bağımlılık sürümleri belgeli | A2 2.1, G 8 | inceleme | PASS | README §3, `requirements*.txt`, `.deb` Depends |
| Q12 | Lisans uyumu ve atıflar | A1 §3, A2 §6 | inceleme | PASS | `THIRD_PARTY_NOTICES.md`, `packaging/debian/copyright`. Proje lisansı seçilmedi |
| Q13 | Pardus kütüphane sürümleriyle uyum | G 7 | Pardus kapsayıcısında tam test takımı | PASS (P-kap: Python 3.13.5, PySide6 6.8.2.1, psutil 7.0.0) | |

## 3. Güvenlik gereksinimleri

| # | Gereksinim | Kaynak | Test yöntemi | Sonuç |
|---|---|---|---|---|
| S1 | Root istenmemeli | A1 §2, G 8 | test + kapsayıcıda root olmayan kullanıcı | PASS (P-kap, dev) |
| S2 | Sistem yapılandırması değiştirilmemeli, sistem dosyasına yazılmamalı | A1 §2, G 8 | AST taraması + çalışma zamanı kip izleme | PASS |
| S3 | Süreçlere sinyal yok, sonlandırma yok | A1 §2, G 8 | AST (dolaylı çağrılar dahil) | PASS |
| S4 | Bilinmeyen shell komutu yok | G 8 | AST (uygulama paketinde subprocess/exec yok) | PASS |
| S5 | Gereksiz ağ bağlantısı yok, veri dışarı gönderilmez | A1 §4, G 8 | AST + kabul 2.4 (çalışırken bağlantı yok) | PASS (P-kap, dev) |
| S6 | Export yalnızca kullanıcının seçtiği konuma | G 8 | test + kabul 2.5 | PASS (P-kap, dev) |
| S7 | Kernel modülü, stres testi, otomatik onarım yok | A1 §2, G 2 | AST dizgi taraması; sentetik senaryolar | PASS |

## 4. Pardus ve teslim gereksinimleri

| # | Gereksinim | Kaynak | Gerçekleştirim | Sonuç | Açıklama |
|---|---|---|---|---|---|
| P1 | Çözüm Pardus üzerinde test edilmeli | A2 §1, G 7 | CI (resmî Pardus 25.1/25.2 imajı), `pardus_kabul.py` | **PASS (P-kap) / NOT TESTED (VM)** | Kapsayıcı Pardus kullanıcı alanıdır; çekirdek ve XFCE VM'de doğrulanmalı |
| P2 | Temiz kurulum, bağımlılıklar | A1 §5, G 7 | apt (Pardus deposu) ve `.deb` | PASS (P-kap) / NOT TESTED (VM) | Kabul 1.1, 1.2, 1.4 |
| P3 | Normal kullanıcıyla çalışma, GUI açılışı, canlı metrikler, grafikler | G 7 | | PASS (P-kap: headless + GUI xvfb/xcb) / NOT TESTED (VM, XFCE) | |
| P4 | Pardus'ta CPU/RAM, 60 sn yanıt | A1 §5, G 7 | `perf_check.py` | PASS (P-kap) / NOT TESTED (VM) | |
| P5 | Temiz kapanış | G 7 | `shutdown()` | PASS (dev smoke testi; P-kap aynı test) / NOT TESTED (VM) | |
| P6 | Pardus paketi | A1 §6 (paketleme) | `.deb`, menü kaydı, man sayfası | PASS (P-kap: lintian, apt install/purge) | Oğuz |
| T1 | Kaynak kod + yapılandırma + bağımlılık listesi | A2 2.1 | `source_code/` | PASS | |
| T2 | Geçici dosya, derleme çıktısı, büyük veri yok | A2 2.1, G 12 | `git ls-files` + yasak kalıp denetimi | PASS | TEST_REPORT §6 |
| T3 | README: hedef sürüm, gereksinimler, kurulum, komutlar, kullanım, örnek senaryo | A2 2.2, G 10 | `README.md` §2–§9 | PASS (dev: ZIP'ten temiz kurulum) / NOT TESTED (VM) | |
| T4 | Teknik rapor, tüm başlıklar | A2 2.3, G 9 | `technical_report.pdf` (18 bölüm) | PASS | Eren ve Yusuf'un gerçekleşen katkıları ekip tarafından doğrulanacak |
| T5 | Demo videosu 8–10 dk, `VIDEO_LINK.txt` | A2 2.4, G 11 | `VIDEO_PLAN.md`; `VIDEO_LINK.txt` = `VIDEO_LINK_PENDING` | **NOT TESTED** | Video yok |
| T6 | ZIP yapısı | A2 §3, G 12 | `scripts/build_submission.py` | PASS | Ön teslim (video bekleniyor) |
| T7 | Grup üyelerinin görev ve sorumlulukları somut | A2 §1, 2.3 | `docs/GOREV_DAGILIMI.md`, rapor §15 | **Kısmen** | Oğuz'un katkısı Git'te (22 commit) görünür. Eren'in commit'leri yapay zekâ destekli ilk sürüm ve Aşama 2 hazırlığı. Yusuf'un commit'i yok. Gerçekleşen katkıları ekip yazmalı |
| T8 | Yapay zekâ kullanımı açıklanmalı | A2 §6 | README §16, rapor §18 | PASS | |
| T9 | Her üye kodu açıklayabilmeli | A2 §4/§6 | `ORAL_EXAM_PREP.md` | **NOT TESTED** | |
| T10 | UZAK'a yükleme (7 Aralık 2026) | A2 §4 | — | **NOT TESTED** | |
| T11 | GNOME uyumluluğu (ek hedef) | A1 §5 | — | NOT TESTED | İsteğe bağlı |

## 5. Özet

- Hiçbir gereksinim FAIL değil.
- İşlevsel, kalite ve güvenlik gereksinimleri hem resmî Pardus 25.1 kapsayıcısında hem
  geliştirme makinesinde doğrulandı.
- **Açık kalanlar:**
  - Temiz Pardus 25.1 XFCE VM doğrulaması (P1–P5 VM sütunu)
  - Demo videosu (T5)
  - Gerçekleşen üye katkılarının kaydı (T7)
  - Sözlü sunum hazırlığı (T9)
  - UZAK'a yükleme (T10)
- Teslim durumu: **PARTIALLY READY (ön teslim; video ve XFCE VM doğrulaması bekleniyor)**.
