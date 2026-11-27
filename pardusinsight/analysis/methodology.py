"""Arayüzdeki "Metodoloji" ekranının içeriği (Qt'den bağımsız, test edilebilir).

Kullanıcının bir uyarıyı doğrulayabilmesi için her metriğin hangi çekirdek
arayüzünden, hangi formülle hesaplandığını ve kuralların geçerli eşiklerini gösterir.
"""
from __future__ import annotations

from html import escape
from typing import List, Tuple

from ..config import AppSettings
from ..core.formatting import fmt_duration, fmt_pct, tr_num
from .rules import default_rules

#: (metrik, kaynak, hesaplama)
DATA_SOURCES: List[Tuple[str, str, str]] = [
    ("Toplam CPU %", "/proc/stat — cpu satırı",
     "(Δtoplam − Δidle − Δiowait) / Δtoplam × 100; iki örnek arasındaki fark kullanılır"),
    ("Kullanıcı / çekirdek CPU payı", "/proc/stat",
     "kullanıcı = user + nice, çekirdek = system + irq + softirq (Δ / Δtoplam)"),
    ("Bellek toplam / kullanılabilir", "/proc/meminfo — MemTotal, MemAvailable",
     "kullanılan = MemTotal − MemAvailable (MemAvailable çekirdeğin tahminidir)"),
    ("Swap kullanımı", "/proc/meminfo — SwapTotal, SwapFree", "kullanılan = SwapTotal − SwapFree"),
    ("Swap giriş / çıkış", "/proc/vmstat — pswpin, pswpout", "Δsayfa / Δsüre (sayfa/sn)"),
    ("Major / minor page fault", "/proc/vmstat — pgmajfault, pgfault",
     "major = Δpgmajfault / Δt; minor = (Δpgfault − Δpgmajfault) / Δt"),
    ("Disk okuma / yazma", "/proc/diskstats (+ /sys/block ile fiziksel disk seçimi)",
     "Δsektör × 512 / Δt; loop, dm, md, zram ve bölümler çift sayımı önlemek için dışlanır"),
    ("Disk meşguliyeti", "/proc/diskstats — io_ticks", "Δio_ticks (ms) / Δt; en meşgul disk"),
    ("Baskı (PSI)", "/proc/pressure/{memory,cpu,io}",
     "'some' avg10 değeri; çekirdek desteklemiyorsa 'ölçülemedi'"),
    ("Yük ve G/Ç bekleyen süreç", "/proc/loadavg, /proc/stat — procs_blocked", "anlık değer"),
    ("Süreç listesi", "psutil (/proc/<pid>/stat, statm, status, io)",
     "CPU % tüm çekirdeklere göre normalize; başka kullanıcıların G/Ç alanları "
     "root olmadan okunamaz"),
]


