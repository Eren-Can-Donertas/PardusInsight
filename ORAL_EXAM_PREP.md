# Sözlü Sunum ve Sınav Hazırlığı

Aşama 2 yönergesine göre her üye kendi katkısını ve projenin teknik ayrıntılarını
açıklayabilmelidir. Aşağıdaki sorular **üç üyenin de** cevaplayabilmesi gereken konulardır.
Yanıtlar kısa tutuldu; her yanıtın sonunda ilgili kod dosyası verildi. Koda bakarak
kendi cümlelerinizle anlatabilecek düzeye gelin.

## 1. İşletim sistemleri soruları

**S1. CPU kullanım yüzdesini nasıl hesaplıyorsunuz? Neden tek bir okuma yetmiyor?**
`/proc/stat`'taki `cpu` satırı açılıştan beri birikmiş süreleri USER_HZ (genelde 1/100 sn)
biriminde verir. Tek okuma yalnızca birikmiş toplamı gösterir. İki okuma arasındaki farkı
alırız: `(Δtoplam − Δidle − Δiowait) / Δtoplam`. İlk örnekte fark olmadığı için CPU % "—"
gösterilir. → `core/normalize.py`, `collectors/procfs.py::parse_stat`

**S2. iowait neden "meşgul" sayılmıyor?**
iowait, CPU'nun boşta beklediği ve bekleyen bir G/Ç isteği olduğu süredir. CPU iş yapmıyordur;
başka bir iş gelse çalıştırabilir. psutil ile aynı tanımı kullanıyoruz ve iowait'i ayrı
gösteriyoruz (disk kuralında bağlam olarak).

**S3. `guest` alanını neden toplama eklemiyorsunuz?**
Çekirdek sanal makine konuklarına ayrılan süreyi `user` (ve `nice`) içinde de sayar. Eklersek
aynı süre iki kez sayılır. → `parse_stat` belge dizgisi

**S4. MemFree ile MemAvailable farkı nedir?**
MemFree hiç kullanılmayan sayfalardır. MemAvailable ise çekirdeğin "yeni bir uygulamaya swap
yapmadan verilebilecek" bellek tahminidir: boş sayfalar + geri kazanılabilir sayfa önbelleği
ve slab. Linux boş belleği önbellek olarak kullandığı için MemFree düşük görünür ama bu sorun
değildir. Biz MemAvailable kullanıyoruz. Çok eski çekirdeklerde bu alan yoksa tahmini değer
kullanılıp işaretleniyor.

**S5. Major ve minor page fault farkı nedir?**
Sayfa hatası, sürecin erişmek istediği sanal sayfanın o an fiziksel bir çerçeveye eşlenmemiş
olmasıdır. **Minor** hatada sayfa zaten bellektedir (ör. paylaşılan kütüphane, sayfa önbelleği)
ve yalnızca sayfa tablosu güncellenir. **Major** hatada sayfa diskten (dosya veya swap)
okunmalıdır ve süreç G/Ç bekler. Bellek baskısında major hatalar artar.
`/proc/vmstat`: `pgmajfault`, minor = `pgfault − pgmajfault`.

**S6. Swap-in ve swap-out ne anlatır? Swap'in dolu olması sorun mudur?**
`pswpout`: anonim sayfaların belleğe sığmadığı için swap'e yazılması. `pswpin`: bu sayfalara
yeniden erişildiği için geri okunması. Swap'in dolu olması tek başına sorun değildir (eski,
kullanılmayan sayfalar orada durabilir). Sorun **etkinliktir**: sürekli giriş/çıkış
"thrashing" belirtisidir. Bu yüzden kuralımız dolulukla değil hızla (sayfa/sn) çalışır.

**S7. PSI (Pressure Stall Information) nedir?**
Çekirdeğin (4.20+) kaynak yetersizliği yüzünden görevlerin ne kadar süre beklediğini ölçen
arayüzüdür. `/proc/pressure/memory` içindeki `some avg10`, son 10 saniyede en az bir görevin
bellek için beklediği zaman yüzdesidir. Bazı dağıtımlarda kapalıdır. Bu yüzden özellik
algılama yapıyoruz: PSI yoksa "ölçülemedi" yazar, kural diğer göstergelerle çalışır.

**S8. Disk meşguliyetini nasıl ölçüyorsunuz, sınırlaması nedir?**
`/proc/diskstats` 13. sütunu `io_ticks`: aygıtın en az bir isteği işlerken geçirdiği toplam
milisaniyedir. Δio_ticks / Δsüre = %util. NVMe/SSD aynı anda çok sayıda isteği paralel
işleyebildiği için %100 görünse de hâlâ kapasite olabilir. Bu yüzden disk kuralı yalnızca
"Gözlem" üretir.

