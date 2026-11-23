"""Ortak test yardımcıları: örnek üreticiler, sahte /proc ağacı ve sahte psutil."""
from __future__ import annotations

import os
import sys
from collections import namedtuple
from dataclasses import replace
from typing import Callable, Dict, List, Optional

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pardusinsight.config import AnalysisSettings  # noqa: E402
from pardusinsight.core.models import ProcessBrief, SystemSample  # noqa: E402

T0 = 1_767_225_600.0
MIB = 1024 * 1024

IS_LINUX = sys.platform.startswith("linux") and os.path.isfile("/proc/stat")
try:
    import psutil  # noqa: F401
    HAS_PSUTIL = True
except ImportError:  # pragma: no cover
    HAS_PSUTIL = False

linux_only = pytest.mark.skipif(not (IS_LINUX and HAS_PSUTIL),
                                reason="gerçek Linux /proc ve psutil gerekir")

BASE_FIELDS: Dict[str, object] = dict(
    interval_s=2.0, cpu_percent=15.0, cpu_user_percent=11.0, cpu_system_percent=4.0,
    cpu_iowait_percent=1.0, cpu_steal_percent=0.0, cpu_count=4, load1=0.6,
    mem_total_bytes=8 * 1024 * MIB, mem_available_bytes=4 * 1024 * MIB,
    mem_available_percent=50.0, mem_used_percent=50.0, swap_total_bytes=2 * 1024 * MIB,
    swap_used_bytes=100 * MIB, swap_used_percent=5.0, swap_in_pages_per_s=0.0,
    swap_out_pages_per_s=0.0, major_faults_per_s=1.0, disk_read_bytes_per_s=0.5 * MIB,
    disk_write_bytes_per_s=0.5 * MIB, disk_busy_percent=3.0, psi_memory_some=0.0,
    psi_memory_full=0.0, psi_cpu_some=0.0, psi_io_some=0.0, procs_running=1,
    procs_blocked=0,
)


def make_sample(t: float, **overrides) -> SystemSample:
    fields = dict(BASE_FIELDS)
    if "mem_available_percent" in overrides and "mem_used_percent" not in overrides:
        avail = overrides["mem_available_percent"]
        fields["mem_used_percent"] = None if avail is None else 100.0 - float(avail)
    fields.update(overrides)
    return SystemSample(timestamp=t, **fields)


def build_series(n: int, fn: Optional[Callable[[int, float], dict]] = None,
                 interval: float = 2.0, start: float = T0) -> List[SystemSample]:
    """n örnek üretir; fn(i, geçen_süre) her örnek için alan geçersiz kılmalarını döndürür."""
    out = []
    for i in range(n):
        elapsed = i * interval
        out.append(make_sample(start + elapsed, **(fn(i, elapsed) if fn else {})))
    return out


@pytest.fixture
def settings() -> AnalysisSettings:
    return AnalysisSettings()


@pytest.fixture
def sample_factory():
    return make_sample


@pytest.fixture
def brief():
    def _brief(pid: int, name: str, cpu: float = 0.0, rss: int = 0, io: Optional[float] = None):
        return ProcessBrief(pid=pid, name=name, cpu_percent=cpu, rss_bytes=rss,
                            io_bytes_per_s=io)
    return _brief


# ---------------------------------------------------------------------------
# Sahte /proc ağacı
# ---------------------------------------------------------------------------

MEMINFO = """MemTotal:        8000000 kB
MemFree:          500000 kB
MemAvailable:    2000000 kB
Buffers:          100000 kB
Cached:          1500000 kB
SwapCached:        10000 kB
SwapTotal:       2000000 kB
SwapFree:        1500000 kB
HugePages_Total:       0
"""

STAT = """cpu  1000 50 300 8000 100 10 20 5 7 0
cpu0 500 25 150 4000 50 5 10 2 3 0
intr 12345 0 0
ctxt 99999
btime 1700000000
processes 4242
procs_running 3
procs_blocked 1
"""

VMSTAT = """nr_free_pages 12345
pgfault 1000000
pgmajfault 2000
pswpin 300
pswpout 400
"""

DISKSTATS = """   7       0 loop0 100 0 2000 10 0 0 0 0 0 20 20 0 0 0 0
 259       0 nvme0n1 1000 10 20000 500 2000 20 40000 800 0 900 1300 0 0 0 0 0 0
 259       1 nvme0n1p1 900 10 18000 450 1900 20 38000 750 0 850 1200 0 0 0 0
 253       0 dm-0 1000 0 20000 500 2000 0 40000 800 0 900 1300 0 0 0 0
   8       0 sda 10 0 80 1 5 0 40 1 0 2 2
"""

PRESSURE_MEMORY = ("some avg10=1.50 avg60=0.80 avg300=0.10 total=12345\n"
                   "full avg10=0.50 avg60=0.20 avg300=0.00 total=2345\n")


@pytest.fixture
def fake_proc(tmp_path):
    proc = tmp_path / "proc"
    sysfs = tmp_path / "sys"
    (proc / "pressure").mkdir(parents=True)
    for name in ("nvme0n1", "sda", "loop0", "dm-0"):
        (sysfs / "block" / name).mkdir(parents=True)
    (proc / "meminfo").write_text(MEMINFO)
    (proc / "stat").write_text(STAT)
    (proc / "vmstat").write_text(VMSTAT)
    (proc / "diskstats").write_text(DISKSTATS)
    (proc / "loadavg").write_text("0.52 0.48 0.40 2/1234 5678\n")
    (proc / "pressure" / "memory").write_text(PRESSURE_MEMORY)
    (proc / "pressure" / "io").write_text("some avg10=2.00 avg60=1.00 avg300=0.50 total=1\n")
    return proc, sysfs


# ---------------------------------------------------------------------------
# Sahte psutil
# ---------------------------------------------------------------------------

Uids = namedtuple("Uids", "real effective saved")
MemInfo = namedtuple("MemInfo", "rss vms")
IoCounters = namedtuple("IoCounters", "read_count write_count read_bytes write_bytes")


class FakeNoSuchProcess(Exception):
    pass


class FakeAccessDenied(Exception):
    pass


class FakeProcess:
    def __init__(self, pid: int, info: Optional[dict] = None,
                 raise_exc: Optional[BaseException] = None) -> None:
        self.pid = pid
        self.info = info or {}
        self.raise_exc = raise_exc

    def as_dict(self, attrs, ad_value=None):
        if self.raise_exc is not None:
            raise self.raise_exc
        return {a: self.info.get(a, ad_value) for a in attrs}


def proc_info(name: str, cpu: float = 0.0, rss_mib: int = 10, uid: int = 0,
              io: Optional[tuple] = (0, 0), create_time: float = 1.0) -> dict:
    return {
        "name": name, "uids": Uids(uid, uid, uid), "status": "sleeping",
        "cpu_percent": cpu, "memory_info": MemInfo(rss_mib * MIB, rss_mib * 2 * MIB),
        "memory_percent": 1.0, "num_threads": 2,
        "io_counters": None if io is None else IoCounters(0, 0, io[0], io[1]),
        "create_time": create_time,
    }


class FakePsutil:
    NoSuchProcess = FakeNoSuchProcess
    AccessDenied = FakeAccessDenied

    def __init__(self, procs=None, iter_error: Optional[BaseException] = None) -> None:
        self.procs = list(procs or [])
        self.iter_error = iter_error

    def process_iter(self):
        if self.iter_error is not None:
            raise self.iter_error
        return iter(list(self.procs))


@pytest.fixture
def fake_psutil_cls():
    return FakePsutil