def methodology_html(settings: AppSettings) -> str:
    a = settings.analysis
    rows = "".join(
        f"<tr><td>{escape(m)}</td><td><code>{escape(src)}</code></td><td>{escape(calc)}</td></tr>"
        for m, src, calc in DATA_SOURCES)
    thresholds = {
        "memory_pressure": [
            f"Kullanılabilir bellek medyanı &lt; {fmt_pct(a.mem_available_warn_pct)} "
            f"(kritik: &lt; {fmt_pct(a.mem_available_crit_pct)})",
            f"Destek: swap etkinliği ≥ {tr_num(a.swap_activity_pages_s, 0)} sayfa/sn, "
            f"major fault ≥ {tr_num(a.major_faults_s, 0)}/sn veya PSI bellek ≥ "
            f"{fmt_pct(a.psi_memory_some_pct)} (en az biri)",
        ],
        "sustained_cpu": [
            f"Örneklerin ≥ {fmt_pct(a.cpu_min_fraction * 100, 0)}'i CPU ≥ "
            f"{fmt_pct(a.cpu_high_pct, 0)}",
            f"Tek süreç grubu toplam yükün ≥ {fmt_pct(a.cpu_process_share * 100, 0)}'ini "
            "oluşturuyorsa 'süreç kaynaklı' olarak açıklanır",
        ],
        "disk_io_anomaly": [
            f"Okuma+yazma medyanı ≥ max({tr_num(a.disk_ratio, 1)} × önceki "
            f"{fmt_duration(a.disk_baseline_s)} medyanı, "
            f"{tr_num(a.disk_min_throughput_mib_s, 0)} MiB/sn)",
            f"veya meşguliyet medyanı ≥ {fmt_pct(a.disk_busy_pct, 0)} (önceki dönemde düşükken)",
        ],
    }
    rules_html = "".join(
        f"<h4>{escape(rule.title)}</h4><p>{escape(rule.description)}</p><ul>"
        + "".join(f"<li>{t}</li>" for t in thresholds.get(rule.rule_id, []))
        + "</ul>" for rule in default_rules())
    return (
        "<h2>Metodoloji</h2>"
        "<p>PardusInsight ölçüm ve analiz yapar; sistemde hiçbir değişiklik yapmaz. Bu sayfa, "
        "gösterilen her değerin nereden geldiğini ve uyarıların hangi koşullarla üretildiğini "
        "açıklar.</p>"
        "<h3>1. Veri kaynakları ve hesaplamalar</h3>"
        "<table border='1' cellspacing='0' cellpadding='4'>"
        "<tr><th>Metrik</th><th>Kaynak</th><th>Hesaplama</th></tr>" + rows + "</table>"
        "<p>Hız gerektiren alanlar ilk örnekte <i>bilinmez</i> (—) olarak gösterilir; sayaç "
        "azalırsa (sıfırlanma, taşma) negatif değer üretilmez, o örnek boş bırakılır. Zaman "
        "damgaları monotonik saate bağlıdır; sistem saatinin değişmesi pencereleri bozmaz.</p>"
        "<h3>2. Örnekleme, tampon ve pencereler</h3><ul>"
        f"<li>Örnekleme aralığı: {tr_num(settings.sample_interval_s, 1)} sn "
        "(arka plan iş parçacığında)</li>"
        f"<li>Geçmiş tamponu: en fazla {tr_num(settings.history_minutes, 0)} dk; daha eski "
        "örnekler silinir</li>"
        f"<li>Analiz: {a.consecutive_windows} ardışık × {tr_num(a.window_s, 0)} sn pencere. Ana "
        "koşul <b>her pencerede ayrı ayrı</b> sağlanmalıdır; tek sıçrama uyarı üretmez.</li>"
        f"<li>Veri yeterliliği: pencerede beklenen örneklerin en az "
        f"{fmt_pct(a.min_window_coverage * 100, 0)}'i geçerli olmalıdır; değilse sonuç "
        "üretilmez ('Yetersiz veri').</li>"
        f"<li>Uyarı, koşul {tr_num(a.resolve_grace_s, 0)} sn boyunca sağlanmazsa 'çözüldü' "
        "olarak kapanır.</li></ul>"
        "<h3>3. Kurallar ve geçerli eşikler</h3>" + rules_html +
        "<h3>4. Uyarıların yorumlanması</h3><ul>"
        "<li><b>Gözlem</b>: olağan dışı ama zararsız olabilecek etkinlik (disk).</li>"
        "<li><b>Uyarı</b>: kaynak baskısı olasılığı.</li>"
        "<li><b>Kritik olasılık</b>: birden fazla bağımsız göstergenin birlikte güçlü baskı "
        "göstermesi.</li>"
        "<li><b>Güven</b> (düşük/orta/yüksek): kaç bağımsız göstergenin koşulu desteklediğini "
        "belirtir.</li></ul>"
        "<p><b>Hiçbir uyarı kesin arıza tanısı değildir.</b> Bir metriğin yavaşlamayla aynı anda "
        "görülmesi nedensellik kanıtı sayılmaz. Eşikler hedef Pardus ortamında kalibre "
        "edilmelidir.</p>"
        "<h3>5. Salt-okunur çalışma</h3><ul>"
        "<li>Root yetkisi istenmez; /proc ve /sys yalnızca okunur.</li>"
        "<li>Süreçlere sinyal gönderilmez, öncelik veya sistem ayarı değiştirilmez.</li>"
        "<li>Ağ bağlantısı kurulmaz; dosya yalnızca kullanıcı 'Dışa aktar' dediğinde, seçtiği "
        "yola yazılır.</li>"
        "<li>Demo modundaki değerler sentetiktir ve ekranda açıkça belirtilir.</li></ul>"
    )
