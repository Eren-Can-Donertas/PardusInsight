"""Üç açıklanabilir analiz kuralı.

Her kural deterministiktir: aynı örnek dizisi ve ayarlar her zaman aynı sonucu
verir. Kurallar "olasılık/uyarı" dili kullanır; bir metriğin yavaşlamayla
birlikte görülmesi nedensellik kanıtı sayılmaz. Ayrıntılı gerekçe ve eşik
açıklamaları: docs/KURALLAR.md
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from ..config import AnalysisSettings
from ..core.formatting import fmt_bytes, fmt_duration, fmt_pct, fmt_rate, fmt_span, tr_num
from ..core.models import (SEVERITY_CRITICAL, SEVERITY_INFO, SEVERITY_WARNING, Evidence,
                           SystemSample)
from .windows import (Window, fraction_at_least, mean, median, min_valid_samples,
                      split_windows, values_of)

MIB = 1024.0 * 1024.0

COMMON_UNCERTAINTY = (
    "Bu bir olasılık değerlendirmesidir, kesin arıza tanısı değildir. Bir metriğin "
    "yavaşlamayla aynı anda görülmesi tek başına nedensellik kanıtı sayılmaz."
)


@dataclass(frozen=True)
class AlertDraft:
    title: str
    severity: str
    confidence: str
    summary: str
    window_start: float
    window_end: float
    evidence: Tuple[Evidence, ...]
    context: Tuple[str, ...]
    uncertainty: str
    suggestions: Tuple[str, ...]


@dataclass(frozen=True)
class RuleOutcome:
    triggered: bool
    reason: str
    draft: Optional[AlertDraft] = None


class Rule:
    """Kural arayüzü. ``samples`` zamana göre sıralı ve boş olmayan listedir."""

    rule_id = "base"
    title = "Kural"
    description = ""

    def evaluate(self, samples: Sequence[SystemSample],
                 settings: AnalysisSettings) -> RuleOutcome:  # pragma: no cover
        raise NotImplementedError


def _windows(samples: Sequence[SystemSample], s: AnalysisSettings) -> List[Window]:
    return split_windows(samples, samples[-1].timestamp, s.window_s, s.consecutive_windows)


def _insufficient(window: Window, have: int, need: int, what: str) -> RuleOutcome:
    return RuleOutcome(False, f"Yetersiz veri: {fmt_span(window.start, window.end)} "
                              f"penceresinde {what} için {have}/{need} geçerli örnek.")


def _coverage_note(windows: Sequence[Window], getter: str, s: AnalysisSettings) -> str:
    expected = int(round(s.window_s / s.sample_interval_s)) * len(windows)
    have = sum(len(w.values(getter)) for w in windows)
    return f"Değerlendirme döneminde beklenen ~{expected} örnekten {have} tanesi geçerli."


def _period_samples(windows: Sequence[Window]) -> List[SystemSample]:
    return [sample for w in windows for sample in w.samples]


# ---------------------------------------------------------------------------
# Kural 1: Bellek baskısı
# ---------------------------------------------------------------------------


class MemoryPressureRule(Rule):
    rule_id = "memory_pressure"
    title = "Bellek baskısı olasılığı"
    description = (
        "Kullanılabilir bellek (MemAvailable) oranı ardışık pencerelerin her birinde "
        "eşiğin altında kalır VE aynı dönemde swap etkinliği, major page-fault hızı "
        "veya PSI bellek baskısından en az biri eşiği aşarsa tetiklenir."
    )

    def evaluate(self, samples: Sequence[SystemSample],
                 settings: AnalysisSettings) -> RuleOutcome:
        s = settings
        windows = _windows(samples, s)
        need = min_valid_samples(s.window_s, s.sample_interval_s, s.min_window_coverage)
        evidence: List[Evidence] = []
        medians: List[float] = []
        for w in windows:
            vals = w.values("mem_available_percent")
            if len(vals) < need:
                return _insufficient(w, len(vals), need, "kullanılabilir bellek")
            med = median(vals)
            assert med is not None
            medians.append(med)
            evidence.append(Evidence(
                metric="mem_available_percent", label="Kullanılabilir bellek (pencere medyanı)",
                value=round(med, 2), threshold=s.mem_available_warn_pct, comparison="<",
                unit="%", window_start=w.start, window_end=w.end,
                satisfied=med < s.mem_available_warn_pct, role="trigger"))

        start, end = windows[0].start, windows[-1].end
        period = _period_samples(windows)
        supports = [
            ("swap_activity", "Swap etkinliği (giriş+çıkış, ortalama)",
             mean(values_of(period, lambda x: x.swap_activity_pages_per_s)),
             s.swap_activity_pages_s, "sayfa/sn"),
            ("major_faults_per_s", "Major page-fault hızı (ortalama)",
             mean(values_of(period, "major_faults_per_s")), s.major_faults_s, "/sn"),
            ("psi_memory_some", "PSI bellek baskısı 'some' avg10 (ortalama)",
             mean(values_of(period, "psi_memory_some")), s.psi_memory_some_pct, "%"),
        ]
        satisfied_supports = 0
        unavailable: List[str] = []
        for metric, label, value, threshold, unit in supports:
            ok = value is not None and value >= threshold
            satisfied_supports += int(ok)
            if value is None:
                unavailable.append(label.split(" (")[0])
            evidence.append(Evidence(
                metric=metric, label=label, value=None if value is None else round(value, 2),
                threshold=threshold, comparison=">=", unit=unit, window_start=start,
                window_end=end, satisfied=ok, role="support",
                note="" if value is not None else "Bu sistemde ölçülemedi"))

        swap_used = mean(values_of(period, "swap_used_percent"))
        evidence.append(Evidence(
            metric="swap_used_percent", label="Swap doluluğu (ortalama)", value=swap_used,
            threshold=None, comparison="", unit="%", window_start=start, window_end=end,
            satisfied=False, role="context"))

        low_everywhere = all(m < s.mem_available_warn_pct for m in medians)
        if not low_everywhere:
            return RuleOutcome(False, "Koşul sağlanmadı: kullanılabilir bellek her pencerede "
                                      f"{fmt_pct(s.mem_available_warn_pct)} altında değil "
                                      f"(son pencere medyanı {fmt_pct(medians[-1])}).")
        if satisfied_supports == 0:
            return RuleOutcome(False, "Kullanılabilir bellek düşük, ancak swap / page-fault / PSI "
                                      "göstergelerinden hiçbiri baskıyı desteklemiyor; uyarı "
                                      "üretilmedi.")

        critical = (all(m < s.mem_available_crit_pct for m in medians)
                    and satisfied_supports >= 2)
        severity = SEVERITY_CRITICAL if critical else SEVERITY_WARNING
        confidence = "yüksek" if satisfied_supports >= 2 else "orta"
        context = tuple(
            f"{name} (PID {pid}): dönem içinde en fazla {fmt_bytes(value)} RSS"
            for (pid, name), value in _aggregate_top(period, "top_memory", "rss_bytes", "max"))
        uncertainty = " ".join(filter(None, [
            COMMON_UNCERTAINTY,
            "MemAvailable çekirdeğin geri kazanılabilir bellek tahminidir; gerçek durum "
            "önbellek davranışına göre farklı olabilir.",
            "Swap girişi, geçmişte swap'e atılmış sayfaların yeniden okunmasından da "
            "kaynaklanabilir.",
            ("Ölçülemeyen göstergeler: " + ", ".join(unavailable) + ".") if unavailable else "",
            "Süreç RSS değerleri paylaşılan belleği birden fazla kez sayabilir.",
            _coverage_note(windows, "mem_available_percent", s),
        ]))
        summary = (
            f"Son {fmt_duration(end - start)} boyunca kullanılabilir bellek her pencerede "
            f"{fmt_pct(s.mem_available_warn_pct)} eşiğinin altında kaldı (son medyan "
            f"{fmt_pct(medians[-1])}) ve {satisfied_supports} destekleyici gösterge eşiği aştı. "
            "Bu durum bellek baskısı olasılığına işaret eder.")
        return RuleOutcome(True, "Bellek baskısı koşulları sağlandı.", AlertDraft(
            title=self.title, severity=severity, confidence=confidence, summary=summary,
            window_start=start, window_end=end, evidence=tuple(evidence), context=context,
            uncertainty=uncertainty,
            suggestions=(
                "Süreçler sekmesinde 'RSS' sütununa göre sıralayarak en çok bellek kullanan "
                "uygulamaları inceleyin.",
                "Kullanmadığınız uygulama veya tarayıcı sekmelerini kendiniz kapatmayı "
                "değerlendirin (PardusInsight hiçbir süreci sonlandırmaz).",
            )))


# ---------------------------------------------------------------------------
# Kural 2: Kalıcı CPU yoğunluğu
# ---------------------------------------------------------------------------


class SustainedCpuRule(Rule):
    rule_id = "sustained_cpu"
    title = "Kalıcı CPU yoğunluğu"
    description = (
        "Ardışık pencerelerin her birinde toplam CPU kullanımı örneklerinin belirli bir "
        "oranı (varsayılan %80) eşiğin (varsayılan %85) üzerindeyse tetiklenir; kısa "
        "sıçramalar uyarı üretmez. En yoğun süreçler bağlam olarak gösterilir."
    )

    def evaluate(self, samples: Sequence[SystemSample],
                 settings: AnalysisSettings) -> RuleOutcome:
        s = settings
        windows = _windows(samples, s)
        need = min_valid_samples(s.window_s, s.sample_interval_s, s.min_window_coverage)
        evidence: List[Evidence] = []
        fractions: List[float] = []
        means: List[float] = []
        for w in windows:
            vals = w.values("cpu_percent")
            if len(vals) < need:
                return _insufficient(w, len(vals), need, "CPU kullanımı")
            frac = fraction_at_least(vals, s.cpu_high_pct) or 0.0
            avg = mean(vals) or 0.0
            fractions.append(frac)
            means.append(avg)
            evidence.append(Evidence(
                metric="cpu_high_fraction",
                label=f"CPU ≥ {fmt_pct(s.cpu_high_pct, 0)} olan örneklerin oranı",
                value=round(frac * 100.0, 1), threshold=round(s.cpu_min_fraction * 100.0, 1),
                comparison=">=", unit="%", window_start=w.start, window_end=w.end,
                satisfied=frac >= s.cpu_min_fraction, role="trigger",
                note=f"Pencere ortalaması {fmt_pct(avg)}, {len(vals)} örnek"))

        start, end = windows[0].start, windows[-1].end
        period = _period_samples(windows)
        user = mean(values_of(period, "cpu_user_percent"))
        system = mean(values_of(period, "cpu_system_percent"))
        steal = mean(values_of(period, "cpu_steal_percent"))
        load = mean(values_of(period, "load1"))
        cpus = samples[-1].cpu_count
        for metric, label, value, unit in (
                ("cpu_user_percent", "Kullanıcı alanı CPU payı (ortalama)", user, "%"),
                ("cpu_system_percent", "Çekirdek alanı CPU payı (ortalama)", system, "%"),
                ("cpu_steal_percent", "Steal (sanal makine) payı (ortalama)", steal, "%"),
                ("load1", f"1 dk yük ortalaması ({cpus or '?'} mantıksal CPU)", load, "")):
            evidence.append(Evidence(
                metric=metric, label=label, value=None if value is None else round(value, 2),
                threshold=None, comparison="", unit=unit, window_start=start, window_end=end,
                satisfied=False, role="context"))

        if not all(f >= s.cpu_min_fraction for f in fractions):
            return RuleOutcome(False, "Koşul sağlanmadı: yüksek CPU her pencerede kalıcı değil "
                                      f"(eşik üstü oranlar: "
                                      f"{', '.join(fmt_pct(f * 100, 0) for f in fractions)}).")

        overall = mean(means) or 0.0
        confidence = ("yüksek" if min(fractions) >= 0.95 and overall >= s.cpu_high_pct + 5
                      else "orta")
        context = tuple(_aggregate_top_cpu(period))
        notes = [COMMON_UNCERTAINTY,
                 "Yüksek CPU kullanımı tek başına sorun değildir; derleme, video işleme gibi "
                 "beklenen işler de bu uyarıyı tetikleyebilir.",
                 "Süreç CPU değerleri örnekleme anlarındaki ölçümlerdir; örnekler arasında "
                 "başlayıp "
                 "biten kısa ömürlü süreçler listede görünmeyebilir."]
        if steal is not None and steal >= 5:
            notes.append("Steal payı yüksek: sanal makinenin ana sistemde CPU için beklediğini "
                         "gösterebilir.")
        notes.append(_coverage_note(windows, "cpu_percent", s))
        source_text, source_evidence = _cpu_source_attribution(period, overall, start, end, s)
        if source_evidence is not None:
            evidence.append(source_evidence)
        summary = (
            f"Son {fmt_duration(end - start)} boyunca her pencerede örneklerin en az "
            f"{fmt_pct(s.cpu_min_fraction * 100, 0)}'i {fmt_pct(s.cpu_high_pct, 0)} CPU eşiğinin "
            f"üzerindeydi (ortalama {fmt_pct(overall)}). {source_text}")
        return RuleOutcome(True, "Kalıcı CPU yoğunluğu koşulları sağlandı.", AlertDraft(
            title=self.title, severity=SEVERITY_WARNING, confidence=confidence,
            summary=summary, window_start=start, window_end=end, evidence=tuple(evidence),
            context=context, uncertainty=" ".join(notes),
            suggestions=(
                "Süreçler sekmesinde CPU sütununa göre sıralayarak yükün kaynağını inceleyin.",
                "Yük beklenen bir işten geliyorsa (derleme, dışa aktarma) uyarıyı "
                "bilgilendirme olarak değerlendirin.",
            )))


def _aggregate_top(period: Sequence[SystemSample], list_attr: str, value_attr: str,
                   mode: str = "mean", n: int = 5) -> List[Tuple[Tuple[int, str], float]]:
    """Dönem boyunca örneklerin süreç özetlerini birleştirir.

    "mean": örnek başına ortalama (listede görünmeyen örnekler 0 sayılır),
    "max": dönem içindeki en yüksek değer. Son örnek yerine tüm dönem
    kullanıldığından, koşul bittikten sonra güncellenen uyarı da doğru bağlamı korur.
    """
    totals: Dict[Tuple[int, str], float] = {}
    for sample in period:
        for p in getattr(sample, list_attr):
            value = getattr(p, value_attr)
            if value is None:
                continue
            key = (p.pid, p.name)
            if mode == "max":
                totals[key] = max(totals.get(key, 0.0), float(value))
            else:
                totals[key] = totals.get(key, 0.0) + float(value)
    if mode != "max":
        count = max(len(period), 1)
        totals = {k: v / count for k, v in totals.items()}
    return sorted(totals.items(), key=lambda kv: kv[1], reverse=True)[:n]


def _cpu_source_attribution(period: Sequence[SystemSample], overall: float, start: float,
                            end: float, s: AnalysisSettings) -> Tuple[str, Optional[Evidence]]:
    """Yükün tek bir süreç adından mı geldiğini, yoksa dağınık mı olduğunu açıklar.

    Aynı adlı süreçler (ör. paralel derleyici örnekleri) tek grup sayılır. Grubun dönem
    ortalaması toplam CPU ortalamasının ``cpu_process_share`` oranını aşarsa yoğunluk
    "süreç kaynaklı" olarak nitelenir. Süreç listesi yoksa yalnızca belirsizlik bildirilir.
    """
    per_process = _aggregate_top(period, "top_cpu", "cpu_percent", "mean", n=50)
    if not per_process or overall <= 0:
        return ("Süreç verisi olmadığından yükün kaynağı belirlenemedi.", None)
    groups: Dict[str, Tuple[float, int]] = {}
    for (_pid, name), value in per_process:
        total, count = groups.get(name, (0.0, 0))
        groups[name] = (total + value, count + 1)
    name, (value, count) = max(groups.items(), key=lambda kv: kv[1][0])
    share = min(value / overall, 1.0)
    dominant = share >= s.cpu_process_share
    label = f"{name}" + (f" ({count} süreç)" if count > 1 else "")
    evidence = Evidence(
        metric="top_process_share", label=f"En yoğun süreç grubunun payı: {label}",
        value=round(share * 100.0, 1), threshold=round(s.cpu_process_share * 100.0, 1),
        comparison=">=", unit="%", window_start=start, window_end=end, satisfied=dominant,
        role="context", note="Süreç ortalaması / toplam CPU ortalaması")
    if dominant:
        text = (f"Yükün yaklaşık {fmt_pct(share * 100, 0)}'i {label} kaynaklı; yoğunluk büyük "
                "olasılıkla bu süreç(ler)den geliyor.")
    else:
        text = (f"En yoğun süreç grubu ({label}) yükün yalnızca yaklaşık "
                f"{fmt_pct(share * 100, 0)}'ini oluşturuyor; yük birden fazla sürece dağılmış.")
    return text, evidence


def _aggregate_top_cpu(period: Sequence[SystemSample], n: int = 5) -> List[str]:
    """Dönem boyunca örneklerde görülen süreçlerin ortalama CPU payı."""
    return [f"{name} (PID {pid}): ortalama {fmt_pct(value)} CPU"
            for (pid, name), value in _aggregate_top(period, "top_cpu", "cpu_percent", "mean", n)]


# ---------------------------------------------------------------------------
# Kural 3: Disk G/Ç anomalisi (gözlemsel)
# ---------------------------------------------------------------------------


class DiskIoAnomalyRule(Rule):
    rule_id = "disk_io_anomaly"
    title = "Disk G/Ç etkinliği anomalisi"
    description = (
        "Ardışık pencerelerin her birinde toplam okuma+yazma hızının pencere medyanı, "
        "önceki 5 dakikanın medyanının belirli katını (varsayılan 3×) ve mutlak alt "
        "sınırı (5 MiB/sn) aşarsa VEYA disk meşguliyetinin pencere medyanı önceki "
        "dönemde düşükken eşiği (%80) aşarsa yalnızca gözlemsel bir uyarı üretir."
    )

    def evaluate(self, samples: Sequence[SystemSample],
                 settings: AnalysisSettings) -> RuleOutcome:
        s = settings
        windows = _windows(samples, s)
        need = min_valid_samples(s.window_s, s.sample_interval_s, s.min_window_coverage)
        eval_start = windows[0].start
        base_start = eval_start - s.disk_baseline_s
        baseline = [x for x in samples if base_start < x.timestamp <= eval_start]
        base_tp = values_of(baseline, lambda x: x.disk_total_bytes_per_s)
        base_busy = values_of(baseline, "disk_busy_percent")
        need_base = max(3, int(math.ceil(
            s.disk_baseline_s / s.sample_interval_s * s.disk_min_baseline_coverage)))
        base_ok = len(base_tp) >= need_base
        base_med = median(base_tp) if base_ok else None
        base_busy_med = median(base_busy) if len(base_busy) >= need_base else None
        min_abs = s.disk_min_throughput_mib_s * MIB
        tp_threshold = max(min_abs, base_med * s.disk_ratio) if base_med is not None else None

        evidence: List[Evidence] = [Evidence(
            metric="baseline_throughput", label="Önceki dönem okuma+yazma hızı (medyan)",
            value=None if base_med is None else round(base_med, 1), threshold=None,
            comparison="", unit="B/sn", window_start=base_start, window_end=eval_start,
            satisfied=base_ok, role="context",
            note=(f"{len(base_tp)} örnek" if base_ok else
                  f"Yetersiz taban verisi ({len(base_tp)}/{need_base} örnek); oran "
                  "karşılaştırması yapılamadı"))]
        ratio_flags: List[bool] = []
        busy_flags: List[bool] = []
        tps: List[float] = []
        for w in windows:
            vals = w.values(lambda x: x.disk_total_bytes_per_s)
            if len(vals) < need:
                return _insufficient(w, len(vals), need, "disk G/Ç")
            # Medyan: pencereye yalnızca birkaç yüksek örnek düştüğünde tetiklenmeyi önler
            tp = median(vals) or 0.0
            tps.append(tp)
            busy_vals = w.values("disk_busy_percent")
            busy = median(busy_vals)
            ratio_ok = tp_threshold is not None and tp >= tp_threshold
            busy_ok = busy is not None and busy >= s.disk_busy_pct
            ratio_flags.append(ratio_ok)
            busy_flags.append(busy_ok)
            evidence.append(Evidence(
                metric="disk_total_bytes_per_s", label="Okuma+yazma hızı (pencere medyanı)",
                value=round(tp, 1),
                threshold=None if tp_threshold is None else round(tp_threshold, 1),
                comparison=">=", unit="B/sn", window_start=w.start, window_end=w.end,
                satisfied=ratio_ok, role="trigger",
                note=(f"Eşik = max({tr_num(s.disk_ratio, 1)} × taban, "
                      f"{tr_num(s.disk_min_throughput_mib_s, 0)} MiB/sn)")))
            evidence.append(Evidence(
                metric="disk_busy_percent", label="Disk meşguliyeti (pencere medyanı)",
                value=None if busy is None else round(busy, 1), threshold=s.disk_busy_pct,
                comparison=">=", unit="%", window_start=w.start, window_end=w.end,
                satisfied=busy_ok, role="trigger"))

        start, end = windows[0].start, windows[-1].end
        period = _period_samples(windows)
        for metric, label, value, unit in (
                ("cpu_iowait_percent", "CPU iowait payı (ortalama)",
                 mean(values_of(period, "cpu_iowait_percent")), "%"),
                ("procs_blocked", "G/Ç bekleyen süreç sayısı (ortalama)",
                 mean(values_of(period, "procs_blocked")), ""),
                ("psi_io_some", "PSI G/Ç baskısı 'some' avg10 (ortalama)",
                 mean(values_of(period, "psi_io_some")), "%")):
            evidence.append(Evidence(
                metric=metric, label=label, value=None if value is None else round(value, 2),
                threshold=None, comparison="", unit=unit, window_start=start, window_end=end,
                satisfied=False, role="context"))

        ratio_cond = all(ratio_flags)
        busy_cond = all(busy_flags) and (base_busy_med is None or base_busy_med < s.disk_busy_pct)
        if not (ratio_cond or busy_cond):
            values = " / ".join(fmt_rate(tp) for tp in tps)
            if tp_threshold is None:
                detail = ("taban verisi yetersiz ve meşguliyet eşiği her pencerede aşılmadı "
                          f"(pencere medyanları {values})")
            else:
                detail = (f"okuma+yazma eşiği ({fmt_rate(tp_threshold)}) her pencerede "
                          f"aşılmadı (pencere medyanları {values}); meşguliyet koşulu da "
                          "sağlanmadı")
            return RuleOutcome(False, f"Koşul sağlanmadı: {detail}.")

        reasons = []
        if ratio_cond:
            reasons.append(f"okuma+yazma hızı önceki döneme göre en az "
                           f"{tr_num(s.disk_ratio, 1)} kat arttı (son pencere "
                           f"{fmt_rate(tps[-1])}, taban {fmt_rate(base_med)})")
        if busy_cond:
            reasons.append(f"disk meşguliyeti her pencerede {fmt_pct(s.disk_busy_pct, 0)} "
                           "eşiğini aştı")
        confidence = "orta" if ratio_cond and busy_cond else "düşük"
        context = tuple(
            f"{name} (PID {pid}): ortalama {fmt_rate(value)}"
            for (pid, name), value in _aggregate_top(period, "top_io", "io_bytes_per_s", "mean"))
        if not context:
            context = ("Erişilebilen süreçlerde belirgin G/Ç bulunamadı (diğer kullanıcıların "
                       "süreçleri root olmadan okunamaz).",)
        uncertainty = " ".join([
            "Bu yalnızca gözlemsel bir bilgidir.", COMMON_UNCERTAINTY,
            "Disk etkinliğindeki artış güncelleme, dosya kopyalama veya dizinleme gibi olağan "
            "işlerden kaynaklanabilir.",
            "Diğer kullanıcılara ve sisteme ait süreçlerin G/Ç sayaçları standart kullanıcı "
            "yetkisiyle okunamadığından süreç bağlamı eksik olabilir.",
            "Meşguliyet yüzdesi, NVMe/SSD gibi paralel istek işleyen aygıtlarda doygunluğu "
            "olduğundan yüksek gösterebilir.",
            _coverage_note(windows, "disk_read_bytes_per_s", s),
        ])
        summary = f"Son {fmt_duration(end - start)} boyunca " + " ve ".join(reasons) + "."
        return RuleOutcome(True, "Disk G/Ç anomalisi gözlendi.", AlertDraft(
            title=self.title, severity=SEVERITY_INFO, confidence=confidence, summary=summary,
            window_start=start, window_end=end, evidence=tuple(evidence), context=context,
            uncertainty=uncertainty,
            suggestions=(
                "Süreçler sekmesinde okuma/yazma sütunlarına göre sıralayarak erişilebilen "
                "süreçleri inceleyin.",
                "Devam eden bir kopyalama, güncelleme veya yedekleme olup olmadığını kontrol edin.",
            )))


def default_rules() -> List[Rule]:
    return [MemoryPressureRule(), SustainedCpuRule(), DiskIoAnomalyRule()]
