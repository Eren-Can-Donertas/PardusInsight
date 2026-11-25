"""Sentetik metrik kaynağı (gerçek sisteme hiçbir yük bindirmez).

Senaryolar, belirli sürelerde belirli kaynak durumlarını temsil eden
"evreler"den oluşur. Kaynak kümülatif sayaçlar üretir; böylece normalizasyon,
tampon ve kural motoru gerçek veriyle aynı yoldan test edilir. Zaman
simülasyondur: her collect() çağrısı saati ``step_s`` kadar ilerletir, bu
yüzden testler beklemeden saatlerce veri üretebilir.

Stres testi yerine kullanılır: hiçbir zaman gerçek CPU/bellek/disk yükü
oluşturmaz.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, fields, replace
from typing import Dict, List, Optional, Sequence, Tuple

from ..core.models import (CpuTimes, DiskCounters, MemoryInfo, PressureInfo,
                           ProcessInfo, ProcessSnapshot, RawSnapshot, VmCounters)

MIB = 1024 * 1024
GIB = 1024 * MIB

DEFAULT_START = 1_767_225_600.0  # 2026-01-01 00:00:00 UTC; testlerde sabit başlangıç


@dataclass(frozen=True)
class Phase:
    """Bir senaryo evresi: hedef metrik düzeyleri ve süresi."""

    name: str
    duration_s: float
    cpu_percent: float = 15.0
    cpu_iowait_percent: float = 1.0
    mem_available_percent: float = 55.0
    swap_used_percent: float = 5.0
    swap_pages_per_s: float = 0.0
    major_faults_per_s: float = 2.0
    disk_read_mib_s: float = 0.4
    disk_write_mib_s: float = 0.8
    disk_busy_percent: float = 3.0
    psi_memory_some: float = 0.0
    hot: Optional[str] = None  # "cpu" | "memory" | "io"
    description: str = ""


def _normal(duration: float, name: str = "normal") -> Phase:
    return Phase(name=name, duration_s=duration,
                 description="Olağan masaüstü kullanımı")


CPU_PHASE = dict(cpu_percent=95.0, hot="cpu",
                 description="Uzun süren derleme benzeri yüksek CPU kullanımı")
MEMORY_PHASE = dict(mem_available_percent=6.0, swap_used_percent=65.0,
                    swap_pages_per_s=600.0, major_faults_per_s=400.0,
                    psi_memory_some=25.0, cpu_percent=35.0, cpu_iowait_percent=8.0,
                    disk_read_mib_s=2.0, disk_write_mib_s=1.5, disk_busy_percent=30.0,
                    hot="memory",
                    description="Tarayıcı belleği büyüyor, swap etkinliği artıyor")
DISK_PHASE = dict(disk_read_mib_s=70.0, disk_write_mib_s=45.0, disk_busy_percent=92.0,
                  cpu_iowait_percent=15.0, cpu_percent=25.0, hot="io",
                  description="Büyük dosya kopyalama/yedekleme benzeri disk etkinliği")


def _spiky_cpu(total_s: float, high_s: float = 8.0, low_s: float = 22.0) -> List[Phase]:
    phases: List[Phase] = [_normal(60.0)]
    elapsed = 0.0
    while elapsed < total_s:
        phases.append(Phase(name="cpu-ani", duration_s=high_s, cpu_percent=98.0, hot="cpu",
                            description="Kısa CPU sıçraması"))
        phases.append(_normal(low_s, "normal"))
        elapsed += high_s + low_s
    return phases


SCENARIOS: Dict[str, Tuple[str, List[Phase]]] = {
    "normal": ("Olağan kullanım; hiçbir uyarı beklenmez", [_normal(3600.0)]),
    "cpu": ("Kalıcı yüksek CPU kullanımı", [
        _normal(120.0), Phase(name="cpu-yogun", duration_s=180.0, **CPU_PHASE),
        _normal(120.0)]),
    "cpu_spikes": ("Kısa CPU sıçramaları; kalıcı CPU uyarısı beklenmez",
                   _spiky_cpu(600.0)),
    "memory": ("Bellek baskısı (düşük MemAvailable + swap + major fault)", [
        _normal(120.0), Phase(name="bellek-baskisi", duration_s=180.0, **MEMORY_PHASE),
        _normal(120.0)]),
    "memory_low_quiet": ("Düşük kullanılabilir bellek ama swap/page-fault etkinliği yok", [
        _normal(60.0), Phase(name="dusuk-bellek-sakin", duration_s=300.0,
                             mem_available_percent=8.0, swap_used_percent=10.0,
                             swap_pages_per_s=0.0, major_faults_per_s=1.0,
                             description="Bellek dolu fakat sistem sayfa takası yapmıyor")]),
    "disk": ("Önceki döneme göre disk G/Ç artışı", [
        _normal(360.0), Phase(name="disk-yogun", duration_s=180.0, **DISK_PHASE),
        _normal(120.0)]),
    "disk_steady": ("Sabit, orta düzey disk etkinliği; anomali beklenmez", [
        Phase(name="sabit-disk", duration_s=900.0, disk_read_mib_s=12.0,
              disk_write_mib_s=8.0, disk_busy_percent=35.0,
              description="Uzun süredir aynı düzeyde süren G/Ç")]),
    "demo": ("Demo: normal -> CPU -> bellek -> disk (yaklaşık 8 dk simülasyon)", [
        _normal(60.0), Phase(name="cpu-yogun", duration_s=100.0, **CPU_PHASE),
        _normal(40.0), Phase(name="bellek-baskisi", duration_s=100.0, **MEMORY_PHASE),
        _normal(40.0), Phase(name="disk-yogun", duration_s=100.0, **DISK_PHASE),
        _normal(60.0)]),
}


def scenario_names() -> List[str]:
    return sorted(SCENARIOS)


def scenario_description(name: str) -> str:
    return SCENARIOS[name][0]


_BASE_PROCESSES: Sequence[Tuple[int, str, str, float, int]] = (
    # pid, ad, kullanıcı, temel CPU %, RSS (MiB)
    (1, "systemd", "root", 0.0, 12),
    (412, "Xorg", "root", 1.2, 95),
    (980, "xfce4-session", "ogrenci", 0.1, 30),
    (1012, "xfwm4", "ogrenci", 0.6, 55),
    (1020, "xfce4-panel", "ogrenci", 0.2, 45),
    (1033, "thunar", "ogrenci", 0.0, 60),
    (1101, "pipewire", "ogrenci", 0.3, 18),
    (1500, "firefox-esr", "ogrenci", 3.0, 900),
    (1650, "code", "ogrenci", 1.5, 650),
    (1800, "xfce4-terminal", "ogrenci", 0.2, 50),
)


class SyntheticSource:
    """Senaryo tabanlı RawSnapshot üreticisi."""

    source_name = "synthetic"

    def __init__(self, scenario: str = "demo", seed: int = 461, step_s: float = 2.0,
                 start_time: float = DEFAULT_START, loop: bool = False,
                 cpu_count: int = 4, mem_total: int = 8 * GIB,
                 swap_total: int = 2 * GIB, noise: bool = True) -> None:
        if scenario not in SCENARIOS:
            raise ValueError(f"Bilinmeyen senaryo: {scenario}. "
                             f"Seçenekler: {', '.join(scenario_names())}")
        self.scenario = scenario
        self.phases = SCENARIOS[scenario][1]
        self.total_duration = sum(p.duration_s for p in self.phases)
        self.step_s = step_s
        self.loop = loop
        self.cpu_count = cpu_count
        self.mem_total = mem_total
        self.swap_total = swap_total
        self.noise = noise
        self._rng = random.Random(seed)
        # Süreç listesi ayrı üreteç kullanır: süreç listesinin kaç örnekte bir toplandığı
        # (process_every) veya hiç toplanmaması sistem metriklerini değiştirmesin.
        self._proc_rng = random.Random(seed * 7919 + 1)
        self._start = start_time
        self._elapsed = -step_s  # ilk collect() t=0 üretir
        self._cpu = [0.0] * 8
        self._vm = [0, 0, 0, 0]
        self._disk = [0.0, 0.0, 0.0, 0, 0]
        self.current_phase: Phase = self.phases[0]

    # -- yardımcılar -------------------------------------------------------
    def phase_at(self, elapsed: float) -> Phase:
        if self.loop and self.total_duration > 0:
            elapsed = elapsed % self.total_duration
        acc = 0.0
        for phase in self.phases:
            acc += phase.duration_s
            if elapsed < acc:
                return phase
        return self.phases[-1]

    def _jitter(self, value: float, rel: float = 0.08, abs_: float = 0.0,
                rng: Optional[random.Random] = None) -> float:
        if not self.noise:
            return value
        return value + (rng or self._rng).gauss(0.0, abs(value) * rel + abs_)

    def mixed_phase(self, start: float, end: float) -> Phase:
        """(start, end] aralığıyla örtüşen evrelerin süreye göre ağırlıklı ortalaması.

        Gerçek sayaçlar aralık boyunca birikir; yalnızca aralığın sonundaki evreyi
        kullanmak kaba aralıklarda (ör. 30 sn) kısa sıçramaları tüm aralığa yayardı.
        Etiket (ad, "hot") en uzun süre örtüşen evreden alınır.
        """
        if end <= start:
            return self.phase_at(end)
        n = max(1, int(math.ceil((end - start) / 0.5)))
        h = (end - start) / n
        picks = [self.phase_at(start + (k + 0.5) * h) for k in range(n)]
        if all(ph is picks[0] for ph in picks):
            return picks[0]
        counts: Dict[int, int] = {}
        for ph in picks:
            counts[id(ph)] = counts.get(id(ph), 0) + 1
        dominant = max(reversed(picks), key=lambda ph: counts[id(ph)])
        numeric = {f.name: sum(getattr(ph, f.name) for ph in picks) / n
                   for f in fields(Phase)
                   if f.type in ("float", float) and f.name != "duration_s"}
        return replace(dominant, **numeric)

    @property
    def now(self) -> float:
        return self._start + max(self._elapsed, 0.0)

    @property
    def finished(self) -> bool:
        return not self.loop and self._elapsed >= self.total_duration

    # -- ana giriş ----------------------------------------------------------
    def collect(self) -> RawSnapshot:
        self._elapsed += self.step_s
        dt = self.step_s if self._elapsed > 0 else 0.0
        phase = self.mixed_phase(self._elapsed - dt, self._elapsed)
        self.current_phase = phase
        ncpu = self.cpu_count

        busy = min(max(self._jitter(phase.cpu_percent, 0.02, 1.5), 0.0), 100.0)
        iowait = min(max(self._jitter(phase.cpu_iowait_percent, 0.1, 0.3), 0.0), 100.0 - busy)
        capacity = dt * ncpu
        busy_s = capacity * busy / 100.0
        iowait_s = capacity * iowait / 100.0
        # user, nice, system, idle, iowait, irq, softirq, steal
        add = [busy_s * 0.72, busy_s * 0.03, busy_s * 0.22, capacity - busy_s - iowait_s,
               iowait_s, busy_s * 0.01, busy_s * 0.02, 0.0]
        self._cpu = [a + b for a, b in zip(self._cpu, add)]

        swap_rate = max(self._jitter(phase.swap_pages_per_s, 0.15), 0.0)
        mf_rate = max(self._jitter(phase.major_faults_per_s, 0.2), 0.0)
        self._vm[0] += int(swap_rate * 0.55 * dt)
        self._vm[1] += int(swap_rate * 0.45 * dt)
        self._vm[2] += int(mf_rate * dt)
        self._vm[3] += int((1500 + mf_rate * 3) * dt)

        read = max(self._jitter(phase.disk_read_mib_s, 0.15), 0.0) * MIB
        write = max(self._jitter(phase.disk_write_mib_s, 0.15), 0.0) * MIB
        disk_busy = min(max(self._jitter(phase.disk_busy_percent, 0.05, 0.5), 0.0), 100.0)
        self._disk[0] += read * dt
        self._disk[1] += write * dt
        self._disk[2] += disk_busy / 100.0 * dt * 1000.0
        self._disk[3] += int(read * dt / (128 * 1024))
        self._disk[4] += int(write * dt / (128 * 1024))

        avail_pct = min(max(self._jitter(phase.mem_available_percent, 0.03, 0.2), 0.5), 99.0)
        available = int(self.mem_total * avail_pct / 100.0)
        swap_used = int(self.swap_total * min(max(phase.swap_used_percent, 0.0), 100.0) / 100.0)
        psi = max(self._jitter(phase.psi_memory_some, 0.1), 0.0)
        blocked = 2 if phase.hot == "io" else (1 if phase.hot == "memory" else 0)

        t = self._start + max(self._elapsed, 0.0)
        return RawSnapshot(
            timestamp=t,
            monotonic=t,
            cpu_times=CpuTimes(*self._cpu),
            cpu_count=ncpu,
            memory=MemoryInfo(
                total=self.mem_total, available=available,
                free=int(available * 0.3), buffers=int(available * 0.05),
                cached=int(available * 0.6), swap_total=self.swap_total,
                swap_free=self.swap_total - swap_used),
            vm=VmCounters(pswpin=self._vm[0], pswpout=self._vm[1],
                          pgmajfault=self._vm[2], pgfault=self._vm[3]),
            disks={"sda": DiskCounters(read_bytes=int(self._disk[0]),
                                       write_bytes=int(self._disk[1]),
                                       busy_ms=int(self._disk[2]),
                                       read_count=self._disk[3], write_count=self._disk[4])},
            load1=round(busy / 100.0 * ncpu + blocked, 2),
            procs_running=max(1, int(round(busy / 100.0 * ncpu))),
            procs_blocked=blocked,
            pressure=PressureInfo(memory_some=round(psi, 2), memory_full=round(psi * 0.4, 2),
                                  cpu_some=round(max(busy - 60.0, 0.0) / 2.0, 2),
                                  io_some=round(disk_busy / 4.0, 2)),
            source=f"synthetic:{self.scenario}",
        )

    def processes(self) -> ProcessSnapshot:
        """Geçerli evreyle tutarlı sahte süreç listesi."""
        phase = self.current_phase
        rows: List[ProcessInfo] = []
        for pid, name, user, cpu, rss_mib in _BASE_PROCESSES:
            rss = rss_mib * MIB
            if phase.hot == "memory" and name == "firefox-esr":
                rss = int(self.mem_total * 0.55)
            rows.append(ProcessInfo(
                pid=pid, name=name, username=user, status="sleeping",
                cpu_percent=round(max(self._jitter(cpu, 0.2, rng=self._proc_rng), 0.0), 2),
                rss_bytes=rss, memory_percent=round(rss / self.mem_total * 100.0, 2),
                num_threads=4,
                read_bytes_per_s=None if user == "root" else 0.0,
                write_bytes_per_s=None if user == "root" else 1024.0,
            ))
        if phase.hot == "cpu":
            for i in range(3):
                rows.append(ProcessInfo(
                    pid=4100 + i, name="cc1plus", username="ogrenci", status="running",
                    cpu_percent=round(self._jitter(28.0, 0.05, rng=self._proc_rng), 2),
                    rss_bytes=350 * MIB,
                    memory_percent=round(350 * MIB / self.mem_total * 100.0, 2),
                    num_threads=1, read_bytes_per_s=0.0, write_bytes_per_s=20_000.0))
        if phase.hot == "io":
            rows.append(ProcessInfo(
                pid=5200, name="rsync", username="ogrenci", status="disk-sleep",
                cpu_percent=6.0, rss_bytes=40 * MIB, memory_percent=0.5, num_threads=1,
                read_bytes_per_s=phase.disk_read_mib_s * MIB * 0.9,
                write_bytes_per_s=phase.disk_write_mib_s * MIB * 0.9))
        denied = sum(1 for r in rows if r.read_bytes_per_s is None)
        return ProcessSnapshot(processes=tuple(rows), total_seen=len(rows),
                               partial_access=denied)


class SyntheticProcessCollector:
    """SyntheticSource'un süreç listesini ProcessCollector arayüzüyle sunar."""

    def __init__(self, source: SyntheticSource) -> None:
        self.source = source

    def collect(self) -> ProcessSnapshot:
        return self.source.processes()
