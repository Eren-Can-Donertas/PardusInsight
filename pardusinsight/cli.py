"""Komut satırı girişi: GUI'yi başlatır veya GUI'siz (headless) izleme yapar.

GUI'siz mod, PDF'deki "GUI/psutil uyumsuzluğu" riskine karşı salt-okunur
komut satırı yedeğidir; ayrıca otomatik testlerde kullanılır.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from dataclasses import replace
from typing import Optional, Sequence

from . import APP_NAME, __version__
from .analysis.explain import alert_to_text
from .collectors.synthetic import scenario_description, scenario_names
from .config import AppSettings, load_settings_file, settings_to_dict
from .core.formatting import fmt_bytes, fmt_pct, fmt_rate, fmt_time
from .core.models import SystemSample
from .core.service import (MonitorService, RecordingSource, build_live_service,
                           build_synthetic_service)
from .export import (ReportError, build_report, load_json_report, write_alerts_csv,
                     write_json_report, write_samples_csv)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pardusinsight",
        description=f"{APP_NAME}: salt-okunur kaynak izleme ve açıklanabilir darboğaz analizi.")
    p.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    p.add_argument("--interval", type=float, default=None,
                   help="örnekleme aralığı, saniye (varsayılan 2)")
    p.add_argument("--history-minutes", type=float, default=None,
                   help="geçmiş tamponu süresi, dakika (varsayılan 30)")
    p.add_argument("--window", type=float, default=None,
                   help="analiz penceresi uzunluğu, saniye (varsayılan 30)")
    p.add_argument("--process-every", type=int, default=None,
                   help="süreç listesini her N örnekte bir topla (varsayılan 1)")
    p.add_argument("--config", metavar="DOSYA", help="JSON ayar dosyası (yalnızca okunur)")
    src = p.add_mutually_exclusive_group()
    src.add_argument("--synthetic", metavar="SENARYO",
                     help="gerçek sistem yerine sentetik veri kullan (Linux gerekmez)")
    src.add_argument("--replay", metavar="DOSYA",
                     help="kaydedilmiş JSON raporunu/senaryoyu yükle ve analiz et")
    p.add_argument("--list-scenarios", action="store_true", help="sentetik senaryoları listele")
    p.add_argument("--speed", type=float, default=1.0,
                   help="sentetik modda hızlandırma katsayısı (0 = beklemeden)")
    p.add_argument("--seed", type=int, default=461, help="sentetik veri tohum değeri")
    p.add_argument("--headless", action="store_true", help="GUI olmadan komut satırında izle")
    p.add_argument("--duration", type=float, default=None,
                   help="headless: toplam süre, saniye")
    p.add_argument("--ticks", type=int, default=None, help="headless: örnek sayısı")
    p.add_argument("--quiet", action="store_true", help="headless: her örneği yazdırma")
    p.add_argument("--export-csv", metavar="DOSYA",
                   help="headless bitiminde örnekleri CSV'ye yaz (uyarılar *_uyarilar.csv)")
    p.add_argument("--export-json", metavar="DOSYA", help="headless bitiminde JSON rapor yaz")
    p.add_argument("--log-level", default="WARNING",
                   choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                   help="tanılama günlüğü düzeyi (yalnızca stderr; dosyaya yazılmaz)")
    return p


SYNTHETIC_BANNER = ("=" * 72 + "\n DEMO / SENTETİK VERİ — aşağıdaki değerler gerçek sistem ölçümü "
                    "DEĞİLDİR.\n" + "=" * 72)


def resolve_settings(args: argparse.Namespace) -> AppSettings:
    settings = load_settings_file(args.config) if args.config else AppSettings()
    if args.interval is not None:
        settings = settings.with_interval(args.interval)
    if args.history_minutes is not None:
        settings = replace(settings, history_minutes=args.history_minutes)
    if args.window is not None:
        settings = replace(settings, analysis=replace(settings.analysis, window_s=args.window))
    if args.process_every is not None:
        settings = replace(settings, process_every=args.process_every)
    return settings.validate()


def alerts_csv_path(samples_path: str) -> str:
    root, ext = os.path.splitext(samples_path)
    return f"{root}_uyarilar{ext or '.csv'}"


def sample_line(sample: SystemSample, active: int, synthetic: bool = False) -> str:
    prefix = "[SENTETİK] " if synthetic else ""
    return (f"{prefix}{fmt_time(sample.timestamp)}  CPU {fmt_pct(sample.cpu_percent):>7} | "
            f"RAM {fmt_pct(sample.mem_used_percent):>6} (kullanılabilir "
            f"{fmt_bytes(sample.mem_available_bytes)}) | "
            f"Swap {fmt_pct(sample.swap_used_percent)} | "
            f"Disk O {fmt_rate(sample.disk_read_bytes_per_s)} Y "
            f"{fmt_rate(sample.disk_write_bytes_per_s)} | aktif uyarı: {active}")


def export_results(service: MonitorService, csv_path: Optional[str],
                   json_path: Optional[str], out=None) -> None:
    samples = service.history.snapshot()
    alerts = service.engine.alert_log()
    if csv_path:
        n = write_samples_csv(csv_path, samples, data_source=service.data_source)
        a_path = alerts_csv_path(csv_path)
        m = write_alerts_csv(a_path, alerts)
        print(f"CSV yazıldı: {csv_path} ({n} örnek), {a_path} ({m} uyarı)", file=out)
    if json_path:
        report = build_report(samples, alerts, settings_to_dict(service.settings),
                              source=service.data_source)
        write_json_report(json_path, report)
        print(f"JSON rapor yazıldı: {json_path} ({len(samples)} örnek, {len(alerts)} uyarı)",
              file=out)


def run_headless(service: MonitorService, args: argparse.Namespace, out=None) -> int:
    synthetic = args.synthetic is not None
    interval = service.settings.sample_interval_s
    delay = 0.0 if (synthetic and args.speed <= 0) else (
        interval / args.speed if synthetic else interval)
    started = time.monotonic()
    next_at = started
    ticks = 0
    if service.is_synthetic:
        print(SYNTHETIC_BANNER, file=out)
    print(f"{APP_NAME} {__version__} — kaynak: {service.source_name}, aralık {interval} sn. "
          "Durdurmak için Ctrl+C.", file=out)
    try:
        while True:
            result = service.tick()
            ticks += 1
            for err in result.errors:
                print(f"  ! {err}", file=out)
            if result.sample is not None and not args.quiet:
                print(sample_line(result.sample, len(result.update.active),
                                  service.is_synthetic), file=out)
            for alert in result.update.new:
                print("\n" + alert_to_text(alert) + "\n", file=out)
            for alert in result.update.resolved:
                print(f"  ✓ Çözüldü: {alert.title} ({fmt_time(alert.resolved_at)})", file=out)
            if args.ticks is not None and ticks >= args.ticks:
                break
            if args.duration is not None and time.monotonic() - started >= args.duration:
                break
            if delay > 0:
                next_at += delay
                time.sleep(max(0.0, next_at - time.monotonic()))
    except KeyboardInterrupt:
        print("\nDurduruldu.", file=out)
    log = service.engine.alert_log()
    print(f"\nÖzet: {ticks} tur, tamponda {len(service.history)} örnek, {len(log)} uyarı "
          f"({sum(1 for a in log if a.active)} aktif).", file=out)
    export_results(service, args.export_csv, args.export_json, out)
    return 0


def run_replay(path: str, settings: AppSettings, args: argparse.Namespace,
               out=None) -> Optional[MonitorService]:
    try:
        data = load_json_report(path)
    except ReportError as exc:
        print(f"Kayıt yüklenemedi: {exc}", file=sys.stderr)
        return None
    service = MonitorService(RecordingSource(os.path.basename(path)), None, settings)
    result = service.load_recording(data.samples, str(data.meta.get("source", "unknown")))
    if service.is_synthetic:
        print(SYNTHETIC_BANNER, file=out)
    print(f"{len(data.samples)} örnek yüklendi; kurallar yeniden çalıştırıldı "
          f"({result.duration_s * 1000:.0f} ms).", file=out)
    for alert in result.alert_log:
        print("\n" + alert_to_text(alert), file=out)
    if not result.alert_log:
        print("Bu kayıtta uyarı koşulu oluşmadı.", file=out)
    return service


def warn_if_root(out=None) -> None:
    geteuid = getattr(os, "geteuid", None)
    if geteuid is not None and geteuid() == 0:
        print("Uyarı: PardusInsight root yetkisi gerektirmez; standart kullanıcıyla "
              "çalıştırmanız önerilir.", file=out or sys.stderr)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=getattr(logging, args.log_level), stream=sys.stderr,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if args.list_scenarios:
        for name in scenario_names():
            print(f"{name:18s} {scenario_description(name)}")
        return 0
    if args.synthetic and args.synthetic not in scenario_names():
        print(f"Bilinmeyen senaryo: {args.synthetic}. Seçenekler: "
              f"{', '.join(scenario_names())}", file=sys.stderr)
        return 2
    try:
        settings = resolve_settings(args)
    except (ValueError, OSError) as exc:
        print(f"Ayarlar geçersiz: {exc}", file=sys.stderr)
        return 2
    warn_if_root()

    if not args.headless:
        try:
            from .ui.app import run_gui
        except ImportError as exc:
            print(f"PySide6 yüklenemedi ({exc}). Kurulum için docs/KURULUM.md'ye bakın; "
                  "GUI olmadan çalıştırmak için --headless kullanın.", file=sys.stderr)
            return 3
        return run_gui(settings, synthetic=args.synthetic, replay=args.replay,
                       speed=args.speed, seed=args.seed)

    if args.replay:
        service = run_replay(args.replay, settings, args)
        if service is None:
            return 1
        export_results(service, args.export_csv, args.export_json)
        return 0
    if args.synthetic:
        service = build_synthetic_service(args.synthetic, settings, seed=args.seed)
    else:
        if not sys.platform.startswith("linux"):
            print("Canlı izleme yalnızca Linux'ta desteklenir; --synthetic kullanın.",
                  file=sys.stderr)
            return 2
        service = build_live_service(settings)
    return run_headless(service, args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
