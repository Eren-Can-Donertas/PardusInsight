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

## Kalibrasyon

Eşikler geliştirme makinesinde sentetik verilerle seçildi. Hedef ortamda kalibrasyon için
`pardusinsight/analysis/calibration.py` ve `scripts/kalibrasyon.py` hazırdır. Kalibrasyon
kuralların ayrı bir benzetimini değil, **kuralların kendi kodunu** kullanır. Her eşik bir değer
ızgarasında tek tek değiştirilir ve kayıtlar kural motoruyla (`replay`) yeniden analiz edilir.

### Yöntem

1. **Olağan kullanım kaydı:** Pardus 25.1 XFCE'de tarayıcı ve ofis ile olağan kullanım
   sırasında 30 dk kayıt alın:
   `pardusinsight --headless --duration 1800 --quiet --export-json normal.json`
   (ya da kabul betiğiyle tek adımda: `python3 scripts/pardus_kabul.py --kalibrasyon-suresi 1800
   --kayit-klasoru docs/kayitlar --cikti docs/PARDUS_SONUCLARI.md`).
2. **(İsteğe bağlı) Bilinen yoğun işler:** Büyük bir projeyi derlemek, büyük dosya kopyalamak gibi
   olağan ama ağır işler sırasında aynı komutla kısa kayıtlar alın. Bunlar stres testi değildir.
3. **Analiz:**
   `python3 scripts/kalibrasyon.py normal.json --yogun derleme.json:sustained_cpu --cikti kalibrasyon.md --oneri-json oneri.json`
4. **Karar kuralı** (araç otomatik uygular, gerekçesini rapora yazar):
   - Varsayılan değer olağan kullanım kaydında uyarı üretiyorsa (yanlış pozitif), uyarıyı sıfıra
     indiren en yakın değer **bir adım güvenlik payıyla** önerilir.
   - Varsayılan sessizse ama beklenen yoğun kaydı kaçırıyorsa, olağan kullanımda sessiz kalıp onu
     yakalayan en yakın daha duyarlı değer önerilir.
   - Aksi hâlde varsayılan korunur ve kaç adım daha duyarlı değerin de sessiz kaldığı (pay)
     raporlanır.
5. Öneriler önce `--config oneri.json` ile denenir. Kalıcı yapılacaksa `config.py` varsayılanları
   ve bu belge gerekçesiyle güncellenir.

Kaydın örnekleme aralığı ayarlardakinden farklıysa analiz o aralığa uyarlanır. Aksi hâlde 5 sn
aralıklı bir kayıt 2 sn varsayımıyla "yetersiz veri" sayılır ve yanıltıcı biçimde hiç uyarı
çıkmaz.

### Taranan eşikler

| Kural | Parametre | Izgara |
|---|---|---|
| Bellek baskısı | `mem_available_warn_pct` | %5 · 7,5 · **10** · 12,5 · 15 · 20 |
| | `swap_activity_pages_s` | 25 · 50 · **100** · 200 · 400 sayfa/sn |
| | `major_faults_s` | 25 · 50 · **100** · 200 · 400 /sn |
| Kalıcı CPU | `cpu_high_pct` | %60 · 70 · 75 · 80 · **85** · 90 · 95 |
| | `cpu_min_fraction` | 0,5 · 0,6 · 0,7 · **0,8** · 0,9 · 1,0 |
| Disk G/Ç | `disk_ratio` | 1,5 · 2 · **3** · 4 · 6 × |
| | `disk_min_throughput_mib_s` | 1 · 2 · **5** · 10 · 20 · 50 MiB/sn |
| | `disk_busy_pct` | %50 · 60 · 70 · **80** · 90 · 95 |

### Sentetik senaryolarla doğrulama

Karşı-örnek senaryolar "olağan", pozitif senaryolar "yoğun" kayıt olarak verildiğinde
(`docs/KALIBRASYON_SENTETIK.md`, tek komutla yeniden üretilir):

```bash
python3 scripts/kalibrasyon.py scenarios/cpu_spikes.json scenarios/memory_low_quiet.json \
  scenarios/disk_steady.json --yogun scenarios/cpu.json:sustained_cpu \
  --yogun scenarios/memory.json:memory_pressure --yogun scenarios/disk.json:disk_io_anomaly \
  --cikti docs/KALIBRASYON_SENTETIK.md
```

Sonuç: Varsayılan eşiklerin hiçbiri karşı-örneklerde uyarı üretmiyor ve üç yoğun senaryonun
hepsini yakalıyor. Değişiklik önerilmiyor. Pay: bellek uyarı eşiğinde 3, swap ve major fault
eşiklerinde 2, CPU eşiğinde 4, CPU oranında 3, disk katsayısı ve alt sınırında 2, disk
meşguliyetinde 3 adım daha duyarlı değerde de yanlış pozitif yok. CPU eşiği %95'e çıkarılırsa
`cpu` senaryosu (%95 civarı yük) artık yakalanmıyor. Bu, eşiğin yükseltilmesine karşı bir
sınırdır.

> **Durum:** Gerçek Pardus 25.1 XFCE kullanım verisiyle kalibrasyon için temiz bir VM'de 30 dk
> olağan kullanım gerekir. Bu adım yukarıdaki tek komutla yapılır ve sonuç tablosu bu
> bölüme eklenir. Sentetik sonuçlar yalnızca yöntemi ve varsayılanların iç tutarlılığını
> gösterir; gerçek kullanımın yerini tutmaz.
