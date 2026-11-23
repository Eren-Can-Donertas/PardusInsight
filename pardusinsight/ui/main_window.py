"""Ana pencere: özet kutucukları, geçmiş grafikleri, süreç tablosu, uyarılar ve günlük."""
from __future__ import annotations

import os
import time
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QMetaObject, QThread, Qt, Signal, Slot
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QMainWindow, QMessageBox,
                               QPlainTextEdit, QTableView, QTabWidget, QToolBar, QVBoxLayout,
                               QWidget)

from .. import APP_NAME, __version__
from ..config import settings_to_dict
from ..core.formatting import fmt_bytes, fmt_pct, fmt_rate, fmt_time, tr_num
from ..core.models import Alert, SystemSample, TickResult
from ..core.service import MonitorService, SelfUsageMonitor
from ..export import (ReportError, build_report, load_json_report, write_alerts_csv,
                      write_json_report, write_samples_csv)
from .alerts_view import SEVERITY_ICON, AlertsPanel
from .charts import SeriesSpec, Span, TimeSeriesChart
from .process_model import PID_ROLE, ProcessTableModel
from .settings_dialog import SettingsDialog
from .worker import SamplerWorker

MIB = 1024.0 * 1024.0
RANGES: List[Tuple[str, float]] = [("Son 1 dk", 60.0), ("Son 5 dk", 300.0),
                                   ("Son 15 dk", 900.0), ("Son 30 dk", 1800.0)]
RULE_CHARTS = {"sustained_cpu": ("cpu",), "memory_pressure": ("memory", "paging"),
               "disk_io_anomaly": ("disk",)}

ABOUT_HTML = f"""
<h3>{APP_NAME} {__version__}</h3>
<p>Pardus için salt-okunur sistem kaynağı izleme ve açıklanabilir darboğaz analizi.<br>
BİL461 İşletim Sistemleri dersi projesi.</p>
<p><b>Güvenlik sınırları</b></p>
<ul>
<li>Root yetkisi istemez; standart kullanıcıyla çalışır.</li>
<li>/proc ve /sys dosyalarını yalnızca okur; sistem ayarı değiştirmez.</li>
<li>Süreç sonlandırma, öncelik değiştirme, kernel modülü veya stres testi yoktur.</li>
<li>Ağ bağlantısı kurmaz; veri yalnızca kullanıcı "Dışa aktar" dediğinde yazılır.</li>
</ul>
<p><b>Uyarılar kesin tanı değildir</b>; her uyarı tetikleyici metrikleri, zaman aralığını ve
belirsizlikleri açıklar.</p>
<p><b>Üçüncü taraf bileşenler:</b> psutil (BSD-3-Clause), Qt for Python / PySide6 (LGPLv3),
Python (PSF License). Ayrıntılar: THIRD_PARTY_NOTICES.md</p>
"""


