"""Örnekleme ve kural eşikleri ayar penceresi (yalnızca uygulama içi ayarlar)."""
from __future__ import annotations

from dataclasses import replace
from typing import Any, Dict, Optional, Tuple

from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout,
                               QGroupBox, QLabel, QMessageBox, QSpinBox, QVBoxLayout, QWidget)

from ..config import AnalysisSettings, AppSettings

# alan adı -> (etiket, min, max, adım, ondalık, sonek)
ANALYSIS_FIELDS: Dict[str, Tuple[str, float, float, float, int, str]] = {
    "window_s": ("Analiz penceresi", 10, 600, 5, 0, " sn"),
    "consecutive_windows": ("Ardışık pencere sayısı", 1, 10, 1, 0, ""),
    "mem_available_warn_pct": ("Kullanılabilir bellek uyarı eşiği", 1, 50, 0.5, 1, " %"),
    "mem_available_crit_pct": ("Kullanılabilir bellek kritik eşiği", 0.5, 50, 0.5, 1, " %"),
    "swap_activity_pages_s": ("Swap etkinliği eşiği", 1, 100000, 10, 0, " sayfa/sn"),
    "major_faults_s": ("Major page-fault eşiği", 1, 100000, 10, 0, " /sn"),
    "psi_memory_some_pct": ("PSI bellek eşiği", 0.5, 100, 0.5, 1, " %"),
    "cpu_high_pct": ("Yüksek CPU eşiği", 10, 100, 1, 0, " %"),
    "cpu_min_fraction": ("Eşik üstü örnek oranı", 0.1, 1.0, 0.05, 2, ""),
    "disk_ratio": ("Disk artış katsayısı", 1.1, 100, 0.5, 1, " ×"),
    "disk_min_throughput_mib_s": ("Disk mutlak alt sınır", 0.5, 10000, 0.5, 1, " MiB/sn"),
    "disk_busy_pct": ("Disk meşguliyet eşiği", 5, 100, 1, 0, " %"),
}


class SettingsDialog(QDialog):
    def __init__(self, settings: AppSettings, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Ayarlar")
        self._settings = settings
        self._spins: Dict[str, QDoubleSpinBox] = {}

        sampling = QGroupBox("Örnekleme")
        form1 = QFormLayout(sampling)
        self.interval = QDoubleSpinBox()
        self.interval.setRange(0.5, 10.0)
        self.interval.setSingleStep(0.5)
        self.interval.setDecimals(1)
        self.interval.setSuffix(" sn")
        self.interval.setValue(settings.sample_interval_s)
        form1.addRow("Örnekleme aralığı", self.interval)
        self.process_every = QSpinBox()
        self.process_every.setRange(1, 10)
        self.process_every.setValue(settings.process_every)
        self.process_every.setToolTip("Yük azaltmak için süreç listesini her N örnekte bir topla")
        form1.addRow("Süreç listesi sıklığı (her N örnekte)", self.process_every)

        rules = QGroupBox("Kural eşikleri")
        form2 = QFormLayout(rules)
        for name, (label, lo, hi, step, decimals, suffix) in ANALYSIS_FIELDS.items():
            spin = QDoubleSpinBox()
            spin.setRange(lo, hi)
            spin.setSingleStep(step)
            spin.setDecimals(decimals)
            spin.setSuffix(suffix)
            spin.setValue(float(getattr(settings.analysis, name)))
            form2.addRow(label, spin)
            self._spins[name] = spin

        note = QLabel("Ayarlar yalnızca bu oturum için uygulanır; hiçbir sistem ayarı "
                      "değiştirilmez. Eşikler hedef Pardus ortamında kalibre edilmelidir.")
        note.setWordWrap(True)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel
                                   | QDialogButtonBox.StandardButton.RestoreDefaults)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.StandardButton.RestoreDefaults).clicked.connect(
            self._defaults)
        layout = QVBoxLayout(self)
        layout.addWidget(sampling)
        layout.addWidget(rules)
        layout.addWidget(note)
        layout.addWidget(buttons)
        self.result_settings: Optional[AppSettings] = None

    def _defaults(self) -> None:
        defaults = AnalysisSettings()
        self.interval.setValue(2.0)
        self.process_every.setValue(1)
        for name, spin in self._spins.items():
            spin.setValue(float(getattr(defaults, name)))

    def build_settings(self) -> AppSettings:
        values: Dict[str, Any] = {name: spin.value() for name, spin in self._spins.items()}
        values["consecutive_windows"] = int(values["consecutive_windows"])
        analysis = replace(self._settings.analysis, **values)
        settings = replace(self._settings, process_every=self.process_every.value(),
                           analysis=analysis)
        return settings.with_interval(self.interval.value()).validate()

    def _accept(self) -> None:
        try:
            self.result_settings = self.build_settings()
        except ValueError as exc:
            QMessageBox.warning(self, "Geçersiz ayar", str(exc))
            return
        self.accept()
