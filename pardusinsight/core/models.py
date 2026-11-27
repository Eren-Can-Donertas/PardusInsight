"""Uygulama genelinde kullanılan değişmez (frozen) veri modelleri.

Ham sayaçlar (RawSnapshot) kolektörlerden gelir; Normalizer bunları iki ardışık
ölçüm arasındaki farklarla SystemSample'a dönüştürür. Kurallar yalnızca
SystemSample listeleri üzerinde çalışır; bu sayede sentetik veriyle tamamen
deterministik test edilebilir.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from typing import Any, Dict, Mapping, Optional, Tuple

# ---------------------------------------------------------------------------
# Ham (kümülatif) sayaçlar
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CpuTimes:
    """/proc/stat "cpu" satırındaki kümülatif süreler (saniye)."""

    user: float
    nice: float
    system: float
    idle: float
    iowait: float = 0.0
    irq: float = 0.0
    softirq: float = 0.0
    steal: float = 0.0

    @property
    def total(self) -> float:
        return (self.user + self.nice + self.system + self.idle + self.iowait
                + self.irq + self.softirq + self.steal)


@dataclass(frozen=True)
class MemoryInfo:
    """Bellek ve swap göstergeleri (bayt)."""

    total: int
    available: int
    free: int
    buffers: int = 0
    cached: int = 0
    swap_total: int = 0
    swap_free: int = 0
    available_estimated: bool = False  # MemAvailable yoksa tahmini değer


@dataclass(frozen=True)
class VmCounters:
    """/proc/vmstat kümülatif sayaçları. Alan okunamadıysa None."""

    pswpin: Optional[int] = None  # swap'ten okunan sayfa sayısı
    pswpout: Optional[int] = None  # swap'e yazılan sayfa sayısı
    pgmajfault: Optional[int] = None  # önemli (major) sayfa hataları
    pgfault: Optional[int] = None


@dataclass(frozen=True)
class DiskCounters:
    """Tek bir blok aygıtın kümülatif G/Ç sayaçları."""

    read_bytes: int
    write_bytes: int
    busy_ms: int  # aygıtın G/Ç ile meşgul olduğu toplam süre (io_ticks)
    read_count: int = 0
    write_count: int = 0


@dataclass(frozen=True)
class PressureInfo:
    """Pressure Stall Information (PSI) avg10 yüzdeleri; çekirdek desteklemiyorsa None."""

    memory_some: Optional[float] = None
    memory_full: Optional[float] = None
    cpu_some: Optional[float] = None
    io_some: Optional[float] = None


@dataclass(frozen=True)
class RawSnapshot:
    """Bir örnekleme anındaki ham ölçümler.

    ``timestamp`` duvar saatidir (gösterim için); ``monotonic`` ise fark
    hesaplarında kullanılır ve sistem saati değişse bile geri gitmez.
    """

    timestamp: float
    monotonic: float
    cpu_times: Optional[CpuTimes] = None
    cpu_count: Optional[int] = None
    memory: Optional[MemoryInfo] = None
    vm: Optional[VmCounters] = None
    disks: Optional[Dict[str, DiskCounters]] = None
    load1: Optional[float] = None
    procs_running: Optional[int] = None
    procs_blocked: Optional[int] = None
    pressure: Optional[PressureInfo] = None
    errors: Tuple[str, ...] = ()
    source: str = "unknown"


# ---------------------------------------------------------------------------
# Süreçler
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProcessInfo:
    """Süreç tablosundaki tek satır. Erişilemeyen alanlar None'dır."""

    pid: int
    name: str
    username: Optional[str] = None
    status: Optional[str] = None
    cpu_percent: Optional[float] = None  # toplam CPU kapasitesine göre (0-100)
    rss_bytes: Optional[int] = None
    memory_percent: Optional[float] = None
    num_threads: Optional[int] = None
    read_bytes_per_s: Optional[float] = None
    write_bytes_per_s: Optional[float] = None

    @property
    def io_bytes_per_s(self) -> Optional[float]:
        if self.read_bytes_per_s is None and self.write_bytes_per_s is None:
            return None
        return (self.read_bytes_per_s or 0.0) + (self.write_bytes_per_s or 0.0)


