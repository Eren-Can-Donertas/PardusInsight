# Üçüncü Taraf Bileşenler ve Lisanslar

PardusInsight aşağıdaki bileşenleri **bağımlılık olarak kullanır**; kaynak kodlarından
herhangi bir parça projeye kopyalanmamıştır.

| Bileşen | Kullanım | Lisans | Kaynak |
|---|---|---|---|
| Python 3 | Uygulama dili ve standart kütüphane (csv, json, dataclasses, statistics…) | PSF License | https://www.python.org/psf/summary/ |
| psutil | Süreç listesi; /proc okunamazsa sistem metrikleri için yedek; çapraz doğrulama | BSD-3-Clause | https://github.com/giampaolo/psutil/blob/master/LICENSE |
| Qt for Python (PySide6, QtCore/QtGui/QtWidgets) | Masaüstü arayüzü | LGPLv3 / GPLv3 (ticari seçenek de vardır) | https://doc.qt.io/qtforpython-6/licenses.html |
| Qt 6 (PySide6 ile gelir) | Arayüz çatısı | LGPLv3 / GPLv3 | https://doc.qt.io/qt-6/licensing.html |
| pytest (yalnızca geliştirme) | Otomatik testler | MIT | https://github.com/pytest-dev/pytest/blob/main/LICENSE |

## LGPLv3 notu (PySide6 / Qt)

PySide6 ve Qt kütüphaneleri değiştirilmeden, ayrı paketler olarak (Debian/Pardus paketleri
veya PyPI tekerlekleri) dinamik olarak kullanılır. Kullanıcı bu kütüphaneleri kendi
sürümleriyle değiştirebilir. PardusInsight bu kütüphanelerin kaynak kodunu içermez ve
yeniden dağıtmaz.

## Başvuru belgeleri (kod değil)

- Linux `proc(5)` kılavuz sayfası: https://man7.org/linux/man-pages/man5/proc.5.html
- Linux çekirdeği, I/O istatistikleri: `Documentation/admin-guide/iostats.rst`
- Linux çekirdeği, Pressure Stall Information: `Documentation/accounting/psi.rst`

## Esinlenilen ancak kodu kullanılmayan araçlar

- htop (GPL-2.0-or-later), https://github.com/htop-dev/htop: Yalnızca işlevsel
  karşılaştırma için anılmıştır. Kodu incelenmemiş veya kopyalanmamıştır.

## Grafik paleti

Grafik seri renkleri (`#2a78d6`, `#eb6834` ve koyu tema karşılıkları) ile durum renkleri,
renk körlüğü ayrımı için doğrulanmış genel amaçlı bir veri görselleştirme paletinden
alınmıştır. Bunlar marka veya telif kapsamında bir öğe değildir.
