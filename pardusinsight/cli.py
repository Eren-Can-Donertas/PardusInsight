"""Komut satırı girişi: GUI'yi başlatır veya GUI'siz (headless) izleme yapar.

GUI'siz mod, PDF'deki "GUI/psutil uyumsuzluğu" riskine karşı salt-okunur
komut satırı yedeğidir; ayrıca otomatik testlerde kullanılır.
"""
from __future__ import annotations

import argparse
import math
import os
import sys
import time
from dataclasses import replace
from typing import List, Optional, Sequence

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
    return p


def resolve_settings(args: argparse.Namespace,
                     warnings: Optional[List[str]] = None) -> AppSettings:
    """Ayar dosyası + komut satırı seçenekleri. ``warnings`` verilirse uyarılar eklenir."""
    settings = load_settings_file(args.config, warnings) if args.config else AppSettings()
    if args.interval is not None:
        settings = settings.with_interval(args.interval)
    if args.history_minutes is not None:
        settings = replace(settings, history_minutes=args.history_minutes)
    if args.window is not None:
        settings = replace(settings, analysis=replace(settings.analysis, window_s=args.window))
    if args.process_every is not None:
        settings = replace(settings, process_every=args.process_every)
    settings = settings.validate()
    if args.headless and (args.export_csv or args.export_json):
        settings = _cover_planned_run(settings, args, warnings)
    if warnings is not None:
        warnings.extend(settings.warnings())
    return settings


def _cover_planned_run(settings: AppSettings, args: argparse.Namespace,
                       warnings: Optional[List[str]]) -> AppSettings:
    """Dışa aktarılacak headless kaydın tamamı tamponda kalsın (ör. 1 sa kalibrasyon kaydı).

    Tampon varsayılan olarak son 30 dk'yı tutar; daha uzun bir --duration/--ticks
    kaydında ilk kısım sessizce atılır ve rapordaki uyarıların kanıt örnekleri eksik kalırdı.
    """
    planned = args.duration
    if planned is None and args.ticks is not None:
        planned = args.ticks * settings.sample_interval_s
    if planned is None or planned <= settings.history_minutes * 60:
        return settings
    minutes = min(240.0, float(math.ceil(planned / 60.0)) + 1.0)
    if warnings is not None:
        note = (f"Geçmiş tamponu, dışa aktarılacak kaydın tamamını tutmak için {minutes:g} dk'ya "
                "çıkarıldı.")
        if planned > 240 * 60:
            note += " Kayıt 240 dk'dan uzun: raporda yalnızca son 240 dk bulunur."
        warnings.append(note)
    return replace(settings, history_minutes=minutes).validate()


def export_problems(args: argparse.Namespace) -> List[str]:
    """Dışa aktarma hedeflerinin klasörleri var ve yazılabilir mi?

    İzlemeden ÖNCE denetlenir; 30 dk'lık bir kayıt, sonunda yazılamayan bir dosya
    yüzünden kaybolmasın.
    """
    problems = []
    for path in (p for p in (args.export_csv, args.export_json) if p):
        folder = os.path.dirname(os.path.abspath(path))
        if not os.path.isdir(folder):
            problems.append(f"Dışa aktarma klasörü yok: {folder}")
        elif not os.access(folder, os.W_OK):
            problems.append(f"Dışa aktarma klasörüne yazılamıyor: {folder}")
        elif os.path.isdir(path):
            problems.append(f"Dışa aktarma hedefi bir klasör: {path}")
    return problems


def alerts_csv_path(samples_path: str) -> str:
    root, ext = os.path.splitext(samples_path)
    return f"{root}_uyarilar{ext or '.csv'}"


def sample_line(sample: SystemSample, active: int) -> str:
    return (f"{fmt_time(sample.timestamp)}  CPU {fmt_pct(sample.cpu_percent):>7} | "
            f"RAM {fmt_pct(sample.mem_used_percent):>6} (kullanılabilir "
            f"{fmt_bytes(sample.mem_available_bytes)}) | Swap {fmt_pct(sample.swap_used_percent)} | "
            f"Disk O {fmt_rate(sample.disk_read_bytes_per_s)} Y "
            f"{fmt_rate(sample.disk_write_bytes_per_s)} | aktif uyarı: {active}")


