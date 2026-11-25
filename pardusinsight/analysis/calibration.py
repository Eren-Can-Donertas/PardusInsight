"""Eşik kalibrasyonu: kayıtlar üzerinde kural duyarlılık taraması ve eşik önerisi.

Yöntem (ayrıntı: docs/KURALLAR.md "Kalibrasyon"):

1. Hedef sistemde olağan kullanım kayıtları ("normal") ve isteğe bağlı olarak
   bilinen yoğun işlerin kayıtları ("yoğun") alınır
   (``pardusinsight --headless --duration 1800 --export-json normal.json``).
2. Her kuralın ana eşikleri, varsayılan değerin çevresindeki bir ızgarada tek tek
   değiştirilir ve kayıtlar **gerçek kural koduyla** (``replay``) yeniden analiz
   edilir. Kalibrasyon kuralların ayrı bir benzetimini kullanmaz; bu yüzden
   kuralların davranışıyla birebir tutarlıdır.
3. Normal kayıtlarda uyarı üretmeyen (yanlış pozitif = 0) değerler belirlenir.
   Varsayılan değer yanlış pozitif üretiyorsa sıfıra inen en yakın değer bir adım
   güvenlik payıyla önerilir. Varsayılan sessizse ve beklenen yoğun kayıtları
   kaçırıyorsa, normal kayıtlarda sessiz kalıp onları yakalayan en yakın değer
   önerilir. Aksi hâlde varsayılan korunur.

Modül saf Python'dur: dosya okumaz/yazmaz, yalnızca örnek listeleri üzerinde çalışır.
"""
from __future__ import annotations

import json
import statistics
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..config import AnalysisSettings
from ..core.formatting import fmt_bytes, fmt_duration, tr_num
from ..core.models import SystemSample
from .engine import replay
from .rules import Rule, default_rules

RULE_TITLES = {r.rule_id: r.title for r in default_rules()}


@dataclass(frozen=True)
class Recording:
    """Kalibrasyonda kullanılan tek kayıt.

    ``heavy``: bilinen yoğun bir işin kaydı (uyarı beklenebilir).
    ``expect``: yoğun kayıtta tetiklenmesi beklenen kural kimlikleri; boşsa kayıt
    yalnızca tabloda gösterilir, öneri kararına katılmaz.
    """

    label: str
    samples: Sequence[SystemSample]
    heavy: bool = False
    expect: Tuple[str, ...] = ()

    @property
    def start(self) -> float:
        return self.samples[0].timestamp if self.samples else 0.0

    @property
    def duration_s(self) -> float:
        return self.samples[-1].timestamp - self.samples[0].timestamp if self.samples else 0.0

    @property
    def interval_s(self) -> Optional[float]:
        """Örnekler arasındaki medyan süre (kayıt sırasında kullanılan aralık)."""
        gaps = [b.timestamp - a.timestamp for a, b in zip(self.samples, self.samples[1:])
                if b.timestamp > a.timestamp]
        return statistics.median(gaps) if gaps else None


@dataclass(frozen=True)
class Parameter:
    """Taranan tek eşik. ``lower_is_more_sensitive``: değer küçüldükçe uyarı artar."""

    name: str
    rule_id: str
    label: str
    grid: Tuple[float, ...]
    lower_is_more_sensitive: bool
    unit: str = ""


PARAMETERS: Tuple[Parameter, ...] = (
    Parameter("mem_available_warn_pct", "memory_pressure", "Kullanılabilir bellek uyarı eşiği",
              (5.0, 7.5, 10.0, 12.5, 15.0, 20.0), False, "%"),
    Parameter("swap_activity_pages_s", "memory_pressure", "Swap etkinliği eşiği",
              (25.0, 50.0, 100.0, 200.0, 400.0), True, "sayfa/sn"),
    Parameter("major_faults_s", "memory_pressure", "Major page-fault eşiği",
              (25.0, 50.0, 100.0, 200.0, 400.0), True, "/sn"),
    Parameter("cpu_high_pct", "sustained_cpu", "Yüksek CPU eşiği",
              (60.0, 70.0, 75.0, 80.0, 85.0, 90.0, 95.0), True, "%"),
    Parameter("cpu_min_fraction", "sustained_cpu", "Eşik üstü örnek oranı",
              (0.5, 0.6, 0.7, 0.8, 0.9, 1.0), True, ""),
    Parameter("disk_ratio", "disk_io_anomaly", "Disk artış katsayısı",
              (1.5, 2.0, 3.0, 4.0, 6.0), True, "×"),
    Parameter("disk_min_throughput_mib_s", "disk_io_anomaly", "Disk mutlak alt sınır",
              (1.0, 2.0, 5.0, 10.0, 20.0, 50.0), True, "MiB/sn"),
    Parameter("disk_busy_pct", "disk_io_anomaly", "Disk meşguliyet eşiği",
              (50.0, 60.0, 70.0, 80.0, 90.0, 95.0), True, "%"),
)


