## Eşik kalibrasyonu

Kuralların eşikleri tek tek değiştirilerek kayıtlar gerçek kural koduyla yeniden analiz edildi (kural başına uyarı sayısı). *Normal* kayıtlarda her uyarı yanlış pozitiftir; *yoğun* kayıtlar bilinen ağır işlerdir.

| Kayıt | Tür | Süre | Örnek | Aralık |
|---|---|---|---|---|
| cpu_spikes | normal | 11 dk | 331 | 2,0 sn |
| memory_low_quiet | normal | 6 dk | 181 | 2,0 sn |
| disk_steady | normal | 15 dk | 451 | 2,0 sn |
| cpu | yoğun (beklenen: sustained_cpu) | 7 dk | 211 | 2,0 sn |
| memory | yoğun (beklenen: memory_pressure) | 7 dk | 211 | 2,0 sn |
| disk | yoğun (beklenen: disk_io_anomaly) | 11 dk | 331 | 2,0 sn |

### Ölçüm profili

| Metrik | Kayıt | Medyan | p95 | p99 | En yüksek |
|---|---|---|---|---|---|
| CPU kullanımı | cpu_spikes | %15,61 | %100 | %100 | %100 |
| CPU kullanımı | memory_low_quiet | %14,87 | %18,23 | %18,67 | %18,76 |
| CPU kullanımı | disk_steady | %14,87 | %18,12 | %18,89 | %20,12 |
| CPU kullanımı | cpu | %17,34 | %97,91 | %100 | %100 |
| CPU kullanımı | memory | %17,34 | %36,89 | %38,99 | %39,6 |
| CPU kullanımı | disk | %15,64 | %26,57 | %28,56 | %30,69 |
| Kullanılabilir bellek | cpu_spikes | %55,06 | %57,75 | %59,22 | %61,49 |
| Kullanılabilir bellek | memory_low_quiet | %8,11 | %55,68 | %57,72 | %59,02 |
| Kullanılabilir bellek | disk_steady | %55,06 | %57,9 | %59,51 | %61,49 |
| Kullanılabilir bellek | cpu | %55,1 | %57,9 | %59,22 | %61,49 |
| Kullanılabilir bellek | memory | %52,73 | %57,46 | %59,02 | %59,51 |
| Kullanılabilir bellek | disk | %55,06 | %57,75 | %59,22 | %61,49 |
| Swap etkinliği | cpu_spikes | 0 sayfa/sn | 0 sayfa/sn | 0 sayfa/sn | 0 sayfa/sn |
| Swap etkinliği | memory_low_quiet | 0 sayfa/sn | 0 sayfa/sn | 0 sayfa/sn | 0 sayfa/sn |
| Swap etkinliği | disk_steady | 0 sayfa/sn | 0 sayfa/sn | 0 sayfa/sn | 0 sayfa/sn |
| Swap etkinliği | cpu | 0 sayfa/sn | 0 sayfa/sn | 0 sayfa/sn | 0 sayfa/sn |
| Swap etkinliği | memory | 0 sayfa/sn | 688,5 sayfa/sn | 736,5 sayfa/sn | 800,5 sayfa/sn |
| Swap etkinliği | disk | 0 sayfa/sn | 0 sayfa/sn | 0 sayfa/sn | 0 sayfa/sn |
| Major page-fault | cpu_spikes | 2 /sn | 2,5 /sn | 2,5 /sn | 3 /sn |
| Major page-fault | memory_low_quiet | 1 /sn | 2 /sn | 2 /sn | 2,5 /sn |
| Major page-fault | disk_steady | 2 /sn | 2,5 /sn | 2,5 /sn | 3 /sn |
| Major page-fault | cpu | 2 /sn | 2,5 /sn | 2,5 /sn | 3 /sn |
| Major page-fault | memory | 2 /sn | 472 /sn | 520 /sn | 547,5 /sn |
| Major page-fault | disk | 2 /sn | 2,5 /sn | 2,5 /sn | 3 /sn |
| PSI bellek some | cpu_spikes | %0 | %0 | %0 | %0 |
| PSI bellek some | memory_low_quiet | %0 | %0 | %0 | %0 |
| PSI bellek some | disk_steady | %0 | %0 | %0 | %0 |
| PSI bellek some | cpu | %0 | %0 | %0 | %0 |
| PSI bellek some | memory | %0 | %28,28 | %30,2 | %30,78 |
| PSI bellek some | disk | %0 | %0 | %0 | %0 |
| Disk okuma+yazma | cpu_spikes | 1,2 MiB/sn | 1,5 MiB/sn | 1,5 MiB/sn | 1,7 MiB/sn |
| Disk okuma+yazma | memory_low_quiet | 1,2 MiB/sn | 1,5 MiB/sn | 1,5 MiB/sn | 1,7 MiB/sn |
| Disk okuma+yazma | disk_steady | 20,3 MiB/sn | 23,8 MiB/sn | 25,5 MiB/sn | 27,6 MiB/sn |
| Disk okuma+yazma | cpu | 1,2 MiB/sn | 1,5 MiB/sn | 1,5 MiB/sn | 1,7 MiB/sn |
| Disk okuma+yazma | memory | 1,4 MiB/sn | 4,0 MiB/sn | 4,2 MiB/sn | 4,3 MiB/sn |
| Disk okuma+yazma | disk | 1,3 MiB/sn | 128,1 MiB/sn | 139,2 MiB/sn | 147,0 MiB/sn |
| Disk meşguliyeti | cpu_spikes | %2,95 | %3,95 | %4,2 | %4,45 |
| Disk meşguliyeti | memory_low_quiet | %2,9 | %3,95 | %4,25 | %4,45 |
| Disk meşguliyeti | disk_steady | %34,85 | %38,35 | %39,35 | %42,35 |
| Disk meşguliyeti | cpu | %2,9 | %3,95 | %4,25 | %4,45 |
| Disk meşguliyeti | memory | %3,6 | %32,65 | %33,65 | %34,45 |
| Disk meşguliyeti | disk | %3,25 | %94,6 | %99,05 | %100 |