@dataclass(frozen=True)
class ProcessSnapshot:
    """Tek bir süreç taramasının sonucu ve hata sayaçları."""

    processes: Tuple[ProcessInfo, ...] = ()
    total_seen: int = 0
    partial_access: int = 0  # en az bir alanı izin nedeniyle okunamayan süreç sayısı
    access_denied: int = 0  # tamamen okunamayan süreç sayısı
    vanished: int = 0  # tarama sırasında sonlanan süreç sayısı
    error: Optional[str] = None


@dataclass(frozen=True)
class ProcessBrief:
    """Örnek içinde saklanan hafif süreç özeti (kural bağlamı için)."""

    pid: int
    name: str
    cpu_percent: Optional[float] = None
    rss_bytes: Optional[int] = None
    io_bytes_per_s: Optional[float] = None


# ---------------------------------------------------------------------------
# Normalize edilmiş örnek
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SystemSample:
    """Normalize edilmiş tek ölçüm. Hesaplanamayan alanlar None'dır."""

    timestamp: float
    interval_s: Optional[float] = None
    cpu_percent: Optional[float] = None
    cpu_user_percent: Optional[float] = None
    cpu_system_percent: Optional[float] = None
    cpu_iowait_percent: Optional[float] = None
    cpu_steal_percent: Optional[float] = None
    cpu_count: Optional[int] = None
    load1: Optional[float] = None
    mem_total_bytes: Optional[int] = None
    mem_available_bytes: Optional[int] = None
    mem_available_percent: Optional[float] = None
    mem_used_percent: Optional[float] = None
    swap_total_bytes: Optional[int] = None
    swap_used_bytes: Optional[int] = None
    swap_used_percent: Optional[float] = None
    swap_in_pages_per_s: Optional[float] = None
    swap_out_pages_per_s: Optional[float] = None
    major_faults_per_s: Optional[float] = None
    minor_faults_per_s: Optional[float] = None  # pgfault - pgmajfault (diskten okuma gerektirmeyen)
    disk_read_bytes_per_s: Optional[float] = None
    disk_write_bytes_per_s: Optional[float] = None
    disk_busy_percent: Optional[float] = None
    disk_read_bytes_total: Optional[int] = None  # açılıştan beri kümülatif (fiziksel diskler)
    disk_write_bytes_total: Optional[int] = None
    psi_memory_some: Optional[float] = None
    psi_memory_full: Optional[float] = None
    psi_cpu_some: Optional[float] = None
    psi_io_some: Optional[float] = None
    procs_running: Optional[int] = None
    procs_blocked: Optional[int] = None
    top_cpu: Tuple[ProcessBrief, ...] = ()
    top_memory: Tuple[ProcessBrief, ...] = ()
    top_io: Tuple[ProcessBrief, ...] = ()
    errors: Tuple[str, ...] = ()

    @property
    def swap_activity_pages_per_s(self) -> Optional[float]:
        if self.swap_in_pages_per_s is None or self.swap_out_pages_per_s is None:
            return None
        return self.swap_in_pages_per_s + self.swap_out_pages_per_s

    @property
    def disk_total_bytes_per_s(self) -> Optional[float]:
        if self.disk_read_bytes_per_s is None or self.disk_write_bytes_per_s is None:
            return None
        return self.disk_read_bytes_per_s + self.disk_write_bytes_per_s


_PROCESS_LIST_FIELDS = ("top_cpu", "top_memory", "top_io")

#: CSV'ye yazılan sayısal alanlar (sıralı). Süreç listeleri ve hatalar hariç.
SAMPLE_METRIC_FIELDS: Tuple[str, ...] = tuple(
    f.name for f in fields(SystemSample)
    if f.name not in _PROCESS_LIST_FIELDS + ("errors",)
)