@dataclass(frozen=True)
class Cell:
    """Bir eşik değerinin her kayıttaki sonucu."""

    value: float
    alerts: Dict[str, int]
    first_delay_s: Dict[str, Optional[float]]


@dataclass(frozen=True)
class Sweep:
    parameter: Parameter
    base_value: float
    cells: Tuple[Cell, ...]  # en az duyarlıdan en duyarlıya sıralı


@dataclass(frozen=True)
class Recommendation:
    parameter: str
    rule_id: str
    label: str
    current: float
    recommended: float
    reason: str

    @property
    def changed(self) -> bool:
        return abs(self.recommended - self.current) > 1e-9


@dataclass(frozen=True)
class AlertSummary:
    rule_id: str
    title: str
    first_delay_s: float
    duration_s: float


@dataclass(frozen=True)
class CalibrationResult:
    base: AnalysisSettings
    recordings: Tuple[Recording, ...]
    profiles: Dict[str, Dict[str, Dict[str, float]]]
    default_alerts: Dict[str, Tuple[AlertSummary, ...]]
    sweeps: Tuple[Sweep, ...]
    recommendations: Tuple[Recommendation, ...]
    notes: Tuple[str, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# Hesaplama
# ---------------------------------------------------------------------------

PROFILE_METRICS: Tuple[Tuple[str, str, str], ...] = (
    ("cpu_percent", "CPU kullanımı", "%"),
    ("mem_available_percent", "Kullanılabilir bellek", "%"),
    ("swap_activity_pages_per_s", "Swap etkinliği", "sayfa/sn"),
    ("major_faults_per_s", "Major page-fault", "/sn"),
    ("psi_memory_some", "PSI bellek some", "%"),
    ("disk_total_bytes_per_s", "Disk okuma+yazma", "B/sn"),
    ("disk_busy_percent", "Disk meşguliyeti", "%"),
)


def _percentile(ordered: Sequence[float], q: float) -> float:
    """En yakın sıra yöntemiyle yüzdelik (sıralı liste)."""
    index = min(len(ordered) - 1, max(0, int(round(q / 100.0 * (len(ordered) - 1)))))
    return ordered[index]


def metric_profile(samples: Sequence[SystemSample]) -> Dict[str, Dict[str, float]]:
    """Kalibrasyon raporu için metrik dağılımları (medyan, p95, p99, en düşük/yüksek)."""
    out: Dict[str, Dict[str, float]] = {}
    for name, _label, _unit in PROFILE_METRICS:
        values = sorted(float(v) for v in (getattr(s, name) for s in samples) if v is not None)
        if values:
            out[name] = {"min": values[0], "p50": _percentile(values, 50),
                         "p95": _percentile(values, 95), "p99": _percentile(values, 99),
                         "max": values[-1], "count": float(len(values))}
    return out


def settings_for(recording: Recording, base: AnalysisSettings) -> AnalysisSettings:
    """Kaydın örnekleme aralığı ayarlardakinden belirgin farklıysa ona uyarlar.

    Kurallar pencere başına beklenen örnek sayısını ``sample_interval_s``'den hesaplar;
    5 sn aralıkla alınmış bir kayıt 2 sn varsayımıyla analiz edilirse pencereler
    "yetersiz veri" sayılır ve hiç uyarı çıkmaz (yanıltıcı biçimde "yanlış pozitif yok").
    """
    interval = recording.interval_s
    if interval is None or abs(interval - base.sample_interval_s) <= 0.1 * base.sample_interval_s:
        return base
    interval = round(min(max(interval, 0.2), 60.0), 2)
    window = max(base.window_s, 2 * interval)
    return replace(base, sample_interval_s=interval, window_s=window).validate()


def _rule(rule_id: str) -> Rule:
    for rule in default_rules():
        if rule.rule_id == rule_id:
            return rule
    raise KeyError(rule_id)


def _with_value(base: AnalysisSettings, name: str, value: float) -> AnalysisSettings:
    changes: Dict[str, Any] = {name: value}
    if name == "mem_available_warn_pct":
        changes["mem_available_crit_pct"] = min(base.mem_available_crit_pct, value)
    return replace(base, **changes).validate()


def _replay_alerts(recording: Recording, settings: AnalysisSettings,
                   rules: Optional[Sequence[Rule]] = None):
    return replay(recording.samples, settings, rules).alert_log()


def sweep_parameter(parameter: Parameter, recordings: Sequence[Recording],
                    base: AnalysisSettings) -> Sweep:
    base_value = float(getattr(base, parameter.name))
    values = sorted(set(parameter.grid) | {base_value},
                    reverse=parameter.lower_is_more_sensitive)
    cells: List[Cell] = []
    for value in values:
        alerts: Dict[str, int] = {}
        delays: Dict[str, Optional[float]] = {}
        for rec in recordings:
            settings = _with_value(settings_for(rec, base), parameter.name, value)
            log = _replay_alerts(rec, settings, [_rule(parameter.rule_id)])
            alerts[rec.label] = len(log)
            delays[rec.label] = (min(a.first_seen for a in log) - rec.start) if log else None
        cells.append(Cell(value, alerts, delays))
    return Sweep(parameter, base_value, tuple(cells))


def _fp(cell: Cell, normals: Sequence[Recording]) -> int:
    return sum(cell.alerts[r.label] for r in normals)


def _detects(cell: Cell, heavies: Sequence[Recording]) -> bool:
    return all(cell.alerts[r.label] > 0 for r in heavies)


def recommend(sweep: Sweep, recordings: Sequence[Recording]) -> Recommendation:
    p = sweep.parameter
    normals = [r for r in recordings if not r.heavy]
    expected = [r for r in recordings if r.heavy and p.rule_id in r.expect]
    cells = list(sweep.cells)  # en az duyarlı -> en duyarlı
    base_i = next(i for i, c in enumerate(cells) if abs(c.value - sweep.base_value) < 1e-9)

    def rec(value: float, reason: str) -> Recommendation:
        return Recommendation(p.name, p.rule_id, p.label, sweep.base_value, value, reason)

    if not normals:
        return rec(sweep.base_value, "Olağan kullanım kaydı yok; yanlış pozitif ölçülemedi, "
                                     "varsayılan korunur.")
    base_fp = _fp(cells[base_i], normals)
    if base_fp > 0:
        quiet = [i for i in range(base_i) if _fp(cells[i], normals) == 0]
        if not quiet:
            return rec(cells[0].value,
                       f"Varsayılan değer olağan kullanımda {base_fp} uyarı üretti ve taranan "
                       "en az duyarlı değer bile sessiz kalmadı; kayıtlar elle incelenmeli.")
        closest = max(quiet)
        chosen = max(closest - 1, 0)  # bir adım güvenlik payı
        margin = "bir adım güvenlik payıyla" if chosen < closest else "güvenlik payı bırakılamadı"
        return rec(cells[chosen].value,
                   f"Varsayılan değer olağan kullanımda {base_fp} uyarı (yanlış pozitif) üretti; "
                   f"{_num(cells[closest].value, p.unit)} değerinde sıfıra iniyor, {margin} "
                   "önerildi.")
    missed = [r for r in expected if cells[base_i].alerts[r.label] == 0]
    if missed:
        ok = [i for i in range(base_i + 1, len(cells))
              if _fp(cells[i], normals) == 0 and _detects(cells[i], expected)]
        if ok:
            chosen = ok[0]
            buffered = chosen + 1 < len(cells) and _fp(cells[chosen + 1], normals) == 0
            note = "" if buffered else " Bir adım daha duyarlı değer yanlış pozitif ürettiği " \
                                       "için pay yok; dikkatli kullanın."
            return rec(cells[chosen].value,
                       f"Varsayılan değer beklenen yoğun kayıtları ({', '.join(r.label for r in missed)}) "
                       f"kaçırdı; önerilen değer onları yakalıyor ve olağan kullanımda sessiz."
                       + note)
        return rec(sweep.base_value,
                   "Beklenen yoğun kayıtları yakalayıp olağan kullanımda sessiz kalan bir değer "
                   "bulunamadı; varsayılan korunur.")
    spare = 0
    for i in range(base_i + 1, len(cells)):
        if _fp(cells[i], normals) != 0:
            break
        spare += 1
    if base_i == len(cells) - 1:
        margin = "; taranan en duyarlı değer budur."
    elif spare:
        margin = f"; {spare} adım daha duyarlı değerde de sessiz."
    else:
        margin = "; ancak bir adım daha duyarlı değer uyarı üretiyor (sınırda)."
    return rec(sweep.base_value,
               "Varsayılan değer olağan kullanımda yanlış pozitif üretmiyor" + margin
               + (" Beklenen yoğun kayıtları da yakalıyor." if expected else ""))


def calibrate(recordings: Sequence[Recording],
              base: Optional[AnalysisSettings] = None,
              parameters: Sequence[Parameter] = PARAMETERS) -> CalibrationResult:
    """Kayıtlar üzerinde tüm parametreleri tarar ve öneri üretir."""
    base = (base or AnalysisSettings()).validate()
    recs = tuple(r for r in recordings if len(r.samples) >= 2)
    labels = [r.label for r in recs]
    if len(set(labels)) != len(labels):
        raise ValueError("kayıt etiketleri benzersiz olmalı")
    notes: List[str] = []
    for r in recordings:
        if len(r.samples) < 2:
            notes.append(f"{r.label}: 2'den az örnek olduğu için kullanılmadı.")
    for r in recs:
        adjusted = settings_for(r, base)
        if adjusted is not base:
            notes.append(f"{r.label}: kayıt {tr_num(adjusted.sample_interval_s, 1)} sn aralıkla "
                         "alınmış; analiz bu aralığa göre yapıldı.")
        needed = base.lookback_s
        if r.duration_s < needed:
            notes.append(f"{r.label}: kayıt {fmt_duration(r.duration_s)}; disk kuralının taban "
                         f"dönemi dahil {fmt_duration(needed)} veriden kısa kayıtlar zayıf kanıttır.")
    profiles = {r.label: metric_profile(r.samples) for r in recs}
    default_alerts = {
        r.label: tuple(AlertSummary(a.rule_id, a.title, a.first_seen - r.start,
                                    (a.resolved_at or a.last_seen) - a.first_seen)
                       for a in _replay_alerts(r, settings_for(r, base)))
        for r in recs}
    sweeps = tuple(sweep_parameter(p, recs, base) for p in parameters) if recs else ()
    recommendations = tuple(recommend(s, recs) for s in sweeps)
    return CalibrationResult(base, recs, profiles, default_alerts, sweeps, recommendations,
                             tuple(notes))


def recommended_config(result: CalibrationResult) -> Dict[str, Any]:
    """Yalnızca değişmesi önerilen eşikleri ``--config`` biçiminde döndürür."""
    changed = {r.parameter: r.recommended for r in result.recommendations if r.changed}
    return {"analysis": changed} if changed else {}


# ---------------------------------------------------------------------------
# Rapor
# ---------------------------------------------------------------------------


def _num(value: float, unit: str = "") -> str:
    if unit == "B/sn":
        return f"{fmt_bytes(value)}/sn"
    text = tr_num(value, 2).rstrip("0").rstrip(",") if value != int(value) else str(int(value))
    return f"%{text}" if unit == "%" else (f"{text} {unit}".strip())


def _cell_text(cell: Cell, label: str) -> str:
    count = cell.alerts[label]
    if not count:
        return "0"
    delay = cell.first_delay_s[label]
    return f"{count} (ilk: {fmt_duration(delay or 0.0)})"


def render_markdown(result: CalibrationResult) -> str:
    lines: List[str] = ["## Eşik kalibrasyonu", ""]
    if not result.recordings:
        lines += ["Kullanılabilir kayıt yok.", ""]
        return "\n".join(lines)
    lines += ["Kuralların eşikleri tek tek değiştirilerek kayıtlar gerçek kural koduyla yeniden "
              "analiz edildi (kural başına uyarı sayısı). *Normal* kayıtlarda her uyarı yanlış "
              "pozitiftir; *yoğun* kayıtlar bilinen ağır işlerdir.", "",
              "| Kayıt | Tür | Süre | Örnek | Aralık |", "|---|---|---|---|---|"]
    for r in result.recordings:
        kind = "yoğun" + (f" (beklenen: {', '.join(r.expect)})" if r.expect else "") \
            if r.heavy else "normal"
        interval = r.interval_s
        lines.append(f"| {r.label} | {kind} | {fmt_duration(r.duration_s)} | {len(r.samples)} | "
                     f"{'—' if interval is None else tr_num(interval, 1) + ' sn'} |")
    if result.notes:
        lines += [""] + [f"- {n}" for n in result.notes]

    lines += ["", "### Ölçüm profili", "",
              "| Metrik | Kayıt | Medyan | p95 | p99 | En yüksek |", "|---|---|---|---|---|---|"]
    for name, label, unit in PROFILE_METRICS:
        for r in result.recordings:
            prof = result.profiles[r.label].get(name)
            if prof:
                lines.append(f"| {label} | {r.label} | {_num(prof['p50'], unit)} | "
                             f"{_num(prof['p95'], unit)} | {_num(prof['p99'], unit)} | "
                             f"{_num(prof['max'], unit)} |")

    lines += ["", "### Varsayılan eşiklerle üretilen uyarılar", "",
              "| Kayıt | Tür | Uyarılar |", "|---|---|---|"]
    for r in result.recordings:
        alerts = result.default_alerts[r.label]
        text = "; ".join(f"{a.title} ({fmt_duration(a.first_delay_s)} sonra, "
                         f"{fmt_duration(a.duration_s)} sürdü)" for a in alerts) or "yok"
        lines.append(f"| {r.label} | {'yoğun' if r.heavy else 'normal'} | {text} |")

    recs_by_param = {rec.parameter: rec for rec in result.recommendations}
    lines += ["", "### Duyarlılık taraması", "",
              "Satırlar en az duyarlı değerden en duyarlıya sıralıdır. Hücre: o değerde üretilen "
              "uyarı sayısı (ilk uyarının kayıt başından gecikmesi)."]
    header = " | ".join(r.label + (" (yoğun)" if r.heavy else "") for r in result.recordings)
    for sweep in result.sweeps:
        p = sweep.parameter
        rec = recs_by_param.get(p.name)
        lines += ["", f"**{p.label}** (`{p.name}`, kural: {RULE_TITLES.get(p.rule_id, p.rule_id)})",
                  "", f"| Değer | {header} |",
                  "|---|" + "---|" * len(result.recordings)]
        for cell in sweep.cells:
            marks = []
            if abs(cell.value - sweep.base_value) < 1e-9:
                marks.append("varsayılan")
            if rec is not None and rec.changed and abs(cell.value - rec.recommended) < 1e-9:
                marks.append("öneri")
            value = _num(cell.value, p.unit) + (f" **({', '.join(marks)})**" if marks else "")
            row = " | ".join(_cell_text(cell, r.label) for r in result.recordings)
            lines.append(f"| {value} | {row} |")

    lines += ["", "### Öneriler", "", "| Parametre | Kural | Mevcut | Önerilen | Gerekçe |",
              "|---|---|---|---|---|"]
    units = {p.name: p.unit for p in PARAMETERS}
    for rec in result.recommendations:
        unit = units.get(rec.parameter, "")
        suggested = _num(rec.recommended, unit) if rec.changed else "değişmez"
        lines.append(f"| `{rec.parameter}` | {RULE_TITLES.get(rec.rule_id, rec.rule_id)} | "
                     f"{_num(rec.current, unit)} | {suggested} | {rec.reason} |")
    config = recommended_config(result)
    if config:
        lines +=["", "Önerilen değerler `--config` dosyası olarak:", "", "```json",
                  json.dumps(config, ensure_ascii=False, indent=1), "```"]
    else:
        lines += ["", "Bu kayıtlara göre varsayılan eşiklerde değişiklik önerilmiyor."]
    lines.append("")
    return "\n".join(lines)
