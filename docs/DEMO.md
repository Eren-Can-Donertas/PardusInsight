# Demo Senaryosu (yaklaşık 5 dakika)

Öneri PDF'indeki demo planına göre hazırlandı. Demo **gerçek yük oluşturmaz**: stres testi
yerine önceden kaydedilmiş, güvenli sentetik senaryolar kullanılır.

## Hazırlık (çekimden önce)

```bash
cd PardusInsight
python3 -m pytest -q                      # sonuç ekranını videoda göstermek için
python3 scripts/generate_scenarios.py     # scenarios/*.json dosyalarını yeniden üretir (isteğe bağlı)
```

- Pardus 25.1 XFCE VM, **standart kullanıcı** (sudo grubunda olmayan bir hesap tercih edilir).
- Terminal ve dosya yöneticisi açık; ekran çözünürlüğü en az 1280×800.

## Akış

| Süre | Adım | Gösterilecek nokta |
|---|---|---|
| 0:00–1:00 | Terminalde `id` (root olmadığını göster) → `python3 -m pardusinsight` | Standart kullanıcıyla açılış, durum çubuğunda "Canlı izleme (/proc + psutil)", 2 sn örnekleme, uygulamanın kendi CPU/RAM kullanımı |
| 1:00–2:00 | Genel Bakış → grafik aralığını "Son 5 dk" yap, fareyi grafiğin üzerinde gezdir; Süreçler sekmesinde CPU ve RSS'e göre sırala, filtreye `xfce` yaz | CPU/RAM/swap/disk geçmişi, süreç listesi. G/Ç sütunlarındaki "—" işaretlerinin root gerektirmeyen tasarımın sonucu olduğunu açıkla |
| 2:00–3:00 | **Kayıt/senaryo aç… → `scenarios/demo.json`**. Uyarılar sekmesi açılır. Bellek baskısı uyarısını seç | Kanıt tablosu (ana koşul ✓, destekleyici göstergeler, bağlam), zaman aralığı, güven düzeyi, belirsizlik metni. Genel Bakış'ta gölgeli uyarı aralıkları |
| | `scenarios/cpu_spikes.json` aç | Karşı-örnek: kısa sıçramalar uyarı üretmez. **Kural durumu** tablosunda "yüksek CPU her pencerede kalıcı değil" açıklaması |
| 3:00–4:00 | **JSON rapor…** ve **CSV dışa aktar…** → dosyaları metin editöründe göster. Terminalde `python3 -m pytest -q` çıktısı. Hakkında penceresi | Dışa aktarmanın yalnızca kullanıcı isteğiyle yapılması, rapor içeriği, 116 otomatik test, güvenlik sınırları |
| 4:00–5:00 | Özet | Mevcut araçlardan farkı (htop anlık değer gösterir; PardusInsight metrikleri ilişkilendirip zaman pencereli, açıklamalı uyarı üretir). Sınırlamalar: eşikler kalibrasyon ister, root olmadan diğer kullanıcıların G/Ç'si okunamaz, uyarı tanı değildir |

## Alternatif: canlı sentetik akış

Kaydedilmiş dosya yerine uyarıların "canlı" oluşmasını göstermek için:

```bash
python3 -m pardusinsight --synthetic demo --speed 4
```

`demo` senaryosu yaklaşık 8 dakikalık simülasyondur (normal → CPU → bellek → disk). 4× hızda
yaklaşık 2 dakikada üç kural sırayla tetiklenir ve çözülür.

## GUI'siz yedek

PySide6 sorunlu olursa aynı analiz komut satırında gösterilebilir:

```bash
python3 -m pardusinsight --headless --replay scenarios/demo.json
python3 -m pardusinsight --headless --duration 30
```
