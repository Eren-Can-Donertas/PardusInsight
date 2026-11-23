"""JSON raporu: meta veri, ayarlar, özet istatistikler, uyarılar ve örnekler.

Aynı biçim "kayıt yeniden analizi" için de okunur (scenarios/ klasöründeki
önceden kaydedilmiş sentetik senaryolar bu biçimdedir). Raporda kullanıcı adı
veya makine adı bulunmaz.
"""
from __future__ import annotations

import json
import platform
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence

from .. import APP_NAME, __version__
from ..analysis.windows import mean
from ..core.formatting import fmt_iso
from ..core.models import (Alert, SystemSample, alert_from_dict, alert_to_dict,
                           sample_from_dict, sample_to_dict)
from .atomic import atomic_write

REPORT_SCHEMA = "pardusinsight.report"
REPORT_SCHEMA_VERSION = 1

SUMMARY_METRICS = (
    "cpu_percent", "mem_used_percent", "mem_available_percent", "swap_used_percent",
    "swap_in_pages_per_s", "swap_out_pages_per_s", "major_faults_per_s",
    "disk_read_bytes_per_s", "disk_write_bytes_per_s", "disk_busy_percent", "load1",
)


class ReportError(ValueError):
    """Rapor dosyası okunamadı veya biçimi geçersiz."""


@dataclass
class ReportData:
    samples: List[SystemSample]
    alerts: List[Alert]
    settings: Dict[str, Any] = field(default_factory=dict)
    meta: Dict[str, Any] = field(default_factory=dict)


def _os_pretty_name() -> Optional[str]:
    try:
        with open("/etc/os-release", "r", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("PRETTY_NAME="):
                    return line.split("=", 1)[1].strip().strip('"')
    except OSError:
        return None
    return None


def system_info() -> Dict[str, Any]:
    return {
        "os": _os_pretty_name(),
        "kernel": platform.release(),
        "machine": platform.machine(),
        "python": platform.python_version(),
    }


def summarize(samples: Sequence[SystemSample]) -> Dict[str, Any]:
    metrics: Dict[str, Any] = {}
    for name in SUMMARY_METRICS:
        values = [float(v) for v in (getattr(s, name) for s in samples) if v is not None]
        if values:
            metrics[name] = {"min": round(min(values), 2), "mean": round(mean(values) or 0, 2),
                             "max": round(max(values), 2), "count": len(values)}
    return {
        "sample_count": len(samples),
        "start": fmt_iso(samples[0].timestamp) if samples else None,
        "end": fmt_iso(samples[-1].timestamp) if samples else None,
        "duration_s": round(samples[-1].timestamp - samples[0].timestamp, 1) if samples else 0,
        "metrics": metrics,
    }


def build_report(samples: Sequence[SystemSample], alerts: Sequence[Alert],
                 settings: Optional[Mapping[str, Any]] = None, source: str = "unknown",
                 include_system_info: bool = True) -> Dict[str, Any]:
    by_rule: Dict[str, int] = {}
    for a in alerts:
        by_rule[a.rule_id] = by_rule.get(a.rule_id, 0) + 1
    summary = summarize(samples)
    summary["alert_count"] = len(alerts)
    summary["alerts_by_rule"] = by_rule
    now = time.time()
    return {
        "schema": REPORT_SCHEMA,
        "schema_version": REPORT_SCHEMA_VERSION,
        "generator": {"name": APP_NAME, "version": __version__},
        "created_at": fmt_iso(now),
        "created_at_epoch": round(now, 3),
        "source": source,
        "system": system_info() if include_system_info else {},
        "settings": dict(settings or {}),
        "summary": summary,
        "alerts": [alert_to_dict(a) for a in alerts],
        "samples": [sample_to_dict(s) for s in samples],
    }


def write_json_report(path: str, report: Mapping[str, Any], compact: bool = False) -> None:
    with atomic_write(path, newline="\n") as handle:
        if compact:
            json.dump(report, handle, ensure_ascii=False, separators=(",", ":"))
        else:
            json.dump(report, handle, ensure_ascii=False, indent=1)
        handle.write("\n")


def load_json_report(path: str) -> ReportData:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except OSError as exc:
        raise ReportError(f"Dosya okunamadı: {exc.strerror or exc}") from exc
    except json.JSONDecodeError as exc:
        raise ReportError(f"Geçersiz JSON (satır {exc.lineno}): {exc.msg}") from exc
    if not isinstance(data, dict) or data.get("schema") != REPORT_SCHEMA:
        raise ReportError("Bu dosya bir PardusInsight raporu değil.")
    version = data.get("schema_version")
    if not isinstance(version, int) or version > REPORT_SCHEMA_VERSION:
        raise ReportError(f"Desteklenmeyen rapor sürümü: {version!r}")
    try:
        samples = [sample_from_dict(s) for s in data.get("samples", [])]
        alerts = [alert_from_dict(a) for a in data.get("alerts", [])]
    except (KeyError, TypeError, ValueError) as exc:
        raise ReportError(f"Rapor içeriği bozuk: {exc}") from exc
    samples.sort(key=lambda s: s.timestamp)
    meta = {k: v for k, v in data.items() if k not in ("samples", "alerts", "settings")}
    return ReportData(samples=samples, alerts=alerts, settings=dict(data.get("settings") or {}),
                      meta=meta)