**S9. Neden loop, dm-*, md*, zram aygıtlarını sayıyorsunuz/saymıyorsunuz?**
Saymıyoruz. LVM (dm) ve RAID (md) gerçek disklerin üzerinde çalışır. Hem onları hem alttaki
diskleri toplarsak aynı G/Ç iki kez sayılır. zram bellekteki sıkıştırılmış swap'tir, loop ise
dosyaya bağlı sanal aygıttır. Bölümler (sda1) de dışlanır. Liste `/sys/block` okunarak
belirlenir. → `procfs.py::is_physical_disk`

**S10. /proc gerçek bir dosya sistemi mi?**
Hayır. procfs, çekirdeğin bellekte tuttuğu veri yapılarını okuma anında metne çeviren sanal bir
dosya sistemidir. Diskte yer kaplamaz. Her okuma çekirdeğin o anki değerlerini verir. Bazı
dosyalar yazılabilir (ör. `/proc/sys/vm/*`). Biz hiçbir dosyayı yazma kipinde açmıyoruz ve bunu
testle denetliyoruz.

**S11. Bir süreç tarama sırasında sonlanırsa ne olur?**
`/proc/<pid>` dizini kaybolur ve psutil `NoSuchProcess` fırlatır. Bunu yakalayıp süreci atlıyor
ve sayıyoruz ("tarama sırasında sonlandı"). PID'ler yeniden kullanılabildiği için G/Ç hızını
`(pid, create_time)` anahtarıyla hesaplıyoruz. Aynı PID'yi alan yeni bir sürece eski sürecin
sayacı uygulanmaz. → `collectors/processes.py`

**S12. Neden root'suz bazı alanlar okunamıyor?**
`/proc/<pid>/io` gibi dosyalar yalnızca sürecin sahibine (veya `CAP_SYS_PTRACE`/root yetkisine)
açıktır. Bu bir güvenlik önlemidir: başka kullanıcının sürecinin G/Ç desenini görmek bilgi
sızdırabilir. Biz yetki istemiyoruz, alanı "—" gösteriyoruz.

**S13. Zamanlayıcı (scheduler) CPU ölçümünü nasıl etkiler? Yük ortalaması nedir?**
Yük ortalaması, çalışmaya hazır ve kesintisiz uykudaki (D durumu, genelde G/Ç bekleyen)
görevlerin üstel ortalamasıdır. Mantıksal CPU sayısından büyükse görevler CPU için sıraya
giriyor demektir. `procs_blocked` (D durumu sayısı) disk darboğazı için ek bağlamdır.

**S14. Sanal makinede "steal" nedir?**
Hipervizörün CPU'yu başka bir konuğa verdiği ve bizim konuğumuzun çalışmak isteyip
çalışamadığı süredir. Steal yüksekse yavaşlığın nedeni ana makinededir. CPU kuralı bunu
belirsizlik notu olarak ekler.

**S15. Sayaç taşması veya sıfırlanması olursa?**
Fark negatif çıkar. Negatif hız üretmek yerine o örnekte alanı boş bırakıyoruz (`_rate`
fonksiyonu). CPU'da herhangi bir alan azalırsa (ör. CPU hotplug) yüzde hesaplanmaz.

**S16. Saat değişirse (NTP, elle ayar) zaman pencereleri bozulur mu?**
Bozulmaz. Farkları `time.monotonic()` ile hesaplıyoruz. Örnek zaman damgası da "ilk duvar
saati + monotonik fark" olarak üretiliyor. Bu yüzden saat geri alınsa da sıralama korunur
(testi var).

## 2. Mimari soruları

**S17. Arayüz neden donmuyor?** Ölçüm ve analiz `SamplerWorker` içinde, ayrı bir `QThread`'de
çalışan `QTimer` ile yapılır. GUI iş parçacığı yalnızca sonucu (değişmez `TickResult`) alıp
çizer. Uzun süren bir tur sonraki turla çakışmaz, yalnızca gecikir. Ölçümü yapay olarak
300 ms'ye uzatan testte bile GUI 250 ms'den uzun bloklanmıyor. → `ui/worker.py`,
`tests/test_gui.py`

**S18. Bellek neden sınırsız büyümüyor?** `HistoryBuffer` iki sınır uygular: en yeni örnekten
30 dakikadan eski örnekler silinir; ayrıca `deque(maxlen=...)` sabit bir kapasite koyar
(1 sn aralıkta 1801 örnek). Uyarı günlüğü 200 kayıtla sınırlıdır.

