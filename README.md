# PardusInsight

**Pardus için salt-okunur sistem kaynağı izleme ve açıklanabilir darboğaz analizi**
BİL461 İşletim Sistemleri · 2026–2027 Güz · Aşama 2 (uygulama)

| Grup üyesi | Öğrenci no | Birincil sorumluluk |
|---|---|---|
| Eren Can Dönertaş | 241101011 | Metrik toplama, normalizasyon ve tampon (`collectors/`, `core/`) |
| Yusuf Yankı Ütgün | 231101020 | Masaüstü arayüzü, grafikler ve raporlama (`ui/`, `export/`) |
| Oğuz Giray Bori | 231101076 | Analiz motoru, test otomasyonu ve paketleme (`analysis/`, `tests/`, `scripts/`) |

Ayrıntılı modül sahipliği ve Git çalışma düzeni: [docs/GOREV_DAGILIMI.md](docs/GOREV_DAGILIMI.md)

---

## Ne yapar?

PardusInsight CPU, RAM, swap, sayfa hataları, disk G/Ç ve süreç ölçümlerini **standart
kullanıcı yetkisiyle** okur, son 30 dakikayı grafiklerde gösterir ve üç kural üzerinden
**açıklamalı uyarılar** üretir. Her uyarı şunları içerir:

- hangi metriklerin hangi eşiklerle karşılaştırıldığını (tetikleyici / destekleyici / bağlam),
- hangi zaman aralığına dayandığını,
- belirsizlikleri ve bunun **kesin arıza tanısı olmadığını**,
- en yoğun süreçleri (bağlam) ve salt-okunur öneriler.

| Kural | Özet koşul (varsayılanlar) | Önem |
|---|---|---|
| Bellek baskısı olasılığı | 2 ardışık 30 sn penceredeki MemAvailable medyanı < %10 **ve** aynı dönemde swap etkinliği ≥ 100 sayfa/sn, major page-fault ≥ 100/sn ya da PSI bellek ≥ %10 göstergelerinden en az biri | Uyarı / Kritik olasılık |
| Kalıcı CPU yoğunluğu | Her iki pencerede örneklerin ≥ %80'i, %85 CPU'nun üzerinde | Uyarı |
| Disk G/Ç anomalisi | Her iki pencerede okuma+yazma medyanı ≥ max(3 × önceki 5 dk medyanı, 5 MiB/sn) **veya** önceki dönemde düşükken meşguliyet ≥ %80 | Gözlem |

Kuralların tanımı, gerekçeleri ve sınırlılıkları: [docs/KURALLAR.md](docs/KURALLAR.md)

## Hızlı başlangıç

```bash
# Pardus 25.1 / Debian 13 paketleriyle (root yalnızca paket kurulumu için)
sudo apt install python3 python3-psutil python3-pyside6.qtwidgets
python3 -m pardusinsight                 # canlı izleme (GUI)

# veya sanal ortamla (root gerekmez)
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pardusinsight
```

Diğer kullanımlar:

```bash
python3 -m pardusinsight --synthetic demo --speed 4     # Linux gerekmez: sentetik veriyle GUI
python3 -m pardusinsight --replay scenarios/demo.json   # kaydedilmiş senaryoyu analiz et
python3 -m pardusinsight --headless --duration 60       # GUI'siz izleme (yedek arayüz)
python3 -m pardusinsight --headless --duration 300 --export-json rapor.json --export-csv ornekler.csv
python3 -m pardusinsight --list-scenarios
```

Kurulum ayrıntıları ve sorun giderme: [docs/KURULUM.md](docs/KURULUM.md) ·
Kullanım kılavuzu: [docs/KULLANIM.md](docs/KULLANIM.md) ·
5 dakikalık demo: [docs/DEMO.md](docs/DEMO.md)

## Mimari

```
Katman 1  /proc/{stat,meminfo,vmstat,diskstats,loadavg,pressure/*}, /sys/block (okuma) · psutil
Katman 2  collectors/  → RawSnapshot (kümülatif sayaçlar)   [arka plan QThread, 2 sn]
Katman 3  core/        → Normalizer (hız/yüzde) → HistoryBuffer (≤ 30 dk, sabit kapasite)
Katman 4  analysis/    → RuleEngine (3 kural, ardışık pencereler, kanıt + belirsizlik)
Katman 5  ui/ export/  → PySide6 paneli, QPainter grafikleri, CSV/JSON raporu
```

`core/service.py` içindeki `MonitorService` Qt'den bağımsızdır; GUI, komut satırı modu ve
testler aynı hattı kullanır. Ayrıntılar: [docs/MIMARI.md](docs/MIMARI.md)

