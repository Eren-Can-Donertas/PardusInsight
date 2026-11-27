"""Sistem ve süreç kolektörlerinin hata toleransı testleri."""
import subprocess
import sys
import time
from collections import namedtuple
from types import SimpleNamespace

import pytest

from conftest import (FakeAccessDenied, FakeNoSuchProcess, FakeProcess, FakePsutil, linux_only,
                      proc_info)
from pardusinsight.collectors.processes import ProcessCollector, top_processes
from pardusinsight.collectors.procfs import ProcFsReader
from pardusinsight.collectors.system import LinuxSystemCollector

try:  # Kullanıcı veritabanı (pwd) yalnızca Unix'te vardır; Windows'ta uid metin olarak kalır
    import pwd  # noqa: F401
    HAS_PWD = True
except ImportError:  # pragma: no cover - Windows
    HAS_PWD = False

CpuT = namedtuple("CpuT", "user nice system idle iowait irq softirq steal")
Disk = namedtuple("Disk", "read_count write_count read_bytes write_bytes busy_time")


class FallbackPsutil:
    def cpu_times(self):
        return CpuT(1.0, 0.0, 1.0, 8.0, 0.0, 0.0, 0.0, 0.0)

    def virtual_memory(self):
        return SimpleNamespace(total=1000, available=400, free=100, buffers=10, cached=200)

    def swap_memory(self):
        return SimpleNamespace(total=500, free=300, sin=4096 * 3, sout=4096 * 5)

    def disk_io_counters(self, perdisk=True):
        return {"sda": Disk(1, 2, 512, 1024, 7), "loop0": Disk(1, 1, 1, 1, 1)}

    def getloadavg(self):
        return (0.25, 0.2, 0.1)


# --------------------------------------------------------------------------- sistem
def test_system_collector_reads_fake_proc_without_errors(fake_proc):
    proc, sysfs = fake_proc
    collector = LinuxSystemCollector(ProcFsReader(str(proc), str(sysfs), 100), psutil_module=None,
                                     clock=lambda: 100.0, monotonic=lambda: 5.0)
    raw = collector.collect()
    assert raw.errors == ()
    assert raw.cpu_times is not None and raw.memory is not None and raw.vm is not None
    assert sorted(raw.disks) == ["nvme0n1", "sda"]
    assert raw.procs_blocked == 1 and raw.load1 == pytest.approx(0.52)
    assert (raw.timestamp, raw.monotonic) == (100.0, 5.0)


def test_system_collector_falls_back_to_psutil(tmp_path):
    empty = tmp_path / "proc"
    empty.mkdir()
    sysfs = tmp_path / "sys"
    (sysfs / "block" / "sda").mkdir(parents=True)
    collector = LinuxSystemCollector(ProcFsReader(str(empty), str(sysfs)),
                                     psutil_module=FallbackPsutil())
    raw = collector.collect()
    assert raw.cpu_times.user == 1.0
    assert raw.memory.available == 400 and raw.memory.swap_free == 300
    assert raw.vm.pswpin == 3 and raw.vm.pgmajfault is None  # psutil'de karşılığı yok
    assert list(raw.disks) == ["sda"] and raw.disks["sda"].busy_ms == 7
    assert raw.load1 == 0.25
    assert any("psutil yedeği kullanıldı" in e for e in raw.errors)


def test_system_collector_without_any_source_does_not_crash(tmp_path):
    empty = tmp_path / "proc"
    empty.mkdir()
    raw = LinuxSystemCollector(ProcFsReader(str(empty), str(tmp_path)),
                               psutil_module=None).collect()
    assert raw.cpu_times is None and raw.memory is None and raw.disks is None
    assert len(raw.errors) == 5 and all("veri alınamadı" in e for e in raw.errors)


# --------------------------------------------------------------------------- süreçler
def test_process_collector_normalizes_cpu_by_core_count():
    ps = FakePsutil([FakeProcess(10, proc_info("derleyici", cpu=200.0, uid=0))])
    snap = ProcessCollector(ps, cpu_count=4).collect()
    p = snap.processes[0]
    assert p.cpu_percent == 50.0  # 2 çekirdek dolu / 4 çekirdek
    assert p.username == ("root" if HAS_PWD else "0")
    assert p.rss_bytes == 10 * 1024 * 1024


