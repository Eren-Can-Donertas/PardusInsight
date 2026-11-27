"""Arka plan örnekleyicisi: MonitorService.tick() çağrılarını ayrı QThread'de yapar.

Zamanlayıcı worker iş parçacığında yaşar; bir tur uzun sürerse turlar üst
üste binmez, yalnızca gecikir. GUI iş parçacığı hiçbir zaman /proc okumaz
veya süreç taraması yapmaz.
"""
from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from ..config import AppSettings
from ..core.models import SystemSample
from ..core.service import MonitorService


class SamplerWorker(QObject):
    tick_ready = Signal(object)  # TickResult
    recording_loaded = Signal(object, str)  # TickResult, etiket
    failed = Signal(str)

    def __init__(self, service: MonitorService, interval_ms: int) -> None:
        super().__init__()
        self.service = service
        self._interval_ms = max(int(interval_ms), 50)
        self._timer: Optional[QTimer] = None

    @Slot()
    def start(self) -> None:
        if self._timer is None:
            self._timer = QTimer(self)
            self._timer.timeout.connect(self.sample_once)
        self._timer.start(self._interval_ms)
        self.sample_once()

    @Slot()
    def stop(self) -> None:
        if self._timer is not None:
            self._timer.stop()

    @Slot(int)
    def set_interval_ms(self, interval_ms: int) -> None:
        self._interval_ms = max(int(interval_ms), 50)
        if self._timer is not None and self._timer.isActive():
            self._timer.setInterval(self._interval_ms)

    @Slot(object)
    def apply_settings(self, settings: AppSettings) -> None:
        try:
            result = self.service.apply_settings(settings)
        except Exception as exc:
            self.failed.emit(f"Ayarlar uygulanamadı: {exc}")
            return
        if result is not None:  # kayıt analizi yeni eşiklerle yeniden çalıştı
            self.tick_ready.emit(result)

    @Slot(object, str, str)
    def load_recording(self, samples: List[SystemSample], label: str, source: str) -> None:
        self.stop()
        try:
            result = self.service.load_recording(samples, source)
        except Exception as exc:
            self.failed.emit(f"Kayıt analiz edilemedi: {type(exc).__name__}: {exc}")
            return
        self.recording_loaded.emit(result, label)

    @Slot()
    def resume_live(self) -> None:
        self.service.reset_live()
        self.start()

    @Slot()
    def sample_once(self) -> None:
        try:
            result = self.service.tick()  # tick() istisna fırlatmamak üzere tasarlandı
        except Exception as exc:  # yine de son savunma hattı
            self.failed.emit(f"Örnekleme hatası: {type(exc).__name__}: {exc}")
            return
        self.tick_ready.emit(result)