### Varsayılan eşiklerle üretilen uyarılar

| Kayıt | Tür | Uyarılar |
|---|---|---|
| cpu_spikes | normal | yok |
| memory_low_quiet | normal | yok |
| disk_steady | normal | yok |
| cpu | yoğun | Kalıcı CPU yoğunluğu (2 dk 54 sn sonra, 2 dk 22 sn sürdü) |
| memory | yoğun | Bellek baskısı olasılığı (2 dk 46 sn sonra, 2 dk 38 sn sürdü) |
| disk | yoğun | Disk G/Ç etkinliği anomalisi (6 dk 46 sn sonra, 2 dk 38 sn sürdü) |

### Duyarlılık taraması

Satırlar en az duyarlı değerden en duyarlıya sıralıdır. Hücre: o değerde üretilen uyarı sayısı (ilk uyarının kayıt başından gecikmesi).

**Kullanılabilir bellek uyarı eşiği** (`mem_available_warn_pct`, kural: Bellek baskısı olasılığı)

| Değer | cpu_spikes | memory_low_quiet | disk_steady | cpu (yoğun) | memory (yoğun) | disk (yoğun) |
|---|---|---|---|---|---|---|
| %5 | 0 | 0 | 0 | 0 | 0 | 0 |
| %7,5 | 0 | 0 | 0 | 0 | 1 (ilk: 2 dk 46 sn) | 0 |
| %10 **(varsayılan)** | 0 | 0 | 0 | 0 | 1 (ilk: 2 dk 46 sn) | 0 |
| %12,5 | 0 | 0 | 0 | 0 | 1 (ilk: 2 dk 46 sn) | 0 |
| %15 | 0 | 0 | 0 | 0 | 1 (ilk: 2 dk 46 sn) | 0 |
| %20 | 0 | 0 | 0 | 0 | 1 (ilk: 2 dk 46 sn) | 0 |

**Swap etkinliği eşiği** (`swap_activity_pages_s`, kural: Bellek baskısı olasılığı)

| Değer | cpu_spikes | memory_low_quiet | disk_steady | cpu (yoğun) | memory (yoğun) | disk (yoğun) |
|---|---|---|---|---|---|---|
| 400 sayfa/sn | 0 | 0 | 0 | 0 | 1 (ilk: 2 dk 46 sn) | 0 |
| 200 sayfa/sn | 0 | 0 | 0 | 0 | 1 (ilk: 2 dk 46 sn) | 0 |
| 100 sayfa/sn **(varsayılan)** | 0 | 0 | 0 | 0 | 1 (ilk: 2 dk 46 sn) | 0 |
| 50 sayfa/sn | 0 | 0 | 0 | 0 | 1 (ilk: 2 dk 46 sn) | 0 |
| 25 sayfa/sn | 0 | 0 | 0 | 0 | 1 (ilk: 2 dk 46 sn) | 0 |

