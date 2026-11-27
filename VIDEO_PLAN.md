# Demo Videosu Planı (8–10 dakika)

> Bu belge yalnızca çekime hazırlık içindir. **Video henüz çekilmedi**; bağlantı
> `VIDEO_LINK.txt` içinde `VIDEO_LINK_PENDING` olarak bekliyor.
> Aşağıdaki konuşmacı dağılımı süreleri dengelemek için bir **öneridir**. Gerçek görev
> dağılımının yerine geçmez. Her üye videoda kendi gerçek katkısını anlatmalıdır.

Aşama 2 yönergesinin video için şartları:
- Video 8–10 dakika sürmeli.
- Video yalnızca slaytlardan oluşmamalı, yazılımın çalıştığı görülmeli.
- Anlatım gerçek bir kullanım senaryosu üzerinden yapılmalı.
- Projenin temel işlevleri ve katkısı gösterilmeli.

## 1. Çekim öncesi hazırlık

- [ ] Pardus 25.1 XFCE VM, **standart kullanıcı** oturumu (sudo grubunda olmayan hesap).
- [ ] Kurulum tamam: `.deb` paketi (`python3 scripts/build_deb.py && sudo apt install ./dist/pardusinsight_0.1.0_all.deb`)
      veya [docs/KURULUM.md](docs/KURULUM.md) seçenek A. `python3 -m pytest -q` geçiyor.
- [ ] Ekran çözünürlüğü en az 1280×800; yazı tipi ölçeği okunaklı. Bildirimler kapalı.
- [ ] Terminal yazı tipi büyütülmüş, komut geçmişi temizlenmiş.
- [ ] Ekran kaydı aracı (ör. SimpleScreenRecorder veya OBS) ve mikrofon testi yapılmış.
- [ ] Firefox'ta birkaç sekme açılmaya hazır. LibreOffice ile bir belge, kopyalanacak büyük
      bir dosya (ör. 2–4 GiB ISO) hazır. **Stres testi aracı kullanılmayacak.**
- [ ] `scenarios/demo.json` ve `scenarios/cpu_spikes.json` dosyaları yerinde.
- [ ] Uygulama en az 2–3 dakika önceden açılmış, grafiklerde geçmiş birikmiş olsun.

## 2. Akış ve konuşmacı önerisi (toplam ~9:30)

