"""CSV/JSON dışa aktarma, geri okuma ve gizlilik testleri."""
import getpass
import json
import os
import socket

import pytest

from pardusinsight.collectors.synthetic import SyntheticProcessCollector, SyntheticSource
from pardusinsight.config import AppSettings, settings_from_dict, settings_to_dict
from pardusinsight.core.models import SAMPLE_METRIC_FIELDS
from pardusinsight.core.service import MonitorService
from pardusinsight.export import (REPORT_SCHEMA, ReportError, build_report, load_json_report,
                                  read_alerts_csv, read_samples_csv, write_alerts_csv,
                                  write_json_report, write_samples_csv)
from pardusinsight.export.atomic import atomic_write


@pytest.fixture(scope="module")
def recorded():
    source = SyntheticSource("demo", step_s=2.0)
    service = MonitorService(source, SyntheticProcessCollector(source))
    for _ in range(251):
        service.tick()
    return service.history.snapshot(), list(service.engine.alert_log()), service


def test_samples_csv_roundtrip(tmp_path, recorded):
    samples, _alerts, _ = recorded
    path = tmp_path / "ornekler.csv"
    assert write_samples_csv(str(path), samples) == len(samples)
    back = read_samples_csv(str(path))
    assert len(back) == len(samples)
    for original, restored in zip(samples, back):
        for name in SAMPLE_METRIC_FIELDS:
            a, b = getattr(original, name), getattr(restored, name)
            assert (a is None and b is None) or a == pytest.approx(b), name


def test_alerts_csv_has_explanations(tmp_path, recorded):
    _samples, alerts, _ = recorded
    path = tmp_path / "uyarilar.csv"
    write_alerts_csv(str(path), alerts)
    rows = read_alerts_csv(str(path))
    assert len(rows) == len(alerts) == 3
    for row in rows:
        assert row["window_start_iso"] and row["window_end_iso"]
        assert "✓" in row["evidence"] and row["uncertainty"]


def test_json_report_roundtrip(tmp_path, recorded):
    samples, alerts, service = recorded
    path = tmp_path / "rapor.json"
    report = build_report(samples, alerts, settings_to_dict(service.settings), source="test")
    write_json_report(str(path), report)
    data = load_json_report(str(path))
    assert data.samples == samples
    assert data.alerts == alerts
    assert data.meta["schema"] == REPORT_SCHEMA
    assert data.meta["summary"]["sample_count"] == len(samples)
    assert data.meta["summary"]["alerts_by_rule"] == {"sustained_cpu": 1, "memory_pressure": 1,
                                                      "disk_io_anomaly": 1}
    assert settings_from_dict(data.settings) == service.settings


@pytest.mark.parametrize("content, message", [
    ("{bozuk", "Geçersiz JSON"),
    ('{"schema": "baska"}', "PardusInsight raporu değil"),
    ('{"schema": "pardusinsight.report", "schema_version": 99}', "Desteklenmeyen"),
    ('{"schema": "pardusinsight.report", "schema_version": 1, "samples": [{"x": 1}]}', "bozuk"),
])
def test_invalid_reports_are_rejected_with_message(tmp_path, content, message):
    path = tmp_path / "x.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ReportError, match=message):
        load_json_report(str(path))


def test_missing_report_file_raises_report_error(tmp_path):
    with pytest.raises(ReportError, match="okunamadı"):
        load_json_report(str(tmp_path / "yok.json"))


def test_atomic_write_keeps_old_file_on_failure(tmp_path):
    path = tmp_path / "rapor.csv"
    path.write_text("eski içerik", encoding="utf-8")
    with pytest.raises(RuntimeError):
        with atomic_write(str(path)) as handle:
            handle.write("yarım")
            raise RuntimeError("disk doldu")
    assert path.read_text(encoding="utf-8") == "eski içerik"
    assert [p.name for p in tmp_path.iterdir()] == ["rapor.csv"]  # geçici dosya kalmadı


def test_empty_history_can_be_exported(tmp_path):
    write_samples_csv(str(tmp_path / "bos.csv"), [])
    assert read_samples_csv(str(tmp_path / "bos.csv")) == []
    write_json_report(str(tmp_path / "bos.json"), build_report([], []))
    assert load_json_report(str(tmp_path / "bos.json")).samples == []


def test_report_does_not_contain_user_or_host_name(tmp_path, recorded):
    samples, alerts, _ = recorded
    path = tmp_path / "rapor.json"
    write_json_report(str(path), build_report(samples[:5], alerts))
    text = path.read_text(encoding="utf-8")
    system = json.loads(text)["system"]
    assert set(system) == {"os", "kernel", "machine", "python"}
    for secret in {socket.gethostname(), getpass.getuser()}:
        if secret and len(secret) > 3:
            assert secret not in text


def test_settings_dict_roundtrip_ignores_unknown_keys():
    data = settings_to_dict(AppSettings())
    data["gelecekte_eklenecek"] = 1
    data["analysis"]["bilinmeyen"] = 2
    assert settings_from_dict(data) == AppSettings()
