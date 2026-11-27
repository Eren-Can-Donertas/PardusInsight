# Pardus Doğrulama Durumu (Aşama 2 özeti)

Bu belge Aşama 2 teslimi için Pardus doğrulamasının **durumunu** özetler. Ayrıntılı kabul
listesi ve sonuçlar ekibin kayıt belgelerindedir:
- [docs/PARDUS_DOGRULAMA.md](docs/PARDUS_DOGRULAMA.md): Madde madde kabul listesi; konteyner
  sonuçları ve VM'de yapılacaklar.
- [docs/TEST_RAPORU.md](docs/TEST_RAPORU.md): CI test kaydı.
- `scripts/pardus_kabul.py`: Listenin otomatik maddelerini tek komutla çalıştırır.

## 1. Özet

| Katman | Durum | Kanıt |
|---|---|---|
| **Resmî Pardus 25.1 Docker imajı** (`pardus/yirmibes:1`, kullanıcı alanı) | **PASS** | GitHub Actions `ci.yml`, "Pardus 25.1 kapsayıcısı" işi; aşağıdaki doğrulanmış koşular |
| **Resmî Pardus 25.2 Docker imajı** (`pardus/yirmibes:latest`) | **PASS** | Aynı iş akışı, "Pardus 25 (son) kapsayıcısı" işi |
| **35 dk uzun koşu** (Pardus 25.1 imajı) | **PASS** | `uzun-kosu.yml` |
| **Temiz Pardus 25.1 XFCE VM** (gerçek çekirdek + masaüstü) | **NOT TESTED** | Ekip yapacak (bölüm 3) |

**Konteyner neyi kanıtlar:**
- Paket adları ve kurulumun (seçenek A ve `.deb`) Pardus deposuyla çalıştığını.
- Pardus'un Python/PySide6/psutil sürümleriyle (3.13.5 / 6.8.2.1 / 7.0.0) bütün testlerin geçtiğini.
- Uygulamanın standart kullanıcıyla çalıştığını, ağ bağlantısı kurmadığını ve dosya bırakmadığını.
- Performans hedeflerini.

**Neyi kanıtlamaz:**
- Çekirdek GitHub sunucusunundur; PSI ve disk aygıtları Pardus çekirdeğinde farklı olabilir.
- Masaüstü oturumu yoktur. XFCE menüsü, tema, gerçek pencere yöneticisi ve gerçek kullanımla
  kalibrasyon VM gerektirir.

## 2. Doğrulanmış CI koşuları

Aşağıdaki değerler GitHub Actions iş günlüklerinden okunarak doğrulandı (27.11.2026).

| Koşu | Commit | İş | Sonuç |
|---|---|---|---|
| CI 45783157502 | `a718982` (`main`) | Pardus 25.1 kapsayıcısı | Python 3.13.5, PySide6 6.8.2.1, psutil 7.0.0 · **316 passed** · `validate_metrics` 10 örnek · GUI'siz %0,08 CPU / 17,9 MiB, GUI %0,87 CPU / 75,1 MiB, en uzun olay döngüsü aralığı 23 ms (0/2995 > 100 ms) · `.deb` apt ile kuruldu ve kaldırıldı · kabul betiği **19 GEÇTİ, 0 KALDI**, 3 atlandı, 8 manuel, 1 bilgi |
| CI 45783157502 | `a718982` | Pardus 25 (son), Ubuntu py3.9/3.13, Windows | Hepsi başarılı |
| Uzun koşu 45781589969 | `6001693` (`main`) | Pardus 25.1, 35 dk canlı izleme | Tampon en çok 901 örnek (kapasite 1801), RSS 31. dk 53,0 MiB → 35. dk 53,1 MiB |
| CI 45968920157 | `4e5eb3b` (`asama2-teslim`, birleşmiş) | Pardus 25.1 ve 25 (son) kapsayıcıları, Ubuntu, Windows | Hepsi başarılı. Pardus 25.1: **326 passed**, kabul **19 GEÇTİ, 0 KALDI**. GUI'siz %0,10 CPU / 18,6 MiB; GUI %0,93 / 75,1 MiB, en uzun aralık 25 ms |

Bu oturumda Pardus imajı yerel makineye ayrıca indirilmedi. Yapay zekâ aracının izin denetimi
`docker pull` komutunu reddetti ve bu engel aşılmaya çalışılmadı. Konteyner sonuçlarının
tamamı ekibin CI iş akışından gelir.

## 3. Temiz Pardus 25.1 XFCE VM'de yapılacaklar (NOT TESTED)

1. Pardus 25.1 XFCE ISO'su ile VM kurun (öneri: 2 vCPU, 4 GiB RAM, swap açık). Sudo yetkisi
   olmayan bir test kullanıcısı açın.
2. Kurulum ([docs/KURULUM.md](docs/KURULUM.md) veya `.deb`):
   ```bash
   sudo apt update && sudo apt install -y git python3 python3-psutil \
        python3-pyside6.qtcore python3-pyside6.qtgui python3-pyside6.qtwidgets python3-pytest
   git clone https://github.com/Eren-Can-Donertas/PardusInsight.git && cd PardusInsight
   ```
3. XFCE oturumunda standart kullanıcıyla, otomatik maddeler ve 30 dk kalibrasyon kaydı:
   ```bash
   python3 scripts/pardus_kabul.py --gui --kalibrasyon-suresi 1800 \
       --kayit-klasoru docs/kayitlar --cikti docs/PARDUS_SONUCLARI.md
   ```
4. Raporun "MANUEL" olarak listelediği elle kontroller: venv kurulumu, XFCE menüsünden açılış,
   htop karşılaştırması, 60 sn etkileşimde takılma olmaması, LibreOffice'te CSV, 30 dk olağan
   kullanımda yanlış pozitif kaydı, koyu tema, kalibrasyon. Konteynerde atlanan grafik oturum
   maddelerini (4.1b, 5.9) de VM'de çalıştırın.
5. Sonuçları `docs/PARDUS_SONUCLARI.md` olarak commit'leyin. Teknik raporun 12. ve 13.
   bölümlerine VM sonuçlarını ekleyin; mümkünse
   `python3 scripts/capture_screenshots.py ekran/` ile XFCE ekran görüntülerini alın.
