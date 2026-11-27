"""Gerçek /proc okumalarının psutil ile tutarlılığı (PDF: en az 10 örnek karşılaştırma).

Yalnızca Linux'ta ve psutil kuruluyken çalışır. İki kaynak aynı anda
okunamadığı için anlık değişen değerlerde makul tolerans kullanılır.
"""
import os
import time

import pytest

from conftest import HAS_PSUTIL, IS_LINUX
from pardusinsight.collectors.procfs import ProcFsReader
from pardusinsight.collectors.system import LinuxSystemCollector
from pardusinsight.core.normalize import Normalizer

pytestmark = [pytest.mark.linux,
              pytest.mark.skipif(not (IS_LINUX and HAS_PSUTIL),
                                 reason="gerçek Linux /proc ve psutil gerekir")]

ROUNDS = 10


@pytest.fixture(scope="module")
def ps():
    import psutil
    return psutil


def test_memory_matches_psutil_over_10_samples(ps):
    reader = ProcFsReader()
    for _ in range(ROUNDS):
        mem = reader.read_memory()
        vm = ps.virtual_memory()
        sw = ps.swap_memory()
        assert mem.total == vm.total
        assert mem.swap_total == sw.total
        assert abs(mem.available - vm.available) <= 0.05 * vm.total
        assert abs((mem.swap_total - mem.swap_free) - sw.used) <= 0.05 * max(sw.total, 1)
        time.sleep(0.05)


def test_cpu_times_match_psutil_over_10_samples(ps):
    reader = ProcFsReader()
    for _ in range(ROUNDS):
        cpu, _running, _blocked = reader.read_cpu()
        ref = ps.cpu_times()
        # Kümülatif sayaçlar; iki okuma arasında geçen kısa süre kadar fark olabilir
        tolerance = 0.5 * (os.cpu_count() or 1)
        assert cpu.user == pytest.approx(ref.user, abs=tolerance)
        assert cpu.system == pytest.approx(ref.system, abs=tolerance)
        assert cpu.idle == pytest.approx(ref.idle, abs=tolerance)
        time.sleep(0.05)


def test_disk_counters_are_monotonic_and_consistent_with_psutil(ps):
    reader = ProcFsReader()
    previous = reader.read_disks()
    if not previous:
        pytest.skip("fiziksel disk bulunamadı (ör. kapsayıcı ortamı)")
    for _ in range(ROUNDS):
        time.sleep(0.05)
        disks = reader.read_disks()
        ref = ps.disk_io_counters(perdisk=True)
        for name, counters in disks.items():
            assert counters.read_bytes >= previous[name].read_bytes
            if name in ref:
                assert abs(counters.read_bytes - ref[name].read_bytes) <= 64 * 1024 * 1024
        previous = disks


def test_live_cpu_percent_close_to_psutil(ps):
    collector = LinuxSystemCollector()
    norm = Normalizer()
    norm.update(collector.collect())
    ps.cpu_percent(interval=None)
    diffs = []
    for _ in range(ROUNDS):
        time.sleep(0.2)
        ours = norm.update(collector.collect()).cpu_percent
        theirs = ps.cpu_percent(interval=None)
        assert ours is not None and 0.0 <= ours <= 100.0
        diffs.append(abs(ours - theirs))
    # Okumalar aynı anda yapılamadığından tek tek değil, ortalama fark değerlendirilir
    assert sum(diffs) / len(diffs) < 15.0


def test_live_collect_has_no_errors_as_standard_user():
    raw = LinuxSystemCollector().collect()
    assert raw.errors == ()
    assert raw.cpu_times is not None and raw.memory is not None and raw.vm is not None