**Major page-fault eşiği** (`major_faults_s`, kural: Bellek baskısı olasılığı)

| Değer | cpu_spikes | memory_low_quiet | disk_steady | cpu (yoğun) | memory (yoğun) | disk (yoğun) |
|---|---|---|---|---|---|---|
| 400 /sn | 0 | 0 | 0 | 0 | 1 (ilk: 2 dk 46 sn) | 0 |
| 200 /sn | 0 | 0 | 0 | 0 | 1 (ilk: 2 dk 46 sn) | 0 |
| 100 /sn **(varsayılan)** | 0 | 0 | 0 | 0 | 1 (ilk: 2 dk 46 sn) | 0 |
| 50 /sn | 0 | 0 | 0 | 0 | 1 (ilk: 2 dk 46 sn) | 0 |
| 25 /sn | 0 | 0 | 0 | 0 | 1 (ilk: 2 dk 46 sn) | 0 |

**Yüksek CPU eşiği** (`cpu_high_pct`, kural: Kalıcı CPU yoğunluğu)

| Değer | cpu_spikes | memory_low_quiet | disk_steady | cpu (yoğun) | memory (yoğun) | disk (yoğun) |
|---|---|---|---|---|---|---|
| %95 | 0 | 0 | 0 | 0 | 0 | 0 |
| %90 | 0 | 0 | 0 | 1 (ilk: 2 dk 58 sn) | 0 | 0 |
| %85 **(varsayılan)** | 0 | 0 | 0 | 1 (ilk: 2 dk 54 sn) | 0 | 0 |
| %80 | 0 | 0 | 0 | 1 (ilk: 2 dk 54 sn) | 0 | 0 |
| %75 | 0 | 0 | 0 | 1 (ilk: 2 dk 54 sn) | 0 | 0 |
| %70 | 0 | 0 | 0 | 1 (ilk: 2 dk 54 sn) | 0 | 0 |
| %60 | 0 | 0 | 0 | 1 (ilk: 2 dk 54 sn) | 0 | 0 |

**Eşik üstü örnek oranı** (`cpu_min_fraction`, kural: Kalıcı CPU yoğunluğu)

| Değer | cpu_spikes | memory_low_quiet | disk_steady | cpu (yoğun) | memory (yoğun) | disk (yoğun) |
|---|---|---|---|---|---|---|
| 1 | 0 | 0 | 0 | 1 (ilk: 3 dk) | 0 | 0 |
| 0,9 | 0 | 0 | 0 | 1 (ilk: 2 dk 58 sn) | 0 | 0 |
| 0,8 **(varsayılan)** | 0 | 0 | 0 | 1 (ilk: 2 dk 54 sn) | 0 | 0 |
| 0,7 | 0 | 0 | 0 | 1 (ilk: 2 dk 52 sn) | 0 | 0 |
| 0,6 | 0 | 0 | 0 | 1 (ilk: 2 dk 48 sn) | 0 | 0 |
| 0,5 | 0 | 0 | 0 | 1 (ilk: 2 dk 46 sn) | 0 | 0 |

**Disk artış katsayısı** (`disk_ratio`, kural: Disk G/Ç etkinliği anomalisi)

| Değer | cpu_spikes | memory_low_quiet | disk_steady | cpu (yoğun) | memory (yoğun) | disk (yoğun) |
|---|---|---|---|---|---|---|
| 6 × | 0 | 0 | 0 | 0 | 0 | 1 (ilk: 6 dk 46 sn) |
| 4 × | 0 | 0 | 0 | 0 | 0 | 1 (ilk: 6 dk 46 sn) |
| 3 × **(varsayılan)** | 0 | 0 | 0 | 0 | 0 | 1 (ilk: 6 dk 46 sn) |
| 2 × | 0 | 0 | 0 | 0 | 0 | 1 (ilk: 6 dk 46 sn) |
| 1,5 × | 0 | 0 | 0 | 0 | 0 | 1 (ilk: 6 dk 46 sn) |

**Disk mutlak alt sınır** (`disk_min_throughput_mib_s`, kural: Disk G/Ç etkinliği anomalisi)

