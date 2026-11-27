"""Ayarlar (pardusinsight/config.py): JSON tür dönüşümü ve aralık denetimleri."""
import json
from dataclasses import replace

import pytest

from pardusinsight.config import (AnalysisSettings, AppSettings, load_settings_file,
                                  settings_from_dict, settings_to_dict, unknown_setting_keys)


@pytest.mark.parametrize("data, message", [
    ([], "kökü bir JSON nesnesi"),
    ({"analysis": 5}, "'analysis' bir JSON nesnesi"),
    ({"analysis": {"cpu_high_pct": "90"}}, "'cpu_high_pct' sayı olmalı"),
    ({"sample_interval_s": None}, "'sample_interval_s' sayı olmalı"),
    ({"analysis": {"window_s": True}}, "'window_s' sayı olmalı"),
    ({"analysis": {"consecutive_windows": 2.5}}, "'consecutive_windows' tam sayı olmalı"),
])
def test_malformed_json_settings_raise_clear_value_error(data, message):
    with pytest.raises(ValueError, match=message):
        settings_from_dict(data)


def test_integer_fields_accept_whole_floats_from_json():
    settings = settings_from_dict({"top_n": 5.0, "process_every": 2.0,
                                   "analysis": {"consecutive_windows": 3.0}})
    assert settings.top_n == 5 and isinstance(settings.top_n, int)
    assert settings.analysis.consecutive_windows == 3
    assert isinstance(settings.analysis.consecutive_windows, int)


def test_numbers_become_floats_and_interval_has_single_source():
    settings = settings_from_dict({"sample_interval_s": 5, "analysis": {"cpu_high_pct": 90}})
    assert settings.analysis.cpu_high_pct == 90.0
    assert settings.analysis.sample_interval_s == settings.sample_interval_s == 5.0


@pytest.mark.parametrize("changes", [
    dict(disk_min_throughput_mib_s=0.0),  # 0 iken boş diskte "0 B/sn -> 0 B/sn artış" uyarısı
    dict(swap_activity_pages_s=0.0),
    dict(major_faults_s=-1.0),
    dict(psi_memory_some_pct=0.0),
    dict(resolve_grace_s=-1.0),
    dict(disk_baseline_s=0.0),
    dict(disk_min_baseline_coverage=0.0),
    dict(consecutive_windows=2.0),  # doğrudan kurulumda da tam sayı şart
])
def test_analysis_thresholds_are_range_checked(changes):
    with pytest.raises(ValueError):
        replace(AnalysisSettings(), **changes).validate()


@pytest.mark.parametrize("changes", [dict(top_n=0), dict(top_n=-1), dict(top_n=50),
                                     dict(process_every=0), dict(process_every=1.5)])
def test_app_settings_are_range_checked(changes):
    with pytest.raises(ValueError):
        replace(AppSettings(), **changes).validate()


def test_analysis_span_longer_than_history_is_rejected():
    long_windows = replace(AppSettings().analysis, window_s=600.0, consecutive_windows=4)
    with pytest.raises(ValueError, match="geçmiş süresinden"):
        replace(AppSettings(), analysis=long_windows).validate()


def test_short_history_warns_that_disk_ratio_cannot_work():
    settings = replace(AppSettings(), history_minutes=2.0).validate()
    (warning,) = settings.warnings()
    assert "disk kuralının" in warning
    assert AppSettings().warnings() == []


def test_unknown_keys_are_reported_but_ignored(tmp_path):
    path = tmp_path / "ayar.json"
    path.write_text(json.dumps({"cpu_high_percent": 90, "analysis": {"cpu_hgh_pct": 1}}),
                    encoding="utf-8")
    warnings = []
    assert load_settings_file(str(path), warnings) == AppSettings()
    assert "cpu_high_percent" in warnings[0] and "analysis.cpu_hgh_pct" in warnings[0]
    assert unknown_setting_keys(settings_to_dict(AppSettings())) == []
