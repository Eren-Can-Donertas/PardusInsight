# Kurulum ve Çalıştırma (Pardus 25.1 XFCE)

> **Durum:** Paket adları ve kurulum adımları (seçenek A ve `.deb`), resmî Pardus 25.1 Docker
> imajında (`pardus/yirmibes:1`) her push'ta CI ile doğrulanıyor. Bağımlılıklar Pardus
> deposundan geliyor: Python 3.13.5, PySide6 6.8.2.1, psutil 7.0.0. Temiz bir XFCE VM'de
> masaüstü oturumuyla yapılacak kontroller [PARDUS_DOGRULAMA.md](PARDUS_DOGRULAMA.md)'de
> listelenmiştir; `scripts/pardus_kabul.py` bunları tek komutla çalıştırır.

PardusInsight'ın **çalışması** root gerektirmez. `sudo` yalnızca paket kurulumunda (`.deb` ve
seçenek A) gerekir; seçenek B tamamen kullanıcı yetkisiyle kurulur.

## Önerilen: `.deb` paketiyle kurulum

Paket, bağımlılıkları (python3-psutil, python3-pyside6.*) Pardus deposundan kendisi çeker. Menü
kaydı (Sistem → PardusInsight), simge, `man pardusinsight` kılavuzu ve hazır senaryolar
(`/usr/share/pardusinsight/scenarios/`) ile gelir. Ayrıntılar: [PAKETLEME.md](PAKETLEME.md)

```bash
cd PardusInsight
python3 scripts/build_deb.py                        # dist/pardusinsight_0.1.0_all.deb
sudo apt install ./dist/pardusinsight_0.1.0_all.deb
pardusinsight                                        # veya menüden
sudo apt remove pardusinsight                        # kaldırma
```

Paket, GitHub Actions'taki her derlemede yapıt (artifact) olarak da üretilir.

## Gereksinimler

- Pardus 25.1 XFCE (x86-64) veya başka bir güncel Linux dağıtımı
- Python ≥ 3.9 (Pardus 25.1 / Debian 13 ile Python 3.13 gelmesi beklenir)
- psutil ≥ 5.9, PySide6 ≥ 6.5 (QtCore, QtGui, QtWidgets)

## Seçenek A – Dağıtım paketleriyle

```bash
sudo apt update
sudo apt install python3 python3-psutil \
     python3-pyside6.qtcore python3-pyside6.qtgui python3-pyside6.qtwidgets qt6-qpa-plugins
# testler için (isteğe bağlı)
sudo apt install python3-pytest

cd PardusInsight
python3 -m pardusinsight
```

## Seçenek B – Sanal ortam (root gerekmez)

```bash
sudo apt install python3-venv      # yalnızca python3-venv yüklü değilse
cd PardusInsight
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pardusinsight
```

PyPI'deki PySide6 tekerlekleri X11'de `libxcb-cursor0` ister. Uygulama
`Could not load the Qt platform plugin "xcb"` hatasıyla açılmazsa:

```bash
sudo apt install libxcb-cursor0
```

## Menüye kısayol ekleme (kullanıcı düzeyinde, A/B seçenekleri için)

`.deb` paketi menü kaydını kendisi kurar. Depodan çalıştırırken (seçenek A veya B):

```bash
scripts/install_user.sh            # ~/.local/share/applications/pardusinsight.desktop + simge
```

Betik yalnızca kullanıcının kendi dizinine bir `.desktop` dosyası ve simge yazar, root istemez.
Kaldırmak için `scripts/install_user.sh --remove` kullanın.

## Çalıştırma modları

`.deb` paketiyle kurulduysa `python3 -m pardusinsight` yerine kısaca `pardusinsight` yazılır.

| Komut | Açıklama |
|---|---|
| `python3 -m pardusinsight` | Canlı izleme (GUI), 2 sn aralık, 30 dk geçmiş |
| `python3 -m pardusinsight --interval 5` | Farklı örnekleme aralığı |
| `python3 -m pardusinsight --synthetic demo --speed 4` | Sentetik veri (Linux gerekmez), 4× hız |
| `python3 -m pardusinsight --replay scenarios/demo.json` | Kaydedilmiş senaryo/raporu analiz et |
| `python3 -m pardusinsight --headless --duration 60` | GUI'siz izleme (PySide6 gerekmez) |
| `python3 -m pardusinsight --headless --duration 600 --export-json r.json --export-csv o.csv` | GUI'siz izleme + rapor |
| `python3 -m pardusinsight --config ayarlar.json` | Eşikleri JSON dosyasından oku |
| `python3 -m pardusinsight --list-scenarios` | Sentetik senaryoları listele |

`ayarlar.json` örneği (yalnızca değiştirmek istediğiniz alanlar):

```json
{"sample_interval_s": 2.0, "analysis": {"cpu_high_pct": 90, "window_s": 45}}
```

## Linux dışı geliştirme ortamları

Windows/macOS'ta canlı izleme yoktur, ama arayüz sentetik veriyle geliştirilip test edilebilir:

```bash
pip install PySide6-Essentials pytest     # psutil isteğe bağlı
python -m pardusinsight --synthetic demo
python -m pytest -q                       # Linux'a özgü testler otomatik atlanır
```

## Sorun giderme

| Belirti | Olası neden / çözüm |
|---|---|
| `PySide6 yüklenemedi` | PySide6 kurulu değil: seçenek A veya B. GUI'siz kullanım için `--headless`. |
| `xcb` eklentisi yüklenemiyor | `sudo apt install libxcb-cursor0` (pip ile kurulan PySide6) |
| Süreçlerin G/Ç sütunları "—" | Normal durum: diğer kullanıcıların süreçlerinin `/proc/<pid>/io` dosyası root olmadan okunamaz |
| "PSI: yok" | Çekirdekte PSI kapalı (`psi=0`). Bellek kuralı swap ve page-fault göstergeleriyle çalışmaya devam eder |
| Günlükte "/proc okunamadı; psutil yedeği kullanıldı" | Kapsayıcı veya kısıtlı ortam. Değerler psutil'den gelir, kural sonuçları etkilenebilir |
