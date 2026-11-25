# Paketleme (Pardus/Debian `.deb` ve pip)

PardusInsight iki biçimde dağıtılabilir:

| Biçim | Ne zaman | Komut |
|---|---|---|
| **`.deb` paketi** (önerilen) | Pardus 25.1 / Debian 13'e sistem geneline kurulum, menü kaydı ve simgeyle | `python3 scripts/build_deb.py` → `dist/pardusinsight_<sürüm>_all.deb` |
| Python tekerleği | Sanal ortama (`venv`) veya Linux dışı geliştirme ortamına kurulum | `python3 -m build` → `dist/pardusinsight-<sürüm>-py3-none-any.whl` |

## `.deb` paketini oluşturma

```bash
python3 scripts/build_deb.py            # dist/pardusinsight_0.1.0_all.deb
python3 scripts/build_deb.py --liste    # control alanları ve dosya listesi
make deb                                # aynısı
```

`scripts/build_deb.py` yalnızca Python standart kütüphanesini kullanır (`tarfile`, `lzma`,
`gzip`, `hashlib`). `dpkg-deb` gerektirmez; paket Windows'ta da üretilebilir. Çıktı
`dpkg-deb --build` ile aynı yapıdadır: `ar` arşivi içinde sırasıyla `debian-binary`,
`control.tar.xz`, `data.tar.xz`.

- **Yeniden üretilebilir:** Dosyalar `root:root`, zaman damgası `SOURCE_DATE_EPOCH` veya
  changelog tarihi, gzip başlıkları zaman damgasız, satır sonları LF. Aynı kaynaktan her
  platformda bayt bayt aynı paket çıkar (`tests/test_packaging.py` bunu denetler).
- **Sürüm tek kaynaktan:** `pardusinsight/__init__.py` içindeki `__version__`. Betik,
  `packaging/debian/changelog` en üst kaydının aynı sürümde olmasını şart koşar.

## Paket düzeni

| Yol | İçerik |
|---|---|
| `/usr/bin/pardusinsight` | Başlatıcı (modül dizinini yola ekler, `pardusinsight.cli.main()`'i çağırır) |
| `/usr/share/pardusinsight/pardusinsight/` | Uygulama modülleri (Debian Python politikası: uygulamaya özel dizin) |
| `/usr/share/pardusinsight/scenarios/` | Önceden kaydedilmiş sentetik senaryolar; arayüzdeki "Kayıt/senaryo aç" burada açılır |
| `/usr/share/applications/pardusinsight.desktop` | XFCE/GNOME menü kaydı (Sistem → PardusInsight) |
| `/usr/share/icons/hicolor/scalable/apps/pardusinsight.svg` | Uygulama simgesi |
| `/usr/share/man/man1/pardusinsight.1.gz` | Türkçe kılavuz sayfası (`man pardusinsight`) |
| `/usr/share/doc/pardusinsight/` | `copyright`, `changelog.gz`, README, kullanım ve kural belgeleri |

**Bağımlılıklar** (`packaging/debian/control.in`): `python3 (>= 3.9)`, `python3-psutil (>= 5.9)`,
`python3-pyside6.qtcore/qtgui/qtwidgets (>= 6.5)`. Önerilen: `qt6-qpa-plugins` (X11 için `xcb`
eklentisi).

**Bakımcı betikleri:** `postinst` yalnızca `py3compile` ile bayt kodu derler. `prerm` bayt
kodu önbelleğini temizler, böylece paket kaldırıldığında dizinde artık dosya kalmaz. Hiçbir
betik servis kurmaz veya sistem ayarı değiştirmez.

## Kurulum ve kaldırma (Pardus 25.1)

```bash
sudo apt install ./dist/pardusinsight_0.1.0_all.deb   # bağımlılıkları Pardus deposundan çeker
pardusinsight                                          # veya menü: Sistem → PardusInsight
pardusinsight --headless --replay /usr/share/pardusinsight/scenarios/demo.json
sudo apt remove pardusinsight                          # kaldırma
```

`sudo` yalnızca paket kurulumu/kaldırması içindir; uygulamanın **çalışması** root gerektirmez.

## Doğrulama

| Denetim | Nerede |
|---|---|
| ar üye sırası, control alanları, md5sums, sahiplik/izinler, üst dizinler, LF satır sonu, gzip zaman damgası, yeniden üretilebilirlik, kılavuzda her CLI seçeneği | `tests/test_packaging.py` (her platformda) |
| Paketten çıkarılan başlatıcının `--version` ve kayıt analizi çalıştırması | `tests/test_packaging.py` |
| `dpkg-deb --info/--contents`, `lintian`, `desktop-file-validate` | CI (`.github/workflows/ci.yml`) |
| Pardus 25.1 resmî kapsayıcısında `apt install ./*.deb`, standart kullanıcıyla çalıştırma, `xvfb` altında GUI açılışı, `apt purge` sonrası artık dosya olmaması | CI, "Pardus 25.1" işi |

## Yeni sürüm çıkarma

1. `pardusinsight/__init__.py` içindeki `__version__` değerini artırın.
2. `packaging/debian/changelog` başına aynı sürümle yeni kayıt ekleyin (tarih RFC 2822 biçiminde,
   ör. `date -R` çıktısı).
3. `python3 -m pytest -q tests/test_packaging.py && python3 scripts/build_deb.py`

## Bilinen açık konu: proje lisansı

Ekip henüz projenin kendi lisansını seçmedi (README, "Lisanslar ve atıflar"). Bu yüzden
`packaging/debian/copyright` geçici `LicenseRef-PardusInsight-Ekip` kaydı içerir. Ekip bir
lisans seçtiğinde bu dosya, `LICENSE` ve `pyproject.toml` birlikte güncellenmelidir.
