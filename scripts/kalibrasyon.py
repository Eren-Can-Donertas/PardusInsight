#!/usr/bin/env python3
"""Kaydedilmiş JSON raporlarından kural eşiklerini kalibre eder (docs/KURALLAR.md).

Her eşik bir değer ızgarasında değiştirilir, kayıtlar gerçek kural koduyla yeniden
analiz edilir ve olağan kullanımda yanlış pozitif üretmeyen değerler önerilir.
Sistemi değiştirmez; yalnızca verilen dosyaları okur. Çıktı yalnızca --cikti /
--oneri-json verildiğinde dosyaya yazılır.

Kayıt almak için (Pardus'ta, tarayıcı + ofis ile olağan kullanım sırasında):
  pardusinsight --headless --duration 1800 --quiet --export-json normal.json
Bilinen yoğun bir iş sırasında (ör. büyük proje derleme) aynı komutla:
  pardusinsight --headless --duration 600 --quiet --export-json derleme.json

Kullanım:
  python3 scripts/kalibrasyon.py normal.json [normal2.json ...]
      [--yogun derleme.json:sustained_cpu] [--yogun kopya.json:disk_io_anomaly]
      [--config ayarlar.json] [--cikti kalibrasyon.md] [--oneri-json oneri.json]

--yogun DOSYA[:kural,...]: bilinen yoğun iş kaydı; ':' sonrası, tetiklenmesi
beklenen kurallar (memory_pressure, sustained_cpu, disk_io_anomaly).
"""
import argparse
import json
import os
import sys
from typing import List, Optional, Sequence, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pardusinsight.analysis.calibration import (RULE_TITLES, Recording,  # noqa: E402
                                                calibrate, recommended_config,
                                                render_markdown)
from pardusinsight.config import AnalysisSettings, load_settings_file  # noqa: E402
from pardusinsight.export import ReportError, load_json_report  # noqa: E402


def split_heavy(spec: str) -> Tuple[str, Tuple[str, ...]]:
    """'yol[:kural,kural]' -> (yol, kurallar). Windows sürücü harfli yolları korunur."""
    path, sep, rules = spec.rpartition(":")
    if sep and rules and all(r.strip() in RULE_TITLES for r in rules.split(",")):
        return path, tuple(r.strip() for r in rules.split(","))
    return spec, ()


def _label(path: str, used: List[str]) -> str:
    base = os.path.splitext(os.path.basename(path))[0] or "kayit"
    label, n = base, 2
    while label in used:
        label, n = f"{base}-{n}", n + 1
    used.append(label)
    return label


def load_recordings(normals: Sequence[str],
                    heavies: Sequence[str]) -> List[Recording]:
    used: List[str] = []
    recordings = [Recording(_label(p, used), tuple(load_json_report(p).samples))
                  for p in normals]
    for spec in heavies:
        path, expect = split_heavy(spec)
        recordings.append(Recording(_label(path, used), tuple(load_json_report(path).samples),
                                    heavy=True, expect=expect))
    return recordings


def _write(path: str, text: str) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("normal", nargs="*", help="olağan kullanım kayıtları (JSON rapor)")
    parser.add_argument("--yogun", action="append", default=[], metavar="DOSYA[:KURAL,...]",
                        help="bilinen yoğun iş kaydı ve beklenen kurallar")
    parser.add_argument("--config", metavar="DOSYA", help="temel alınacak ayar dosyası")
    parser.add_argument("--cikti", metavar="DOSYA", help="Markdown raporu bu dosyaya yaz")
    parser.add_argument("--oneri-json", metavar="DOSYA",
                        help="önerilen eşikleri --config biçiminde bu dosyaya yaz")
    args = parser.parse_args(argv)
    if not args.normal and not args.yogun:
        parser.error("en az bir kayıt dosyası verin")
    try:
        base = load_settings_file(args.config).analysis if args.config else AnalysisSettings()
    except (ValueError, OSError) as exc:
        print(f"Ayarlar okunamadı: {exc}", file=sys.stderr)
        return 2
    try:
        recordings = load_recordings(args.normal, args.yogun)
    except ReportError as exc:
        print(f"Kayıt okunamadı: {exc}", file=sys.stderr)
        return 2
    result = calibrate(recordings, base)
    text = render_markdown(result)
    if args.cikti:
        _write(args.cikti, text)
        print(f"Kalibrasyon raporu yazıldı: {args.cikti}")
    else:
        print(text)
    if args.oneri_json:
        config = recommended_config(result)
        _write(args.oneri_json, json.dumps(config, ensure_ascii=False, indent=1) + "\n")
        print(f"Öneri dosyası yazıldı: {args.oneri_json} "
              f"({len(config.get('analysis', {}))} değişiklik)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
