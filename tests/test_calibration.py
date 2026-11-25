"""Eşik kalibrasyonu (pardusinsight/analysis/calibration.py, scripts/kalibrasyon.py) testleri."""
import json
import sys
from pathlib import Path

import pytest

from conftest import build_series
from pardusinsight.analysis.calibration import (PARAMETERS, Recording, calibrate,
                                                recommended_config, render_markdown,
                                                settings_for)
from pardusinsight.collectors.synthetic import SyntheticProcessCollector, SyntheticSource
from pardusinsight.config import AnalysisSettings
from pardusinsight.core.service import MonitorService
from pardusinsight.export import build_report, write_json_report

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import kalibrasyon  # noqa: E402

CPU_PARAMS = [p for p in PARAMETERS if p.rule_id == "sustained_cpu"]
CPU_HIGH = [p for p in PARAMETERS if p.name == "cpu_high_pct"]


def synthetic(name, seconds=None, seed=461):
    source = SyntheticSource(name, seed=seed, step_s=2.0)
    service = MonitorService(source, SyntheticProcessCollector(source))
    for _ in range(int((seconds or source.total_duration) / 2) + 1):
        service.tick()
    return tuple(service.history.snapshot())


def rec_of(result, name):
    return next(r for r in result.recommendations if r.parameter == name)


def test_defaults_quiet_on_normal_and_detect_expected_heavy():
    result = calibrate([Recording("normal", synthetic("normal", 600)),
                        Recording("derleme", synthetic("cpu"), heavy=True,
                                  expect=("sustained_cpu",))], parameters=CPU_PARAMS)
    assert result.default_alerts["normal"] == ()
    assert [a.rule_id for a in result.default_alerts["derleme"]] == ["sustained_cpu"]
    assert all(not r.changed for r in result.recommendations)
    assert recommended_config(result) == {}


def test_false_positive_on_normal_use_raises_threshold_with_margin():
    # Arka planda sürekli %88 CPU kullanan ama "olağan" sayılan bir makine
    busy_normal = tuple(build_series(300, lambda i, t: dict(cpu_percent=88.0)))
    result = calibrate([Recording("normal", busy_normal)], parameters=CPU_HIGH)
    rec = rec_of(result, "cpu_high_pct")
    assert [a.rule_id for a in result.default_alerts["normal"]] == ["sustained_cpu"]
    # %90'da sıfıra iniyor; bir adım güvenlik payıyla %95 önerilir
    assert rec.changed and rec.recommended == 95.0
    assert "yanlış pozitif" in rec.reason
    assert recommended_config(result) == {"analysis": {"cpu_high_pct": 95.0}}


def test_missed_heavy_recording_lowers_threshold_while_normal_stays_quiet():
    normal = tuple(build_series(300, lambda i, t: dict(cpu_percent=20.0)))
    heavy = tuple(build_series(300, lambda i, t: dict(cpu_percent=78.0)))
    result = calibrate([Recording("normal", normal),
                        Recording("yogun", heavy, heavy=True, expect=("sustained_cpu",))],
                       parameters=CPU_HIGH)
    rec = rec_of(result, "cpu_high_pct")
    assert rec.changed and rec.recommended == 75.0  # %80 yakalamıyor, %75 yakalıyor
    assert "kaçırdı" in rec.reason


def test_trigger_is_monotonic_in_threshold():
    # Sürekli %82 CPU: %80 ve altındaki eşiklerde tetiklenmeli, %85 ve üstünde tetiklenmemeli
    samples = tuple(build_series(200, lambda i, t: dict(cpu_percent=82.0)))
    sweep = calibrate([Recording("normal", samples)], parameters=CPU_HIGH).sweeps[0]
    fired = {cell.value: cell.alerts["normal"] > 0 for cell in sweep.cells}
    assert [v for v, f in fired.items() if f] == [80.0, 75.0, 70.0, 60.0]
    order = [fired[cell.value] for cell in sweep.cells]  # az duyarlı -> çok duyarlı
    assert order == sorted(order)  # bir kez tetiklenince daha duyarlı değerlerde de tetiklenir


