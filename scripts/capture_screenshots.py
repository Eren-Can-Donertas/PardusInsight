#!/usr/bin/env python3
"""Gerçek uygulama penceresinden ekran görüntüleri alır (rapor ve kullanıcı rehberi için).

Uygulamanın kendi MainWindow sınıfı kullanılır; çizimler sahte değildir. Canlı mod
gerçek /proc verisiyle örnek toplar (varsayılan 60 sn). Demo görüntüleri sentetik
veriyle üretilir ve pencerede "DEMO / SENTETİK VERİ" şeridi görünür.

Kullanım (Pardus XFCE oturumunda gerçek pencere yöneticisiyle):
    python3 scripts/capture_screenshots.py ekran_goruntuleri/
Ekransız ortamda:
    QT_QPA_PLATFORM=offscreen python3 scripts/capture_screenshots.py cikti/
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication  # noqa: E402

from pardusinsight.config import AppSettings  # noqa: E402
from pardusinsight.core.service import build_live_service, build_synthetic_service  # noqa: E402
from pardusinsight.export import load_json_report  # noqa: E402
from pardusinsight.ui.main_window import MainWindow  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def save(app: QApplication, window: MainWindow, tab: int, path: str) -> None:
    window.tabs.setCurrentIndex(tab)
    for _ in range(3):
        app.processEvents()
    window.grab().save(path)
    print("kaydedildi:", path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("output")
    parser.add_argument("--live-seconds", type=float, default=60.0,
                        help="canlı modda toplanacak gerçek veri süresi")
    parser.add_argument("--skip-live", action="store_true")
    parser.add_argument("--include-process-list", action="store_true",
                        help="canlı süreç tablosunu da kaydet (kişisel bilgi içerebilir)")
    args = parser.parse_args()
    os.makedirs(args.output, exist_ok=True)
    app = QApplication.instance() or QApplication(sys.argv)

    if not args.skip_live and sys.platform.startswith("linux"):
        live = MainWindow(build_live_service(AppSettings()), "Canlı izleme (/proc + psutil)",
                          start_worker=False)
        live.resize(1280, 820)
        live.show()
        deadline = time.monotonic() + args.live_seconds
        while time.monotonic() < deadline:  # gerçek 2 sn aralıkla örnekle
            live.apply_tick(live.service.tick())
            end = time.monotonic() + live.service.settings.sample_interval_s
            while time.monotonic() < end:
                app.processEvents()
                time.sleep(0.05)
        live.range_combo.setCurrentIndex(0)
        save(app, live, 0, os.path.join(args.output, "canli_genel_bakis.png"))
        # Gerçek süreç listesi kullanıcı adı ve uygulama adları içerir; yalnızca istenirse
        if args.include_process_list:
            save(app, live, 1, os.path.join(args.output, "canli_surecler.png"))
        save(app, live, 4, os.path.join(args.output, "metodoloji.png"))
        live.shutdown()
        live.close()

    demo = MainWindow(build_synthetic_service("demo", AppSettings(), loop=False,
                                              start_time=1767225600.0),
                      "Sentetik veri: demo", start_worker=False)
    demo.resize(1280, 820)
    demo.show()
    for _ in range(185):  # normal -> CPU -> bellek evrelerinin sonuna kadar
        demo.apply_tick(demo.service.tick())
    demo.range_combo.setCurrentIndex(2)
    save(app, demo, 0, os.path.join(args.output, "demo_genel_bakis.png"))
    save(app, demo, 1, os.path.join(args.output, "demo_surecler.png"))
    save(app, demo, 2, os.path.join(args.output, "demo_uyarilar.png"))
    demo.close()

    replay = MainWindow(build_synthetic_service("normal", AppSettings()), "Kayıt analizi",
                        start_worker=False)
    replay.resize(1280, 820)
    replay.show()
    data = load_json_report(os.path.join(ROOT, "scenarios", "cpu_spikes.json"))
    result = replay.service.load_recording(data.samples, str(data.meta.get("source")))
    replay.on_recording_loaded(result, "cpu_spikes.json")
    save(app, replay, 2, os.path.join(args.output, "karsi_ornek_cpu_spikes.png"))
    replay.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
