# Pardus 25.1 XFCE Kabul ve Doğrulama Listesi

Doğrulama iki katmanda yapılır:

1. **Resmî Pardus 25.1 kapsayıcısı (otomatik, her push'ta):** GitHub Actions, Docker Hub'daki
   resmî `pardus/yirmibes:1` imajında (`VERSION_ID=25.1`) bağımlılıkları **Pardus deposundan**
   kurar. Ardından testleri, ölçüm doğrulamasını, performans ölçümünü ve
   `scripts/pardus_kabul.py`'yi **root olmayan** bir kullanıcıyla çalıştırır. `.deb` paketini apt
   ile kurup dener ve kaldırır (`.github/workflows/ci.yml`). Aynı iş `pardus/yirmibes:latest`
   (25.2) için de çalışır. 35 dakikalık bellek sınırı denemesi ayrı iş akışındadır
   (`uzun-kosu.yml`). Kapsayıcı Pardus'un kullanıcı alanını (paketler, Python, PySide6, psutil)
   birebir sağlar. **Çekirdek GitHub sunucusunundur ve masaüstü oturumu yoktur.**
2. **Temiz Pardus 25.1 XFCE VM (elle):** Gerçek çekirdek, XFCE oturumu, menü, tema ve gerçek
   kullanım gerektiren maddeler. Otomatik olanların hepsi VM'de tek komutla yeniden çalışır.
   Komut sonuçları ve yapılacak elle kontrollerin listesini `docs/PARDUS_SONUCLARI.md`'ye yazar:

```bash
cd PardusInsight
python3 scripts/pardus_kabul.py --gui --kalibrasyon-suresi 1800 \
    --kayit-klasoru docs/kayitlar --cikti docs/PARDUS_SONUCLARI.md
```

`--kalibrasyon-suresi 1800` 30 dk olağan kullanım kaydı alır (bu sırada tarayıcı ve ofis ile
normal çalışın) ve eşik kalibrasyonunu yapar ([KURALLAR.md](KURALLAR.md) "Kalibrasyon"). Yalnızca
hızlı kontrol için `--hizli` kullanılabilir.

Simgeler: ✅ geçti · ❌ kaldı · ☐ VM'de yapılacak · — uygulanamaz.

## Ortam

| | Pardus 25.1 kapsayıcısı (CI) | Pardus 25.1 XFCE VM |
|---|---|---|
| Sürüm | Pardus GNU/Linux 25 (yirmibes), `VERSION_ID=25.1` | ☐ |
| Çekirdek | GitHub sunucusunun çekirdeği (7.0.0-*-azure/aws), PSI açık | ☐ (`uname -r`) |
| Python / PySide6 / psutil | 3.13.5 / 6.8.2.1 / 7.0.0 (Pardus deposundan) | ☐ |
| Kaynaklar | 4 vCPU, 16 GiB (GitHub sunucusu) | ☐ (öneri: 2 vCPU, 4 GiB, swap açık) |
| Masaüstü | yok (GUI testleri offscreen ve xvfb/xcb ile) | ☐ XFCE |

## 1. Kurulum

| # | Kontrol | Beklenen | Kapsayıcı (CI) | VM |
|---|---|---|---|---|
| 1.1 | `apt-cache policy python3-pyside6.qtwidgets python3-psutil` | Paketler depoda mevcut | ✅ Pardus deposunda (yirmibes-deb) | ☐ betik |
| 1.2 | [KURULUM.md](KURULUM.md) seçenek A ile kurulum | Hatasız | ✅ `apt-get install` ile, ek paket: `qt6-qpa-plugins` | ☐ betik |
| 1.3 | Seçenek B (venv) ile kurulum | Hatasız; gerekirse `libxcb-cursor0` notu doğru | — (Ubuntu CI'da pip ile ✅) | ☐ |
| 1.4 | `.deb` paketi: `sudo apt install ./dist/pardusinsight_*_all.deb` | Bağımlılıklar depodan gelir, menü kaydı kurulur | ✅ apt ile kuruldu, `lintian` hatasız, menü kaydı `desktop-file-validate` ile doğrulandı (betik), kaldırınca artık dosya yok | ☐ betik |
| 1.5 | XFCE menüsünde Sistem → "PardusInsight" | Menüden açılıyor, simge görünüyor | — | ☐ elle |

## 2. Standart kullanıcı ve güvenlik

| # | Kontrol | Beklenen | Kapsayıcı (CI) | VM |
|---|---|---|---|---|
| 2.1 | sudo yetkisi olmayan kullanıcıyla çalıştırma | Açılır, parola/yetki istemez | ✅ testler ve kurulu paket `ogrenci` kullanıcısıyla | ☐ betik |
| 2.2 | "/proc okunamadı" hatası | Yok | ✅ canlı izlemede yok | ☐ betik |
| 2.3 | Root süreçlerinin G/Ç alanları | "—", uygulama çökmez | ✅ `test_crosscheck_linux`, betik | ☐ betik |
| 2.4 | Uygulama açıkken ağ bağlantısı | PardusInsight'a ait bağlantı yok | ✅ betik (psutil ile süreç bağlantıları) | ☐ betik |
| 2.5 | Dışa aktarma yapılmadan ev dizininde yeni dosya | Yok | ✅ betik, `test_no_files_are_written_without_explicit_export` | ☐ betik |
| 2.6 | `python3 -m pytest -q tests/test_cli_safety.py` | Tümü geçer | ✅ (AST güvenlik denetimi dahil) | ☐ betik |

## 3. Ölçüm doğruluğu (PDF: en az 10 örnek karşılaştırma)

| # | Kontrol | Beklenen | Kapsayıcı (CI) | VM |
|---|---|---|---|---|
| 3.1 | `python3 scripts/validate_metrics.py --rounds 10` | MemTotal/SwapTotal eşit, CPU % farkı < 2 puan | ✅ en büyük CPU % farkı 0,1–0,3 puan (koşudan koşuya), bellek farkı 0 (tablo: [TEST_RAPORU.md](TEST_RAPORU.md)) | ☐ betik |
| 3.2 | `python3 -m pytest -q tests/test_crosscheck_linux.py` | 5 test geçer | ✅ | ☐ betik |
| 3.3 | Uygulama ile `free`/`htop` değerleri | Aynı büyüklük mertebesi | ✅ betik: `free -b` ile MemTotal birebir eşit, MemAvailable farkı 0 | ☐ betik + elle (htop) |
| 3.4 | PSI desteği | Not edin | GitHub çekirdeğinde var (Pardus çekirdeği değil) | ☐ betik |

## 4. Performans (PDF hedefleri)

| # | Kontrol | Beklenen | Kapsayıcı (CI) | VM |
|---|---|---|---|---|
| 4.1 | `python3 scripts/perf_check.py [--gui] --duration 60` | Ortalama CPU < %5, RSS < 200 MiB, "YANIT VERİYOR" | ✅ GUI'siz %0,08 CPU / 18,2 MiB; GUI (offscreen) %0,53 CPU / 74,9 MiB, en uzun olay döngüsü aralığı 21 ms | ☐ betik (`--gui`, XFCE) |
| 4.2 | 35 dk sürekli çalışma | Tampon 30 dk'da durur, RAM sabit | ✅ `uzun-kosu.yml`: tampon 900 örnekte sabit (kapasite 1801), RSS son 5 dk'da 52,5 → 52,6 MiB | ☐ `--uzun` |
| 4.3 | 60 sn boyunca pencereyi taşı, sekme değiştir, sırala | Takılma yok | — | ☐ elle |

## 5. İşlevler

| # | Kontrol | Beklenen | Kapsayıcı (CI) | VM |
|---|---|---|---|---|
| 5.1 | `scenarios/demo.json` aç | 3 uyarı (CPU, bellek, disk), kanıt tablosu dolu | ✅ kurulu paketle `--replay` | ☐ betik + elle (GUI) |
| 5.2 | `cpu_spikes`, `memory_low_quiet`, `disk_steady` senaryoları | Uyarı yok; kural durumu nedeni açıklıyor | ✅ betik | ☐ betik |
| 5.3 | CSV/JSON dışa aktar; CSV'yi LibreOffice Calc'ta aç | Sütunlar ve Türkçe karakterler doğru | ✅ gidiş-dönüş (betik) | ☐ elle (Calc) |
| 5.4 | Dışa aktarılan JSON'u geri yükle | Aynı örnek sayısı | ✅ | ☐ betik |
| 5.5 | Eşik ayarı (CPU %0,1) ile canlı izleme | Kalıcı CPU uyarısı tetiklenir | ✅ betik | ☐ betik |
| 5.6 | Olağan kullanımda 30 dk (tarayıcı + ofis) | Uyarı yok veya her uyarı açıklanabilir | — (masaüstü kullanımı yok) | ☐ `--kalibrasyon-suresi 1800` |
| 5.7 | XFCE koyu tema | Grafikler ve metinler okunaklı | — | ☐ elle |
| 5.8 | `--headless --duration 60`, Ctrl+C | Satır satır özet, temiz çıkış | ✅ betik | ☐ betik |
| 5.9 | GUI gerçek X11 (xcb) eklentisiyle açılış | Çökmeden açılır | ✅ xvfb altında 20 sn | ☐ XFCE |

## 6. Eşik kalibrasyonu

Yöntem ve araç: [KURALLAR.md](KURALLAR.md) "Kalibrasyon". Sentetik senaryolarla doğrulama:
[KALIBRASYON_SENTETIK.md](KALIBRASYON_SENTETIK.md). Gerçek kullanım verisi yalnızca VM'de
alınabilir. Kabul betiği `--kalibrasyon-suresi 1800` ile kaydı alır, kalibrasyonu çalıştırır ve
öneri tablosunu rapora ekler. Önerilen bir değişiklik varsa `config.py` varsayılanları ve
KURALLAR.md gerekçesiyle güncellenir.

## İkincil (zaman kalırsa): Pardus 25 GNOME

Bölüm 2, 4 ve 5 GNOME oturumunda (Wayland) tekrarlanmalıdır. PySide6, Wayland'de `xcb` yerine
`wayland` eklentisini kullanabilir. Kabul betiği oturum türünü ortam tablosuna yazar.
