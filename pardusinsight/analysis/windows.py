"""Zaman penceresi yardımcıları.

Değerlendirme dönemi, en yeni örnekten geriye doğru eşit uzunlukta ve
birbirini izleyen pencerelere bölünür. Bir kuralın tetiklenmesi için koşulun
her pencerede ayrı ayrı sağlanması gerekir; tek bir ani sıçrama böylece
uyarı üretmez.
"""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import Callable, List, Optional, Sequence, Tuple, Union

from ..core.models import SystemSample

Getter = Union[str, Callable[[SystemSample], Optional[float]]]


@dataclass(frozen=True)
class Window:
    start: float  # hariç
    end: float  # dahil
    samples: Tuple[SystemSample, ...]

    def values(self, getter: Getter) -> List[float]:
        return values_of(self.samples, getter)


def values_of(samples: Sequence[SystemSample], getter: Getter) -> List[float]:
    out: List[float] = []
    for sample in samples:
        value = getattr(sample, getter) if isinstance(getter, str) else getter(sample)
        if value is not None:
            out.append(float(value))
    return out


def split_windows(samples: Sequence[SystemSample], end: float, window_s: float,
                  count: int) -> List[Window]:
    """(end - (k+1)·w, end - k·w] aralıklarını eskiden yeniye sıralı döndürür."""
    windows: List[Window] = []
    for k in range(count - 1, -1, -1):
        w_end = end - k * window_s
        w_start = w_end - window_s
        windows.append(Window(w_start, w_end, tuple(
            s for s in samples if w_start < s.timestamp <= w_end + 1e-9)))
    return windows


def min_valid_samples(window_s: float, interval_s: float, coverage: float) -> int:
    expected = window_s / interval_s
    return max(2, int(math.ceil(expected * coverage - 1e-9)))


def mean(values: Sequence[float]) -> Optional[float]:
    return statistics.fmean(values) if values else None


def median(values: Sequence[float]) -> Optional[float]:
    return statistics.median(values) if values else None


def fraction_at_least(values: Sequence[float], threshold: float) -> Optional[float]:
    if not values:
        return None
    return sum(1 for v in values if v >= threshold) / len(values)
