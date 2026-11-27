# PardusInsight

**Pardus için salt-okunur sistem kaynağı izleme ve açıklanabilir darboğaz analizi**
BİL461 İşletim Sistemleri · 2026–2027 Güz · TOBB ETÜ · Aşama 2 teslimi

| Grup üyesi | Öğrenci no |
|---|---|
| Eren Can Dönertaş | 241101011 |
| Yusuf Yankı Ütgün | 231101020 |
| Oğuz Giray Bori | 231101076 |

> **Teslim ZIP'inden açtıysanız:** Bu README ZIP'in kökündedir. Aşağıdaki bütün komutları
> `source_code/` klasöründe çalıştırın (`cd source_code`). Git deposundan klonladıysanız
> deponun kökü aynı klasördür.

> **Doğrulama durumu:** Otomatik testler her push'ta GitHub Actions'ta **resmî Pardus 25.1 ve
> 25.2 Docker imajlarında** (Pardus deposundaki paketlerle, standart kullanıcıyla), Ubuntu'da ve
> Windows'ta çalışır. Kapsayıcı Pardus'un kullanıcı alanını sağlar; çekirdek GitHub
> sunucusunundur ve masaüstü yoktur. **Temiz bir Pardus 25.1 XFCE VM'de doğrulama henüz
> yapılmadı.** Ayrıntılar: [PARDUS_VALIDATION.md](PARDUS_VALIDATION.md),
> [docs/PARDUS_DOGRULAMA.md](docs/PARDUS_DOGRULAMA.md).

---

## 1. Proje tanımı

PardusInsight; CPU, RAM, swap, sayfa hataları, disk G/Ç ve süreç bilgilerini Linux
`/proc` arayüzünden **standart kullanıcı yetkisiyle** okur. Son 30 dakikayı grafiklerde
gösterir ve üç kural üzerinden **açıklamalı uyarılar** üretir. Her uyarıda şunlar yer alır:

- hangi metriklerin hangi eşiklerle karşılaştırıldığı (ana koşul / destekleyici / bağlam),
- dayandığı zaman aralığı ve güven düzeyi,
- belirsizlikler ve bunun **kesin arıza tanısı olmadığı**,
- en yoğun süreçler ve yalnızca öneri niteliğinde, salt-okunur adımlar.

| Kural | Özet koşul (varsayılanlar, 2 ardışık × 30 sn pencere) | Önem |
|---|---|---|
| Bellek baskısı olasılığı | MemAvailable medyanı < %10 **ve** swap etkinliği ≥ 100 sayfa/sn, major page-fault ≥ 100/sn veya PSI bellek ≥ %10 göstergelerinden en az biri | Uyarı / Kritik olasılık |
| Kalıcı CPU yoğunluğu | Her pencerede örneklerin ≥ %80'i CPU ≥ %85; yükün süreç kaynaklı mı dağınık mı olduğu açıklanır | Uyarı |
| Disk G/Ç anomalisi | Okuma+yazma medyanı ≥ max(3 × önceki 5 dk, 5 MiB/sn) **veya** meşguliyet ≥ %80 | Gözlem |

Uygulama yalnızca ölçüm ve analiz yapar. Kernel modülü, root erişimi, süreç sonlandırma,
otomatik onarım, sistem ayarı değişikliği, ağ bağlantısı ve stres testi **yoktur**.

## 2. Hedef platform ve sistem gereksinimleri

| | |
|---|---|
| Hedef işletim sistemi | **Pardus 25.1 XFCE**, x86-64 (Debian 13 "trixie" tabanlı) |
| Diğer | Güncel Linux dağıtımları. Canlı izleme yalnızca Linux'ta çalışır, sentetik demo her platformda |
| Donanım | 1+ çekirdek, uygulama için ~100 MiB boş RAM, ~5 MiB disk |
| Yetki | Standart kullanıcı. `sudo` yalnızca dağıtım paketlerini kurmak için gerekir |
| Ağ | Gerekmez. Uygulama çevrimdışı çalışır |

