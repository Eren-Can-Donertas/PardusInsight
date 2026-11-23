"""Türkçe biçimlendirme yardımcıları ve sentetik kaynak testleri."""
import pytest

from pardusinsight.collectors.synthetic import SyntheticSource
from pardusinsight.core.formatting import (fmt_bytes, fmt_duration, fmt_pct, fmt_rate,
                                           fmt_value, tr_num)


def test_turkish_number_and_percent_format():
    assert tr_num(12.345, 1) == "12,3"
    assert fmt_pct(85) == "%85,0"
    assert fmt_pct(None) == "—"


def test_bytes_rates_and_durations():
    assert fmt_bytes(512) == "512 B"
    assert fmt_bytes(1536) == "1,5 KiB"
    assert fmt_bytes(3 * 1024 ** 3) == "3,0 GiB"
    assert fmt_rate(2 * 1024 * 1024) == "2,0 MiB/sn"
    assert fmt_duration(59) == "59 sn"
    assert fmt_duration(60) == "1 dk"
    assert fmt_duration(112) == "1 dk 52 sn"
    assert fmt_duration(3720) == "1 sa 2 dk"


def test_evidence_value_format_by_unit():
    assert fmt_value(None, "%") == "ölçülemedi"
    assert fmt_value(10.0, "%") == "%10,0"
    assert fmt_value(1024.0, "B/sn") == "1,0 KiB/sn"
    assert fmt_value(150.0, "sayfa/sn") == "150,0 sayfa/sn"


def test_synthetic_source_counters_are_cumulative_and_time_advances():
    src = SyntheticSource("demo", step_s=2.0, start_time=100.0)
    first, second = src.collect(), src.collect()
    assert (first.timestamp, second.timestamp) == (100.0, 102.0)
    assert second.cpu_times.total == pytest.approx(first.cpu_times.total + 2.0 * src.cpu_count)
    assert second.vm.pgfault >= first.vm.pgfault
    with pytest.raises(ValueError):
        SyntheticSource("olmayan-senaryo")
