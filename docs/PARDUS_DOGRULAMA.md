# Pardus 25.1 XFCE Kabul ve Doğrulama Listesi

Bu liste **henüz uygulanmadı**. Geliştirme ve otomatik testler Ubuntu 24.04 üzerinde yapıldı
(bkz. [TEST_RAPORU.md](TEST_RAPORU.md)). Aşağıdaki maddeler temiz bir Pardus 25.1 XFCE VM'de
tek tek denenmeli, sonuç ve tarih bu dosyaya işlenmelidir.

Ortam bilgisi (doldurun):
`Pardus sürümü: ____ · çekirdek (uname -r): ____ · Python: ____ · PySide6: ____ · psutil: ____ · VM: __ vCPU / __ GiB RAM / swap: ____`

## 1. Kurulum

| # | Kontrol | Beklenen | Sonuç |
|---|---|---|---|
| 1.1 | `apt-cache policy python3-pyside6.qtwidgets python3-psutil` | Paketler depoda mevcut | ☐ |
| 1.2 | [KURULUM.md](KURULUM.md) seçenek A ile kurulum | Hatasız | ☐ |
| 1.3 | Seçenek B (venv) ile kurulum | Hatasız; gerekirse `libxcb-cursor0` notu doğru | ☐ |
| 1.4 | `scripts/install_user.sh` → XFCE menüsünde "PardusInsight" | Menüden açılıyor | ☐ |

## 2. Standart kullanıcı ve güvenlik

| # | Kontrol | Beklenen | Sonuç |
|---|---|---|---|
| 2.1 | sudo yetkisi olmayan kullanıcıyla `python3 -m pardusinsight` | Açılır, parola/yetki istemez | ☐ |
| 2.2 | Günlük sekmesinde "/proc okunamadı" hatası | Yok | ☐ |
| 2.3 | Süreçler sekmesinde root süreçlerinin G/Ç alanları | "—", uygulama çökmez | ☐ |
| 2.4 | `ss -tunap \| grep python` (uygulama açıkken) | PardusInsight'a ait bağlantı yok | ☐ |
| 2.5 | Uygulama kapandıktan sonra ev dizininde yeni dosya | Dışa aktarma yapılmadıysa yok | ☐ |
| 2.6 | `python3 -m pytest -q tests/test_cli_safety.py` | Tümü geçer | ☐ |

## 3. Ölçüm doğruluğu (PDF: en az 10 örnek karşılaştırma)

| # | Kontrol | Beklenen | Sonuç |
|---|---|---|---|
| 3.1 | `python3 scripts/validate_metrics.py --rounds 10` | MemTotal/SwapTotal eşit, CPU % farkı < 2 puan | ☐ (tabloyu TEST_RAPORU.md'ye ekleyin) |
| 3.2 | `python3 -m pytest -q tests/test_crosscheck_linux.py` | 5 test geçer | ☐ |
| 3.3 | Uygulama ile `htop`/`xfce4-taskmanager` CPU-RAM değerleri | Aynı büyüklük mertebesi | ☐ |
| 3.4 | Durum çubuğunda "PSI" bilgisi | Pardus çekirdeğinde PSI var mı? Not edin | ☐ |

## 4. Performans (PDF hedefleri)

| # | Kontrol | Beklenen | Sonuç |
|---|---|---|---|
| 4.1 | `python3 scripts/perf_check.py --gui --duration 60` (XFCE oturumunda) | Ortalama CPU < %5, RSS < 200 MiB, "YANIT VERİYOR" | ☐ |
| 4.2 | Uygulamayı 35 dk açık bırak; durum çubuğunda tampon | "30/30 dk", RAM sabit kalır (sınırsız büyüme yok) | ☐ |
| 4.3 | 60 sn boyunca pencereyi taşı, sekme değiştir, tabloyu sırala | Takılma yok | ☐ |

## 5. İşlevler

| # | Kontrol | Beklenen | Sonuç |
|---|---|---|---|
| 5.1 | `scenarios/demo.json` aç | 3 uyarı (CPU, bellek, disk), kanıt tablosu dolu | ☐ |
| 5.2 | `scenarios/cpu_spikes.json` ve `memory_low_quiet.json` aç | Uyarı yok; kural durumu nedeni açıklıyor | ☐ |
| 5.3 | CSV ve JSON dışa aktar, LibreOffice Calc'ta CSV'yi aç | Sütunlar doğru, Türkçe karakterler bozulmamış | ☐ |
| 5.4 | Dışa aktarılan JSON'u "Kayıt/senaryo aç" ile geri yükle | Aynı örnek sayısı | ☐ |
| 5.5 | Ayarlar → CPU eşiği %20 → birkaç dakika bekle | Kalıcı CPU uyarısı olağan kullanımda tetiklenir (eşik ayarı çalışıyor) | ☐ |
| 5.6 | Olağan kullanımda 30 dk (tarayıcı + ofis) | Hiç uyarı yok veya her uyarı açıklanabilir (yanlış pozitif kaydı) | ☐ |
| 5.7 | XFCE koyu tema | Grafikler ve metinler okunaklı | ☐ |
| 5.8 | `--headless --duration 60` | Satır satır özet, Ctrl+C ile temiz çıkış | ☐ |

## 6. Eşik kalibrasyonu
[KURALLAR.md](KURALLAR.md) "Kalibrasyon planı" bölümündeki adımlar uygulanmalı ve değişen
eşikler gerekçesiyle kaydedilmelidir.

## İkincil (zaman kalırsa): Pardus 25 GNOME
Bölüm 2, 4 ve 5 GNOME oturumunda (Wayland) tekrarlanmalıdır. PySide6, Wayland'de `xcb` yerine
`wayland` eklentisini kullanabilir.