## 3. Gerekli yazılım ve kütüphaneler

| Bileşen | Gerekli sürüm | Test edilen sürümler | Pardus/Debian paketi | Lisans |
|---|---|---|---|---|
| Python | ≥ 3.9 | 3.12.3 | `python3` (Debian 13: 3.13) | PSF |
| psutil | ≥ 5.9 | 7.2.2, 5.9.8 | `python3-psutil` | BSD-3-Clause |
| PySide6 (QtCore, QtGui, QtWidgets) | ≥ 6.5 | 6.12.0, 6.8.2.1 | `python3-pyside6.qtwidgets` (Debian 13: 6.8.2) | LGPLv3 |
| pytest (yalnızca testler) | ≥ 7 | 9.2.0, 8.3.5 | `python3-pytest` | MIT |

Ayrıntılı lisans bilgisi: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)

## 4. Kurulum

### 4.1 Pardus 25.1 / Debian 13 paketleriyle (önerilen)

```bash
sudo apt update
sudo apt install -y python3 python3-psutil \
     python3-pyside6.qtcore python3-pyside6.qtgui python3-pyside6.qtwidgets python3-pytest
cd source_code            # ZIP'ten açtıysanız; git clone ile aldıysanız: cd PardusInsight
python3 -m pardusinsight --version
```

### 4.2 Sanal ortamla (root gerekmez)

```bash
sudo apt install -y python3-venv          # yalnızca python3-venv kurulu değilse
cd source_code                            # veya PardusInsight
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pardusinsight --version
```

PyPI'den kurulan PySide6, X11'de `libxcb-cursor0` paketini ister:
`sudo apt install libxcb-cursor0`.

### 4.3 Pardus/Debian paketiyle (`.deb`: menü kaydı, simge, `man pardusinsight`)

```bash
python3 scripts/build_deb.py                         # dist/pardusinsight_0.1.0_all.deb üretir
sudo apt install ./dist/pardusinsight_0.1.0_all.deb  # bağımlılıklar Pardus deposundan gelir
pardusinsight                                        # veya menü: Sistem → PardusInsight
```

Ayrıntılar: [docs/PAKETLEME.md](docs/PAKETLEME.md)

### 4.4 Menüye kısayol, paket kurmadan (isteğe bağlı, root gerekmez)

```bash
sh scripts/install_user.sh            # ~/.local/share/applications/pardusinsight.desktop
sh scripts/install_user.sh --remove   # kaldırır
```

Ayrıntılı kurulum ve sorun giderme: [docs/KURULUM.md](docs/KURULUM.md)

## 5. Çalıştırma komutları

| Komut | Açıklama |
|---|---|
| `python3 -m pardusinsight` | Canlı izleme (GUI), 2 sn aralık, 30 dk geçmiş |
| `python3 -m pardusinsight --synthetic demo --speed 4` | **Demo:** sentetik veri, 4× hız (Linux gerekmez) |
| `python3 -m pardusinsight --replay scenarios/demo.json` | Kaydedilmiş senaryoyu veya raporu açıp kuralları yeniden çalıştırır |
| `python3 -m pardusinsight --headless --duration 60` | GUI'siz izleme (PySide6 gerekmez) |
| `python3 -m pardusinsight --headless --duration 300 --export-csv o.csv --export-json r.json` | GUI'siz izleme + rapor |
| `python3 -m pardusinsight --interval 5 --window 45` | Farklı örnekleme aralığı ve analiz penceresi |
| `python3 -m pardusinsight --config ayarlar.json` | Eşikleri JSON dosyasından okur (uygulama dosyaya yazmaz) |
| `python3 -m pardusinsight --list-scenarios` | Sentetik senaryoları listeler |
| `python3 -m pardusinsight --log-level INFO` | Tanılama günlüğünü stderr'e yazar (dosya oluşturmaz) |

Sanal ortam kullanıyorsanız `python3` yerine `.venv/bin/python` yazın.