| Süre | Konuşmacı (öneri) | Ekran | Anlatılacak |
|---|---|---|---|
| 0:00–0:40 | Eren | Başlık ekranı (tek slayt), ardından Pardus masaüstü | Problem: yavaşlamanın nedenini tek tek araçlarla yorumlamak zor. Amaç: salt-okunur, açıklanabilir analiz. Ekip tanıtımı |
| 0:40–1:40 | Eren | Terminal: `id`; menüden **Sistem → PardusInsight** (veya `pardusinsight`). Genel Bakış sekmesi | Standart kullanıcıyla açılış (root yok). Kartlar: CPU/RAM/swap/disk. 2 sn örnekleme, 30 dk tampon. Durum satırında uygulamanın kendi CPU/RAM kullanımı |
| 1:40–2:50 | Eren | **Gerçek kullanım senaryosu:** Firefox'ta sekmeler açılır, LibreOffice açılır, büyük dosya kopyalanır. Grafikler canlı izlenir | Grafiklerin tepkisi, disk G/Ç grafiği. Kopyalama 1 dakikadan uzun sürerse disk "Gözlem" uyarısı çıkabilir; çıkmazsa Kural durumu tablosunda nedenini göster |
| 2:50–3:50 | Eren | Metodoloji sekmesi + `pardusinsight/collectors/procfs.py` | İşletim sistemleri bağlantısı: `/proc/stat` farklarıyla CPU %, `/proc/meminfo` MemAvailable, `/proc/vmstat` pswpin/pgmajfault, `/proc/diskstats`. Fark/süre hesabı, ilk örnekte hızın bilinmemesi |
| 3:50–4:30 | Oğuz | Mimari şema (teknik rapordan tek görsel) | 5 katman, arka plan QThread, ardışık pencereler, kural motoru |
| 4:30–6:00 | Oğuz | Kayıt/senaryo aç → `scenarios/demo.json`. **Sarı "DEMO / SENTETİK VERİ" şeridini göster** | Bellek baskısı uyarısı: ana koşul ve destekleyici göstergeler, eşikler, zaman aralığı, güven, belirsizlik. CPU uyarısı: "cc1plus (3 süreç) kaynaklı". Disk: yalnızca "Gözlem" |
| 6:00–6:40 | Oğuz | `scenarios/cpu_spikes.json` → Kural durumu | Yanlış alarm karşı-örneği: kısa sıçramalar uyarı üretmez ve nedeni tabloda yazar |
| 6:40–7:20 | Oğuz | Terminal: `python3 -m pytest -q`; tarayıcıda GitHub Actions (Pardus 25.1/25.2 kapsayıcısı işleri) | Test sayısı. Pozitif, negatif, eşik sınırı ve mutasyon denemesi. AST ile güvenlik denetimi. Kapsayıcı testinin neyi kanıtladığı ve neyi kanıtlamadığı (XFCE ve gerçek çekirdek VM'de) |
| 7:20–8:20 | Yusuf | Süreçler sekmesi (sırala/filtrele), Ayarlar (CPU eşiği değişince Metodoloji güncellenir), CSV ve JSON dışa aktarma, dosyanın metin editöründe açılması | Dışa aktarma yalnızca kullanıcı isteğiyle yapılır. `data_source` sütunu, birimler, eksik değerlerin gösterimi |
| 8:20–9:00 | Yusuf | Hakkında penceresi, `scripts/perf_check.py --gui` çıktısı | Güvenlik yaklaşımı (sinyal yok, ağ yok, sistem ayarı yok). Pardus üzerinde ölçülen CPU/RAM değerleri ve yanıt verebilirlik |
| 9:00–9:30 | Üçü birlikte | Kapanış slaytı | Özgün katkı (açıklanabilir, pencereli kurallar). Bilinen kısıtlar. Her üyenin bir cümleyle kendi gerçek katkısı |

Önerilen süre dengesi: Eren ~3:50, Oğuz ~3:30, Yusuf ~1:40 + kapanış. Yusuf'un süresi
kısa kalırsa 2:50–3:50 bölümündeki arayüz anlatımı (grafik ve kartlar) ona verilebilir.

## 3. Çekim sırasında dikkat

- Sentetik veri gösterilirken şeridin görünür olduğundan emin olun. Sentetik veri gerçek ölçüm gibi anlatılmamalıdır.
- Uyarıların "kesin tanı değil, olasılık" olduğunu en az bir kez söyleyin.
- Root veya `sudo` ile uygulama çalıştırmayın (kurulum adımı hariç; o kısım videoda gösterilmek zorunda değil).
- Ekranda kişisel bilgi (e-posta, tarayıcı geçmişi, başka dosyalar) görünmesin.

## 4. Çekim sonrası

1. Videoyu 8–10 dakika aralığında kalacak şekilde kırpın.
2. YouTube'a "Liste dışı" (unlisted) veya "Herkese açık" olarak yükleyin. Gizli (private) video değerlendiriciler tarafından açılamaz.
3. Bağlantıyı gizli pencerede (oturum açmadan) açarak erişimi doğrulayın.
4. `VIDEO_LINK.txt` içindeki `VIDEO_LINK_PENDING` satırını gerçek bağlantıyla değiştirin.
5. Teslim ZIP'ini yeniden oluşturun: `python3 scripts/build_submission.py`.
6. [FINAL_CHECKLIST.md](FINAL_CHECKLIST.md) içindeki video maddelerini işaretleyin.
