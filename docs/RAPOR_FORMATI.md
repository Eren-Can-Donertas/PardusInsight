# Rapor Biçimleri

Raporlar yalnızca kullanıcı "Dışa aktar" dediğinde ya da `--export-csv` / `--export-json`
verildiğinde yazılır. Dosyalar atomik yazılır: önce geçici dosyaya yazılır, sonra hedefin
yerine konur. Dosya izinleri gizlilik için yalnızca sahibine açıktır (0600). Raporlarda
kullanıcı adı ve makine adı yoktur.

## CSV – örnekler (`<ad>.csv`)

UTF-8, virgülle ayrılmış, ondalık ayırıcı nokta. Boş hücre = ölçülemedi.

| Sütun | Birim | Açıklama |
|---|---|---|
| `time_iso` | ISO 8601 | Yerel saat |
| `timestamp` | Unix sn | Örnek zamanı (monotonik saate bağlı) |
| `interval_s` | sn | Önceki örnekle arasındaki süre |
| `cpu_percent` | % | Toplam CPU (meşgul = toplam − idle − iowait) |
| `cpu_user_percent`, `cpu_system_percent`, `cpu_iowait_percent`, `cpu_steal_percent` | % | Dağılım (user+nice, system+irq+softirq) |
| `cpu_count` | adet | Mantıksal CPU |
| `load1` | — | 1 dk yük ortalaması |
| `mem_total_bytes`, `mem_available_bytes` | bayt | `/proc/meminfo` MemTotal, MemAvailable |
| `mem_available_percent`, `mem_used_percent` | % | |
| `swap_total_bytes`, `swap_used_bytes`, `swap_used_percent` | bayt / % | |
| `swap_in_pages_per_s`, `swap_out_pages_per_s` | sayfa/sn | `pswpin`, `pswpout` farkı |
| `major_faults_per_s` | /sn | `pgmajfault` farkı |
| `disk_read_bytes_per_s`, `disk_write_bytes_per_s` | bayt/sn | Fiziksel disklerin toplamı |
| `disk_busy_percent` | % | En meşgul diskin io_ticks oranı |
| `psi_memory_some`, `psi_memory_full`, `psi_cpu_some`, `psi_io_some` | % | PSI avg10 (yoksa boş) |
| `procs_running`, `procs_blocked` | adet | `/proc/stat` |
| `errors` | metin | O örnekteki okuma hataları (` \| ` ile ayrılmış) |

## CSV – uyarılar (`<ad>_uyarilar.csv`)

`alert_id, rule_id, title, severity, severity_label, confidence, active, first_seen_iso,
last_seen_iso, resolved_at_iso, window_start_iso, window_end_iso, summary, evidence, context,
uncertainty`. `evidence` sütunundaki öğeler ` ; ` ile ayrılır. Her öğe
`✓/✗/• etiket: değer (eşik ≥ X) [pencere]` biçimindedir.

## JSON rapor

```json
{
  "schema": "pardusinsight.report",
  "schema_version": 1,
  "generator": {"name": "PardusInsight", "version": "0.1.0"},
  "created_at": "2026-11-23T14:05:00+0300",
  "source": "linux | synthetic:<senaryo> | replay:<dosya>",
  "system": {"os": "...", "kernel": "...", "machine": "x86_64", "python": "3.13.x"},
  "settings": { "...AppSettings alanları...": 0, "analysis": { "...eşikler...": 0 } },
  "summary": {
    "sample_count": 900, "start": "...", "end": "...", "duration_s": 1798.0,
    "metrics": {"cpu_percent": {"min": 0, "mean": 0, "max": 0, "count": 0}, "...": {}},
    "alert_count": 2, "alerts_by_rule": {"memory_pressure": 1, "sustained_cpu": 1}
  },
  "alerts": [{"alert_id": "...", "rule_id": "...", "evidence": [{"metric": "...", "role": "trigger", "...": 0}], "...": 0}],
  "samples": [{"timestamp": 0, "cpu_percent": 0, "top_cpu": [{"pid": 1, "name": "..."}], "...": 0}]
}
```

`samples` öğeleri CSV sütunlarına ek olarak `top_cpu`, `top_memory`, `top_io` (en yoğun 5
süreç özeti) içerir. `scenarios/` klasöründeki dosyalar aynı şemayı kullanır ve ek olarak
`scenario` alanı taşır. **Kayıt/senaryo aç** işlevi bu dosyaları okur. Uyarılar dosyadakinden
değil, örneklerden ve geçerli ayarlarla yeniden hesaplanır.