## 6. Gerçek sistem izleme: temel işlevler

| Sekme | İçerik |
|---|---|
| **Genel Bakış** | CPU (kullanıcı/çekirdek/iowait), RAM (kullanılabilir/toplam), swap (giriş/çıkış, major fault), disk (okuma/yazma, meşguliyet), yük ve aktif uyarı kartları. CPU, bellek/swap, sayfa etkinliği ve disk grafikleri (son 1/5/15/30 dk). Grafiklerde eşik çizgisi ve etiketli uyarı aralıkları gösterilir. Fareyle üzerine gelindiğinde o anın değerleri görünür |
| **Süreçler** | PID, ad, kullanıcı, durum, CPU %, RSS, bellek %, iş parçacığı, okuma/yazma hızı. Sıralama ve filtre var. Root olmadan okunamayan alanlar "—" ile gösterilir. Süreçler üzerinde **hiçbir işlem yapılamaz** |
| **Uyarılar** | Uyarı listesi, kanıt tablosu (rol, metrik, değer, eşik, pencere), bağlam, belirsizlik, öneriler. **Kural durumu** tablosu her kuralın neden tetiklenmediğini de gösterir |
| **Günlük** | Yeni ve çözülen uyarılar, okuma hataları, dışa aktarma ve ayar değişiklikleri |
| **Metodoloji** | Her metriğin hangi `/proc` dosyasından hangi formülle hesaplandığı, pencere mantığı ve geçerli eşikler |

Araç çubuğu: Duraklat/Sürdür (Ctrl+P), CSV dışa aktar (Ctrl+E), JSON rapor (Ctrl+J),
Kayıt/senaryo aç (Ctrl+O), Ayarlar, Hakkında. Durum çubuğunda uygulamanın **kendi** CPU ve
RAM kullanımı görünür. Ayrıntılar: [docs/KULLANIM.md](docs/KULLANIM.md)

## 7. Demo modu (sentetik veri)

Demo modu gerçek sisteme hiçbir yük bindirmez ve **gerçek ölçüm olarak gösterilmez**:

- Pencerenin üstünde bütün sekmelerde sarı **"DEMO / SENTETİK VERİ — Gösterilen değerler
  gerçek sistem ölçümü DEĞİLDİR"** şeridi görünür. Pencere başlığı da modu belirtir.
- CSV'de `data_source` sütunu `synthetic:<senaryo>`, JSON'da `is_synthetic: true` olur.
  Komut satırında her satırın başında `[SENTETİK]` yazar.

| Senaryo (`--synthetic` veya `scenarios/<ad>.json`) | Beklenen sonuç |
|---|---|
| `normal` | Uyarı yok |
| `cpu` | Kalıcı CPU yoğunluğu (cc1plus kaynaklı) |
| `memory` | Bellek baskısı olasılığı |
| `disk` | Disk G/Ç anomalisi (gözlem) |
| `demo` | Sırayla CPU → bellek → disk (~8 dk simülasyon) |
| `cpu_spikes`, `memory_low_quiet`, `disk_steady` | **Yanlış alarm karşı-örnekleri:** uyarı yok |

## 8. CSV / JSON dışa aktarma

Dışa aktarma **yalnızca kullanıcı isteğiyle** yapılır. GUI'de *CSV dışa aktar…* ve *JSON rapor…*
düğmeleri, komut satırında `--export-csv` ve `--export-json` seçenekleri kullanılır. Varsayılan
konum ev dizinidir ve yolu kullanıcı seçer. Uygulama kendiliğinden dosya yazmaz.

- `<ad>.csv`: her satır bir ölçüm. ISO zaman damgası ve Unix zamanı içerir. Sütunların
  çoğunun adında birimi yer alır (`_bytes`, `_percent`, `_per_s`); tam birim listesi JSON
  raporundaki `units` alanında ve rapor biçimi belgesindedir. Ölçülemeyen değerler boş hücre
  olarak yazılır. Ayrıca `data_source` sütunu bulunur.
