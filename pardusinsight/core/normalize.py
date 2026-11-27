"""Ham kümülatif sayaçları hız ve yüzdelere dönüştürür.

Kurallar:
* İlk örnekte fark alınamayacağı için hız alanları None olur.
* Bir sayaç azalırsa (çekirdek sayaç sıfırlaması, CPU hotplug, taşma) negatif
  hız üretmek yerine o alan None bırakılır.
* Örnek zaman damgası, ilk ölçümün duvar saatine monotonik saat farkı
  eklenerek hesaplanır; böylece NTP/saat değişiklikleri zaman pencerelerini
  bozmaz.
"""
from __future__ import annotations

from typing import Dict, Optional

from ..collectors.processes import top_processes
from .models import DiskCounters, ProcessSnapshot, RawSnapshot, SystemSample


def _clamp_pct(value: float) -> float:
    return max(0.0, min(100.0, value))


def _rate(cur: Optional[int], prev: Optional[int], dt: float) -> Optional[float]:
    if cur is None or prev is None or dt <= 0 or cur < prev:
        return None
    return (cur - prev) / dt


class Normalizer:
    """Ardışık RawSnapshot'lardan SystemSample üretir (durumludur)."""

    def __init__(self, top_n: int = 5) -> None:
        self.top_n = top_n
        self._prev: Optional[RawSnapshot] = None
        self._anchor: Optional[tuple] = None  # (duvar saati, monotonik)

    def reset(self) -> None:
        self._prev = None
        self._anchor = None

    def _timestamp(self, raw: RawSnapshot) -> float:
        if self._anchor is None:
            self._anchor = (raw.timestamp, raw.monotonic)
        wall0, mono0 = self._anchor
        return wall0 + (raw.monotonic - mono0)

    def update(self, raw: RawSnapshot,
               processes: Optional[ProcessSnapshot] = None) -> SystemSample:
        prev = self._prev
        dt = raw.monotonic - prev.monotonic if prev is not None else 0.0
        has_delta = prev is not None and dt > 0
        values: Dict[str, object] = {
            "timestamp": self._timestamp(raw),
            "interval_s": round(dt, 3) if has_delta else None,
            "cpu_count": raw.cpu_count,
            "load1": raw.load1,
            "procs_running": raw.procs_running,
            "procs_blocked": raw.procs_blocked,
        }

        # CPU yüzdeleri (psutil ile aynı tanım: meşgul = toplam - idle - iowait)
        if prev is not None and has_delta and raw.cpu_times is not None \
                and prev.cpu_times is not None:
            cur_t, prev_t = raw.cpu_times, prev.cpu_times
            deltas = {name: getattr(cur_t, name) - getattr(prev_t, name)
                      for name in ("user", "nice", "system", "idle", "iowait",
                                   "irq", "softirq", "steal")}
            total = sum(deltas.values())
            if total > 0 and all(d >= -1e-9 for d in deltas.values()):
                busy = total - deltas["idle"] - deltas["iowait"]
                values["cpu_percent"] = round(_clamp_pct(busy / total * 100.0), 2)
                values["cpu_user_percent"] = round(
                    _clamp_pct((deltas["user"] + deltas["nice"]) / total * 100.0), 2)
                values["cpu_system_percent"] = round(_clamp_pct(
                    (deltas["system"] + deltas["irq"] + deltas["softirq"]) / total * 100.0), 2)
                values["cpu_iowait_percent"] = round(
                    _clamp_pct(deltas["iowait"] / total * 100.0), 2)
                values["cpu_steal_percent"] = round(
                    _clamp_pct(deltas["steal"] / total * 100.0), 2)

        # Bellek ve swap (anlık göstergeler)
        mem = raw.memory
        if mem is not None and mem.total > 0:
            values["mem_total_bytes"] = mem.total
            values["mem_available_bytes"] = mem.available
            values["mem_available_percent"] = round(mem.available / mem.total * 100.0, 2)
            values["mem_used_percent"] = round(
                (mem.total - mem.available) / mem.total * 100.0, 2)
            values["swap_total_bytes"] = mem.swap_total
            used = max(mem.swap_total - mem.swap_free, 0)
            values["swap_used_bytes"] = used
            values["swap_used_percent"] = (round(used / mem.swap_total * 100.0, 2)
                                           if mem.swap_total > 0 else 0.0)

        # Swap ve sayfa hatası hızları
        if prev is not None and has_delta and raw.vm is not None and prev.vm is not None:
            values["swap_in_pages_per_s"] = _round(_rate(raw.vm.pswpin, prev.vm.pswpin, dt))
            values["swap_out_pages_per_s"] = _round(_rate(raw.vm.pswpout, prev.vm.pswpout, dt))
            values["major_faults_per_s"] = _round(
                _rate(raw.vm.pgmajfault, prev.vm.pgmajfault, dt))
            all_faults = _rate(raw.vm.pgfault, prev.vm.pgfault, dt)
            major = _rate(raw.vm.pgmajfault, prev.vm.pgmajfault, dt)
            if all_faults is not None and major is not None:
                # pgfault tüm hataları sayar; minor = toplam - major
                values["minor_faults_per_s"] = _round(max(all_faults - major, 0.0))

        # Disk G/Ç: kümülatif baytlar ilk örnekte de bilinir, hızlar fark gerektirir
        if raw.disks:
            values["disk_read_bytes_total"] = sum(d.read_bytes for d in raw.disks.values())
            values["disk_write_bytes_total"] = sum(d.write_bytes for d in raw.disks.values())
        if prev is not None and has_delta and raw.disks is not None \
                and prev.disks is not None:
            disk = _disk_rates(raw.disks, prev.disks, dt)
            if disk is not None:
                values.update(disk)

        # PSI
        if raw.pressure is not None:
            values["psi_memory_some"] = raw.pressure.memory_some
            values["psi_memory_full"] = raw.pressure.memory_full
            values["psi_cpu_some"] = raw.pressure.cpu_some
            values["psi_io_some"] = raw.pressure.io_some

        top_cpu, top_mem, top_io = top_processes(processes, self.top_n)
        errors = list(raw.errors)
        if processes is not None and processes.error:
            errors.append(processes.error)

        self._prev = raw
        return SystemSample(top_cpu=top_cpu, top_memory=top_mem, top_io=top_io,
                            errors=tuple(errors), **values)  # type: ignore[arg-type]


def _round(value: Optional[float], digits: int = 2) -> Optional[float]:
    return None if value is None else round(value, digits)


def _disk_rates(cur: Dict[str, DiskCounters], prev: Dict[str, DiskCounters],
                dt: float) -> Optional[Dict[str, float]]:
    """Ortak aygıtlar üzerinden toplam okuma/yazma hızı ve en yüksek meşguliyet."""
    common = [name for name in cur if name in prev]
    if not common:
        return None
    read = write = 0.0
    busy_max = 0.0
    valid = False
    for name in common:
        c, p = cur[name], prev[name]
        r = _rate(c.read_bytes, p.read_bytes, dt)
        w = _rate(c.write_bytes, p.write_bytes, dt)
        b = _rate(c.busy_ms, p.busy_ms, dt)
        if r is None or w is None:
            continue  # bu aygıtta sayaç sıfırlanmış
        valid = True
        read += r
        write += w
        if b is not None:
            busy_max = max(busy_max, _clamp_pct(b / 1000.0 * 100.0))
    if not valid:
        return None
    return {
        "disk_read_bytes_per_s": round(read, 1),
        "disk_write_bytes_per_s": round(write, 1),
        "disk_busy_percent": round(busy_max, 2),
    }