#: Her ölçüm alanının birimi (CSV/JSON raporlarında ve belgelerde kullanılır)
SAMPLE_UNITS: Dict[str, str] = {
    "timestamp": "unix_saniye", "interval_s": "saniye",
    "cpu_percent": "yuzde", "cpu_user_percent": "yuzde", "cpu_system_percent": "yuzde",
    "cpu_iowait_percent": "yuzde", "cpu_steal_percent": "yuzde", "cpu_count": "adet",
    "load1": "yuk_ortalamasi", "mem_total_bytes": "bayt", "mem_available_bytes": "bayt",
    "mem_available_percent": "yuzde", "mem_used_percent": "yuzde",
    "swap_total_bytes": "bayt", "swap_used_bytes": "bayt", "swap_used_percent": "yuzde",
    "swap_in_pages_per_s": "sayfa/saniye", "swap_out_pages_per_s": "sayfa/saniye",
    "major_faults_per_s": "olay/saniye", "minor_faults_per_s": "olay/saniye",
    "disk_read_bytes_per_s": "bayt/saniye", "disk_write_bytes_per_s": "bayt/saniye",
    "disk_busy_percent": "yuzde", "disk_read_bytes_total": "bayt",
    "disk_write_bytes_total": "bayt", "psi_memory_some": "yuzde", "psi_memory_full": "yuzde",
    "psi_cpu_some": "yuzde", "psi_io_some": "yuzde", "procs_running": "adet",
    "procs_blocked": "adet",
}

_INT_FIELDS = {
    f.name for f in fields(SystemSample)
    if f.name in ("cpu_count", "mem_total_bytes", "mem_available_bytes",
                  "swap_total_bytes", "swap_used_bytes", "procs_running",
                  "procs_blocked", "disk_read_bytes_total", "disk_write_bytes_total")
}


def sample_to_dict(sample: SystemSample) -> Dict[str, Any]:
    """JSON'a uygun sözlük üretir."""
    data = asdict(sample)
    data["errors"] = list(sample.errors)
    for name in _PROCESS_LIST_FIELDS:
        data[name] = [asdict(p) for p in getattr(sample, name)]
    return data


def _coerce_number(name: str, value: Any) -> Any:
    if value is None or value == "":
        return None
    if name in _INT_FIELDS:
        return int(float(value))
    return float(value)


def sample_from_dict(data: Mapping[str, Any]) -> SystemSample:
    """sample_to_dict veya CSV satırından SystemSample oluşturur.

    Bilinmeyen anahtarlar yok sayılır (ileri uyumluluk); eksik alanlar None olur.
    """
    if "timestamp" not in data:
        raise ValueError("örnekte 'timestamp' alanı yok")
    kwargs: Dict[str, Any] = {}
    for name in SAMPLE_METRIC_FIELDS:
        if name in data:
            kwargs[name] = _coerce_number(name, data[name])
    if kwargs.get("timestamp") is None:
        raise ValueError("örnekte geçerli 'timestamp' yok")
    for name in _PROCESS_LIST_FIELDS:
        items = data.get(name) or []
        kwargs[name] = tuple(
            ProcessBrief(
                pid=int(p["pid"]),
                name=str(p.get("name", "?")),
                cpu_percent=_opt_float(p.get("cpu_percent")),
                rss_bytes=_opt_int(p.get("rss_bytes")),
                io_bytes_per_s=_opt_float(p.get("io_bytes_per_s")),
            )
            for p in items
        )
    errors = data.get("errors") or ()
    if isinstance(errors, str):
        errors = tuple(e for e in errors.split(" | ") if e)
    kwargs["errors"] = tuple(str(e) for e in errors)
    return SystemSample(**kwargs)


def _opt_float(v: Any) -> Optional[float]:
    return None if v is None else float(v)


def _opt_int(v: Any) -> Optional[int]:
    return None if v is None else int(v)


# ---------------------------------------------------------------------------
# Uyarılar
# ---------------------------------------------------------------------------

SEVERITY_INFO = "info"
SEVERITY_WARNING = "warning"
SEVERITY_CRITICAL = "critical"

