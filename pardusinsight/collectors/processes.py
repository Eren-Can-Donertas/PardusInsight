"""Süreç listesi kolektörü (psutil).

Standart kullanıcı yetkisiyle diğer kullanıcılara ait süreçlerin bazı alanları
(ör. G/Ç sayaçları) okunamaz; bu alanlar None olarak bırakılır ve sayılır.
Tarama sırasında sonlanan süreçler (NoSuchProcess) atlanır. Hiçbir süreç
üzerinde değiştirici işlem (sinyal, öncelik, sonlandırma) yapılmaz.
"""
from __future__ import annotations

import os
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..core.models import ProcessBrief, ProcessInfo, ProcessSnapshot

_ATTRS = ["name", "uids", "status", "cpu_percent", "memory_info",
          "memory_percent", "num_threads", "io_counters", "create_time"]
# Okunamaması "kısmi erişim" sayılan alanlar
_SENSITIVE = ("io_counters", "memory_info", "cpu_percent")


class ProcessCollector:
    """Her çağrıda tüm süreçleri tarar ve G/Ç hızlarını önceki taramaya göre hesaplar."""

    def __init__(self, psutil_module: Any, cpu_count: Optional[int] = None,
                 monotonic: Callable[[], float] = time.monotonic) -> None:
        self.psutil = psutil_module
        self.cpu_count = max(1, cpu_count or os.cpu_count() or 1)
        self._monotonic = monotonic
        # (pid, create_time) -> (zaman, okuma baytı, yazma baytı); PID yeniden kullanımına karşı
        self._prev_io: Dict[Tuple[int, Optional[float]], Tuple[float, int, int]] = {}
        # uid -> kullanıcı adı; her taramada NSS sorgusu yapmamak için önbellek
        self._user_cache: Dict[int, str] = {}

    def _username(self, uids: Any) -> Optional[str]:
        if uids is None:
            return None
        uid = int(getattr(uids, "real", uids[0] if isinstance(uids, (tuple, list)) else uids))
        name = self._user_cache.get(uid)
        if name is None:
            try:
                import pwd  # yalnızca Unix; okuma amaçlı kullanıcı veritabanı sorgusu

                name = pwd.getpwuid(uid).pw_name
            except (ImportError, KeyError):
                name = str(uid)
            self._user_cache[uid] = name
        return name

    def collect(self) -> ProcessSnapshot:
        ps = self.psutil
        no_such = getattr(ps, "NoSuchProcess", LookupError)
        denied_exc = getattr(ps, "AccessDenied", PermissionError)
        now = self._monotonic()
        rows: List[ProcessInfo] = []
        partial = denied = vanished = total = 0
        error: Optional[str] = None
        new_io: Dict[Tuple[int, Optional[float]], Tuple[float, int, int]] = {}
        try:
            iterator = iter(ps.process_iter())
        except Exception as exc:  # psutil tamamen başarısız olursa
            return ProcessSnapshot(error=f"Süreç listesi alınamadı ({type(exc).__name__})")

        while True:
            try:
                proc = next(iterator)
            except StopIteration:
                break
            except no_such:
                vanished += 1
                break  # üreteç sonlandı
            except Exception as exc:
                error = f"Süreç taraması yarıda kesildi ({type(exc).__name__})"
                break
            total += 1
            try:
                info = proc.as_dict(attrs=_ATTRS, ad_value=None)
            except no_such:
                vanished += 1
                continue
            except denied_exc:
                denied += 1
                continue
            except Exception:
                # Beklenmeyen tek süreç hatası tüm taramayı durdurmamalı
                denied += 1
                continue
            row = self._build_row(proc, info, now, new_io)
            if any(info.get(key) is None for key in _SENSITIVE):
                partial += 1
            rows.append(row)

        self._prev_io = new_io  # kaybolan süreçlerin kayıtları böylece temizlenir
        return ProcessSnapshot(
            processes=tuple(rows), total_seen=total, partial_access=partial,
            access_denied=denied, vanished=vanished, error=error,
        )

    def _build_row(self, proc: Any, info: Dict[str, Any], now: float,
                   new_io: Dict[Tuple[int, Optional[float]], Tuple[float, int, int]]
                   ) -> ProcessInfo:
        pid = int(getattr(proc, "pid", info.get("pid", -1)))
        mem = info.get("memory_info")
        rss = int(mem.rss) if mem is not None else None
        cpu_raw = info.get("cpu_percent")
        cpu = round(float(cpu_raw) / self.cpu_count, 2) if cpu_raw is not None else None
        read_rate = write_rate = None
        io = info.get("io_counters")
        if io is not None:
            key = (pid, info.get("create_time"))
            read_b, write_b = int(io.read_bytes), int(io.write_bytes)
            new_io[key] = (now, read_b, write_b)
            prev = self._prev_io.get(key)
            if prev is not None:
                dt = now - prev[0]
                if dt > 0 and read_b >= prev[1] and write_b >= prev[2]:
                    read_rate = (read_b - prev[1]) / dt
                    write_rate = (write_b - prev[2]) / dt
        mem_pct = info.get("memory_percent")
        return ProcessInfo(
            pid=pid,
            name=str(info.get("name") or f"pid {pid}"),
            username=self._username(info.get("uids")),
            status=info.get("status"),
            cpu_percent=cpu,
            rss_bytes=rss,
            memory_percent=round(float(mem_pct), 2) if mem_pct is not None else None,
            num_threads=info.get("num_threads"),
            read_bytes_per_s=read_rate,
            write_bytes_per_s=write_rate,
        )


def top_processes(snapshot: Optional[ProcessSnapshot], n: int = 5
                  ) -> Tuple[Tuple[ProcessBrief, ...], Tuple[ProcessBrief, ...],
                             Tuple[ProcessBrief, ...]]:
    """CPU, bellek ve G/Ç'ye göre en yoğun n süreci özetler."""
    if snapshot is None or not snapshot.processes:
        return (), (), ()

    def brief(p: ProcessInfo) -> ProcessBrief:
        return ProcessBrief(pid=p.pid, name=p.name, cpu_percent=p.cpu_percent,
                            rss_bytes=p.rss_bytes, io_bytes_per_s=p.io_bytes_per_s)

    procs = snapshot.processes
    by_cpu = sorted((p for p in procs if p.cpu_percent),
                    key=lambda p: p.cpu_percent or 0.0, reverse=True)[:n]
    by_mem = sorted((p for p in procs if p.rss_bytes),
                    key=lambda p: p.rss_bytes or 0, reverse=True)[:n]
    by_io = sorted((p for p in procs if p.io_bytes_per_s),
                   key=lambda p: p.io_bytes_per_s or 0.0, reverse=True)[:n]
    return (tuple(brief(p) for p in by_cpu), tuple(brief(p) for p in by_mem),
            tuple(brief(p) for p in by_io))
