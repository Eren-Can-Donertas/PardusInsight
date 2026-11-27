# Pardus 25.1 XFCE Doğrulama Planı ve Kabul Listesi

> **DURUM: NOT TESTED (Pardus üzerinde test yapılmadı).**
>
> **Neden?** Geliştirme bu ana kadar Ubuntu 24.04 çalışan bir makinede yapıldı. Bu makinede
> Pardus ISO'su, Pardus sanal makinesi ya da hazır bir VM imajı yok. Resmî Pardus Docker
> imajı (`pardus/yirmibes`) ile kısmi bir kullanıcı alanı testi denendi. Ancak imajı indirme
> işlemi, yapay zekâ aracının otomatik izin denetimi tarafından reddedildi ve atlatılmadı.
> Bu yüzden aşağıdaki maddelerin **tamamı ekip tarafından gerçek Pardus'ta yapılmalıdır.**
> Ubuntu'da alınan sonuçlar [TEST_REPORT.md](TEST_REPORT.md) içinde ayrı tutulur ve Pardus
> sonucu olarak sunulmaz.

Ortam bilgisi (doldurun):
`Pardus sürümü: ____ · çekirdek (uname -r): ____ · Python: ____ · PySide6: ____ · psutil: ____ · VM: __ vCPU / __ GiB RAM / swap: ____ · Test eden: ____ · Tarih: ____`

## 0. Temiz Pardus 25.1 XFCE kurulumu (VM)

1. Pardus 25.1 XFCE ISO'sunu resmî siteden indirin (pardus.org.tr) ve VirtualBox/GNOME Boxes
   üzerinde en az 2 vCPU, 4 GiB RAM ve 25 GiB diskle kurun.
2. Kurulumda oluşturulan kullanıcıya ek olarak **sudo yetkisi olmayan** bir test kullanıcısı
   açın. Paketleri yönetici hesabıyla kurup uygulamayı bu standart kullanıcıyla çalıştırın:
   ```bash
   sudo adduser denetci          # yönetici hesabından; denetci sudo grubunda olmamalı
   ```
3. VM'nin anlık görüntüsünü (snapshot) alın. Tekrar gerektiğinde temiz kuruluma dönülebilir.

## 1. Bağımlılıkların kurulması (kopyala-yapıştır)

Yönetici hesabıyla:

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-psutil \
     python3-pyside6.qtcore python3-pyside6.qtgui python3-pyside6.qtwidgets python3-pytest
apt-cache policy python3-psutil python3-pyside6.qtwidgets   # sürümleri not edin
```

Standart kullanıcıyla (`su - denetci` veya oturum değiştirerek):

```bash
git clone https://github.com/Eren-Can-Donertas/PardusInsight.git
cd PardusInsight
# ya da teslim ZIP'inden: unzip PardusInsight.zip && cd PardusInsight/source_code
python3 -m pardusinsight --version
```

Dağıtım paketleri bulunamazsa sanal ortam yedeği (root gerekmez):

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
# xcb hatası alınırsa yönetici hesabıyla: sudo apt install libxcb-cursor0
```

## 2. Otomatik doğrulama betiği

XFCE oturumu açık standart kullanıcıyla, proje klasöründe:

```bash
sh scripts/pardus_validate.sh                 # sonuçlar ./pardus_dogrulama_<tarih>/ altında
# sanal ortamla: PYTHON=.venv/bin/python sh scripts/pardus_validate.sh
```

Betik hiçbir şey kurmaz ve sistemi değiştirmez. Sırasıyla şunları yapar ve çıktılarını kaydeder:
ortam bilgisi, paket sürümleri, standart kullanıcı kontrolü, `pytest`, 10 örnekli
/proc–psutil karşılaştırması, 60 sn canlı headless izleme (CSV/JSON çıktısıyla), demo kayıt
analizi, 60 sn GUI'siz ve GUI'li performans ölçümü, gerçek pencereden ekran görüntüleri.
`ozet.txt` dosyasını [TEST_REPORT.md](TEST_REPORT.md) içindeki "Pardus sonuçları" bölümüne
ekleyin. Ekran görüntülerini teknik rapora koyabilirsiniz.

## 3. İsteğe bağlı kısmi kontrol: Pardus Docker imajı

VM'nin yerini **tutmaz**, çünkü konteyner ana makinenin çekirdeğini kullanır ve XFCE yoktur.
Yine de Pardus 25 depolarındaki paket adları ve sürümleriyle kurulumu ve otomatik testleri
hızlıca doğrular. Docker kurulu bir Linux makinede, proje klasöründe çalıştırın:

```bash
docker run --rm -v "$PWD":/src:ro pardus/yirmibes bash -c '
  set -e
  apt-get update -qq
  apt-get install -y -qq python3 python3-psutil python3-pyside6.qtwidgets python3-pytest \
      libegl1 libfontconfig1 libxkbcommon0 > /dev/null
  cat /etc/os-release | head -3
  python3 -c "import sys, psutil, PySide6; print(sys.version.split()[0], psutil.__version__, PySide6.__version__)"
  cp -r /src /tmp/pi && cd /tmp/pi
  QT_QPA_PLATFORM=offscreen python3 -m pytest -q -p no:cacheprovider'
```

Sonucu "Pardus 25 konteyner (kullanıcı alanı) — kısmi" etiketiyle raporlayın. Bu sonuç,
aşağıdaki XFCE maddelerinin yerine geçmez.

## 4. Elle yapılacak kabul kontrolleri

### 4.1 Kurulum

