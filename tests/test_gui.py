"""PySide6 arayüz testleri (QT_QPA_PLATFORM=offscreen ile ekransız çalışır).

PySide6 kurulu değilse atlanır. Pardus XFCE masaüstündeki gerçek görsel
davranış ayrıca elle doğrulanmalıdır (docs/PARDUS_DOGRULAMA.md).
"""
import time

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import QElapsedTimer, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from pardusinsight.collectors.synthetic import SyntheticProcessCollector, SyntheticSource  # noqa: E402,E501
from pardusinsight.config import AppSettings  # noqa: E402
from pardusinsight.core.models import ProcessInfo  # noqa: E402
from pardusinsight.core.service import MonitorService, build_synthetic_service  # noqa: E402
from pardusinsight.export import build_report, load_json_report, write_json_report  # noqa: E402
from pardusinsight.ui.charts import SeriesSpec, TimeSeriesChart, nice_ceiling  # noqa: E402
from pardusinsight.ui.main_window import MainWindow  # noqa: E402
from pardusinsight.ui.process_model import SORT_ROLE, ProcessTableModel  # noqa: E402
from pardusinsight.ui.settings_dialog import SettingsDialog  # noqa: E402

pytestmark = pytest.mark.gui


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(qapp):
    service = build_synthetic_service("demo", AppSettings(), loop=False, start_time=1.767e9)
    win = MainWindow(service, "Sentetik test", start_worker=False)
    win.resize(1200, 800)
    yield win
    win.close()


def test_window_updates_tiles_processes_and_alerts(window, qapp):
    for _ in range(150):
        window.apply_tick(window.service.tick())
    qapp.processEvents()
    assert window.tiles["cpu"].value.text().startswith("%")
    assert window.process_model.rowCount() == 0  # sekme kapalıyken tablo güncellenmez
    window.tabs.setCurrentIndex(1)
    assert window.process_model.rowCount() >= 10
    assert window.alerts_panel.list.count() == 2  # CPU (çözüldü) + bellek (aktif)
    assert window.tabs.tabText(2) == "Uyarılar (1)"
    assert "Bellek baskısı" in window.alerts_panel.detail.toPlainText()
    statuses = window.alerts_panel.status_table
    assert statuses.rowCount() == 3 and statuses.item(0, 1).text() == "Tetiklendi"
    assert window.charts["cpu"].point_count() > 100
    assert not window.grab().isNull()


def test_window_exports_csv_and_json(window, tmp_path):
    for _ in range(40):
        window.apply_tick(window.service.tick())
    assert window.export_csv(str(tmp_path / "a.csv"))
    assert (tmp_path / "a_uyarilar.csv").exists()
    assert window.export_json(str(tmp_path / "a.json"))
    assert len(load_json_report(str(tmp_path / "a.json")).samples) == 40


def test_window_loads_recording_for_analysis(window, tmp_path, qapp):
    source = SyntheticSource("cpu")
    recorder = MonitorService(source, SyntheticProcessCollector(source))
    for _ in range(211):
        recorder.tick()
    path = tmp_path / "kayit.json"
    write_json_report(str(path), build_report(recorder.history.snapshot(), []))
    assert window.open_recording(str(path))  # worker aynı iş parçacığında: doğrudan çalışır
    qapp.processEvents()
    assert window.replay_label == "kayit.json"
    assert window.live_action.isEnabled() and not window.pause_action.isEnabled()
    assert "Kalıcı CPU" in window.alerts_panel.list.item(0).text()


def test_background_sampling_keeps_gui_responsive(qapp):
    """Yavaş bir ölçüm kaynağı (her tur 300 ms) GUI olay döngüsünü bloklamamalı."""

    class SlowSource(SyntheticSource):
        def collect(self):
            time.sleep(0.3)
            return super().collect()

    source = SlowSource("demo", start_time=1.767e9)
    service = MonitorService(source, SyntheticProcessCollector(source))
    win = MainWindow(service, "yavaş kaynak", speed=10.0)  # 200 ms aralık, gerçek QThread
    ticks = []
    win.worker.tick_ready.connect(lambda r: ticks.append(r))
    gaps = []
    clock = QElapsedTimer()
    clock.start()
    last = [clock.elapsed()]

    def heartbeat():
        now = clock.elapsed()
        gaps.append(now - last[0])
        last[0] = now

    beat = QTimer()
    beat.timeout.connect(heartbeat)
    beat.start(20)
    deadline = time.monotonic() + 2.5
    while time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.005)
    beat.stop()
    win.shutdown()
    win.close()
    assert len(ticks) >= 4, "arka plan örneklemesi çalışmadı"
    assert max(gaps[1:]) < 250, f"GUI olay döngüsü {max(gaps)} ms bloklandı"
    assert not win.thread.isRunning()


def test_chart_handles_gaps_and_nice_axis(qapp):
    from conftest import build_series

    samples = build_series(50, lambda i, t: dict(cpu_percent=None if 10 <= i < 15 else 40.0))
    chart = TimeSeriesChart("CPU", "%", [SeriesSpec("Toplam", lambda s: s.cpu_percent)],
                            fixed_max=100.0)
    chart.resize(400, 200)
    chart.set_data(samples, 60.0)
    assert chart.point_count() == 31  # son 60 sn
    assert not chart.grab().isNull()
    assert [nice_ceiling(v) for v in (0.7, 3, 7, 420)] == [1, 5, 10, 500]


def test_process_model_sorts_numerically_and_filters(qapp):
    from PySide6.QtCore import Qt

    model = ProcessTableModel()
    model.set_processes([ProcessInfo(pid=1, name="systemd", username="root", cpu_percent=0.5),
                         ProcessInfo(pid=20, name="firefox-esr", username="ogrenci",
                                     cpu_percent=12.0),
                         ProcessInfo(pid=3, name="xfwm4", username="ogrenci", cpu_percent=None)])
    # Varsayılan: CPU % azalan; okunamayan (None) değer en sonda
    assert [model.index(r, 1).data() for r in range(3)] == ["firefox-esr", "systemd", "xfwm4"]
    assert model.index(2, 4).data() == "—"
    model.sort(4, Qt.SortOrder.AscendingOrder)
    assert [model.index(r, 1).data() for r in range(3)] == ["xfwm4", "systemd", "firefox-esr"]
    model.sort(0, Qt.SortOrder.AscendingOrder)  # PID sayısal sıralanır (1, 3, 20)
    assert [model.index(r, 0).data() for r in range(3)] == ["1", "3", "20"]
    model.set_filter("ogrenci")
    assert model.rowCount() == 2
    model.set_filter("20")
    assert model.rowCount() == 1 and model.index(0, 0).data(SORT_ROLE) == 20.0
    assert model.row_of_pid(20) == 0 and model.row_of_pid(1) is None


def test_settings_dialog_builds_valid_settings(qapp):
    dialog = SettingsDialog(AppSettings())
    dialog.interval.setValue(3.0)
    dialog._spins["cpu_high_pct"].setValue(90)
    settings = dialog.build_settings()
    assert settings.sample_interval_s == 3.0 == settings.analysis.sample_interval_s
    assert settings.analysis.cpu_high_pct == 90.0
    dialog._spins["mem_available_crit_pct"].setValue(40)  # uyarı eşiğinden büyük: geçersiz
    with pytest.raises(ValueError):
        dialog.build_settings()
