"""Normalizasyon ve sınırlı geçmiş tamponu testleri."""
import threading

import pytest

from conftest import T0, make_sample
from pardusinsight.core.history import HistoryBuffer, since
from pardusinsight.core.models import (CpuTimes, DiskCounters, MemoryInfo, RawSnapshot,
                                       VmCounters)
from pardusinsight.core.normalize import Normalizer

GIB = 1024 ** 3


def raw(mono, wall=None, cpu=(10, 0, 5, 80, 5, 0, 0, 0), vm=(0, 0, 0, 0),
        disk=(0, 0, 0), mem=(8 * GIB, 4 * GIB, 2 * GIB, 1 * GIB)):
    total, avail, swap_total, swap_free = mem
    return RawSnapshot(
        timestamp=T0 + mono if wall is None else wall, monotonic=mono,
        cpu_times=CpuTimes(*cpu), cpu_count=4,
        memory=MemoryInfo(total=total, available=avail, free=avail // 2,
                          swap_total=swap_total, swap_free=swap_free),
        vm=VmCounters(*vm),
        disks={"sda": DiskCounters(read_bytes=disk[0], write_bytes=disk[1], busy_ms=disk[2])},
    )


def test_first_sample_has_gauges_but_no_rates():
    s = Normalizer().update(raw(0.0))
    assert s.cpu_percent is None and s.swap_in_pages_per_s is None
    assert s.disk_read_bytes_per_s is None
    assert s.mem_available_percent == 50.0 and s.swap_used_percent == 50.0


def test_cpu_percent_from_deltas():
    n = Normalizer()
    n.update(raw(0.0, cpu=(10, 0, 5, 80, 5, 0, 0, 0)))
    # Δuser=30 Δsystem=10 Δidle=50 Δiowait=10 -> meşgul 40/100
    s = n.update(raw(2.0, cpu=(40, 0, 15, 130, 15, 0, 0, 0)))
    assert s.cpu_percent == pytest.approx(40.0)
    assert s.cpu_user_percent == pytest.approx(30.0)
    assert s.cpu_iowait_percent == pytest.approx(10.0)
    assert s.interval_s == 2.0


def test_counter_reset_gives_none_instead_of_negative():
    n = Normalizer()
    n.update(raw(0.0, vm=(100, 100, 100, 100), disk=(1000, 1000, 100)))
    s = n.update(raw(2.0, cpu=(5, 0, 1, 10, 0, 0, 0, 0), vm=(10, 10, 10, 10), disk=(1, 1, 1)))
    assert s.cpu_percent is None
    assert s.swap_in_pages_per_s is None and s.major_faults_per_s is None
    assert s.disk_read_bytes_per_s is None


def test_swap_and_major_fault_rates():
    n = Normalizer()
    n.update(raw(0.0, vm=(100, 200, 50, 0)))
    s = n.update(raw(2.0, vm=(300, 600, 450, 0)))
    assert (s.swap_in_pages_per_s, s.swap_out_pages_per_s) == (100.0, 200.0)
    assert s.major_faults_per_s == 200.0
    assert s.swap_activity_pages_per_s == 300.0


def test_disk_rates_and_busy_percent_clamped():
    n = Normalizer()
    n.update(raw(0.0, disk=(0, 0, 0)))
    s = n.update(raw(2.0, disk=(4_000_000, 2_000_000, 2500)))  # 2,5 sn meşgul / 2 sn
    assert s.disk_read_bytes_per_s == 2_000_000.0
    assert s.disk_write_bytes_per_s == 1_000_000.0
    assert s.disk_busy_percent == 100.0
    assert s.disk_total_bytes_per_s == 3_000_000.0


def test_timestamps_follow_monotonic_clock_when_wall_clock_jumps():
    n = Normalizer()
    a = n.update(raw(10.0, wall=T0))
    b = n.update(raw(12.0, wall=T0 - 3600))  # sistem saati 1 saat geri alındı
    assert b.timestamp - a.timestamp == pytest.approx(2.0)


def test_no_swap_configured_reports_zero_percent():
    s = Normalizer().update(raw(0.0, mem=(8 * GIB, 4 * GIB, 0, 0)))
    assert s.swap_used_percent == 0.0 and s.swap_total_bytes == 0


# --------------------------------------------------------------------------- tampon
def test_history_bounded_to_30_minutes_at_2s():
    buf = HistoryBuffer(max_age_s=1800.0, min_interval_s=1.0)
    for i in range(2000):  # ~66 dakikalık veri
        buf.append(make_sample(T0 + i * 2.0))
    assert len(buf) == 901
    assert buf.duration_s() == pytest.approx(1800.0)
    assert buf.snapshot()[0].timestamp == T0 + (2000 - 901) * 2.0


def test_history_hard_capacity_limit_with_fast_sampling():
    buf = HistoryBuffer(max_age_s=60.0, min_interval_s=1.0)
    for i in range(1000):  # 0,1 sn aralık: yaş sınırı tek başına yetmezdi
        buf.append(make_sample(T0 + i * 0.1))
    assert len(buf) <= buf.capacity == 61


def test_last_seconds_window_and_since():
    buf = HistoryBuffer(max_age_s=600.0)
    buf.extend(make_sample(T0 + i * 2.0) for i in range(100))
    window = buf.last_seconds(10.0)
    assert [s.timestamp - T0 for s in window] == [188.0, 190.0, 192.0, 194.0, 196.0, 198.0]
    assert len(since(buf.snapshot(), T0 + 190.0)) == 5


def test_backward_timestamp_resets_history():
    buf = HistoryBuffer()
    buf.extend(make_sample(T0 + i) for i in range(5))
    buf.append(make_sample(T0 - 100))
    assert len(buf) == 1


def test_concurrent_append_and_snapshot_is_safe():
    buf = HistoryBuffer(max_age_s=30.0, min_interval_s=0.01)
    errors = []

    def writer():
        for i in range(5000):
            buf.append(make_sample(T0 + i * 0.01))

    def reader():
        try:
            for _ in range(500):
                snap = buf.snapshot()
                assert all(a.timestamp <= b.timestamp for a, b in zip(snap, snap[1:]))
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=writer), threading.Thread(target=reader)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