**S19. Bir kural nasıl çalışır?** Son 60 saniye iki adet 30 sn'lik pencereye bölünür. Ana koşul
her pencerede ayrı ayrı sağlanmalıdır. Bellek kuralında ayrıca en az bir destekleyici gösterge
(swap, major fault, PSI) gerekir. Pencerede veri azsa sonuç üretilmez. Uyarı kanıt listesi,
zaman aralığı, güven ve belirsizlik metniyle oluşturulur. → `analysis/rules.py`

**S20. Neden ortalama değil medyan / oran?** Ortalama tek bir aşırı değerden etkilenir. CPU'da
"örneklerin %80'i eşik üstünde" ölçütü, disk ve bellekte pencere medyanı kullanılır. Böylece
kısa sıçramalar (`cpu_spikes` senaryosu) uyarı üretmez.

**S21. Neden QtCharts yerine kendi grafiğiniz?** Ek paket gerektirmez (Debian'da QtCharts ayrı
pakettir). Piksel başına min/maks seyreltmesi sayesinde 900 noktayı çizmek ucuzdur. Eşik çizgisi
ve uyarı aralığı gölgesi gibi bize özel öğeler kolayca eklenebilir. → `ui/charts.py`

**S22. Sentetik veri neden var, stres testi neden yok?** Stres testi gerçek sistemi zorlar ve
öneride yasaklandı. Sentetik kaynak, gerçek kolektörle aynı kümülatif sayaç yapısını üretir.
Böylece normalizasyon → tampon → kural hattının tamamı deterministik test edilir. Arayüz ve
raporlar sentetik veriyi açıkça etiketler.

**S23. Güvenlik sınırlarını nasıl kanıtlıyorsunuz?** `tests/test_cli_safety.py`, kodun soyut
sözdizimi ağacını (AST) tarar. `subprocess`, `socket`, `signal` gibi modüllerin ve `kill`,
`terminate`, `nice` gibi çağrıların bulunmadığını, `open()` çağrılarının yalnızca `"r"` kipinde
olduğunu doğrular. Ayrıca açık istek yokken hiçbir dosya yazılmadığını test eder.

**S24. Pardus'ta nasıl test ettiniz? Konteyner testi neyi kanıtlar, neyi kanıtlamaz?**
GitHub Actions her push'ta resmî Pardus 25.1 ve 25.2 Docker imajında (`pardus/yirmibes`)
bağımlılıkları **Pardus deposundan** kurar. Testleri root olmayan bir kullanıcıyla çalıştırır,
`.deb` paketini apt ile kurup dener, kabul betiğini (`scripts/pardus_kabul.py`) koşturur. Bu,
paket adlarını, Python/PySide6/psutil sürümlerini (3.13.5 / 6.8.2.1 / 7.0.0) ve standart
kullanıcıyla çalışmayı kanıtlar. **Kanıtlamaz:** Çekirdek GitHub sunucusunundur (PSI, disk
aygıtları Pardus çekirdeğinden farklı olabilir) ve XFCE masaüstü yoktur. Bunlar için temiz XFCE VM
gerekir. → `.github/workflows/ci.yml`, `docs/PARDUS_DOGRULAMA.md`

**S25. Veri yetersizken uyarı neden kapanmıyor?** Örnekleme durakladığında veya veri boşluğu
olduğunda koşulun bittiği bilinemez. Uyarıyı "çözüldü" saymak sahte çözülmeye ve aynı yük için
birden çok uyarıya yol açardı. Bu yüzden kural "yetersiz veri" döndürünce aktif uyarı açık kalır.
Ancak veri bir değerlendirme dönemi + bekleme süresi boyunca yetersiz kalırsa kapatılır.
→ `analysis/engine.py`

**S26. Kayıt 2 sn aralıkla alındı ama 1 sn ayarıyla açıldı; ne olur?** Kurallar pencere başına
beklenen örnek sayısını örnekleme aralığından hesaplar. Ayardaki aralık kullanılsaydı her pencere
"yetersiz" sayılır ve hiç uyarı çıkmazdı. Motor, örneklerin **gözlenen** aralığını (medyan)
kullanır. → `RuleEngine.effective_settings`

**S27. Eşikleri nasıl kalibre edersiniz?** `scripts/kalibrasyon.py`, olağan kullanım
kayıtlarında yanlış pozitif varsa eşiği yükseltir, bilinen yoğun kayıtta uyarı kaçarsa düşürür.
Gerçek veriyle kalibrasyon VM'de 30 dk kayıtla yapılır. → `analysis/calibration.py`,
`docs/KALIBRASYON_SENTETIK.md`

