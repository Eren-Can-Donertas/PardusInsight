"""GUI başlatıcı."""
from __future__ import annotations

import sys
from typing import Optional

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from .. import APP_NAME
from ..config import AppSettings
from ..core.service import (MonitorService, RecordingSource, build_live_service,
                            build_synthetic_service)
from .main_window import MainWindow


def run_gui(settings: AppSettings, synthetic: Optional[str] = None,
            replay: Optional[str] = None, speed: float = 1.0, seed: int = 461) -> int:
    existing = QApplication.instance()
    app = existing if isinstance(existing, QApplication) else QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    can_sample = True
    if synthetic:
        service: MonitorService = build_synthetic_service(synthetic, settings, seed=seed)
        mode = f"Sentetik veri: {synthetic}" + (f" (×{speed:g} hız)" if speed != 1 else "")
    elif sys.platform.startswith("linux"):
        service = build_live_service(settings)
        mode = "Canlı izleme (/proc + psutil)"
        if service.process_source is None:
            mode += " — psutil yok, süreç listesi kapalı"
    else:
        service = MonitorService(RecordingSource("yok"), None, settings)
        mode = "Canlı izleme bu platformda yok — kayıt açın veya --synthetic kullanın"
        can_sample = False
    window = MainWindow(service, mode, speed=speed if synthetic else 1.0,
                        can_sample=can_sample and not replay)
    window.show()
    if replay:
        window.can_sample = can_sample
        QTimer.singleShot(0, lambda: window.open_recording(replay))
    elif not can_sample:
        QMessageBox.information(window, APP_NAME, mode)
    code = app.exec()
    window.shutdown()
    return code