def export_results(service: MonitorService, csv_path: Optional[str],
                   json_path: Optional[str], out=None) -> bool:
    """İstenen dosyaları yazar; biri başarısız olsa da diğerini dener. Başarılıysa True."""
    samples = service.history.snapshot()
    alerts = service.engine.alert_log()
    ok = True
    if csv_path:
        a_path = alerts_csv_path(csv_path)
        try:
            n = write_samples_csv(csv_path, samples)
            m = write_alerts_csv(a_path, alerts)
        except OSError as exc:
            ok = False
            print(f"CSV yazılamadı ({csv_path}): {exc.strerror or exc}", file=sys.stderr)
        else:
            print(f"CSV yazıldı: {csv_path} ({n} örnek), {a_path} ({m} uyarı)", file=out)
    if json_path:
        report = build_report(samples, alerts, settings_to_dict(service.settings),
                              source=service.source_name)
        try:
            write_json_report(json_path, report)
        except OSError as exc:
            ok = False
            print(f"JSON rapor yazılamadı ({json_path}): {exc.strerror or exc}", file=sys.stderr)
        else:
            print(f"JSON rapor yazıldı: {json_path} ({len(samples)} örnek, {len(alerts)} uyarı)",
                  file=out)
    return ok


def run_headless(service: MonitorService, args: argparse.Namespace, out=None) -> int:
    synthetic = args.synthetic is not None
    interval = service.settings.sample_interval_s
    delay = 0.0 if (synthetic and args.speed <= 0) else (
        interval / args.speed if synthetic else interval)
    started = time.monotonic()
    next_at = started
    ticks = 0
    print(f"{APP_NAME} {__version__} — kaynak: {service.source_name}, aralık {interval} sn. "
          "Durdurmak için Ctrl+C.", file=out)
    try:
        while True:
            result = service.tick()
            ticks += 1
            for err in result.errors:
                print(f"  ! {err}", file=out)
            if result.sample is not None and not args.quiet:
                print(sample_line(result.sample, len(result.update.active)), file=out)
            for alert in result.update.new:
                print("\n" + alert_to_text(alert) + "\n", file=out)
            for alert in result.update.resolved:
                print(f"  ✓ Çözüldü: {alert.title} ({fmt_time(alert.resolved_at)})", file=out)
            if args.ticks is not None and ticks >= args.ticks:
                break
            if args.duration is not None and time.monotonic() - started >= args.duration:
                break
            if delay > 0:
                # Uzun süren bir turdan sonra kaçırılan turlar art arda koşturulmaz
                next_at = max(next_at + delay, time.monotonic())
                time.sleep(max(0.0, next_at - time.monotonic()))
    except KeyboardInterrupt:
        print("\nDurduruldu.", file=out)
    log = service.engine.alert_log()
    print(f"\nÖzet: {ticks} tur, tamponda {len(service.history)} örnek, {len(log)} uyarı "
          f"({sum(1 for a in log if a.active)} aktif).", file=out)
    return 0 if export_results(service, args.export_csv, args.export_json, out) else 1


def run_replay(path: str, settings: AppSettings, args: argparse.Namespace,
               out=None) -> Optional[MonitorService]:
    try:
        data = load_json_report(path)
    except ReportError as exc:
        print(f"Kayıt yüklenemedi: {exc}", file=sys.stderr)
        return None
    service = MonitorService(RecordingSource(os.path.basename(path)), None, settings)
    result = service.load_recording(data.samples)
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


def _tolerate_unencodable_output() -> None:
    """Windows'ta çıktı dosyaya yönlendirildiğinde konsol kodlaması (ör. cp1254) '✓', '≥'
    gibi karakterleri kodlayamaz; çökmek yerine '?' yazılır."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(errors="replace")
            except (ValueError, OSError):  # pragma: no cover - kapalı/özel akış
                pass


def main(argv: Optional[Sequence[str]] = None) -> int:
    _tolerate_unencodable_output()
    args = build_parser().parse_args(argv)
    if args.list_scenarios:
        for name in scenario_names():
            print(f"{name:18s} {scenario_description(name)}")
        return 0
    if args.synthetic and args.synthetic not in scenario_names():
        print(f"Bilinmeyen senaryo: {args.synthetic}. Seçenekler: "
              f"{', '.join(scenario_names())}", file=sys.stderr)
        return 2
    warnings: List[str] = []
    try:
        settings = resolve_settings(args, warnings)
    except (ValueError, OSError) as exc:
        print(f"Ayarlar geçersiz: {exc}", file=sys.stderr)
        return 2
    for warning in warnings:
        print(f"Uyarı: {warning}", file=sys.stderr)
    problems = export_problems(args) if args.headless else []
    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
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
        return 0 if export_results(service, args.export_csv, args.export_json) else 1
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