def test_vanished_process_is_skipped_without_crash():
    ps = FakePsutil([FakeProcess(1, proc_info("a")),
                     FakeProcess(2, raise_exc=FakeNoSuchProcess()),
                     FakeProcess(3, proc_info("c"))])
    snap = ProcessCollector(ps, cpu_count=1).collect()
    assert [p.pid for p in snap.processes] == [1, 3]
    assert snap.vanished == 1 and snap.error is None


def test_access_denied_fields_become_none_and_are_counted():
    info = proc_info("root-servisi", io=None)
    ps = FakePsutil([FakeProcess(5, info), FakeProcess(6, raise_exc=FakeAccessDenied())])
    snap = ProcessCollector(ps, cpu_count=1).collect()
    assert len(snap.processes) == 1
    assert snap.processes[0].read_bytes_per_s is None
    assert snap.partial_access == 1 and snap.access_denied == 1


def test_io_rates_between_scans_and_pid_reuse():
    clock = iter([0.0, 2.0, 4.0])
    proc = FakeProcess(7, proc_info("kopya", io=(1000, 0), create_time=10.0))
    collector = ProcessCollector(FakePsutil([proc]), cpu_count=1, monotonic=lambda: next(clock))
    assert collector.collect().processes[0].read_bytes_per_s is None  # ilk tarama
    proc.info = proc_info("kopya", io=(5000, 2000), create_time=10.0)
    p = collector.collect().processes[0]
    assert p.read_bytes_per_s == 2000.0 and p.write_bytes_per_s == 1000.0
    # Aynı PID başka bir süreç tarafından yeniden kullanıldı: hız hesaplanmamalı
    proc.info = proc_info("yeni", io=(9000, 0), create_time=99.0)
    assert collector.collect().processes[0].read_bytes_per_s is None


def test_process_iter_failure_returns_error_snapshot():
    snap = ProcessCollector(FakePsutil(iter_error=OSError("yok")), cpu_count=1).collect()
    assert snap.processes == () and "alınamadı" in snap.error


def test_iteration_interrupted_midway_keeps_partial_results():
    class Broken(FakePsutil):
        def process_iter(self):
            def gen():
                yield FakeProcess(1, proc_info("a"))
                raise RuntimeError("beklenmedik")
            return gen()

    snap = ProcessCollector(Broken(), cpu_count=1).collect()
    assert [p.pid for p in snap.processes] == [1]
    assert "yarıda kesildi" in snap.error


def test_top_processes_ordering():
    ps = FakePsutil([FakeProcess(1, proc_info("az", cpu=1, rss_mib=900)),
                     FakeProcess(2, proc_info("cok", cpu=90, rss_mib=10)),
                     FakeProcess(3, proc_info("orta", cpu=40, rss_mib=100))])
    top_cpu, top_mem, _ = top_processes(ProcessCollector(ps, cpu_count=1).collect(), n=2)
    assert [p.name for p in top_cpu] == ["cok", "orta"]
    assert [p.name for p in top_mem] == ["az", "orta"]
    assert top_processes(None) == ((), (), ())


@linux_only
def test_real_scan_survives_processes_exiting_during_scan():
    import psutil

    collector = ProcessCollector(psutil)
    children = []
    try:
        for _ in range(5):
            children.append(subprocess.Popen([sys.executable, "-c", "pass"]))
            snap = collector.collect()
            assert snap.total_seen > 0 and snap.error is None
            time.sleep(0.05)
    finally:
        for child in children:
            child.wait(timeout=10)
    # Çocuklar sonlandıktan sonra da tarama sorunsuz
    assert collector.collect().error is None


def test_permission_error_on_proc_file_is_reported_not_raised(fake_proc, monkeypatch):
    proc, sysfs = fake_proc
    reader = ProcFsReader(str(proc), str(sysfs), 100)

    def denied():
        raise PermissionError(13, "İzin reddedildi", str(proc / "meminfo"))

    monkeypatch.setattr(reader, "read_memory", denied)
    raw = LinuxSystemCollector(reader, psutil_module=None).collect()
    assert raw.memory is None and raw.cpu_times is not None
    assert raw.errors == ("Bellek (/proc/meminfo): /proc okunamadı (PermissionError); "
                          "veri alınamadı",)
