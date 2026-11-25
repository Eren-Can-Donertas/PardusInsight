"""Zaman penceresi testleri (pardusinsight/analysis/windows.py ve motorun geçmiş seçimi).

Kurallar değerlendirme dönemini en yeni örnekten geriye doğru eşit uzunlukta,
ardışık pencerelere böler: (bitiş - (k+1)·w, bitiş - k·w]. Başlangıç hariç, bitiş
dahildir; böylece her örnek en fazla bir pencereye düşer (docs/KURALLAR.md).
"""
import random

import pytest

from conftest import T0, build_series, make_sample
from pardusinsight.analysis.engine import RuleEngine
from pardusinsight.analysis.rules import Rule, RuleOutcome
from pardusinsight.analysis.windows import (fraction_at_least, mean, median, min_valid_samples,
                                            split_windows, values_of)
from pardusinsight.config import AnalysisSettings


def stamps(window):
    return [s.timestamp for s in window.samples]


# ----------------------------------------------------------------------------- bölme
def test_two_windows_of_thirty_seconds_at_two_second_interval():
    samples = build_series(60)  # 0..118 sn
    end = samples[-1].timestamp
    windows = split_windows(samples, end, 30.0, 2)
    assert [(w.start, w.end) for w in windows] == [(end - 60, end - 30), (end - 30, end)]
    assert len(windows[0].samples) == len(windows[1].samples) == 15
    assert stamps(windows[1])[-1] == end  # en yeni örnek son pencerede


def test_windows_are_ordered_oldest_first_and_contiguous():
    samples = build_series(100)
    windows = split_windows(samples, samples[-1].timestamp, 20.0, 4)
    for older, newer in zip(windows, windows[1:]):
        assert older.end == newer.start
        assert max(stamps(older)) < min(stamps(newer))


def test_boundary_sample_belongs_to_older_window_only():
    # Pencere sınırına tam denk gelen örnek: eski pencerenin bitişi (dahil), yeninin başı (hariç)
    samples = build_series(31)  # 0..60 sn; 30. sn sınırda
    end = samples[-1].timestamp
    older, newer = split_windows(samples, end, 30.0, 2)
    assert end - 30.0 in stamps(older) and end - 30.0 not in stamps(newer)
    assert end - 60.0 not in stamps(older)  # en eski sınır dönem dışında


def test_samples_older_than_evaluation_span_are_excluded():
    samples = build_series(200)
    end = samples[-1].timestamp
    windows = split_windows(samples, end, 30.0, 2)
    inside = [t for w in windows for t in stamps(w)]
    assert min(inside) > end - 60.0
    assert len(inside) == 30


@pytest.mark.parametrize("count", [1, 2, 3, 5])
def test_every_sample_in_span_lands_in_exactly_one_window(count):
    rng = random.Random(count)
    # Düzensiz aralıklar (1,2–2,8 sn) ve gerçekçi epoch ölçeğinde zaman damgaları
    t, samples = T0, []
    for _ in range(300):
        t += rng.uniform(1.2, 2.8)
        samples.append(make_sample(t))
    end = samples[-1].timestamp
    windows = split_windows(samples, end, 30.0, count)
    seen = [ts for w in windows for ts in stamps(w)]
    expected = [s.timestamp for s in samples if end - count * 30.0 < s.timestamp <= end]
    assert sorted(seen) == expected
    assert len(seen) == len(set(seen))  # hiçbir örnek iki pencerede değil


def test_gap_leaves_an_empty_window():
    early = build_series(20)  # 0..38 sn
    late = build_series(10, start=T0 + 100.0)  # 100..118 sn, arada 62 sn boşluk
    samples = early + late
    older, newer = split_windows(samples, samples[-1].timestamp, 30.0, 2)
    assert older.samples == () and older.values("cpu_percent") == []
    assert len(newer.samples) == 10


def test_end_before_samples_yields_empty_windows():
    samples = build_series(10)
    windows = split_windows(samples, T0 - 1.0, 30.0, 2)
    assert all(w.samples == () for w in windows)


# ----------------------------------------------------------------------------- değerler
def test_values_of_skips_missing_and_accepts_callables():
    samples = [make_sample(T0, cpu_percent=10), make_sample(T0 + 2, cpu_percent=None),
               make_sample(T0 + 4, cpu_percent=30.5)]
    assert values_of(samples, "cpu_percent") == [10.0, 30.5]
    assert all(isinstance(v, float) for v in values_of(samples, "cpu_percent"))
    total = values_of(samples, lambda s: s.disk_total_bytes_per_s)
    assert total == [1024 * 1024.0] * 3
    assert values_of([make_sample(T0, disk_read_bytes_per_s=None)],
                     lambda s: s.disk_total_bytes_per_s) == []


def test_statistics_helpers_handle_empty_input():
    assert mean([]) is None and median([]) is None and fraction_at_least([], 50) is None
    assert mean([1.0, 2.0, 6.0]) == 3.0
    assert median([5.0, 1.0, 3.0, 100.0]) == 4.0  # aykırı değere dayanıklı
    assert fraction_at_least([84.9, 85.0, 99.0, 10.0], 85.0) == 0.5  # eşik dahil (>=)


# ----------------------------------------------------------------------------- veri yeterliliği
@pytest.mark.parametrize("window, interval, coverage, expected", [
    (30.0, 2.0, 0.6, 9),     # varsayılan: 15 örneğin %60'ı
    (30.0, 2.0, 1.0, 15),
    (45.0, 3.0, 0.7, 11),    # 10,5 -> yukarı yuvarlanır
    (20.0, 2.0, 0.3, 3),     # 10 × 0,3 = 3,0000000000000004: kayan nokta hatası 4 yapmamalı
    (4.0, 2.0, 0.1, 2),      # en az 2 örnek
])
def test_min_valid_samples(window, interval, coverage, expected):
    assert min_valid_samples(window, interval, coverage) == expected


# ----------------------------------------------------------------------------- motor
class Recorder(Rule):
    """Motorun kurala hangi zaman aralığını verdiğini kaydeder."""

    rule_id = "kaydedici"
    title = "Kaydedici"

    def __init__(self):
        self.received = []

    def evaluate(self, samples, settings):
        self.received.append((samples[0].timestamp, samples[-1].timestamp, len(samples)))
        return RuleOutcome(False, "kayıt")


def test_engine_passes_full_lookback_including_disk_baseline():
    settings = AnalysisSettings()
    recorder = Recorder()
    engine = RuleEngine(settings, rules=[recorder])
    samples = build_series(600)  # 20 dk
    engine.evaluate(samples)
    first, last, _count = recorder.received[-1]
    # Disk kuralı değerlendirme döneminin (2 × 30 sn) öncesindeki 300 sn'lik tabana bakar
    needed_from = last - settings.evaluation_span_s - settings.disk_baseline_s
    assert first <= needed_from + settings.sample_interval_s
    assert first >= last - settings.lookback_s - settings.window_s  # gereksiz geçmiş verilmez


def test_engine_lookback_follows_window_settings():
    recorder = Recorder()
    settings = AnalysisSettings(window_s=60.0, consecutive_windows=3, disk_baseline_s=120.0)
    engine = RuleEngine(settings, rules=[recorder])
    samples = build_series(600)
    engine.evaluate(samples)
    first, last, _ = recorder.received[-1]
    assert last - first >= 3 * 60.0 + 120.0 - settings.sample_interval_s