**S28. Testlerinizin gerçekten kural mantığını sınadığını nereden biliyorsunuz?** Mutasyon
denemesi yapıldı: kural, motor ve pencere kodunda 23 bilinçli hata oluşturuldu ve her biri en
az bir testi düşürdü. Örneğin "her pencerede → herhangi bir pencerede" veya "medyan → ortalama"
değişiklikleri yakalanıyor. → `docs/TEST_RAPORU.md` §1.3

## 3. Kod değişikliği senaryoları (sınavda "şunu değiştirin" denebilir)

| Senaryo | Nereye dokunulur | Dikkat |
|---|---|---|
| Varsayılan örnekleme aralığını 5 sn yapın | `config.py` → `AppSettings.sample_interval_s` ve `AnalysisSettings.sample_interval_s` (ya da `--interval 5`) | Pencere en az 2 aralık olmalı (`validate`) |
| CPU eşiğini %90 yapın | `AnalysisSettings.cpu_high_pct` veya Ayarlar penceresi | `test_cpu_threshold_is_configurable` örnek alınabilir |
| Yeni kural: "yüksek iowait" | `analysis/rules.py`'de `Rule` alt sınıfı + `default_rules()`'a ekleme; `methodology.py`'ye eşik metni; testler | `split_windows` ve `Evidence` yapısını kullanın; pozitif, negatif ve sınır testi yazın |
| Ağ trafiği metriği ekleyin | `procfs.py`'de `/proc/net/dev` ayrıştırıcı, `RawSnapshot`/`SystemSample` alanı, `normalize.py`'de fark | Bu yalnızca okuma yapar, ağ bağlantısı kurmaz. Güvenlik testi etkilenmez |
| Geçmişi 60 dk yapın | `--history-minutes 60` veya `AppSettings.history_minutes` | Kapasite otomatik hesaplanır |
| Süreç sonlandırma düğmesi isteniyor | **Eklenmemeli**: proje salt-okunur tasarlandı ve güvenlik testi `kill/terminate` çağrısını yakalar | Gerekçeyi anlatın |
| PSI olmayan çekirdek | Değişiklik gerekmez | `read_pressure()` `None` döner; kanıt "ölçülemedi" olur |
| Grafik aralığına "Son 10 dk" ekleyin | `ui/main_window.py` → `RANGES` | — |

## 4. Üye bazında odak (öneri PDF'indeki sorumluluklara göre)

- **Eren (toplama, normalizasyon, tampon):** S1–S11, S15–S18. `procfs.py`, `normalize.py`,
  `history.py`, `service.py`. `/proc` doğrulama tablosu ve performans ölçümü.
- **Yusuf (arayüz, grafikler, raporlama):** S17, S21. `ui/` paketi, worker/QThread,
  CSV/JSON biçimi, demo şeridi, Metodoloji ekranı.
- **Oğuz (analiz motoru, test, paketleme):** S19, S20, S22–S28. `rules.py`, `engine.py`,
  `calibration.py`, sentetik senaryolar, test stratejisi ve mutasyon denemesi, CI ve Pardus
  kapsayıcısı, `.deb` paketi, `pardus_kabul.py`.

Bu dağılım öneri planıdır. Sunumda herkes **gerçekte yaptığı** işi anlatmalıdır. Git
kayıtlarında görünen katkılar teknik raporun 15. bölümündedir.

## 5. En sık sorulabilecek 10 soru (hızlı tekrar)

1. CPU % nasıl hesaplanıyor? → İki `/proc/stat` okuması arasındaki fark.
2. MemAvailable neden MemFree değil? → Önbellek geri kazanılabilir; çekirdeğin tahmini.
3. Major/minor fault farkı? → Diskten okuma gerekip gerekmemesi.
4. Swap doluluğu mu, etkinliği mi önemli? → Etkinlik (sayfa/sn).
5. Uyarı neden "kesin tanı" değil? → Eş zamanlılık nedensellik değildir; eşikler kalibre edilmedi.
6. Tek sıçrama neden uyarı üretmez? → İki ardışık pencere + oran/medyan.
7. GUI neden donmaz? → QThread worker + değişmez sonuç nesneleri.
8. Bellek neden büyümez? → 30 dk yaş sınırı + sabit kapasite.
9. Root olmadan ne okunamaz? → Başka kullanıcıların `/proc/<pid>/io` dosyaları.
10. Pardus ile ilişkisi? → Hedef Pardus 25.1 XFCE; Pardus deposundaki paketlerle ve `.deb` ile
    kurulum; CI'da resmî Pardus 25.1/25.2 kapsayıcısında standart kullanıcıyla test; XFCE VM
    doğrulaması ekipte.
