"""Linux /proc (ve gerektiğinde /sys) dosyalarının salt-okunur ayrıştırıcıları.

Ayrıştırıcılar saf fonksiyonlardır (metin -> veri) ve testlerde örnek metinlerle
doğrulanır. ``ProcFsReader`` dosyaları yalnızca ``"r"`` kipinde açar; kök dizin
parametresi sayesinde testlerde sahte bir /proc ağacı kullanılabilir.

Kaynak: proc(5) kılavuz sayfası, Documentation/admin-guide/iostats.rst,
Documentation/accounting/psi.rst (Linux çekirdeği belgeleri).
"""
from __future__ import annotations

import os
import re
from typing import Dict, Iterable, Optional, Tuple

from ..core.models import CpuTimes, DiskCounters, MemoryInfo, PressureInfo, VmCounters

SECTOR_SIZE = 512  # /proc/diskstats sektör birimi çekirdekte her zaman 512 bayttır

#: Fiziksel olmayan ya da başka aygıtların üzerine kurulu (çift sayıma yol açan) aygıtlar
_VIRTUAL_DISK_PREFIXES = ("loop", "ram", "zram", "dm-", "md", "sr", "fd", "nbd")
_WHOLE_DISK_RE = re.compile(r"^(?:[shv]d[a-z]+|xvd[a-z]+|nvme\d+n\d+|mmcblk\d+)$")


def clock_ticks_per_second() -> int:
    """/proc/stat değerlerinin birimi olan USER_HZ (genellikle 100)."""
    try:
        value = os.sysconf("SC_CLK_TCK")
        if value and value > 0:
            return int(value)
    except (ValueError, OSError, AttributeError):
        pass
    return 100


# ---------------------------------------------------------------------------
# Saf ayrıştırıcılar
# ---------------------------------------------------------------------------


def parse_meminfo(text: str) -> Dict[str, int]:
    """/proc/meminfo -> {anahtar: bayt}. "kB" birimli değerler bayta çevrilir."""
    result: Dict[str, int] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, _, rest = line.partition(":")
        parts = rest.split()
        if not parts:
            continue
        try:
            value = int(parts[0])
        except ValueError:
            continue
        if len(parts) > 1 and parts[1].lower() == "kb":
            value *= 1024
        result[key.strip()] = value
    return result


def meminfo_to_memory(values: Dict[str, int]) -> MemoryInfo:
    """meminfo sözlüğünden MemoryInfo üretir.

    MemAvailable 3.14 öncesi çekirdeklerde yoktur; bu durumda
    MemFree + Buffers + Cached ile kaba bir tahmin yapılır ve işaretlenir.
    """
    if "MemTotal" not in values or "MemFree" not in values:
        raise ValueError("meminfo içinde MemTotal/MemFree yok")
    total = values["MemTotal"]
    free = values["MemFree"]
    buffers = values.get("Buffers", 0)
    cached = values.get("Cached", 0)
    estimated = "MemAvailable" not in values
    available = values["MemAvailable"] if not estimated else free + buffers + cached
    return MemoryInfo(
        total=total,
        available=min(available, total),
        free=free,
        buffers=buffers,
        cached=cached,
        swap_total=values.get("SwapTotal", 0),
        swap_free=values.get("SwapFree", 0),
        available_estimated=estimated,
    )


def parse_stat(text: str, ticks_per_second: int = 100
               ) -> Tuple[CpuTimes, Optional[int], Optional[int]]:
    """/proc/stat -> (toplam CpuTimes [saniye], procs_running, procs_blocked).

    guest/guest_nice alanları çekirdekte zaten user/nice içinde sayıldığından
    çift sayımı önlemek için kullanılmaz.
    """
    cpu: Optional[CpuTimes] = None
    running: Optional[int] = None
    blocked: Optional[int] = None
    hz = float(ticks_per_second)
    for line in text.splitlines():
        parts = line.split()
        if not parts:
            continue
        if parts[0] == "cpu":
            nums = [int(x) for x in parts[1:9]]
            if len(nums) < 4:
                raise ValueError("/proc/stat cpu satırı beklenenden kısa")
            nums += [0] * (8 - len(nums))
            cpu = CpuTimes(*(n / hz for n in nums))
        elif parts[0] == "procs_running" and len(parts) > 1:
            running = int(parts[1])
        elif parts[0] == "procs_blocked" and len(parts) > 1:
            blocked = int(parts[1])
    if cpu is None:
        raise ValueError("/proc/stat içinde toplam cpu satırı yok")
    return cpu, running, blocked


def parse_vmstat(text: str) -> VmCounters:
    """/proc/vmstat içinden swap ve sayfa hatası sayaçlarını alır."""
    wanted = {"pswpin", "pswpout", "pgmajfault", "pgfault"}
    found: Dict[str, int] = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0] in wanted:
            try:
                found[parts[0]] = int(parts[1])
            except ValueError:
                continue
    return VmCounters(
        pswpin=found.get("pswpin"),
        pswpout=found.get("pswpout"),
        pgmajfault=found.get("pgmajfault"),
        pgfault=found.get("pgfault"),
    )