| Değer | cpu_spikes | memory_low_quiet | disk_steady | cpu (yoğun) | memory (yoğun) | disk (yoğun) |
|---|---|---|---|---|---|---|
| 50 MiB/sn | 0 | 0 | 0 | 0 | 0 | 1 (ilk: 6 dk 46 sn) |
| 20 MiB/sn | 0 | 0 | 0 | 0 | 0 | 1 (ilk: 6 dk 46 sn) |
| 10 MiB/sn | 0 | 0 | 0 | 0 | 0 | 1 (ilk: 6 dk 46 sn) |
| 5 MiB/sn **(varsayılan)** | 0 | 0 | 0 | 0 | 0 | 1 (ilk: 6 dk 46 sn) |
| 2 MiB/sn | 0 | 0 | 0 | 0 | 0 | 1 (ilk: 6 dk 46 sn) |
| 1 MiB/sn | 0 | 0 | 0 | 0 | 0 | 1 (ilk: 6 dk 46 sn) |

**Disk meşguliyet eşiği** (`disk_busy_pct`, kural: Disk G/Ç etkinliği anomalisi)

| Değer | cpu_spikes | memory_low_quiet | disk_steady | cpu (yoğun) | memory (yoğun) | disk (yoğun) |
|---|---|---|---|---|---|---|
| %95 | 0 | 0 | 0 | 0 | 0 | 1 (ilk: 6 dk 46 sn) |
| %90 | 0 | 0 | 0 | 0 | 0 | 1 (ilk: 6 dk 46 sn) |
| %80 **(varsayılan)** | 0 | 0 | 0 | 0 | 0 | 1 (ilk: 6 dk 46 sn) |
| %70 | 0 | 0 | 0 | 0 | 0 | 1 (ilk: 6 dk 46 sn) |
| %60 | 0 | 0 | 0 | 0 | 0 | 1 (ilk: 6 dk 46 sn) |
| %50 | 0 | 0 | 0 | 0 | 0 | 1 (ilk: 6 dk 46 sn) |

### Öneriler

| Parametre | Kural | Mevcut | Önerilen | Gerekçe |
|---|---|---|---|---|
| `mem_available_warn_pct` | Bellek baskısı olasılığı | %10 | değişmez | Varsayılan değer olağan kullanımda yanlış pozitif üretmiyor; 3 adım daha duyarlı değerde de sessiz. Beklenen yoğun kayıtları da yakalıyor. |
| `swap_activity_pages_s` | Bellek baskısı olasılığı | 100 sayfa/sn | değişmez | Varsayılan değer olağan kullanımda yanlış pozitif üretmiyor; 2 adım daha duyarlı değerde de sessiz. Beklenen yoğun kayıtları da yakalıyor. |
| `major_faults_s` | Bellek baskısı olasılığı | 100 /sn | değişmez | Varsayılan değer olağan kullanımda yanlış pozitif üretmiyor; 2 adım daha duyarlı değerde de sessiz. Beklenen yoğun kayıtları da yakalıyor. |
| `cpu_high_pct` | Kalıcı CPU yoğunluğu | %85 | değişmez | Varsayılan değer olağan kullanımda yanlış pozitif üretmiyor; 4 adım daha duyarlı değerde de sessiz. Beklenen yoğun kayıtları da yakalıyor. |
| `cpu_min_fraction` | Kalıcı CPU yoğunluğu | 0,8 | değişmez | Varsayılan değer olağan kullanımda yanlış pozitif üretmiyor; 3 adım daha duyarlı değerde de sessiz. Beklenen yoğun kayıtları da yakalıyor. |
| `disk_ratio` | Disk G/Ç etkinliği anomalisi | 3 × | değişmez | Varsayılan değer olağan kullanımda yanlış pozitif üretmiyor; 2 adım daha duyarlı değerde de sessiz. Beklenen yoğun kayıtları da yakalıyor. |
| `disk_min_throughput_mib_s` | Disk G/Ç etkinliği anomalisi | 5 MiB/sn | değişmez | Varsayılan değer olağan kullanımda yanlış pozitif üretmiyor; 2 adım daha duyarlı değerde de sessiz. Beklenen yoğun kayıtları da yakalıyor. |
| `disk_busy_pct` | Disk G/Ç etkinliği anomalisi | %80 | değişmez | Varsayılan değer olağan kullanımda yanlış pozitif üretmiyor; 3 adım daha duyarlı değerde de sessiz. Beklenen yoğun kayıtları da yakalıyor. |

Bu kayıtlara göre varsayılan eşiklerde değişiklik önerilmiyor.