SEVERITY_LABELS = {
    SEVERITY_INFO: "Gözlem",
    SEVERITY_WARNING: "Uyarı",
    SEVERITY_CRITICAL: "Kritik olasılık",
}

SEVERITY_ORDER = {SEVERITY_INFO: 0, SEVERITY_WARNING: 1, SEVERITY_CRITICAL: 2}


@dataclass(frozen=True)
class Evidence:
    """Bir uyarıyı destekleyen (veya desteklemeyen) tek ölçüt."""

    metric: str
    label: str
    value: Optional[float]
    threshold: Optional[float]
    comparison: str  # "<", ">=", ...
    unit: str
    window_start: float
    window_end: float
    satisfied: bool
    note: str = ""
    role: str = "trigger"  # "trigger" (ana koşul) | "support" (destekleyici) | "context" (bağlam)


ROLE_LABELS = {"trigger": "Ana koşul", "support": "Destekleyici", "context": "Bağlam"}


@dataclass(frozen=True)
class RuleStatus:
    """Bir kuralın son değerlendirme durumu (arayüzde 'neden tetiklenmedi' bilgisi)."""

    rule_id: str
    title: str
    triggered: bool
    reason: str
    evaluated_at: float


@dataclass(frozen=True)
class Alert:
    """Kural motorunun ürettiği açıklamalı uyarı."""

    alert_id: str
    rule_id: str
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
    first_seen: float
    last_seen: float
    resolved_at: Optional[float] = None

    @property
    def active(self) -> bool:
        return self.resolved_at is None

    @property
    def severity_label(self) -> str:
        return SEVERITY_LABELS.get(self.severity, self.severity)


def alert_to_dict(alert: Alert) -> Dict[str, Any]:
    data = asdict(alert)
    data["evidence"] = [asdict(e) for e in alert.evidence]
    data["context"] = list(alert.context)
    data["suggestions"] = list(alert.suggestions)
    data["active"] = alert.active
    return data


def alert_from_dict(data: Mapping[str, Any]) -> Alert:
    evidence = tuple(
        Evidence(
            metric=str(e["metric"]),
            label=str(e.get("label", e["metric"])),
            value=_opt_float(e.get("value")),
            threshold=_opt_float(e.get("threshold")),
            comparison=str(e.get("comparison", "")),
            unit=str(e.get("unit", "")),
            window_start=float(e["window_start"]),
            window_end=float(e["window_end"]),
            satisfied=bool(e.get("satisfied", False)),
            note=str(e.get("note", "")),
            role=str(e.get("role", "trigger")),
        )
        for e in data.get("evidence", [])
    )
    return Alert(
        alert_id=str(data["alert_id"]),
        rule_id=str(data["rule_id"]),
        title=str(data["title"]),
        severity=str(data["severity"]),
        confidence=str(data.get("confidence", "")),
        summary=str(data.get("summary", "")),
        window_start=float(data["window_start"]),
        window_end=float(data["window_end"]),
        evidence=evidence,
        context=tuple(str(c) for c in data.get("context", [])),
        uncertainty=str(data.get("uncertainty", "")),
        suggestions=tuple(str(s) for s in data.get("suggestions", [])),
        first_seen=float(data["first_seen"]),
        last_seen=float(data["last_seen"]),
        resolved_at=_opt_float(data.get("resolved_at")),
    )


@dataclass(frozen=True)
class EngineUpdate:
    """Kural motorunun tek değerlendirme sonucunda değişenler."""

    new: Tuple[Alert, ...] = ()
    resolved: Tuple[Alert, ...] = ()
    active: Tuple[Alert, ...] = ()
    errors: Tuple[str, ...] = ()
    statuses: Tuple[RuleStatus, ...] = ()


@dataclass(frozen=True)
class TickResult:
    """İzleme servisinin bir örnekleme turunun çıktısı (GUI'ye iletilir)."""

    sample: Optional[SystemSample]
    processes: Optional[ProcessSnapshot]
    update: EngineUpdate
    alert_log: Tuple[Alert, ...]
    history_len: int
    duration_s: float
    errors: Tuple[str, ...] = field(default_factory=tuple)