def test_recording_interval_is_respected():
    # 5 sn aralıkla alınmış kayıt 2 sn varsayımıyla analiz edilirse "yetersiz veri" olurdu
    samples = tuple(build_series(60, lambda i, t: dict(cpu_percent=97.0), interval=5.0))
    adjusted = settings_for(Recording("r", samples), AnalysisSettings())
    assert adjusted.sample_interval_s == 5.0
    result = calibrate([Recording("r", samples)], parameters=CPU_HIGH)
    assert [a.rule_id for a in result.default_alerts["r"]] == ["sustained_cpu"]
    assert any("5,0 sn" in note for note in result.notes)


def test_without_normal_recordings_defaults_are_kept():
    result = calibrate([Recording("y", synthetic("cpu"), heavy=True, expect=("sustained_cpu",))],
                       parameters=CPU_HIGH)
    rec = rec_of(result, "cpu_high_pct")
    assert not rec.changed and "Olağan kullanım kaydı yok" in rec.reason


def test_labels_must_be_unique_and_short_recordings_are_noted():
    series = tuple(build_series(10))
    with pytest.raises(ValueError):
        calibrate([Recording("a", series), Recording("a", series)], parameters=CPU_HIGH)
    result = calibrate([Recording("kisa", series)], parameters=CPU_HIGH)
    assert any("zayıf kanıt" in note for note in result.notes)


def test_markdown_report_sections():
    busy_normal = tuple(build_series(300, lambda i, t: dict(cpu_percent=88.0)))
    text = render_markdown(calibrate([Recording("normal", busy_normal)], parameters=CPU_HIGH))
    for heading in ("## Eşik kalibrasyonu", "### Ölçüm profili",
                    "### Varsayılan eşiklerle üretilen uyarılar", "### Duyarlılık taraması",
                    "### Öneriler"):
        assert heading in text
    assert "**(varsayılan)**" in text and "**(öneri)**" in text
    block = text.split("```json", 1)[1].split("```", 1)[0]
    assert json.loads(block) == {"analysis": {"cpu_high_pct": 95.0}}


# ----------------------------------------------------------------------------- komut satırı
def test_heavy_spec_parsing_keeps_windows_drive_letters():
    assert kalibrasyon.split_heavy("C:\\kayit\\derleme.json:sustained_cpu") == (
        "C:\\kayit\\derleme.json", ("sustained_cpu",))
    assert kalibrasyon.split_heavy("C:\\kayit\\derleme.json") == ("C:\\kayit\\derleme.json", ())
    assert kalibrasyon.split_heavy("a.json:memory_pressure,disk_io_anomaly")[1] == (
        "memory_pressure", "disk_io_anomaly")


def test_script_writes_report_and_suggestions_only_when_asked(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(kalibrasyon, "calibrate",
                        lambda recs, base: calibrate(recs, base, parameters=CPU_HIGH))
    path = tmp_path / "normal.json"
    samples = build_series(300, lambda i, t: dict(cpu_percent=88.0))
    write_json_report(str(path), build_report(samples, [], {}, source="test"))
    assert kalibrasyon.main([str(path)]) == 0
    assert "## Eşik kalibrasyonu" in capsys.readouterr().out
    assert sorted(p.name for p in tmp_path.iterdir()) == ["normal.json"]  # istenmeden yazmaz

    md, js = tmp_path / "rapor.md", tmp_path / "oneri.json"
    assert kalibrasyon.main([str(path), "--cikti", str(md), "--oneri-json", str(js)]) == 0
    assert "### Öneriler" in md.read_text(encoding="utf-8")
    assert json.loads(js.read_text(encoding="utf-8")) == {"analysis": {"cpu_high_pct": 95.0}}


def test_script_reports_unreadable_recording(tmp_path, capsys):
    bad = tmp_path / "bozuk.json"
    bad.write_text("{}", encoding="utf-8")
    assert kalibrasyon.main([str(bad)]) == 2
    assert "Kayıt okunamadı" in capsys.readouterr().err