def parse_diskstats(text: str) -> Dict[str, DiskCounters]:
    """/proc/diskstats -> {aygıt adı: DiskCounters}. Filtreleme yapılmaz."""
    result: Dict[str, DiskCounters] = {}
    for line in text.splitlines():
        parts = line.split()
        # major minor name + en az 11 alan (2.6+ çekirdekler)
        if len(parts) < 14:
            continue
        name = parts[2]
        try:
            reads = int(parts[3])
            sectors_read = int(parts[5])
            writes = int(parts[7])
            sectors_written = int(parts[9])
            busy_ms = int(parts[12])
        except ValueError:
            continue
        result[name] = DiskCounters(
            read_bytes=sectors_read * SECTOR_SIZE,
            write_bytes=sectors_written * SECTOR_SIZE,
            busy_ms=busy_ms,
            read_count=reads,
            write_count=writes,
        )
    return result


def is_physical_disk(name: str, block_devices: Optional[Iterable[str]] = None) -> bool:
    """Bir aygıtın toplam G/Ç hesabına katılıp katılmayacağına karar verir.

    ``block_devices`` (/sys/block içeriği) verilirse yalnızca bütün diskler
    (bölümler hariç) kabul edilir; verilmezse ad kalıbına bakılır. Sanal ve
    üst katman aygıtları (loop, dm, md, zram...) çift sayımı önlemek için dışlanır.
    """
    if name.startswith(_VIRTUAL_DISK_PREFIXES):
        return False
    if block_devices is not None:
        return name in set(block_devices)
    return bool(_WHOLE_DISK_RE.match(name))


def parse_loadavg(text: str) -> float:
    parts = text.split()
    if not parts:
        raise ValueError("/proc/loadavg boş")
    return float(parts[0])


def parse_pressure(text: str) -> Dict[str, float]:
    """/proc/pressure/<kaynak> -> {"some": avg10, "full": avg10}."""
    result: Dict[str, float] = {}
    for line in text.splitlines():
        parts = line.split()
        if not parts or parts[0] not in ("some", "full"):
            continue
        for item in parts[1:]:
            key, _, value = item.partition("=")
            if key == "avg10":
                try:
                    result[parts[0]] = float(value)
                except ValueError:
                    pass
    return result


# ---------------------------------------------------------------------------
# Dosya okuyucu
# ---------------------------------------------------------------------------


class ProcFsReader:
    """/proc ve /sys altındaki seçilmiş dosyaları salt-okunur okur."""

    def __init__(self, proc_root: str = "/proc", sys_root: str = "/sys",
                 ticks_per_second: Optional[int] = None) -> None:
        self.proc_root = proc_root
        self.sys_root = sys_root
        self.ticks_per_second = ticks_per_second or clock_ticks_per_second()

    def _read(self, *parts: str) -> str:
        path = os.path.join(self.proc_root, *parts)
        # Yalnızca okuma kipi; /proc dosyalarının hepsinin yazılamaz olduğu varsayılmaz,
        # bu yüzden hiçbir koşulda yazma kipi kullanılmaz.
        with open(path, "r", encoding="ascii", errors="replace") as handle:
            return handle.read()

    def available(self) -> bool:
        return os.path.isfile(os.path.join(self.proc_root, "stat"))

    def read_cpu(self) -> Tuple[CpuTimes, Optional[int], Optional[int]]:
        return parse_stat(self._read("stat"), self.ticks_per_second)

    def read_memory(self) -> MemoryInfo:
        return meminfo_to_memory(parse_meminfo(self._read("meminfo")))

    def read_vm(self) -> VmCounters:
        return parse_vmstat(self._read("vmstat"))

    def read_load1(self) -> float:
        return parse_loadavg(self._read("loadavg"))

    def block_devices(self) -> Optional[Tuple[str, ...]]:
        """/sys/block içeriği (yalnızca listeleme). Okunamazsa None."""
        try:
            return tuple(sorted(os.listdir(os.path.join(self.sys_root, "block"))))
        except OSError:
            return None

    def read_disks(self) -> Dict[str, DiskCounters]:
        allowed = self.block_devices()
        raw = parse_diskstats(self._read("diskstats"))
        return {name: c for name, c in raw.items() if is_physical_disk(name, allowed)}

    def read_pressure(self) -> Optional[PressureInfo]:
        """PSI desteklenmiyorsa ya da okunamıyorsa None döner (özellik algılama)."""
        values: Dict[str, Dict[str, float]] = {}
        for resource in ("memory", "cpu", "io"):
            try:
                values[resource] = parse_pressure(self._read("pressure", resource))
            except OSError:
                values[resource] = {}
        if not any(values.values()):
            return None
        return PressureInfo(
            memory_some=values["memory"].get("some"),
            memory_full=values["memory"].get("full"),
            cpu_some=values["cpu"].get("some"),
            io_some=values["io"].get("some"),
        )