- `<ad>_uyarilar.csv`: uyarılar, kanıtlar ve belirsizlik metni.
- `<ad>.json`: meta veri, `units` (birim sözlüğü), ayarlar, özet istatistikler, uyarılar ve
  örnekler. Bu dosya *Kayıt/senaryo aç* ile yeniden analiz edilebilir.

Sütunların tam listesi: [docs/RAPOR_FORMATI.md](docs/RAPOR_FORMATI.md)

## 9. Örnek kullanım ve test senaryosu (yaklaşık 5 dakika)

1. **Demo analizi:** `python3 -m pardusinsight --replay scenarios/demo.json`. Uyarılar sekmesinde
   üç uyarı görünür. *Bellek baskısı olasılığı* seçildiğinde kanıt tablosunda iki ana koşul ✓ ve
   üç destekleyici gösterge ✓ yer alır. Sarı demo şeridi görünür.
2. **Karşı-örnek:** *Kayıt/senaryo aç… → scenarios/cpu_spikes.json*. Uyarı yoktur. Kural durumu
   tablosu "yüksek CPU her pencerede kalıcı değil" der.
3. **Canlı izleme:** *Canlı izlemeye dön*. Bir tarayıcıda birkaç sekme açın ve grafiklerin
   güncellendiğini izleyin. Metodoloji sekmesinde CPU %'nin `/proc/stat` farkından nasıl
   hesaplandığını görün.
4. **Dışa aktarma:** *CSV dışa aktar…* ile dosyayı kaydedin ve LibreOffice Calc'ta açın.
   `data_source` sütunu `linux` olmalıdır.
5. **GUI'siz:** `python3 -m pardusinsight --headless --duration 30` komutu her 2 saniyede bir özet satırı yazar.

## 10. Testler

```bash
python3 -m pytest -q                 # tüm testler (ekransız ortamda GUI testleri offscreen çalışır)
python3 -m pytest -q -m "not linux"  # yalnızca deterministik testler (canlı /proc testleri hariç)
python3 -m pytest -q -m linux        # canlı /proc ile psutil karşılaştırması (10'ar örnek)
python3 scripts/validate_metrics.py --rounds 10   # doğrulama tablosu
python3 scripts/perf_check.py --gui --duration 60 # uygulamanın CPU/RAM ölçümü ve donmama kontrolü
make kapsam                          # satır kapsamı raporuyla
python3 scripts/pardus_kabul.py --gui --cikti docs/PARDUS_SONUCLARI.md   # Pardus VM'de kabul listesi
```

