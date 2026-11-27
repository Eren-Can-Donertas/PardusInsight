"""Sistem geneli metrik kolektörü: önce /proc, olmazsa psutil yedeği.

Her bölüm (CPU, bellek, vmstat, disk, yük, PSI) bağımsız okunur; bir bölümün
başarısız olması diğerlerini etkilemez. Hata mesajları RawSnapshot.errors
alanında kullanıcıya iletilir, uygulama çökmez.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Callable, Dict, List, Optional, Tuple, TypeVar

from ..core.models import CpuTimes, DiskCounters, MemoryInfo, RawSnapshot, VmCounters
from .procfs import ProcFsReader, is_physical_disk

T = TypeVar("T")
logger = logging.getLogger(__name__)

_READ_ERRORS = (OSError, ValueError, KeyError, IndexError)


def load_psutil() -> Optional[Any]:
    """psutil kuruluysa modülü döndürür; değilse None (sentetik mod için)."""
    try:
        import psutil  # noqa: WPS433 (isteğe bağlı bağımlılık)
    except ImportError:
        return None
    return psutil


class LinuxSystemCollector:
    """Canlı sistemden RawSnapshot üretir."""

    source_name = "linux"

    def __init__(self, reader: Optional[ProcFsReader] = None, psutil_module: Any = "auto",
                 clock: Callable[[], float] = time.time,
                 monotonic: Callable[[], float] = time.monotonic) -> None:
        self.reader = reader or ProcFsReader()
        # Any: psutil isteğe bağlıdır; yedek fonksiyonlar yalnızca modül yüklüyse çağrılır
        self.psutil: Any = load_psutil() if psutil_module == "auto" else psutil_module
        self._clock = clock
        self._monotonic = monotonic
        self._cpu_count = os.cpu_count()
        self._reported: set = set()  # aynı hatayı her turda WARNING olarak tekrarlamamak için

    # -- yardımcı -----------------------------------------------------------
    def _section(self, name: str, primary: Callable[[], T],
                 fallback: Optional[Callable[[], T]], errors: List[str]) -> Optional[T]:
        try:
            return primary()
        except _READ_ERRORS as exc:
            message = f"{name}: /proc okunamadı ({type(exc).__name__})"
            level = logging.DEBUG if name in self._reported else logging.WARNING
            self._reported.add(name)
            logger.log(level, "%s: %s", message, exc)
        if fallback is not None and self.psutil is not None:
            try:
                value = fallback()
                errors.append(message + "; psutil yedeği kullanıldı")
                return value
            except Exception as exc:  # psutil beklenmedik hata verebilir
                errors.append(f"{message}; psutil yedeği de başarısız ({type(exc).__name__})")
                return None
        errors.append(message + "; veri alınamadı")
        return None

    # -- psutil yedekleri ------------------------------------------------------
    def _psutil_cpu(self) -> Tuple[CpuTimes, Optional[int], Optional[int]]:
        t = self.psutil.cpu_times()
        cpu = CpuTimes(
            user=t.user, nice=getattr(t, "nice", 0.0), system=t.system, idle=t.idle,
            iowait=getattr(t, "iowait", 0.0), irq=getattr(t, "irq", 0.0),
            softirq=getattr(t, "softirq", 0.0), steal=getattr(t, "steal", 0.0),
        )
        return cpu, None, None

    def _psutil_memory(self) -> MemoryInfo:
        vm = self.psutil.virtual_memory()
        sw = self.psutil.swap_memory()
        return MemoryInfo(
            total=int(vm.total), available=int(vm.available), free=int(vm.free),
            buffers=int(getattr(vm, "buffers", 0)), cached=int(getattr(vm, "cached", 0)),
            swap_total=int(sw.total), swap_free=int(sw.free),
        )

    def _psutil_vm(self) -> VmCounters:
        sw = self.psutil.swap_memory()
        page = os.sysconf("SC_PAGE_SIZE") if hasattr(os, "sysconf") else 4096
        return VmCounters(pswpin=int(sw.sin) // page, pswpout=int(sw.sout) // page)

    def _psutil_disks(self) -> Dict[str, DiskCounters]:
        per_disk = self.psutil.disk_io_counters(perdisk=True) or {}
        allowed = self.reader.block_devices()
        return {
            name: DiskCounters(
                read_bytes=int(c.read_bytes), write_bytes=int(c.write_bytes),
                busy_ms=int(getattr(c, "busy_time", 0)),
                read_count=int(c.read_count), write_count=int(c.write_count),
            )
            for name, c in per_disk.items() if is_physical_disk(name, allowed)
        }

    def _psutil_load(self) -> float:
        return float(self.psutil.getloadavg()[0])

    # -- ana giriş --------------------------------------------------------------
    def collect(self) -> RawSnapshot:
        errors: List[str] = []
        mono = self._monotonic()
        wall = self._clock()
        cpu_part = self._section("CPU (/proc/stat)", self.reader.read_cpu,
                                 self._psutil_cpu, errors)
        memory = self._section("Bellek (/proc/meminfo)", self.reader.read_memory,
                               self._psutil_memory, errors)
        vm = self._section("Sanal bellek (/proc/vmstat)", self.reader.read_vm,
                           self._psutil_vm, errors)
        disks = self._section("Disk (/proc/diskstats)", self.reader.read_disks,
                              self._psutil_disks, errors)
        load1 = self._section("Yük (/proc/loadavg)", self.reader.read_load1,
                              self._psutil_load, errors)
        try:
            pressure = self.reader.read_pressure()
        except _READ_ERRORS:
            pressure = None
        cpu_times, running, blocked = cpu_part if cpu_part else (None, None, None)
        return RawSnapshot(
            timestamp=wall,
            monotonic=mono,
            cpu_times=cpu_times,
            cpu_count=self._cpu_count,
            memory=memory,
            vm=vm,
            disks=disks,
            load1=load1,
            procs_running=running,
            procs_blocked=blocked,
            pressure=pressure,
            errors=tuple(errors),
            source=self.source_name,
        )
