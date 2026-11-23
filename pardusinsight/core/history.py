"""Sınırlı bellekli, iş parçacığı güvenli örnek geçmişi (ring buffer).

İki sınır birlikte uygulanır:
* Yaş sınırı: en yeni örnekten ``max_age_s`` saniyeden eski örnekler atılır
  (varsayılan 30 dakika).
* Sabit kapasite: ``deque(maxlen=...)`` örnekleme aralığı ne kadar kısalırsa
  kısalsın bellek kullanımının üst sınırını garanti eder.
"""
from __future__ import annotations

import bisect
import math
import threading
from collections import deque
from typing import Deque, Iterable, List, Optional

from .models import SystemSample

DEFAULT_MAX_AGE_S = 30 * 60.0


class HistoryBuffer:
    def __init__(self, max_age_s: float = DEFAULT_MAX_AGE_S,
                 min_interval_s: float = 1.0) -> None:
        if max_age_s <= 0:
            raise ValueError("max_age_s pozitif olmalı")
        if min_interval_s <= 0:
            raise ValueError("min_interval_s pozitif olmalı")
        self.max_age_s = float(max_age_s)
        self.capacity = int(math.ceil(max_age_s / min_interval_s)) + 1
        self._samples: Deque[SystemSample] = deque(maxlen=self.capacity)
        self._lock = threading.Lock()

    def append(self, sample: SystemSample) -> None:
        with self._lock:
            if self._samples and sample.timestamp < self._samples[-1].timestamp:
                # Zaman geriye gidemez (Normalizer monotonik zaman kullanır);
                # yine de olursa sıralamayı korumak için geçmiş sıfırlanır.
                self._samples.clear()
            self._samples.append(sample)
            cutoff = sample.timestamp - self.max_age_s
            while self._samples and self._samples[0].timestamp < cutoff:
                self._samples.popleft()

    def extend(self, samples: Iterable[SystemSample]) -> None:
        for sample in samples:
            self.append(sample)

    def clear(self) -> None:
        with self._lock:
            self._samples.clear()

    def snapshot(self) -> List[SystemSample]:
        """Tüm örneklerin kopyası (GUI iş parçacığı güvenle okuyabilir)."""
        with self._lock:
            return list(self._samples)

    def latest(self) -> Optional[SystemSample]:
        with self._lock:
            return self._samples[-1] if self._samples else None

    def last_seconds(self, seconds: float) -> List[SystemSample]:
        """En yeni örneğe göre son ``seconds`` saniyedeki örnekler (uçlar dahil)."""
        samples = self.snapshot()
        if not samples:
            return []
        return since(samples, samples[-1].timestamp - seconds)

    def duration_s(self) -> float:
        with self._lock:
            if len(self._samples) < 2:
                return 0.0
            return self._samples[-1].timestamp - self._samples[0].timestamp

    def __len__(self) -> int:
        with self._lock:
            return len(self._samples)


def since(samples: List[SystemSample], start: float) -> List[SystemSample]:
    """Zamana göre sıralı listede ``timestamp >= start`` olan kısım (ikili arama)."""
    keys = [s.timestamp for s in samples]
    return samples[bisect.bisect_left(keys, start):]