class SummaryTile(QFrame):
    def __init__(self, title: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.title = QLabel(title)
        self.value = QLabel("—")
        font = self.value.font()
        font.setPointSizeF(font.pointSizeF() * 1.7)
        font.setBold(True)
        self.value.setFont(font)
        self.detail = QLabel("")
        self.detail.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.addWidget(self.title)
        layout.addWidget(self.value)
        layout.addWidget(self.detail)
        self.setAccessibleName(title)

    def set(self, value: str, detail: str = "") -> None:
        self.value.setText(value)
        self.detail.setText(detail)


class MainWindow(QMainWindow):
    request_start = Signal()
    request_stop = Signal()
    request_interval = Signal(int)
    request_settings = Signal(object)
    request_recording = Signal(object, str)
    request_resume_live = Signal()

    def __init__(self, service: MonitorService, mode_label: str, speed: float = 1.0,
                 start_worker: bool = True, can_sample: bool = True) -> None:
        super().__init__()
        self.service = service
        self.mode_label = mode_label
        self.speed = speed if speed > 0 else 1.0
        self.can_sample = can_sample
        self.paused = False
        self.replay_label: Optional[str] = None
        self.last_result: Optional[TickResult] = None
        self._alert_log: Tuple[Alert, ...] = ()
        self._last_errors: Tuple[str, ...] = ()
        self._self_usage = SelfUsageMonitor()
        self.setWindowTitle(f"{APP_NAME} — {mode_label}")
        self.resize(1180, 780)
        self._build_ui()

        self.worker = SamplerWorker(service, self._interval_ms())
        self.worker.tick_ready.connect(self.apply_tick)
        self.worker.recording_loaded.connect(self.on_recording_loaded)
        self.worker.failed.connect(self._on_worker_failed)
        self.request_start.connect(self.worker.start)
        self.request_stop.connect(self.worker.stop)
        self.request_interval.connect(self.worker.set_interval_ms)
        self.request_settings.connect(self.worker.apply_settings)
        self.request_recording.connect(self.worker.load_recording)
        self.request_resume_live.connect(self.worker.resume_live)
        self.thread: Optional[QThread] = None
        if start_worker:
            self.thread = QThread(self)
            self.thread.setObjectName("pardusinsight-sampler")
            self.worker.moveToThread(self.thread)
            if can_sample:
                self.thread.started.connect(self.worker.start)
            self.thread.start()
        self._log(f"{APP_NAME} {__version__} başlatıldı — {mode_label}. Örnekleme aralığı "
                  f"{tr_num(service.settings.sample_interval_s, 1)} sn, geçmiş tamponu "
                  f"{tr_num(service.settings.history_minutes, 0)} dk.")

    # ------------------------------------------------------------------ kurulum
    def _interval_ms(self) -> int:
        return int(self.service.settings.sample_interval_s * 1000 / self.speed)

    def _build_ui(self) -> None:
        self._pending_processes: Optional[TickResult] = None
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_overview(), "Genel Bakış")
        self.tabs.addTab(self._build_processes(), "Süreçler")
        self.alerts_panel = AlertsPanel()
        self.tabs.addTab(self.alerts_panel, "Uyarılar")
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(1000)
        self.tabs.addTab(self.log_view, "Günlük")
        self.tabs.currentChanged.connect(
            lambda index: self._flush_processes() if index == 1 else None)
        self.setCentralWidget(self.tabs)
        self._build_toolbar()
        self.mode_status = QLabel(self.mode_label)
        self.samples_status = QLabel("Örnek: 0")
        self.usage_status = QLabel("Uygulama: —")
        self.usage_status.setToolTip("PardusInsight'ın kendi CPU (tek çekirdek = %100) ve "
                                     "bellek (RSS) kullanımı")
        bar = self.statusBar()
        bar.addPermanentWidget(self.mode_status)
        bar.addPermanentWidget(self.samples_status)
        bar.addPermanentWidget(self.usage_status)

    def _build_toolbar(self) -> None:
        tb = QToolBar("Ana araç çubuğu")
        tb.setMovable(False)
        self.addToolBar(tb)
        self.pause_action = QAction("Duraklat", self)
        self.pause_action.setShortcut(QKeySequence("Ctrl+P"))
        self.pause_action.setToolTip("Örneklemeyi duraklat/sürdür (Ctrl+P)")
        self.pause_action.triggered.connect(self.toggle_pause)
        self.pause_action.setEnabled(self.can_sample)
        self.live_action = QAction("Canlı izlemeye dön", self)
        self.live_action.setEnabled(False)
        self.live_action.triggered.connect(self.resume_live)
        csv_action = QAction("CSV dışa aktar…", self)
        csv_action.setShortcut(QKeySequence("Ctrl+E"))
        csv_action.triggered.connect(lambda: self.export_csv())
        json_action = QAction("JSON rapor…", self)
        json_action.setShortcut(QKeySequence("Ctrl+J"))
        json_action.triggered.connect(lambda: self.export_json())
        open_action = QAction("Kayıt/senaryo aç…", self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.setToolTip("Daha önce kaydedilmiş JSON raporunu veya sentetik senaryoyu "
                               "yükleyip kuralları yeniden çalıştır")
        open_action.triggered.connect(lambda: self.open_recording())
        settings_action = QAction("Ayarlar…", self)
        settings_action.triggered.connect(self.show_settings)
        about_action = QAction("Hakkında", self)
        about_action.triggered.connect(self.show_about)
        quit_action = QAction("Çık", self)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)
        for action in (self.pause_action, self.live_action):
            tb.addAction(action)
        tb.addSeparator()
        for action in (csv_action, json_action, open_action):
            tb.addAction(action)
        tb.addSeparator()
        tb.addAction(settings_action)
        tb.addAction(about_action)
        self.addAction(quit_action)

    def _build_overview(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        tiles = QGridLayout()
        self.tiles: Dict[str, SummaryTile] = {}
        for i, (key, title) in enumerate((("cpu", "CPU"), ("ram", "RAM"), ("swap", "Swap"),
                                          ("disk", "Disk G/Ç"), ("load", "Yük (1 dk)"),
                                          ("alerts", "Aktif uyarı"))):
            tile = SummaryTile(title)
            self.tiles[key] = tile
            tiles.addWidget(tile, 0, i)
        layout.addLayout(tiles)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Grafik aralığı:"))
        self.range_combo = QComboBox()
        for label, seconds in RANGES:
            self.range_combo.addItem(label, seconds)
        self.range_combo.setCurrentIndex(1)
        self.range_combo.currentIndexChanged.connect(lambda _i: self._refresh_charts())
        controls.addWidget(self.range_combo)
        controls.addStretch(1)
        self.source_info = QLabel("")
        controls.addWidget(self.source_info)
        layout.addLayout(controls)

        a = self.service.settings.analysis
        self.charts: Dict[str, TimeSeriesChart] = {
            "cpu": TimeSeriesChart("CPU kullanımı", "%", [
                SeriesSpec("Toplam", lambda s: s.cpu_percent),
                SeriesSpec("iowait", lambda s: s.cpu_iowait_percent)], fixed_max=100.0),
            "memory": TimeSeriesChart("Bellek ve swap doluluğu", "%", [
                SeriesSpec("RAM kullanılan", lambda s: s.mem_used_percent),
                SeriesSpec("Swap kullanılan", lambda s: s.swap_used_percent)], fixed_max=100.0),
            "paging": TimeSeriesChart("Swap etkinliği ve major page-fault", "/sn", [
                SeriesSpec("Swap giriş+çıkış (sayfa)", lambda s: s.swap_activity_pages_per_s),
                SeriesSpec("Major fault", lambda s: s.major_faults_per_s)], value_digits=0),
            "disk": TimeSeriesChart("Disk G/Ç", "MiB/sn", [
                SeriesSpec("Okuma", lambda s: None if s.disk_read_bytes_per_s is None
                           else s.disk_read_bytes_per_s / MIB),
                SeriesSpec("Yazma", lambda s: None if s.disk_write_bytes_per_s is None
                           else s.disk_write_bytes_per_s / MIB)]),
        }
        self.charts["cpu"].set_threshold(a.cpu_high_pct, "CPU eşiği")
        self.charts["memory"].set_threshold(100.0 - a.mem_available_warn_pct, "RAM uyarı eşiği")
        grid = QGridLayout()
        grid.addWidget(self.charts["cpu"], 0, 0)
        grid.addWidget(self.charts["memory"], 0, 1)
        grid.addWidget(self.charts["paging"], 1, 0)
        grid.addWidget(self.charts["disk"], 1, 1)
        layout.addLayout(grid, 1)
        return page

    def _build_processes(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        top = QHBoxLayout()
        top.addWidget(QLabel("Filtre:"))
        self.process_filter = QLineEdit()
        self.process_filter.setPlaceholderText("Ad, kullanıcı veya PID")
        self.process_filter.setClearButtonEnabled(True)
        top.addWidget(self.process_filter, 1)
        layout.addLayout(top)
        self.process_model = ProcessTableModel(self)
        self.process_filter.textChanged.connect(self.process_model.set_filter)
        self.process_view = QTableView()
        self.process_view.setModel(self.process_model)
        self.process_view.setSortingEnabled(True)
        self.process_view.sortByColumn(4, Qt.SortOrder.DescendingOrder)
        self.process_view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.process_view.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.process_view.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        self.process_view.verticalHeader().setVisible(False)
        self.process_view.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.process_view, 1)
        self.process_info = QLabel("Süreç verisi bekleniyor…")
        self.process_info.setWordWrap(True)
        layout.addWidget(self.process_info)
        return page

    # ------------------------------------------------------------------ güncelleme
    @Slot(object)
    def apply_tick(self, result: TickResult) -> None:
        self.last_result = result
        if result.sample is not None:
            self._update_tiles(result.sample, result.update.active)
        if result.processes is not None:
            # Süreç tablosu görünmüyorsa güncelleme sekme açılana kadar ertelenir
            self._pending_processes = result
            if self.tabs.currentIndex() == 1:
                self._flush_processes()
        self._alert_log = result.alert_log
        self.alerts_panel.set_alerts(result.alert_log)
        self.alerts_panel.set_statuses(result.update.statuses)
        active = len(result.update.active)
        self.tabs.setTabText(2, f"Uyarılar ({active})" if active else "Uyarılar")
        for alert in result.update.new:
            self._log(f"{SEVERITY_ICON.get(alert.severity, '•')} Yeni {alert.severity_label.lower()}"
                      f": {alert.title} — {alert.summary}")
            self.statusBar().showMessage(f"Yeni uyarı: {alert.title}", 8000)
        for alert in result.update.resolved:
            self._log(f"✓ Çözüldü: {alert.title}")
        errors = tuple(result.errors)
        if errors and errors != self._last_errors:
            for err in errors:
                self._log(f"! {err}")
        self._last_errors = errors
        self._refresh_charts()
        self._update_status(result)

    def _update_tiles(self, s: SystemSample, active: Tuple[Alert, ...]) -> None:
        self.tiles["cpu"].set(fmt_pct(s.cpu_percent),
                              f"kullanıcı {fmt_pct(s.cpu_user_percent)} · çekirdek "
                              f"{fmt_pct(s.cpu_system_percent)} · iowait "
                              f"{fmt_pct(s.cpu_iowait_percent)}")
        self.tiles["ram"].set(fmt_pct(s.mem_used_percent),
                              f"kullanılabilir {fmt_bytes(s.mem_available_bytes)} / "
                              f"{fmt_bytes(s.mem_total_bytes)}")
        if s.swap_total_bytes == 0:
            self.tiles["swap"].set("yok", "Swap alanı yapılandırılmamış")
        else:
            self.tiles["swap"].set(
                fmt_pct(s.swap_used_percent),
                f"giriş {_num(s.swap_in_pages_per_s)} · çıkış {_num(s.swap_out_pages_per_s)} "
                f"sayfa/sn · major fault {_num(s.major_faults_per_s)}/sn")
        self.tiles["disk"].set(fmt_rate(s.disk_total_bytes_per_s),
                               f"okuma {fmt_rate(s.disk_read_bytes_per_s)} · yazma "
                               f"{fmt_rate(s.disk_write_bytes_per_s)} · meşgul "
                               f"{fmt_pct(s.disk_busy_percent)}")
        self.tiles["load"].set("—" if s.load1 is None else tr_num(s.load1, 2),
                               f"{s.cpu_count or '?'} mantıksal CPU · G/Ç bekleyen "
                               f"{'—' if s.procs_blocked is None else s.procs_blocked}")
        self.tiles["alerts"].set(str(len(active)),
                                 ", ".join(a.title for a in active) or "Koşul yok")
        psi = "mevcut" if s.psi_memory_some is not None else "yok (çekirdek desteği kapalı)"
        self.source_info.setText(f"Kaynak: {self.service.source_name} · PSI: {psi}")

    def _flush_processes(self) -> None:
        result, self._pending_processes = self._pending_processes, None
        if result is not None:
            self._update_processes(result)

    def _update_processes(self, result: TickResult) -> None:
        snap = result.processes
        assert snap is not None
        selected_pid = None
        current = self.process_view.currentIndex()
        if current.isValid():
            selected_pid = current.data(PID_ROLE)
        self.process_model.set_processes(snap.processes)
        if selected_pid is not None:
            row = self.process_model.row_of_pid(selected_pid)
            if row is not None:
                self.process_view.selectRow(row)
        parts = [f"{len(snap.processes)} süreç listeleniyor"]
        if snap.partial_access:
            parts.append(f"{snap.partial_access} sürecin bazı alanları (ör. G/Ç) izin nedeniyle "
                         "okunamadı — root gerektirmeyen tasarım gereği beklenen durum")
        if snap.access_denied:
            parts.append(f"{snap.access_denied} süreç hiç okunamadı")
        if snap.vanished:
            parts.append(f"{snap.vanished} süreç tarama sırasında sonlandı")
        if snap.error:
            parts.append(f"hata: {snap.error}")
        self.process_info.setText(" · ".join(parts) + ". Süreçler üzerinde hiçbir işlem "
                                                      "yapılmaz (salt-okunur).")

    def _chart_span(self) -> float:
        span = float(self.range_combo.currentData() or 300.0)
        if self.replay_label is not None:
            span = max(span, self.service.history.duration_s())
        return span

    def _refresh_charts(self) -> None:
        samples = self.service.history.snapshot()
        now = samples[-1].timestamp if samples else time.time()
        span = self._chart_span()
        spans: Dict[str, List[Span]] = {key: [] for key in self.charts}
        for alert in self._alert_log:
            end = alert.resolved_at if alert.resolved_at is not None else alert.last_seen
            label = f"{SEVERITY_ICON.get(alert.severity, '•')} {alert.severity_label}"
            for key in RULE_CHARTS.get(alert.rule_id, ()):
                spans[key].append(Span(alert.window_start, end, alert.severity, label))
        for key, chart in self.charts.items():
            chart.set_spans(spans[key])
            chart.set_data(samples, span, now)

    def _update_status(self, result: TickResult) -> None:
        hist = self.service.history
        self.samples_status.setText(
            f"Örnek: {result.history_len} · tampon {tr_num(hist.duration_s() / 60.0, 1)}/"
            f"{tr_num(hist.max_age_s / 60.0, 0)} dk · tur {tr_num(result.duration_s * 1000, 0)} ms")
        cpu = self._self_usage.cpu_percent()
        rss = self._self_usage.rss_bytes()
        self.usage_status.setText(f"Uygulama: CPU {fmt_pct(cpu)} · RAM {fmt_bytes(rss)}")

    def _log(self, message: str) -> None:
        self.log_view.appendPlainText(f"{time.strftime('%H:%M:%S')}  {message}")

    @Slot(str)
    def _on_worker_failed(self, message: str) -> None:
        self._log(f"! {message}")
        self.statusBar().showMessage(message, 10000)

    # ------------------------------------------------------------------ eylemler
    def toggle_pause(self) -> None:
        if self.replay_label is not None:
            return
        self.paused = not self.paused
        if self.paused:
            self.request_stop.emit()
            self.pause_action.setText("Sürdür")
            self.mode_status.setText(f"{self.mode_label} (duraklatıldı)")
            self._log("Örnekleme duraklatıldı.")
        else:
            self.request_start.emit()
            self.pause_action.setText("Duraklat")
            self.mode_status.setText(self.mode_label)
            self._log("Örnekleme sürdürüldü.")

    def resume_live(self) -> None:
        if not self.can_sample:
            return
        self.replay_label = None
        self.paused = False
        self.pause_action.setText("Duraklat")
        self.pause_action.setEnabled(True)
        self.live_action.setEnabled(False)
        self.mode_status.setText(self.mode_label)
        self.setWindowTitle(f"{APP_NAME} — {self.mode_label}")
        self._alert_log = ()
        self.request_resume_live.emit()
        self._log("Canlı izlemeye dönüldü; geçmiş ve uyarılar sıfırlandı.")

    def _default_path(self, suffix: str) -> str:
        base = os.path.expanduser("~")
        return os.path.join(base, time.strftime(f"pardusinsight_%Y%m%d_%H%M%S{suffix}"))

    def export_csv(self, path: Optional[str] = None) -> bool:
        if path is None:
            path, _ = QFileDialog.getSaveFileName(self, "Örnekleri CSV olarak kaydet",
                                                  self._default_path(".csv"), "CSV (*.csv)")
            if not path:
                return False
        from ..cli import alerts_csv_path

        samples = self.service.history.snapshot()
        alerts_path = alerts_csv_path(path)
        try:
            n = write_samples_csv(path, samples)
            m = write_alerts_csv(alerts_path, self._alert_log)
        except OSError as exc:
            QMessageBox.warning(self, "Dışa aktarılamadı", f"Dosya yazılamadı: {exc}")
            return False
        message = f"CSV kaydedildi: {path} ({n} örnek) ve {alerts_path} ({m} uyarı)"
        self._log(message)
        self.statusBar().showMessage(message, 10000)
        return True

    def export_json(self, path: Optional[str] = None) -> bool:
        if path is None:
            path, _ = QFileDialog.getSaveFileName(self, "JSON rapor kaydet",
                                                  self._default_path(".json"),
                                                  "JSON (*.json)")
            if not path:
                return False
        samples = self.service.history.snapshot()
        report = build_report(samples, self._alert_log, settings_to_dict(self.service.settings),
                              source=self.replay_label or self.service.source_name)
        try:
            write_json_report(path, report)
        except OSError as exc:
            QMessageBox.warning(self, "Dışa aktarılamadı", f"Dosya yazılamadı: {exc}")
            return False
        message = f"JSON rapor kaydedildi: {path} ({len(samples)} örnek, {len(self._alert_log)} uyarı)"
        self._log(message)
        self.statusBar().showMessage(message, 10000)
        return True

    def open_recording(self, path: Optional[str] = None) -> bool:
        if path is None:
            start_dir = _scenarios_dir() or os.path.expanduser("~")
            path, _ = QFileDialog.getOpenFileName(self, "Kayıt veya senaryo aç", start_dir,
                                                  "PardusInsight raporu (*.json)")
            if not path:
                return False
        try:
            data = load_json_report(path)
        except ReportError as exc:
            QMessageBox.warning(self, "Kayıt açılamadı", str(exc))
            return False
        if not data.samples:
            QMessageBox.information(self, "Kayıt boş", "Bu dosyada örnek bulunmuyor.")
            return False
        self.request_recording.emit(data.samples, os.path.basename(path))
        return True

    @Slot(object, str)
    def on_recording_loaded(self, result: TickResult, label: str) -> None:
        self.replay_label = label
        self.pause_action.setEnabled(False)
        self.live_action.setEnabled(self.can_sample)
        self.mode_status.setText(f"Kayıt analizi: {label}")
        self.setWindowTitle(f"{APP_NAME} — Kayıt analizi: {label}")
        self.process_model.set_processes(())
        self.process_info.setText("Kayıt analizinde süreç listesi yoktur; uyarı bağlamındaki "
                                  "süreç özetleri kayıttan gelir.")
        self._log(f"Kayıt yüklendi: {label} — {result.history_len} örnek, "
                  f"{len(result.alert_log)} uyarı ({tr_num(result.duration_s * 1000, 0)} ms).")
        self.apply_tick(result)
        self.tabs.setCurrentWidget(self.alerts_panel)

    def show_settings(self) -> None:
        dialog = SettingsDialog(self.service.settings, self)
        if dialog.exec() and dialog.result_settings is not None:
            new = dialog.result_settings
            self.request_settings.emit(new)
            self.request_interval.emit(int(new.sample_interval_s * 1000 / self.speed))
            self.charts["cpu"].set_threshold(new.analysis.cpu_high_pct, "CPU eşiği")
            self.charts["memory"].set_threshold(100.0 - new.analysis.mem_available_warn_pct,
                                                "RAM uyarı eşiği")
            self._log("Ayarlar güncellendi: aralık "
                      f"{tr_num(new.sample_interval_s, 1)} sn, pencere "
                      f"{tr_num(new.analysis.window_s, 0)} sn × {new.analysis.consecutive_windows}.")

    def show_about(self) -> None:
        QMessageBox.about(self, f"{APP_NAME} hakkında", ABOUT_HTML)

    def shutdown(self) -> None:
        """Worker'ı durdurur ve iş parçacığının bitmesini bekler."""
        if self.thread is not None and self.thread.isRunning():
            # Zamanlayıcı worker iş parçacığına ait olduğu için orada durdurulmalı
            QMetaObject.invokeMethod(self.worker, "stop",
                                     Qt.ConnectionType.BlockingQueuedConnection)
            self.thread.quit()
            self.thread.wait(5000)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        self.shutdown()
        super().closeEvent(event)


def _num(value: Optional[float]) -> str:
    return "—" if value is None else tr_num(value, 0)


def _scenarios_dir() -> Optional[str]:
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    path = os.path.join(here, "scenarios")
    return path if os.path.isdir(path) else None
