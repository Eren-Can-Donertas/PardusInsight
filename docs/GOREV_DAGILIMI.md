# Görev Dağılımı ve Git Çalışma Düzeni

Modül sahipliği, Aşama 1 önerisindeki (bölüm 6) iş bölümüne göre düzenlenmiştir.
"Birincil görev sahipliği sorumluluğu tanımlar; diğer iki üyenin de ilgili koda hâkim olması
beklenir."

## Modül sahipliği

| Sahip | Dizin / dosya | Kapsam | İlgili testler |
|---|---|---|---|
| **Eren Can Dönertaş** | `pardusinsight/collectors/procfs.py`, `system.py`, `processes.py` | /proc ayrıştırıcıları, psutil yedeği, süreç taraması | `tests/test_procfs.py`, `tests/test_collectors.py`, `tests/test_crosscheck_linux.py` |
| | `pardusinsight/core/models.py`, `normalize.py`, `history.py`, `service.py` | Veri modelleri, normalizasyon, 30 dk tampon, izleme servisi | `tests/test_normalize_history.py` |
| | `scripts/validate_metrics.py` | /proc–psutil doğrulama tablosu, performans | — |
| **Yusuf Yankı Ütgün** | `pardusinsight/ui/` | Ana pencere, grafikler, süreç tablosu, uyarı kartları, ayarlar, worker | `tests/test_gui.py` |
| | `pardusinsight/export/`, `core/formatting.py`, `analysis/explain.py` | CSV/JSON raporları, Türkçe biçimlendirme, uyarı metinleri | `tests/test_export.py` |
| | `docs/KULLANIM.md`, `docs/DEMO.md`, `docs/RAPOR_FORMATI.md` | Kullanıcı rehberi ve demo | — |
| **Oğuz Giray Bori** | `pardusinsight/analysis/` (rules, engine, windows) , `config.py` | 3 kural, kural motoru, eşikler | `tests/test_rules.py`, `tests/test_engine.py` |
| | `pardusinsight/collectors/synthetic.py`, `scenarios/`, `scripts/generate_scenarios.py` | Sentetik senaryolar | `tests/test_scenarios_service.py` |
| | `tests/`, `pyproject.toml`, `cli.py`, `scripts/perf_check.py`, `scripts/install_user.sh` | Test otomasyonu, paketleme, komut satırı | `tests/test_cli_safety.py` |
| | `docs/TEST_RAPORU.md`, `docs/PARDUS_DOGRULAMA.md`, `docs/KURULUM.md` | Test raporu, Pardus kabul listesi | — |
| Ortak | `README.md`, `docs/MIMARI.md`, `docs/KURALLAR.md` | Teknik kararların kaydı | — |

## Git geçmişi hakkında

İlk sürüm tek oturumda yapay zekâ desteğiyle üretildi (bkz. README "Yapay zekâ kullanımı").
Commit'ler modül sınırlarına göre ayrıldı ve her commit mesajında PDF'deki sorumlu üye
belirtildi. **Commit'ler, kodu yazan kişiyi doğru göstermek için depoyu oluşturan kişinin Git
kimliğiyle atıldı.** Diğer üyeler adına commit atılmadı; başkası adına sahte katkı kaydı
oluşturmak akademik dürüstlüğe aykırı olur.

Her üyenin katkısının Git kayıtlarında görünmesi için önerilen akış:

1. Depoyu ortak bir uzak sunucuya (GitHub/GitLab) yükleyin. Her üye kendi hesabıyla çalışsın.
2. Her üye kendi modülü için bir dal açsın (`eren/collectors-dogrulama`, `yusuf/ui-pardus`,
   `oguz/kalibrasyon`) ve şu işleri **kendi commit'leriyle** yapsın:
   - **Eren:** Pardus'ta `validate_metrics.py` çıktısını TEST_RAPORU'na ekleme; farklı
     çekirdek alanları ve PSI için kolektör düzeltmeleri; performans ölçümü.
   - **Yusuf:** XFCE açık/koyu temada arayüz kontrolü ve düzeltmeleri; kullanıcı rehberi
     ekran görüntüleri; demo videosu.
   - **Oğuz:** Pardus VM'de eşik kalibrasyonu (KURALLAR.md); PARDUS_DOGRULAMA.md listesinin
     doldurulması; paketleme.
3. Birleştirmeyi Pull Request ile yapın. Her PR'ı en az bir diğer üye incelesin (PDF: haftalık kod incelemesi).
4. Her üye kendi modülünü sunumda açıklayabilecek düzeyde okumalıdır. Anlaşılmayan kısımlar
   sadeleştirilmeli veya belgelenmelidir.
