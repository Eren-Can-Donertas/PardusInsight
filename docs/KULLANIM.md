# Kullanım Kılavuzu

## Ana pencere

**Araç çubuğu**

| Düğme | Kısayol | İşlev |
|---|---|---|
| Duraklat / Sürdür | Ctrl+P | Örneklemeyi durdurur veya sürdürür (geçmiş korunur) |
| Canlı izlemeye dön | — | Kayıt analizinden çıkar, geçmişi ve uyarıları sıfırlayıp canlı izlemeye döner |
| CSV dışa aktar… | Ctrl+E | Tampondaki örnekleri `<ad>.csv`, uyarıları `<ad>_uyarilar.csv` dosyasına yazar |
| JSON rapor… | Ctrl+J | Meta veri, ayarlar, özet istatistikler, uyarılar ve örnekleri içeren rapor |
| Kayıt/senaryo aç… | Ctrl+O | JSON raporu veya `scenarios/*.json` dosyasını yükler, kuralları baştan çalıştırır |
| Ayarlar… | — | Örnekleme aralığı, süreç listesi sıklığı ve kural eşikleri |
| Hakkında | — | Sürüm, güvenlik sınırları, lisanslar |

Dışa aktarma yalnızca bu düğmelerle, kullanıcının seçtiği yola yapılır. Uygulama
kendiliğinden hiçbir dosya yazmaz.

## Sekmeler

### Genel Bakış
- **Özet kutucukları:** CPU (kullanıcı/çekirdek/iowait payı), RAM (kullanılabilir/toplam),
  Swap (giriş/çıkış sayfa/sn, major fault/sn), Disk (okuma/yazma, meşguliyet), 1 dk yük,
  aktif uyarı sayısı.
- **Grafikler:** CPU %, Bellek/Swap doluluğu, Swap etkinliği ve major page-fault, Disk G/Ç.
  Aralık seçici: son 1 / 5 / 15 / 30 dk. Kesik çizgi kural eşiğidir. Sarı/kırmızı/gri
  gölgeli alanlar uyarı aralıklarını gösterir ve üzerlerinde "⚠ Uyarı", "⛔ Kritik olasılık",
  "ℹ Gözlem" etiketi bulunur. Fare grafiğin üzerine getirildiğinde o andaki değerler görünür.
- **Kaynak bilgisi:** veri kaynağı ve PSI desteği.

### Süreçler
Salt-okunur süreç tablosu: PID, ad, kullanıcı, durum, CPU % (tüm çekirdekler = %100),
RSS, bellek %, iş parçacığı, okuma/yazma hızı. Sütun başlığına tıklayarak sıralayın, filtre
kutusuna ad, kullanıcı veya PID yazın. Okunamayan alanlar "—" ile gösterilir; fareyle
üzerine gelindiğinde nedeni açıklanır. Süreçler üzerinde **hiçbir işlem yapılamaz**.

### Uyarılar
- Solda uyarı listesi (aktif olanlar üstte). Sağda seçilen uyarının ayrıntısı: önem,
  güven, zaman aralığı, özet, **kanıt tablosu** (rol, metrik, değer, eşik, pencere),
  bağlam süreçleri, belirsizlikler ve salt-okunur öneriler.
- Altta **Kural durumu**: her kuralın son değerlendirmesi ve tetiklenmediyse nedeni
  (ör. "Yetersiz veri", "kullanılabilir bellek düşük ancak … desteklemiyor").

### Günlük
Başlatma bilgisi, yeni/çözülen uyarılar, okuma hataları, dışa aktarma ve ayar değişiklikleri.

## Durum çubuğu
Çalışma modu · tampondaki örnek sayısı ve süresi · son ölçüm turunun süresi ·
**uygulamanın kendi CPU ve RAM kullanımı** (performans hedeflerini izlemek için).

## Komut satırı (GUI'siz) modu

```bash
python3 -m pardusinsight --headless --duration 120
```

Her örnek için tek satır özet yazdırır. Yeni uyarılar tam açıklamasıyla, çözülen uyarılar
tek satırla basılır. `--quiet` ile örnek satırları gizlenir. `--export-csv` ve
`--export-json` verilirse çalışma sonunda rapor yazılır.

## Rapor biçimleri
Sütunlar ve JSON şeması: [RAPOR_FORMATI.md](RAPOR_FORMATI.md)