```
pardusinsight/
  collectors/  procfs.py (saf ayrıştırıcılar), system.py (/proc + psutil yedeği),
               processes.py (süreç listesi), synthetic.py (senaryolar)
  core/        models.py, normalize.py, history.py, service.py, formatting.py
  analysis/    rules.py, engine.py, windows.py, explain.py
  export/      csv_export.py, json_export.py, atomic.py
  ui/          main_window.py, worker.py, charts.py, process_model.py, alerts_view.py,
               settings_dialog.py, app.py
  cli.py, config.py
tests/         116 otomatik test (birim + entegrasyon + GUI + güvenlik)
scenarios/     önceden kaydedilmiş sentetik senaryolar (JSON)
scripts/       generate_scenarios.py, validate_metrics.py, perf_check.py, install_user.sh
docs/          kurulum, kullanım, kurallar, mimari, demo, test raporu, Pardus doğrulama listesi
```

## Güvenlik sınırları

- Root yetkisi **istemez**; root ile başlatılırsa yalnızca bilgi uyarısı verir.
- `/proc` ve `/sys` yalnızca okunur (`open(..., "r")`); hiçbir sistem ayarı değiştirilmez.
- Süreç sonlandırma, sinyal gönderme, öncelik/affinity değiştirme, kernel modülü, stres testi yoktur.
  Demo ve testler gerçek yük oluşturmak yerine **sentetik senaryolar** kullanır.
- Ağ bağlantısı kurmaz; dosya yalnızca kullanıcı "Dışa aktar" dediğinde, seçtiği yola yazılır.
  Raporlarda kullanıcı adı ve makine adı bulunmaz.
- Kaybolan süreçler (`NoSuchProcess`), izin hataları (`AccessDenied`) ve okunamayan `/proc`
  dosyaları uygulamayı çökertmez; ilgili alan "—" / "ölçülemedi" olarak gösterilir.

Bu sınırlar `tests/test_cli_safety.py` içinde kaynak kod taraması (AST) ile otomatik denetlenir.

## Testler

```bash
.venv/bin/python -m pytest -q          # ekransız ortamda GUI testleri offscreen çalışır
```

Son koşu (geliştirme makinesi, Ubuntu 24.04, Python 3.12.3, PySide6 6.12.0, psutil 7.2.2):
**116 test geçti, 0 başarısız.** psutil/PySide6 kurulu olmayan Python'da 103 test geçer;
canlı /proc testleri (6) ve GUI test modülü atlanır. Test envanteri, doğrulama tablosu ve performans ölçümleri:
[docs/TEST_RAPORU.md](docs/TEST_RAPORU.md)

> **Pardus 25.1 XFCE üzerinde henüz test edilmedi.** Bu belgelerdeki tüm ölçümler geliştirme
> makinesine aittir. Pardus'ta yapılması gereken kontroller:
> [docs/PARDUS_DOGRULAMA.md](docs/PARDUS_DOGRULAMA.md)

## Yapay zekâ kullanımı

Ders yönergesi yapay zekâ kullanımına izin verir ve kullanımın açıklanmasını ister.

- **Öneri aşaması (Aşama 1):** Öneri metninin taslağı, planlama, dil kontrolü ve test
  senaryolarının yapılandırılmasında yapay zekâ desteği alındı (öneri PDF'inde belirtildiği gibi).
- **Geliştirme aşaması:** Bu deponun ilk sürümü, ekibin onaylanan önerisi
  (`BIL461_PardusInsight.pdf`) girdi olarak verilerek **Anthropic Claude (Claude Code)** ile
  oluşturuldu. Yapay zekânın katkısı: mimari taslak, modüllerin kodu, kural eşiklerinin ilk
  değerleri, otomatik testler, sentetik senaryolar ve bu belgelerin taslağı.
- **Ekibin sorumluluğu:** Her üye kendi modülünü satır satır inceleyip açıklayabilmeli,
  Pardus 25.1 XFCE üzerinde doğrulama ve eşik kalibrasyonunu yapmalı, bulduğu hataları
  düzeltmelidir. Yapay zekâ çıktısı doğrulanmadan "çalışıyor" kabul edilmemiştir. Bu
  README'deki test sonuçları yalnızca gerçekten çalıştırılan testleri yansıtır.
- Dış projelerden kod kopyalanmamıştır. `/proc` biçimleri için Linux çekirdeği belgeleri
  (proc(5), `Documentation/admin-guide/iostats.rst`, `Documentation/accounting/psi.rst`)
  başvuru olarak kullanılmıştır. htop vb. araçların kodu kullanılmamıştır.

## Lisanslar ve atıflar

Kullanılan üçüncü taraf bileşenler ve lisansları: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)
(psutil – BSD-3-Clause, Qt for Python/PySide6 – LGPLv3, Python – PSF, pytest – MIT).
Grafik renkleri, renk körlüğüne karşı doğrulanmış kategorik bir paletten seçilmiştir.

Projenin kendi lisansı henüz seçilmedi; ekip kararı olarak `LICENSE` dosyası eklenmelidir
(PySide6 LGPLv3 dinamik bağlandığı için MIT, GPL-3.0 vb. seçeneklerle uyumludur).
