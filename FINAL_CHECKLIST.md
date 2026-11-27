# Nihai Teslim Kontrol Listesi (7 Aralık 2026, UZAK)

**Genel durum: PARTIALLY READY — ön teslim.** Video ve Pardus doğrulaması tamamlanmadan nihai
teslim hazır sayılmaz.

## A. Yazılım

- [x] Temel işlevler çalışıyor: canlı metrikler, 2 sn örnekleme, 30 dk tampon, grafikler,
      süreç tablosu, 3 kural, açıklamalı uyarılar, CSV/JSON, demo modu, metodoloji
- [x] 136 otomatik test geçiyor (geliştirme makinesi). ruff ve mypy temiz
- [x] Debian 13'teki PySide6 sürümüyle (6.8.2.1) 136/136
- [x] Güvenlik sınırları otomatik denetleniyor (AST)
- [ ] **Pardus 25.1 XFCE'de doğrulama** → `sh scripts/pardus_validate.sh` + PARDUS_VALIDATION.md
- [ ] Pardus'ta eşik kalibrasyonu ve olağan kullanımda yanlış pozitif kaydı (docs/KURALLAR.md)
- [ ] Pardus sonuçlarını TEST_REPORT.md §8 ve teknik raporun 12. ve 13. bölümlerine ekleme

## B. Teslim dosyaları (A2 §2–§3)

- [x] `source_code/`: kaynak kod, yapılandırma, bağımlılık listesi, testler, senaryolar
- [x] `README.md`: hedef sürüm, gereksinimler, kurulum, komutlar, kullanım, örnek senaryo
- [x] `technical_report.pdf`: A2'nin istediği tüm başlıklar (18 bölüm)
- [ ] Teknik rapor §15: **her üye gerçekleşen katkısını yazsın** (`report/technical_report.html` → `sh report/build_pdf.sh`)
- [ ] Teknik rapor §12: Pardus sonuçları eklensin; mümkünse Pardus XFCE ekran görüntüleri
      (`python3 scripts/capture_screenshots.py ekran/`) ile Ubuntu görüntüleri değiştirilsin
- [ ] Projenin kendi lisansını seçme (isteğe bağlı; ör. MIT veya GPL-3.0) ve `LICENSE` ekleme
- [x] `VIDEO_LINK.txt` var (şu an `VIDEO_LINK_PENDING`)

## C. Video (A2 §2.4)

- [ ] VIDEO_PLAN.md'ye göre 8–10 dk video, Pardus 25.1 XFCE üzerinde, gerçek kullanım senaryosuyla
- [ ] YouTube'a "Liste dışı" veya "Herkese açık" yükleme; gizli pencerede erişimi kontrol
- [ ] `VIDEO_LINK.txt` ilk satırına gerçek bağlantıyı yazma

## D. Paketleme ve yükleme

- [ ] `python3 scripts/build_submission.py` çıktısında "DURUM: video bağlantısı mevcut" ve "Denetim: … uygun" yazmalı
- [ ] ZIP'i başka bir klasöre açıp README'deki kurulum adımlarını bir kez daha deneyin
- [ ] Dosya adı: `PardusInsight.zip`. UZAK'a tek dosya olarak yükleme (grup adına bir kişi)
- [ ] GitHub'da `asama2-teslim` dalının `main` dalına birleştirilmesi (PR incelemesiyle)

## E. Sözlü sunum

- [ ] Üç üye ORAL_EXAM_PREP.md'deki soruları çalıştı
- [ ] Her üye kendi gerçek katkısını ve sorumlu olduğu modülü açıklayabiliyor
- [ ] Canlı demo için Pardus VM hazır; yedek olarak `--replay scenarios/demo.json`