[![CI](https://github.com/Eren-Can-Donertas/PardusInsight/actions/workflows/ci.yml/badge.svg)](https://github.com/Eren-Can-Donertas/PardusInsight/actions/workflows/ci.yml)

Testler her push'ta GitHub Actions'ta Ubuntu (Python 3.9 ve 3.13), Windows ve resmî Pardus
25.1/25.2 kapsayıcılarında çalışır. Pardus kapsayıcısında `.deb` paketi de apt ile kurulup
denenir, kabul betiği çalıştırılır. Ayrı bir iş akışı 35 dakikalık uzun koşuda bellek sınırını
denetler. Güncel sonuçlar ve test envanteri: [TEST_REPORT.md](TEST_REPORT.md) (Aşama 2 özeti)
ve [docs/TEST_RAPORU.md](docs/TEST_RAPORU.md) (ayrıntılı test kaydı).

## 11. Sorun giderme

| Belirti | Neden / çözüm |
|---|---|
| `PySide6 yüklenemedi` | PySide6 kurulu değil: Bölüm 4. GUI'siz kullanım için `--headless` |
| `Could not load the Qt platform plugin "xcb"` | `sudo apt install libxcb-cursor0` (pip ile kurulan PySide6) |
| Süreç G/Ç sütunları "—" | Normal: başka kullanıcıların `/proc/<pid>/io` dosyası root olmadan okunamaz |
| Durum satırında "PSI: yok" | Çekirdekte PSI kapalı. Bellek kuralı swap ve page-fault ile çalışır |
| Günlükte "/proc okunamadı; psutil yedeği kullanıldı" | Kısıtlı ortam (kapsayıcı vb.). Değerler psutil'den gelir |
| İlk örnekte CPU ve hızlar "—" | Normal: hız iki ölçüm arasındaki farktan hesaplanır |
| Uyarı gelmiyor | Uyarılar sekmesindeki **Kural durumu** nedeni gösterir (ör. "Yetersiz veri" veya "koşul sağlanmadı") |

## 12. Bilinen kısıtlar

- **Temiz Pardus 25.1 XFCE VM'de henüz doğrulanmadı.** Testler Pardus kapsayıcısında (kullanıcı
  alanı) çalışıyor, ama gerçek Pardus çekirdeği, XFCE oturumu ve görünüm denenmedi.
- Eşikler gerçek kullanım verisiyle kalibre edilmedi. Kalibrasyon aracı hazır
  (`scripts/kalibrasyon.py`, [docs/KALIBRASYON_SENTETIK.md](docs/KALIBRASYON_SENTETIK.md)).
- Root olmadan diğer kullanıcıların süreç G/Ç sayaçları okunamaz.
- Süreç değerleri örnekleme anlarına aittir; 2 saniyeden kısa yaşayan süreçler görünmeyebilir.
- RSS paylaşılan belleği birden fazla sayabilir. NVMe/SSD'de disk meşguliyeti doygunluğu abartabilir.
- Uyarılar olasılık değerlendirmesidir, kesin tanı değildir.
- Demo videosu henüz çekilmedi (`VIDEO_LINK.txt`).

## 13. Güvenlik yaklaşımı

- Root yetkisi istenmez. Root ile başlatılırsa yalnızca bilgi uyarısı verilir.
- `/proc` ve `/sys` yalnızca okunur. Sistem dosyalarına yazılmaz, sistem ayarı değiştirilmez.
- Süreçlere sinyal gönderilmez. Öncelik veya affinity değiştirilmez. Kabuk komutu çalıştırılmaz.
- Ağ bağlantısı kurulmaz ve hiçbir veri otomatik olarak dışarı gönderilmez.
- Geçmiş tamponu 30 dakika ve sabit kapasiteyle sınırlıdır.
- Raporlar yalnızca kullanıcının seçtiği yola, atomik olarak ve 0600 izniyle yazılır. Raporlarda kullanıcı adı veya makine adı bulunmaz.

Bu kurallar `tests/test_cli_safety.py` içinde kaynak kod taramasıyla (AST) otomatik denetlenir.

## 14. Lisanslar

Kullanılan bileşenler: psutil (BSD-3-Clause), Qt for Python / PySide6 (LGPLv3, değiştirilmeden
dinamik kullanılır), Python (PSF), pytest (MIT, yalnızca geliştirme). Dış projelerden kod
kopyalanmamıştır. Ayrıntılar: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
Projenin kendi lisansı henüz ekip tarafından seçilmedi.

## 15. Proje yapısı ve belgeler

```
pardusinsight/   collectors/ (procfs, system, processes, synthetic)  core/ (models, normalize,
                 history, service, formatting)  analysis/ (windows, rules, engine, explain,
                 methodology)  export/ (csv, json, atomic)  ui/ (main_window, worker, charts, ...)
                 cli.py  config.py
tests/           otomatik testler (birim, entegrasyon, GUI, güvenlik, paket, kabul betiği)
scenarios/       önceden kaydedilmiş sentetik senaryolar (her kural için pozitif + karşı-örnek)
scripts/         validate_metrics, perf_check, generate_scenarios, capture_screenshots,
                 build_deb (.deb), kalibrasyon (eşik kalibrasyonu), pardus_kabul (Pardus kabul
                 listesi otomasyonu), build_submission (teslim ZIP'i), install_user.sh
packaging/       Debian paket dosyaları, .desktop, simge, man sayfası
.github/         CI: Ubuntu, Windows ve resmî Pardus 25.1/25.2 kapsayıcıları; 35 dk uzun koşu
docs/            KURULUM, KULLANIM, KURALLAR, MIMARI, RAPOR_FORMATI, GOREV_DAGILIMI, PAKETLEME,
                 KALIBRASYON_SENTETIK, TEST_RAPORU, PARDUS_DOGRULAMA
report/          teknik raporun kaynağı (HTML) ve PDF üretim betiği
```

| Belge | İçerik |
|---|---|
| [docs/MIMARI.md](docs/MIMARI.md) | Katmanlar, iş parçacığı modeli, tasarım kararları |
| [docs/KURALLAR.md](docs/KURALLAR.md) | Kuralların tanımı, eşik sınırları, kalibrasyon planı |
| [docs/GOREV_DAGILIMI.md](docs/GOREV_DAGILIMI.md) | Modül sahipliği ve Git çalışma düzeni |
| [docs/PAKETLEME.md](docs/PAKETLEME.md) · [docs/KALIBRASYON_SENTETIK.md](docs/KALIBRASYON_SENTETIK.md) | `.deb` paketi; eşik kalibrasyon yöntemi |
| [docs/TEST_RAPORU.md](docs/TEST_RAPORU.md) · [docs/PARDUS_DOGRULAMA.md](docs/PARDUS_DOGRULAMA.md) | Ayrıntılı test kaydı (CI, Pardus kapsayıcısı); Pardus kabul listesi |
| [TEST_REPORT.md](TEST_REPORT.md) | Aşama 2 test ve ölçüm özeti |
| [REQUIREMENTS_MATRIX.md](REQUIREMENTS_MATRIX.md) | Gereksinim izlenebilirlik matrisi |
| [PARDUS_VALIDATION.md](PARDUS_VALIDATION.md) | Pardus kurulum ve kabul listesi |
| [VIDEO_PLAN.md](VIDEO_PLAN.md) · [ORAL_EXAM_PREP.md](ORAL_EXAM_PREP.md) · [FINAL_CHECKLIST.md](FINAL_CHECKLIST.md) | Video planı, sözlü sınav hazırlığı, teslim kontrol listesi |

Teslim paketi `python3 scripts/build_submission.py` ile `dist/PardusInsight.zip` olarak üretilir.

## 16. Yapay zekâ kullanımı

- **İlk sürüm ve Aşama 2 teslim hazırlığı:** Kod, testler ve belgeler, ekibin Aşama 1 önerisi ve
  Aşama 2 yönergesi girdi olarak verilerek **Anthropic Claude (Claude Code)** ile üretildi.
  Testler ve ölçümler gerçekten çalıştırıldı, sonuçları olduğu gibi raporlandı.
- **Oğuz'un görevleri:** Paketleme (`.deb`), sürekli entegrasyon (resmî Pardus 25.1 kapsayıcısı
  dahil), eşik kalibrasyon aracı, Pardus kabul betiği, zaman penceresi ve kural testleri ile kod
  incelemesinde bulunan hataların düzeltilmesi de **Claude Code** desteğiyle yapıldı. Kod
  incelemesinde her bulgu kod çalıştırılarak yeniden üretildi ve bağımsız olarak doğrulandı.
  Düzeltmeler, eski kodda başarısız olan regresyon testleriyle birlikte commit'lendi. İlgili
  commit'ler `Co-Authored-By: Claude` satırı taşır.
- **Ekibin sorumluluğu:** Her üye kodu anlayıp açıklayabilmelidir. XFCE VM doğrulaması, gerçek
  kullanımla kalibrasyon, demo videosu ve üye katkılarının kaydı ekip tarafından tamamlanmalıdır.

Ayrıntılı beyan: teknik raporun 18. bölümü.
