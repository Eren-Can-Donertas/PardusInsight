# Analiz Kuralları

Kurallar `pardusinsight/analysis/rules.py` içindedir. Varsayılan eşikler
`pardusinsight/config.py` içinde tanımlıdır ve GUI'deki **Ayarlar** penceresinden veya
`--config ayarlar.json` ile değiştirilebilir. Değişiklikler yalnızca uygulama içinde geçerlidir.

## Ortak ilkeler

- **Ardışık pencereler:** Değerlendirme dönemi en yeni örnekten geriye doğru
  `consecutive_windows` (2) adet `window_s` (30 sn) uzunluğunda pencereye bölünür. Ana koşul
  **her pencerede ayrı ayrı** sağlanmalıdır. Bu, PDF'deki "en az iki ardışık ölçüm penceresi"
  ilkesini uygular. Tek bir sıçrama uyarı üretmez.
- **Veri yeterliliği:** Pencerede beklenen örneklerin en az %60'ı geçerli değilse kural
  "Yetersiz veri" der ve tetiklenmez. Bu durum Uyarılar sekmesindeki **Kural durumu**
  tablosunda gösterilir.
- **Olasılık dili:** Uyarılar "olasılık", "gözlem" gibi ifadeler kullanır. Her uyarıda ortak bir
  uyarı cümlesi bulunur: *"Bu bir olasılık değerlendirmesidir, kesin arıza tanısı değildir. Bir
  metriğin yavaşlamayla aynı anda görülmesi tek başına nedensellik kanıtı sayılmaz."*
- **Kanıt rolleri:** `Ana koşul` (tetiklemeye katılır), `Destekleyici` (en az biri gerekir),
  `Bağlam` (yalnızca yorum için, eşiksiz).
- **Yaşam döngüsü:** Koşul ilk sağlandığında uyarı açılır. Sağlanmaya devam ettikçe kanıtlar
  güncellenir. Koşul `resolve_grace_s` (10 sn) boyunca sağlanmazsa uyarı "çözüldü" olur ve
  geçmişte kalır.

## Kural 1 – Bellek baskısı olasılığı (`memory_pressure`)

**Koşul:** Her pencerede `mem_available_percent` medyanı `< %10` **VE** değerlendirme
döneminde aşağıdakilerden **en az biri**:

| Destekleyici gösterge | Kaynak | Eşik |
|---|---|---|
| Swap etkinliği (pswpin + pswpout) ortalaması | `/proc/vmstat` | ≥ 100 sayfa/sn |
| Major page-fault hızı ortalaması | `/proc/vmstat` `pgmajfault` | ≥ 100 /sn |
| PSI bellek "some" avg10 ortalaması | `/proc/pressure/memory` | ≥ %10 |

**Önem:** Her pencerede medyan `< %5` ve en az 2 destekleyici gösterge varsa *Kritik olasılık*,
aksi hâlde *Uyarı*. **Güven:** 2+ destekleyici gösterge varsa "yüksek", aksi hâlde "orta".

**Neden destekleyici gösterge gerekiyor?** Düşük `MemAvailable` tek başına sorun değildir.
Sistem belleği dolu olduğu hâlde sayfa takası yapmıyorsa kullanıcı yavaşlama hissetmeyebilir.
Swap, major fault ve PSI ise çekirdeğin bellek için **beklemeye başladığını** gösterir.
Karşı-örnek senaryosu: `memory_low_quiet`.

**Sınırlılıklar:** `MemAvailable` bir tahmindir. Swap girişi, geçmişte swap'e atılmış
sayfaların yeniden okunmasından da kaynaklanabilir. RSS paylaşılan belleği birden fazla
kez sayabilir. PSI bazı çekirdeklerde kapalıdır.

## Kural 2 – Kalıcı CPU yoğunluğu (`sustained_cpu`)

