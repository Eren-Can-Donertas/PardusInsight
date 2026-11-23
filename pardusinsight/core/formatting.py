"""Türkçe sayı, bayt ve zaman biçimlendirme yardımcıları (Qt'den bağımsız)."""
from __future__ import annotations

import time
from typing import Optional

NA = "—"


def tr_num(value: float, digits: int = 1) -> str:
    """Ondalık ayırıcı olarak virgül kullanır: 12.5 -> '12,5'."""
    return f"{value:.{digits}f}".replace(".", ",")


def fmt_pct(value: Optional[float], digits: int = 1) -> str:
    return NA if value is None else f"%{tr_num(value, digits)}"


def fmt_bytes(value: Optional[float]) -> str:
    if value is None:
        return NA
    size = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if abs(size) < 1024.0 or unit == "TiB":
            digits = 0 if unit == "B" else 1
            return f"{tr_num(size, digits)} {unit}"
        size /= 1024.0
    return NA  # pragma: no cover


def fmt_rate(value: Optional[float]) -> str:
    return NA if value is None else f"{fmt_bytes(value)}/sn"


def fmt_time(ts: Optional[float]) -> str:
    return NA if ts is None else time.strftime("%H:%M:%S", time.localtime(ts))


def fmt_datetime(ts: Optional[float]) -> str:
    return NA if ts is None else time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))


def fmt_iso(ts: Optional[float]) -> str:
    if ts is None:
        return ""
    return time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(ts))


def fmt_duration(seconds: float) -> str:
    seconds = int(round(max(seconds, 0)))
    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours} sa {minutes} dk"
    if minutes:
        return f"{minutes} dk {sec} sn" if sec else f"{minutes} dk"
    return f"{sec} sn"


def fmt_span(start: float, end: float) -> str:
    return f"{fmt_time(start)}–{fmt_time(end)} ({fmt_duration(end - start)})"


def fmt_value(value: Optional[float], unit: str) -> str:
    """Kanıt değerlerini birimine göre biçimlendirir."""
    if value is None:
        return "ölçülemedi"
    if unit == "%":
        return fmt_pct(value)
    if unit == "B/sn":
        return fmt_rate(value)
    if unit == "B":
        return fmt_bytes(value)
    if unit == "oran":
        return tr_num(value, 2)
    return f"{tr_num(value, 1)} {unit}".strip()
