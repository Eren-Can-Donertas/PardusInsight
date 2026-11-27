"""CSV dışa aktarma ve geri okuma.

Örnek dosyası: her satır bir ölçüm; sütun adları SystemSample alanlarıdır
(docs/RAPOR_FORMATI.md). Sayılar nokta ondalık ayırıcıyla yazılır, böylece
LibreOffice Calc ve Python tarafından kayıpsız okunabilir.
"""
from __future__ import annotations

import csv
from typing import Dict, List, Sequence

from ..analysis.explain import evidence_line
from ..core.formatting import fmt_iso
from ..core.models import (SAMPLE_METRIC_FIELDS, Alert, SystemSample, sample_from_dict)
from .atomic import atomic_write

#: Son sütun verinin kaynağıdır: "linux" (gerçek ölçüm), "synthetic:<senaryo>" (demo) vb.
SAMPLE_COLUMNS: List[str] = ["time_iso", *SAMPLE_METRIC_FIELDS, "errors", "data_source"]
ALERT_COLUMNS: List[str] = [
    "alert_id", "rule_id", "title", "severity", "severity_label", "confidence", "active",
    "first_seen_iso", "last_seen_iso", "resolved_at_iso", "window_start_iso",
    "window_end_iso", "summary", "evidence", "context", "uncertainty",
]


def _cell(value: object) -> object:
    return "" if value is None else value


def write_samples_csv(path: str, samples: Sequence[SystemSample],
                      data_source: str = "unknown") -> int:
    """Örnekleri yazar ve yazılan satır sayısını döndürür.

    Her satıra veri kaynağı yazılır; sentetik (demo) veri gerçek ölçümle karıştırılamaz.
    """
    with atomic_write(path) as handle:
        writer = csv.writer(handle)
        writer.writerow(SAMPLE_COLUMNS)
        for sample in samples:
            row: List[object] = [fmt_iso(sample.timestamp)]
            row.extend(_cell(getattr(sample, name)) for name in SAMPLE_METRIC_FIELDS)
            row.append(" | ".join(sample.errors))
            row.append(data_source)
            writer.writerow(row)
    return len(samples)


def read_samples_csv(path: str) -> List[SystemSample]:
    with open(path, "r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = {"timestamp"} - set(reader.fieldnames or [])
        if missing:
            raise ValueError("CSV dosyası PardusInsight örnek biçiminde değil "
                             "('timestamp' sütunu yok)")
        return [sample_from_dict(row) for row in reader]


def _evidence_text(alert: Alert) -> str:
    return " ; ".join(evidence_line(e) for e in alert.evidence)


def write_alerts_csv(path: str, alerts: Sequence[Alert]) -> int:
    with atomic_write(path) as handle:
        writer = csv.writer(handle)
        writer.writerow(ALERT_COLUMNS)
        for a in alerts:
            writer.writerow([
                a.alert_id, a.rule_id, a.title, a.severity, a.severity_label, a.confidence,
                "evet" if a.active else "hayır", fmt_iso(a.first_seen), fmt_iso(a.last_seen),
                fmt_iso(a.resolved_at), fmt_iso(a.window_start), fmt_iso(a.window_end),
                a.summary, _evidence_text(a), " ; ".join(a.context), a.uncertainty,
            ])
    return len(alerts)


def read_alerts_csv(path: str) -> List[Dict[str, str]]:
    with open(path, "r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))