| # | Kontrol | Beklenen | Sonuç |
|---|---|---|---|
| 1.1 | `apt-cache policy python3-pyside6.qtwidgets python3-psutil` | Paketler depoda mevcut | ☐ |
| 1.2 | Bölüm 1'deki apt kurulumu | Hatasız | ☐ |
| 1.3 | Sanal ortam (venv) kurulumu | Hatasız; gerekirse `libxcb-cursor0` notu doğru | ☐ |
| 1.4 | `scripts/install_user.sh` → XFCE menüsünde "PardusInsight" | Menüden açılıyor | ☐ |
| 1.5 | Teslim ZIP'inden kurulum (`source_code/`) | README adımlarıyla açılıyor | ☐ |

### 4.2 Standart kullanıcı ve güvenlik

| # | Kontrol | Beklenen | Sonuç |
|---|---|---|---|
| 2.1 | sudo yetkisi olmayan kullanıcıyla `python3 -m pardusinsight` | Açılır, parola/yetki istemez | ☐ |
| 2.2 | Günlük sekmesinde "/proc okunamadı" hatası | Yok | ☐ |
| 2.3 | Süreçler sekmesinde root süreçlerinin G/Ç alanları | "—", uygulama çökmez | ☐ |
| 2.4 | `ss -tunap \| grep python` (uygulama açıkken) | PardusInsight'a ait bağlantı yok | ☐ |
| 2.5 | Uygulama kapandıktan sonra ev dizininde yeni dosya | Dışa aktarma yapılmadıysa yok | ☐ |
| 2.6 | `python3 -m pytest -q tests/test_cli_safety.py` | Tümü geçer | ☐ |

### 4.3 Canlı metrikler ve doğruluk

| # | Kontrol | Beklenen | Sonuç |
|---|---|---|---|
| 3.1 | `python3 scripts/validate_metrics.py --rounds 10` | MemTotal/SwapTotal eşit, CPU % farkı < 2 puan | ☐ |
| 3.2 | `python3 -m pytest -q -m linux` | Canlı /proc testleri geçer | ☐ |
| 3.3 | Uygulama ile `xfce4-taskmanager` CPU/RAM değerleri | Aynı büyüklük mertebesi | ☐ |
| 3.4 | Durum satırındaki "PSI" bilgisi | Pardus çekirdeğinde PSI var mı? Not edin | ☐ |
| 3.5 | Grafikler 2 sn'de bir güncelleniyor | Evet | ☐ |

### 4.4 Performans (öneri PDF'indeki hedefler)

| # | Kontrol | Beklenen | Sonuç |
|---|---|---|---|
| 4.1 | `python3 scripts/perf_check.py --gui --duration 60` (XFCE oturumunda) | Ortalama CPU < %5, RSS < 200 MiB, "YANIT VERİYOR" | ☐ |
| 4.2 | Uygulamayı 35 dk açık bırakın, durum çubuğundaki tampon bilgisine bakın | "30/30 dk", RAM sabit (sınırsız büyüme yok) | ☐ |
| 4.3 | 60 sn boyunca pencereyi taşıyın, sekme değiştirin, tabloyu sıralayın | Takılma yok | ☐ |

### 4.5 İşlevler

| # | Kontrol | Beklenen | Sonuç |
|---|---|---|---|
| 5.1 | `scenarios/demo.json` aç | 3 uyarı (CPU, bellek, disk), kanıt tablosu dolu, **sarı "DEMO / SENTETİK VERİ" şeridi görünür** | ☐ |
| 5.2 | `scenarios/cpu_spikes.json` ve `memory_low_quiet.json` aç | Uyarı yok; kural durumu nedeni açıklıyor | ☐ |
| 5.3 | CSV ve JSON dışa aktar; CSV'yi LibreOffice Calc'ta aç | Sütunlar doğru, Türkçe karakterler bozuk değil, `data_source` sütunu dolu | ☐ |
| 5.4 | Dışa aktarılan JSON'u "Kayıt/senaryo aç" ile geri yükle | Aynı örnek sayısı | ☐ |
| 5.5 | Ayarlar → CPU eşiği %20 → birkaç dakika bekle | Kalıcı CPU uyarısı tetiklenir (eşik ayarı çalışıyor) | ☐ |
| 5.6 | Olağan kullanımda 30 dk (tarayıcı + ofis) | Hiç uyarı yok veya her uyarı açıklanabilir (yanlış pozitif kaydı tutun) | ☐ |
| 5.7 | XFCE koyu tema | Grafikler ve metinler okunaklı | ☐ |
| 5.8 | `--headless --duration 60` | Satır satır özet, Ctrl+C ile temiz çıkış | ☐ |
| 5.9 | `--synthetic demo --speed 4` | Pencerede ve başlıkta sentetik veri olduğu açıkça yazıyor | ☐ |
| 5.10 | Pencereyi kapat (Çık / Ctrl+Q) | Süreç birkaç saniye içinde sonlanır (`pgrep -f pardusinsight` boş) | ☐ |

## 5. Eşik kalibrasyonu

[docs/KURALLAR.md](docs/KURALLAR.md) içindeki "Kalibrasyon planı" bölümü uygulanmalıdır.
Değiştirilen eşikler gerekçesiyle kaydedilmelidir. Olağan kullanımda (5.6) yanlış pozitif
çıkarsa ilgili kuralın eşiği ve gerekçesi rapora yazılmalıdır.

## 6. İkincil (zaman kalırsa): Pardus 25 GNOME

4.2, 4.4 ve 4.5 bölümleri GNOME oturumunda (Wayland) tekrarlanmalıdır. PySide6 Wayland'de
`wayland` eklentisini kullanır.
