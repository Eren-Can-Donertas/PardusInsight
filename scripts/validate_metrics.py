#!/usr/bin/env python3
"""/proc okumalarını psutil ile karşılaştırır ve Markdown doğrulama tablosu yazdırır.

PDF'deki "seçilen /proc değerleri veya psutil ile tutarlılık; en az 10 örnek
karşılaştırma" ölçütü için. Sistemi değiştirmez, yük oluşturmaz.
Kullanım: python3 scripts/validate_metrics.py [--rounds 10] [--interval 1]
"""
import argparse
import os
import platform
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pardusinsight.collectors.procfs import ProcFsReader  # noqa: E402
from pardusinsight.collectors.system import LinuxSystemCollector, load_psutil  # noqa: E402
from pardusinsight.core.normalize import Normalizer  # noqa: E402
from pardusinsight.export.json_export import system_info  # noqa: E402

MIB = 1024 * 1024


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rounds", type=int, default=10)
    parser.add_argument("--interval", type=float, default=1.0)
    args = parser.parse_args()
    ps = load_psutil()
    if ps is None or not os.path.isfile("/proc/stat"):
        print("Bu betik Linux ve psutil gerektirir.", file=sys.stderr)
        return 2
    reader = ProcFsReader()
    collector = LinuxSystemCollector(reader, psutil_module=ps)
    norm = Normalizer()
    norm.update(collector.collect())
    ps.cpu_percent(interval=None)
    info = system_info()
    print(f"Ortam: {info['os']} · çekirdek {info['kernel']} · Python {info['python']} · "
          f"psutil {ps.__version__} · {os.cpu_count()} mantıksal CPU\n")
    print("| # | MemTotal eşit | MemAvailable farkı (MiB) | SwapTotal eşit | "
          "Swap kullanılan farkı (MiB) | CPU user farkı (sn) | CPU % (/proc) | "
          "CPU % (psutil) | Disk okuma farkı (MiB) |")
    print("|---|---|---|---|---|---|---|---|---|")
    worst = {"avail": 0.0, "swap": 0.0, "user": 0.0, "cpu": 0.0, "disk": 0.0}
    for i in range(1, args.rounds + 1):
        time.sleep(args.interval)
        sample = norm.update(collector.collect())
        cpu_ps = ps.cpu_percent(interval=None)
        mem = reader.read_memory()
        vm, sw = ps.virtual_memory(), ps.swap_memory()
        cpu_times, _r, _b = reader.read_cpu()
        ref_times = ps.cpu_times()
        disks = reader.read_disks()
        ref_disks = ps.disk_io_counters(perdisk=True)
        disk_diff = max((abs(c.read_bytes - ref_disks[n].read_bytes) / MIB
                         for n, c in disks.items() if n in ref_disks), default=0.0)
        avail = abs(mem.available - vm.available) / MIB
        swap = abs((mem.swap_total - mem.swap_free) - sw.used) / MIB
        user = abs(cpu_times.user - ref_times.user)
        cpu_diff = abs((sample.cpu_percent or 0.0) - cpu_ps)
        for key, value in (("avail", avail), ("swap", swap), ("user", user),
                           ("cpu", cpu_diff), ("disk", disk_diff)):
            worst[key] = max(worst[key], value)
        print(f"| {i} | {'evet' if mem.total == vm.total else 'HAYIR'} | {avail:.2f} | "
              f"{'evet' if mem.swap_total == sw.total else 'HAYIR'} | {swap:.2f} | {user:.2f} | "
              f"{sample.cpu_percent:.1f} | {cpu_ps:.1f} | {disk_diff:.2f} |")
    print(f"\nEn büyük farklar: MemAvailable {worst['avail']:.2f} MiB, "
          f"swap {worst['swap']:.2f} MiB, "
          f"CPU user {worst['user']:.2f} sn, CPU % {worst['cpu']:.1f} puan, disk okuma "
          f"{worst['disk']:.2f} MiB.")
    print("Not: iki kaynak aynı anda okunamadığından anlık değişen değerlerde küçük farklar "
          "beklenir; CPU % farkı ölçüm anlarının kaymasından kaynaklanır.")
    print(f"Platform: {platform.platform()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
