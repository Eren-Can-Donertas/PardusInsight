#!/usr/bin/env python3
"""PardusInsight'ın kendi kaynak kullanımını ve GUI yanıt verebilirliğini ölçer.

PDF hedefleri: ortalama CPU payı < %5, RAM < 200 MiB, 60 sn boyunca GUI'nin
yanıt vermeye devam etmesi. Sistemi zorlamaz; yalnızca normal izleme yapar.

Kullanım:
  python3 scripts/perf_check.py                # GUI'siz, canlı, 60 sn
  python3 scripts/perf_check.py --gui          # GUI + arka plan worker, 60 sn
  python3 scripts/perf_check.py --gui --synthetic demo --duration 30
  (Ekransız ortamda: QT_QPA_PLATFORM=offscreen python3 scripts/perf_check.py --gui)
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pardusinsight.config import AppSettings  # noqa: E402
from pardusinsight.core.service import (SelfUsageMonitor, build_live_service,  # noqa: E402
                                        build_synthetic_service)

MIB = 1024 * 1024


def make_service(args):
    settings = AppSettings().with_interval(args.interval)
    if args.synthetic:
        return build_synthetic_service(args.synthetic, settings)
    return build_live_service(settings)


def report(label, cpu_total_s, wall_s, rss_values, tick_ms, extra=""):
    ncpu = os.cpu_count() or 1
    single = cpu_total_s / wall_s * 100.0
    print(f"\n== {label} ==")
    print(f"Süre: {wall_s:.1f} sn · tur sayısı: {len(tick_ms)}")
    print(f"Ortalama CPU: %{single:.2f} (tek çekirdek = %100) · "
          f"%{single / ncpu:.2f} (toplam {ncpu} çekirdek kapasitesine göre)")
    if rss_values:
        print(f"RSS: başlangıç {rss_values[0] / MIB:.1f} MiB · en yüksek "
              f"{max(rss_values) / MIB:.1f} MiB · son {rss_values[-1] / MIB:.1f} MiB")
    if tick_ms:
        ordered = sorted(tick_ms)
        print(f"Tur süresi: medyan {ordered[len(ordered) // 2]:.1f} ms · en yüksek "
              f"{ordered[-1]:.1f} ms")
    if extra:
        print(extra)
    ok_cpu = single < 5.0
    ok_rss = (max(rss_values) / MIB < 200.0) if rss_values else None
    print(f"Hedef CPU < %5 (tek çekirdek): {'SAĞLANDI' if ok_cpu else 'SAĞLANMADI'} · "
          f"Hedef RAM < 200 MiB: "
          f"{'ölçülemedi' if ok_rss is None else ('SAĞLANDI' if ok_rss else 'SAĞLANMADI')}")


def run_headless(args) -> int:
    service = make_service(args)
    rss, ticks = [], []
    t0, c0 = time.monotonic(), sum(os.times()[:2])
    next_at = t0
    while time.monotonic() - t0 < args.duration:
        result = service.tick()
        ticks.append(result.duration_s * 1000)
        value = SelfUsageMonitor.rss_bytes()
        if value:
            rss.append(value)
        next_at += args.interval
        time.sleep(max(0.0, next_at - time.monotonic()))
    report("GUI'siz izleme", sum(os.times()[:2]) - c0, time.monotonic() - t0, rss, ticks,
           f"Tampondaki örnek: {len(service.history)}")
    return 0


def run_gui(args) -> int:
    from PySide6.QtCore import QElapsedTimer, QTimer
    from PySide6.QtWidgets import QApplication

    from pardusinsight.ui.main_window import MainWindow

    app = QApplication.instance() or QApplication(sys.argv)
    service = make_service(args)
    window = MainWindow(service, "Performans ölçümü")
    window.show()
    rss, ticks, gaps = [], [], []
    window.worker.tick_ready.connect(lambda r: ticks.append(r.duration_s * 1000))
    clock = QElapsedTimer()
    clock.start()
    last = [0]

    def heartbeat():
        now = clock.elapsed()
        gaps.append(now - last[0])
        last[0] = now
        value = SelfUsageMonitor.rss_bytes()
        if value and len(gaps) % 50 == 0:
            rss.append(value)

    beat = QTimer()
    beat.timeout.connect(heartbeat)
    beat.start(20)
    t0, c0 = time.monotonic(), sum(os.times()[:2])
    QTimer.singleShot(int(args.duration * 1000), app.quit)
    app.exec()
    wall, cpu = time.monotonic() - t0, sum(os.times()[:2]) - c0
    window.shutdown()
    late = sum(1 for g in gaps[1:] if g > 100)
    report("GUI + arka plan örnekleme", cpu, wall, rss, ticks,
           f"Olay döngüsü kalp atışı (20 ms): en uzun aralık {max(gaps[1:] or [0])} ms, "
           f"100 ms'yi aşan {late}/{len(gaps)} aralık "
           f"→ {'YANIT VERİYOR' if max(gaps[1:] or [0]) < 500 else 'DONMA ŞÜPHESİ'}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--duration", type=float, default=60.0)
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--synthetic", metavar="SENARYO")
    parser.add_argument("--gui", action="store_true")
    args = parser.parse_args()
    return run_gui(args) if args.gui else run_headless(args)


if __name__ == "__main__":
    sys.exit(main())
