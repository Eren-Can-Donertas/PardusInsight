# Nihai Teslim Kontrol Listesi (7 Aralık 2026, UZAK)

**Genel durum: PARTIALLY READY (ön teslim).** Video ve temiz Pardus 25.1 XFCE VM doğrulaması
tamamlanmadan nihai teslim hazır sayılmaz.

## A. Yazılım

- [x] Temel işlevler çalışıyor: canlı metrikler, 2 sn örnekleme, 30 dk tampon, grafikler,
      süreç tablosu, 3 kural, açıklamalı uyarılar, CSV/JSON, demo modu, metodoloji
- [x] Geliştirme makinesinde 329 test geçiyor. mypy temiz. ruff: `main` dosyalarında 10 biçim bulgusu (isteğe bağlı düzeltme)
- [x] Resmî Pardus 25.1/25.2 kapsayıcısında CI (`main`: 316/316; birleşmiş dal: TEST_REPORT §1.1)
- [x] `.deb` paketi Pardus kapsayıcısında kurulup kaldırılıyor. Kabul betiğinde KALDI yok. 35 dk uzun koşu geçti
- [x] Güvenlik sınırları otomatik denetleniyor (AST + kabul betiği)
- [ ] **Temiz Pardus 25.1 XFCE VM'de doğrulama:** PARDUS_VALIDATION.md §3
      (`python3 scripts/pardus_kabul.py --gui --kalibrasyon-suresi 1800 ...`)
- [ ] VM'de 30 dk olağan kullanımla eşik kalibrasyonu ve yanlış pozitif kaydı
- [ ] VM sonuçlarını `docs/PARDUS_SONUCLARI.md`, docs/TEST_RAPORU.md ve teknik raporun 12. ve 13. bölümlerine ekleme
- [ ] (İsteğe bağlı) ruff biçim bulgularının düzeltilmesi (`scripts/build_deb.py` kullanılmayan import vb.)

## B. Teslim dosyaları (A2 §2–§3)

- [x] `source_code/`: kaynak kod, yapılandırma, bağımlılık listesi, testler, senaryolar, paketleme, CI
- [x] `README.md`: hedef sürüm, gereksinimler, kurulum, komutlar, kullanım, örnek senaryo
- [x] `technical_report.pdf`: A2'nin istediği tüm başlıklar (18 bölüm)
- [ ] Teknik rapor §15: **Eren ve Yusuf gerçekleşen katkılarını yazmalı, Oğuz kendi satırını
      doğrulamalı** (`report/technical_report.html` → `sh report/build_pdf.sh`)
- [ ] Teknik rapor: VM sonuçları ve mümkünse Pardus XFCE ekran görüntüleri
      (`python3 scripts/capture_screenshots.py ekran/`)
- [ ] (İsteğe bağlı) projenin kendi lisansı: `LICENSE` (ör. MIT veya GPL-3.0)
- [x] `VIDEO_LINK.txt` var (şu an `VIDEO_LINK_PENDING`)

## C. Video (A2 §2.4)

- [ ] VIDEO_PLAN.md'ye göre 8–10 dk video; Pardus 25.1 XFCE üzerinde, gerçek kullanım senaryosuyla
- [ ] YouTube'a "Liste dışı" veya "Herkese açık" yükleme; gizli pencerede erişimi kontrol
- [ ] `VIDEO_LINK.txt` ilk satırına gerçek bağlantıyı yazma

## D. Paketleme ve yükleme

- [ ] PR #1'in (`asama2-teslim` → `main`) ekip tarafından incelenip birleştirilmesi
- [ ] `python3 scripts/build_submission.py` çıktısında "Denetim: … uygun" ve
      "DURUM: video bağlantısı mevcut" yazmalı
- [ ] ZIP'i başka bir klasöre açıp README adımlarını bir kez daha deneyin
- [ ] Dosya adı: `PardusInsight.zip`. UZAK'a tek dosya olarak yükleme (grup adına bir kişi)

## E. Sözlü sunum

- [ ] Üç üye ORAL_EXAM_PREP.md'deki soruları çalıştı
- [ ] Her üye kendi gerçek katkısını ve sorumlu olduğu modülü açıklayabiliyor
- [ ] Canlı demo için Pardus VM hazır; yedek olarak `--replay scenarios/demo.json`
