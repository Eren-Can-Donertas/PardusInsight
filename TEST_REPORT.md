# Test Raporu (Aşama 2 özeti)

Bu belge Aşama 2 teslimi için test ve ölçüm sonuçlarını özetler. Ayrıntılı test kaydı
(test envanteri, mutasyon denemesi, kod incelemesi bulguları, Pardus kapsayıcısı tabloları):
[docs/TEST_RAPORU.md](docs/TEST_RAPORU.md). Pardus doğrulama durumu:
[PARDUS_VALIDATION.md](PARDUS_VALIDATION.md).

**Sonuç etiketleri:**
- **PASS:** gerçekten çalıştırıldı ve geçti.
- **NOT TESTED:** çalıştırılmadı.

Ortamlar ayrı tutulur. "Pardus kapsayıcısı" sonuçları resmî Pardus Docker imajındaki CI'dan
gelir; "geliştirme makinesi" sonuçları Ubuntu 24.04'ten gelir. **Temiz Pardus 25.1 XFCE VM'de
test yapılmadı.** Tarih: 27 Kasım 2026 · Dal: `asama2-teslim`.

## 1. Otomatik testler

| # | Ortam | Python / PySide6 / psutil | Sonuç | Kaynak |
|---|---|---|---|---|
| 1 | **Resmî Pardus 25.1 kapsayıcısı** (CI, root olmayan kullanıcı, bağımlılıklar Pardus deposundan) | 3.13.5 / 6.8.2.1 / 7.0.0 | **316 passed** (`main`, `a718982`) | CI 45783157502, iş günlüğü |
| 2 | Resmî Pardus 25.2 kapsayıcısı, Ubuntu (py3.9, py3.13), Windows (CI) | — | Hepsi başarılı (`a718982`) | CI 45783157502 |
| 3 | **CI, birleşmiş dal** (`asama2-teslim`, `4e5eb3b`): Pardus 25.1 ve 25.2 kapsayıcıları, Ubuntu py3.9/py3.13, Windows | Pardus: 3.13.5 / 6.8.2.1 / 7.0.0 | **326 passed** (Pardus 25.1, 25.2, Ubuntu); Windows 317 passed + 9 skipped | CI 45968920157 |
| 4 | Geliştirme makinesi, son kod | 3.12.3 / 6.12.0 / 7.2.2 | **329 passed**, 0 başarısız | yerel |
| 5 | Geliştirme makinesi, Debian 13 sürümleri | 3.12.3 / 6.8.2.1 / 5.9.8 | 326 passed (birleştirme commit'i) | yerel, ayrı sanal ortam |
| 6 | Geliştirme makinesi, psutil ve PySide6 yok | 3.12.3 / — / — | 309 passed, 9 skipped (birleştirme commit'i) | yerel |
| 7 | Deterministik alt küme (`-m "not linux"`) | 3.12.3 / 6.12.0 / 7.2.2 | 320 passed, 6 deselected (birleştirme commit'i) | yerel |
| 8 | **Teslim ZIP'inden temiz kurulum** | 3.12.3 / 6.12.0 / 7.2.2 | Bölüm 6 | yerel |

Test sayısının gelişimi:
- İlk sürüm: 116 test.
- Bu daldaki Aşama 2 eklemeleri: 136.
- Oğuz'un `main` dalındaki çalışması: 316.
- Birleştirme sonrası: 326. Bu daldan gelen 10 test eklendi; `main`'deki eşdeğer testlerle örtüşen 5 eşik sınırı testi yinelenmesin diye çıkarıldı.
- Üç hata düzeltmesi ve regresyon testleri sonrası: **329**.

### 1.1 Birleşmiş dalın CI sonucu

CI 45968920157 (birleşmiş dal, `4e5eb3b`): **bütün işler başarılı**. Pardus 25.1 kapsayıcısı (Python 3.13.5, PySide6 6.8.2.1, psutil 7.0.0): **326 passed**, kabul betiği **19 GEÇTİ, 0 KALDI** (3 atlandı, 8 manuel, 1 bilgi). Pardus 25 (son): 326 passed, kabul aynı. Ubuntu Python 3.9: 326 passed. Ubuntu Python 3.13: 326 passed. Windows: 317 passed, 9 skipped (Linux'a özgü). Değerler iş günlüklerinden okundu.

Birleştirmeden sonra gelen commit'lerin (üç hata düzeltmesi ve belgeler; son kod 329 test) CI sonucu PR #1'in "Checks" sekmesinde görünür.

### 1.2 Bu dalda eklenen testler (kapsam)

| Alan | Testler |
|---|---|
| Ölçüm | minor page fault ve kümülatif disk baytları; `/proc` okumasında PermissionError'da çökmeme |
| Analiz | CPU yükünün süreç kaynaklı/dağınık açıklaması (3 test) |
| Demo etiketi | CSV `data_source`, JSON `is_synthetic` ve birimler; komut satırında `[SENTETİK]`; GUI'de demo şeridi |
| Arayüz | Gerçek QThread ile açılış → örnekleme → temiz kapanış (smoke); Metodoloji içeriği |
| Hata düzeltmeleri | 1 sn altı kayıtların kesilmemesi; kayıt modunda eşik değişikliğinin yeniden analiz yapması; ayar kutusunun değerleri kırpmaması |

## 2. Statik denetim (geliştirme makinesi, son kod)

| Araç | Sonuç |
|---|---|
| mypy 2.4.1 (`pardusinsight/`) | **No issues found in 34 source files** |
| ruff 0.15.17 (E, F, W, B; satır 100) | Bu dalın dosyalarında bulgu yok. `main`'den gelen dosyalarda 10 bulgu var: 9 × E501 satır uzunluğu (`calibration.py`, `engine.py`, `build_deb.py`, testler) ve 1 × F401 (`scripts/build_deb.py` içinde kullanılmayan `Dict` importu). Bu dosyalar o kural yokken yazıldı; sahibinin kodu bu dalda değiştirilmedi, düzeltilmesi önerilir |
| desktop-file-validate | `install_user.sh` çıktısı geçerli. `.deb` içindeki `.desktop` dosyası da CI'da doğrulanıyor |
| shellcheck | **Yapılamadı** (geliştirme makinesinde kurulu değil) |

## 3. /proc – psutil doğrulaması (10 örnek)

| Ortam | En büyük farklar | Kaynak |
|---|---|---|
| Pardus 25.1 kapsayıcısı (CI) | MemTotal/SwapTotal eşit; CPU % ≤ 0,1 puan; bellek farkı 0 | CI günlüğü; tablo: docs/TEST_RAPORU.md §2 |
| Geliştirme makinesi (Ubuntu 24.04, 16 CPU) | MemTotal/SwapTotal 10/10 eşit; MemAvailable 0,00 MiB; CPU % 0,1 puan; disk okuma 0,00 MiB | `scripts/validate_metrics.py --rounds 10` |

## 4. Performans (Aşama 1 hedefleri: CPU < %5, RAM < 200 MiB, 60 sn yanıt veren GUI)

| Ortam | Mod | Ortalama CPU (tek çekirdek) | RSS en yüksek | GUI olay döngüsü | Hedef |
|---|---|---|---|---|---|
| Pardus 25.1 kapsayıcısı (CI, `a718982`, 4 vCPU) | GUI'siz | %0,08 | 17,9 MiB | — | PASS |
| | GUI + worker (offscreen) | %0,87 | 75,1 MiB | en uzun 23 ms; 0/2995 > 100 ms | PASS |
| Pardus 25.1 kapsayıcısı (CI, birleşmiş dal `4e5eb3b`) | GUI'siz | %0,10 | 18,6 MiB | — | PASS |
| | GUI + worker (offscreen) | %0,93 | 75,1 MiB | en uzun 25 ms; 0/3015 > 100 ms | PASS |
| Pardus 25.1 kapsayıcısı, 35 dk uzun koşu (`6001693`) | GUI'siz canlı | — | 53,0 → 53,1 MiB (31. → 35. dk) | tampon en çok 901 örnek (kapasite 1801) | PASS |
| Geliştirme makinesi (~500 süreç, 16 CPU, birleşmiş kod) | GUI'siz | %1,75 | 19,7 MiB | — | PASS |
| | GUI + worker (offscreen) | %3,15 | 82,2 MiB | en uzun 27 ms; 0/2999 > 100 ms | PASS |
| Temiz Pardus 25.1 XFCE VM | — | — | — | — | NOT TESTED |

Konteynerde çok az süreç çalıştığı için oradaki CPU değerleri düşüktür. Maliyetin büyük kısmı
süreç taramasıdır. Bu dalda yapılan iki optimizasyon:
- Süreç tablosunun sıralaması model içine taşındı.
- Gizli sekmeler güncellenmiyor.

Bu ikisiyle geliştirme makinesindeki GUI ölçümü %5,04'ten %3,15'e düştü.

## 5. Güvenlik denetimi

`tests/test_cli_safety.py` paketin tüm kaynağını AST ile tarar:
- **Süreç denetimi:** kill, nice, exec* ve dolaylı çağrı biçimleri.
- **Ağ:** socket, urllib, QtNetwork.
- **Dosya yazma:** yalnızca kullanıcının seçtiği yola rapor yazan `export/atomic.py` istisnadır.
- **Kalıcı ayar:** QSettings.
- **Yetki yükseltme dizgileri.**

Denetleyicinin kendisi ihlal ve izinli örneklerle sınanır. Bunlara ek olarak şunlar da test edilir: açık istek olmadan dosya yazılmaması, raporda kullanıcı ve makine adı bulunmaması, root ile başlatıldığında yalnızca uyarı verilmesi. CI'daki kabul betiği Pardus kapsayıcısında da doğruluyor: ağ bağlantısı yok, ev dizininde dosya oluşmuyor, root süreçlerinin G/Ç alanları boş.

## 6. Teslim paketi (ZIP)

`python3 scripts/build_submission.py` → `dist/PardusInsight.zip`. Betik arşivi açıp şunları denetler:
- Kök yapısı (A2 §3).
- `.git`, `.venv`, `__pycache__` ve önbelleklerin bulunmaması.
- Bu belge, gereksinim matrisi gibi geliştirici belgelerinin ZIP'te olmaması.
- Kurs PDF'lerinin ve 2 MiB'tan büyük dosyaların bulunmaması.
- README bağlantılarının çözülmesi.
- `VIDEO_LINK.txt` içeriği.

ZIP sonuçları son derlemeden sonra aşağıya eklenir.

*(Son derleme ve temiz kurulum sonuçları: bölüm 6.1.)*

## 7. Doğrulanmayanlar

| Konu | Durum |
|---|---|
| Temiz Pardus 25.1 XFCE VM: gerçek çekirdek (PSI), XFCE menüsü, koyu tema, yüksek DPI, gerçek pencere yöneticisinde performans | NOT TESTED; `scripts/pardus_kabul.py --gui` ile yapılacak |
| Gerçek kullanım verisiyle eşik kalibrasyonu ve yanlış pozitif oranı | NOT TESTED; araç hazır (`scripts/kalibrasyon.py`) |
| Düşük kaynaklı VM (2 vCPU) | NOT TESTED |
| GNOME/Wayland | NOT TESTED (ek hedef) |
| shellcheck | Araç yok |