**Koşul:** Her pencerede `cpu_percent ≥ %85` olan örneklerin oranı `≥ %80`.
Pencere uzunluğu ve eşikler kullanıcı tarafından ayarlanabilir (PDF: "kullanıcı tarafından
belirlenen pencere").

**Bağlam:** Dönem boyunca örneklerde görülen süreçlerin ortalama CPU payı (ilk 5),
kullanıcı/çekirdek alanı payı, steal payı, 1 dk yük ortalaması.

**Süreç kaynaklı mı, dağınık mı?** Aynı adlı süreçler (ör. paralel derleyici örnekleri) tek
grup sayılır. En yoğun grubun dönem ortalaması toplam CPU ortalamasının
`cpu_process_share` (varsayılan %50) oranını aşarsa özet "yükün yaklaşık %X'i <süreç>
kaynaklı" der. Aşmazsa "yük birden fazla sürece dağılmış" der. Süreç verisi yoksa kaynak
"belirlenemedi" olarak bildirilir. Bu bilgi bağlamdır; tetiklemeyi etkilemez.

**Neden oran?** Ortalama, kısa ama çok yüksek sıçramalardan etkilenir (`cpu_spikes`
senaryosunda ortalama yüksek olabilir ama yük kalıcı değildir). Oran ölçütü yükün
pencerenin büyük kısmına yayılmasını ister.

**Sınırlılıklar:** Yüksek CPU beklenen bir iş (derleme, video işleme) olabilir. Süreç
değerleri örnekleme anlarına aittir ve kısa ömürlü süreçler kaçabilir. Sanal makinelerde
steal yüksekse sorun ana sistemde olabilir.

## Kural 3 – Disk G/Ç etkinliği anomalisi (`disk_io_anomaly`)

**Koşul (biri yeterli):**

1. **Oran koşulu:** Taban dönemi (değerlendirme döneminden önceki 300 sn) en az %50 dolu
   ise, her pencerede okuma+yazma hızı medyanı `≥ max(3 × taban medyanı, 5 MiB/sn)`.
2. **Meşguliyet koşulu:** Her pencerede disk meşguliyeti medyanı `≥ %80` **ve** taban
   döneminde meşguliyet medyanı `< %80` (ya da taban verisi yetersiz).

**Önem:** Her zaman *Gözlem* (PDF: "yalnızca gözlemsel uyarı").
**Bağlam:** CPU iowait, G/Ç bekleyen süreç sayısı (`procs_blocked`), PSI G/Ç, erişilebilen
süreçlerin G/Ç hızları.

**Neden medyan ve mutlak alt sınır?** Medyan, pencereye düşen birkaç yüksek örneğin
tetiklemesini önler. Mutlak alt sınır ise boş bir diskte 0,1 → 1 MiB/sn gibi anlamsız
"10 kat artışları" eler. Karşı-örnek senaryosu: `disk_steady`. Test karşı-örnekleri
`tests/test_rules.py` içindedir.

**Sınırlılıklar:** Diğer kullanıcıların süreçlerinin G/Ç sayaçları root olmadan okunamaz.
NVMe/SSD'de %util doygunluğu abartabilir. Artış olağan bir işten kaynaklanabilir.

## Eşik sınırlarında davranış

Karşılaştırmalar kodda ve testlerde aynı tanımlıdır (`tests/test_rules.py`, "eşik sınırları"):

| Ölçüt | Karşılaştırma | Örnek |
|---|---|---|
| Kullanılabilir bellek medyanı | `<` (katı) | tam %10,0 → tetiklemez; %9,99 → tetikler |
| Destekleyici göstergeler (swap, major fault, PSI) | `≥` | swap tam 100 sayfa/sn → destek sayılır |
| CPU eşik üstü oranı | `≥` | 15 örnekten 12'si (%80) → tetikler; 11'i → tetiklemez |
| Disk hızı medyanı / meşguliyet | `≥` | tam 5 MiB/sn veya tam %80 → tetikler |

## Kalibrasyon planı (Pardus üzerinde yapılacak)

Eşikler geliştirme makinesinde sentetik verilerle seçildi ve **henüz Pardus 25.1 XFCE
üzerinde kalibre edilmedi**. Önerilen yöntem:

1. Temiz VM'de 30 dk olağan kullanım (tarayıcı + ofis) için JSON rapor alın
   (`--headless --duration 1800 --export-json normal.json`).
2. `summary.metrics` içindeki min/ortalama/maks değerlerine bakın. Olağan kullanımda hiçbir
   kural tetiklenmemelidir (yanlış pozitif = 0 hedefi).
3. Bilinen yoğun işlerde (ör. büyük bir projeyi derlemek, büyük dosya kopyalamak) tetiklenme
   zamanlarını not edin. Bunlar stres testi değil, olağan kullanıcı işleridir.
4. Gerekirse `config.py` varsayılanlarını güncelleyin ve gerekçeyi bu belgeye yazın.
