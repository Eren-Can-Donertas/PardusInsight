"""Uyarıların insan tarafından okunabilir metin/HTML açıklamaları (Qt'den bağımsız)."""
from __future__ import annotations

from html import escape
from typing import List

from ..core.formatting import fmt_datetime, fmt_span, fmt_time, fmt_value
from ..core.models import ROLE_LABELS, Alert, Evidence


_COMPARISON_SYMBOLS = {">=": "≥", "<=": "≤"}


def comparison_symbol(op: str) -> str:
    return _COMPARISON_SYMBOLS.get(op, op)


def evidence_line(e: Evidence) -> str:
    if e.role == "context":
        mark = "•"
    else:
        mark = "✓" if e.satisfied else "✗"
    threshold = (f" (eşik {comparison_symbol(e.comparison)} {fmt_value(e.threshold, e.unit)})"
                 if e.threshold is not None else "")
    span = f" [{fmt_time(e.window_start)}–{fmt_time(e.window_end)}]"
    note = f" — {e.note}" if e.note else ""
    return f"{mark} {e.label}: {fmt_value(e.value, e.unit)}{threshold}{span}{note}"


def alert_to_text(alert: Alert) -> str:
    status = "AKTİF" if alert.active else f"çözüldü {fmt_time(alert.resolved_at)}"
    lines: List[str] = [
        f"[{alert.severity_label}] {alert.title} ({status}, güven: {alert.confidence})",
        f"  Zaman aralığı: {fmt_span(alert.window_start, alert.window_end)}",
        f"  {alert.summary}",
        "  Tetikleyici ve destekleyici metrikler:",
    ]
    lines += [f"    {evidence_line(e)}" for e in alert.evidence]
    if alert.context:
        lines.append("  Bağlam (en yoğun süreçler):")
        lines += [f"    - {c}" for c in alert.context]
    lines.append(f"  Belirsizlik: {alert.uncertainty}")
    return "\n".join(lines)


def alert_to_html(alert: Alert) -> str:
    status = ("<b>Aktif</b>" if alert.active
              else f"Çözüldü ({escape(fmt_datetime(alert.resolved_at))})")
    rows = []
    for e in alert.evidence:
        if e.role == "context":
            mark, color = "•", "#777777"
        elif e.satisfied:
            mark, color = "✓", "#2e7d32"
        else:
            mark, color = "✗", "#c62828"
        threshold = ("" if e.threshold is None else
                     f"{escape(comparison_symbol(e.comparison))} "
                     f"{escape(fmt_value(e.threshold, e.unit))}")
        note = f"<br><small>{escape(e.note)}</small>" if e.note else ""
        rows.append(
            f"<tr><td style='color:{color}'>{mark}</td>"
            f"<td>{escape(ROLE_LABELS.get(e.role, e.role))}</td>"
            f"<td>{escape(e.label)}{note}</td>"
            f"<td align='right'>{escape(fmt_value(e.value, e.unit))}</td>"
            f"<td>{threshold}</td>"
            f"<td>{escape(fmt_time(e.window_start))}–{escape(fmt_time(e.window_end))}</td></tr>")
    context = "".join(f"<li>{escape(c)}</li>" for c in alert.context) or "<li>—</li>"
    suggestions = "".join(f"<li>{escape(s)}</li>" for s in alert.suggestions)
    return (
        f"<h3>{escape(alert.title)}</h3>"
        f"<p><b>Önem:</b> {escape(alert.severity_label)} &nbsp; <b>Güven:</b> "
        f"{escape(alert.confidence)} &nbsp; <b>Durum:</b> {status}</p>"
        f"<p><b>Zaman aralığı:</b> {escape(fmt_span(alert.window_start, alert.window_end))}"
        f"<br><b>İlk görülme:</b> {escape(fmt_datetime(alert.first_seen))} &nbsp; "
        f"<b>Son görülme:</b> {escape(fmt_datetime(alert.last_seen))}</p>"
        f"<p>{escape(alert.summary)}</p>"
        "<h4>Tetikleyici metrikler ve kanıtlar</h4>"
        "<table border='0' cellspacing='2' cellpadding='3'>"
        "<tr><th></th><th align='left'>Rol</th><th align='left'>Metrik</th>"
        "<th align='right'>Değer</th><th align='left'>Eşik</th>"
        "<th align='left'>Pencere</th></tr>"
        + "".join(rows) + "</table>"
        f"<h4>Bağlam</h4><ul>{context}</ul>"
        f"<h4>Belirsizlik ve sınırlılıklar</h4><p>{escape(alert.uncertainty)}</p>"
        f"<h4>Öneriler (salt-okunur)</h4><ul>{suggestions}</ul>"
    )
