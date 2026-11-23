"""Qt'den bağımsız izleme servisi: topla -> normalize et -> tampona ekle -> analiz et.

GUI bu sınıfı arka plan iş parçacığında çağırır; komut satırı modu ve
testler doğrudan kullanır. ``tick()`` hiçbir koşulda istisna fırlatmaz.
"""
from __future__ import annotations

import os
import time
from typing import Any, List, Optional, Protocol, Sequence

from ..analysis.engine import RuleEngine
from ..config import AppSettings
from .history import HistoryBuffer
from .models import EngineUpdate, ProcessSnapshot, RawSnapshot, SystemSample, TickResult
from .normalize import Normalizer


class MetricSource(Protocol):
    source_name: str

    def collect(self) -> RawSnapshot: ...


class ProcessSource(Protocol):
    def collect(self) -> ProcessSnapshot: ...


class RecordingSource:
    """Kayıt analizi modunda kullanılan kaynak: canlı ölçüm üretmez."""

    def __init__(self, label: str) -> None:
        self.source_name = f"replay:{label}"

    def collect(self) -> RawSnapshot:
        raise RuntimeError("Kayıt analizi modunda canlı ölçüm alınmaz")


class MonitorService:
    def __init__(self, source: MetricSource, process_source: Optional[ProcessSource] = None,
                 settings: Optional[AppSettings] = None) -> None:
        self.settings = (settings or AppSettings()).validate()
        self.source = source
        self.process_source = process_source
        self.normalizer = Normalizer(top_n=self.settings.top_n)
        self.history = self._new_history(self.settings)
        self.engine = RuleEngine(self.settings.analysis)
        self._tick_count = 0
        self._last_processes: Optional[ProcessSnapshot] = None
        self.replay_mode = False

    @staticmethod
    def _new_history(settings: AppSettings) -> HistoryBuffer:
        # Kapasite en kısa aralığa göre: 1 sn veya ayarlanan daha kısa aralık
        return HistoryBuffer(max_age_s=settings.history_minutes * 60.0,
                             min_interval_s=min(settings.sample_interval_s, 1.0))

    @property
    def source_name(self) -> str:
        return getattr(self.source, "source_name", "unknown")

    def apply_settings(self, settings: AppSettings) -> None:
        """Örnekleme aralığı ve analiz eşiklerini değiştirir (geçmiş korunur)."""
        settings.validate()
        new_history = self._new_history(settings)
        if (new_history.capacity != self.history.capacity
                or new_history.max_age_s != self.history.max_age_s):
            new_history.extend(self.history.snapshot())
            self.history = new_history
        if hasattr(self.source, "step_s"):  # sentetik kaynakta simülasyon adımı
            self.source.step_s = settings.sample_interval_s  # type: ignore[attr-defined]
        self.settings = settings
        self.engine.update_settings(settings.analysis)

    def tick(self) -> TickResult:
        started = time.perf_counter()
        errors: List[str] = []
        processes: Optional[ProcessSnapshot] = None
        sample: Optional[SystemSample] = None
        update = EngineUpdate()
        try:
            raw = self.source.collect()
        except Exception as exc:  # kaynak tamamen başarısız: örnek atlanır
            errors.append(f"Ölçüm alınamadı ({type(exc).__name__}: {exc})")
            raw = None
        if raw is not None:
            if self.process_source is not None:
                if self._tick_count % self.settings.process_every == 0:
                    try:
                        processes = self.process_source.collect()
                    except Exception as exc:
                        errors.append(f"Süreç listesi alınamadı ({type(exc).__name__})")
                    else:
                        self._last_processes = processes
                else:
                    processes = self._last_processes
            try:
                sample = self.normalizer.update(raw, processes)
                self.history.append(sample)
                errors.extend(sample.errors)
            except Exception as exc:
                errors.append(f"Normalizasyon hatası ({type(exc).__name__}: {exc})")
            try:
                update = self.engine.evaluate(self.history.snapshot())
                errors.extend(update.errors)
            except Exception as exc:
                errors.append(f"Analiz hatası ({type(exc).__name__}: {exc})")
        self._tick_count += 1
        return TickResult(sample=sample, processes=processes, update=update,
                          alert_log=self.engine.alert_log(), history_len=len(self.history),
                          duration_s=time.perf_counter() - started, errors=tuple(errors))

    def reset_live(self) -> None:
        """Kayıt analizinden canlı izlemeye döner: geçmiş ve uyarılar sıfırlanır."""
        self.history = self._new_history(self.settings)
        self.engine = RuleEngine(self.settings.analysis)
        self.normalizer.reset()
        self._last_processes = None
        self.replay_mode = False

    def load_recording(self, samples: Sequence[SystemSample]) -> TickResult:
        """Kaydedilmiş örnekleri geçmişe yükler ve kuralları baştan çalıştırır."""
        from ..analysis.engine import replay

        started = time.perf_counter()
        ordered = sorted(samples, key=lambda s: s.timestamp)
        engine = replay(ordered, self.settings.analysis)
        span = ordered[-1].timestamp - ordered[0].timestamp if ordered else 0.0
        minutes = max(self.settings.history_minutes, span / 60.0 + 1.0)
        self.history = HistoryBuffer(max_age_s=minutes * 60.0, min_interval_s=1.0)
        self.history.extend(ordered)
        self.engine = engine
        self.normalizer.reset()
        self.replay_mode = True
        return TickResult(sample=ordered[-1] if ordered else None, processes=None,
                          update=EngineUpdate(active=engine.active_alerts(),
                                              statuses=engine.statuses()),
                          alert_log=engine.alert_log(), history_len=len(self.history),
                          duration_s=time.perf_counter() - started)


class SelfUsageMonitor:
    """Uygulamanın kendi CPU ve bellek kullanımı (performans hedefi doğrulaması).

    CPU: os.times() farkı / duvar saati farkı (tek çekirdek = %100).
    RSS: Linux'ta /proc/self/status içindeki VmRSS; yoksa None.
    """

    def __init__(self, clock: Any = time.monotonic) -> None:
        self._clock = clock
        self._prev = self._read()

    def _read(self) -> tuple:
        t = os.times()
        return (self._clock(), t.user + t.system)

    def cpu_percent(self) -> Optional[float]:
        cur = self._read()
        dt = cur[0] - self._prev[0]
        used = cur[1] - self._prev[1]
        self._prev = cur
        if dt <= 0:
            return None
        return max(0.0, used / dt * 100.0)

    @staticmethod
    def rss_bytes() -> Optional[int]:
        try:
            with open("/proc/self/status", "r", encoding="ascii", errors="replace") as handle:
                for line in handle:
                    if line.startswith("VmRSS:"):
                        return int(line.split()[1]) * 1024
        except (OSError, ValueError, IndexError):
            return None
        return None


def build_live_service(settings: Optional[AppSettings] = None) -> MonitorService:
    """Canlı Linux kaynağıyla servis kurar. psutil yoksa süreç listesi devre dışıdır."""
    from ..collectors.processes import ProcessCollector
    from ..collectors.system import LinuxSystemCollector, load_psutil

    psutil_module = load_psutil()
    source = LinuxSystemCollector(psutil_module=psutil_module)
    processes = ProcessCollector(psutil_module) if psutil_module is not None else None
    return MonitorService(source, processes, settings)


def build_synthetic_service(scenario: str, settings: Optional[AppSettings] = None,
                            seed: int = 461, loop: bool = True,
                            start_time: Optional[float] = None) -> MonitorService:
    from ..collectors.synthetic import SyntheticProcessCollector, SyntheticSource

    settings = settings or AppSettings()
    source = SyntheticSource(scenario, seed=seed, step_s=settings.sample_interval_s,
                             loop=loop,
                             start_time=time.time() if start_time is None else start_time)
    return MonitorService(source, SyntheticProcessCollector(source), settings)
