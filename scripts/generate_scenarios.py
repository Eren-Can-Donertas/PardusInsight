#!/usr/bin/env python3
"""scenarios/ klasöründeki önceden kaydedilmiş sentetik senaryo dosyalarını üretir.

Dosyalar deterministiktir: sabit tohum, sabit başlangıç zamanı ve sabit (UTC)
meta zaman damgaları kullanılır; aynı kodla yeniden üretildiğinde bayt bayt aynı
çıkar. Demo sırasında "Kayıt/senaryo aç" ile yüklenip kuralların nasıl tetiklendiği
gösterilir. Her kural için en az bir pozitif ve bir karşı-örnek senaryo vardır.
tests/test_scenarios_service.py, kayıtlı dosyaların güncel kodla aynı örnek ve
uyarıları verdiğini denetler; kurallar değişirse bu betiği yeniden çalıştırın.

Kullanım: python3 scripts/generate_scenarios.py [hedef_klasör]
"""
import os
import sys
import time
from typing import Any, Dict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pardusinsight.collectors.synthetic import (DEFAULT_START, SCENARIOS,  # noqa: E402
                                                SyntheticProcessCollector, SyntheticSource)
from pardusinsight.config import AppSettings, settings_to_dict  # noqa: E402
from pardusinsight.core.service import MonitorService  # noqa: E402
from pardusinsight.export import build_report, write_json_report  # noqa: E402

SEED = 461
# Pozitif örnekler ve karşı-örnekler (her kural için en az bir tane)
FILES = ["demo", "cpu", "memory", "disk", "cpu_spikes", "memory_low_quiet", "disk_steady"]


def _utc_iso(ts: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S+0000", time.gmtime(ts))


def run(name: str, settings: AppSettings = None) -> MonitorService:
    """Senaryoyu baştan sona izleme servisinden geçirir."""
    settings = settings or AppSettings()
    source = SyntheticSource(name, seed=SEED, step_s=settings.sample_interval_s)
    service = MonitorService(source, SyntheticProcessCollector(source), settings)
    for _ in range(int(source.total_duration / settings.sample_interval_s) + 1):
        service.tick()
    return service


def scenario_report(name: str) -> Dict[str, Any]:
    """Senaryonun JSON raporunu makineden ve saat diliminden bağımsız üretir."""
    settings = AppSettings()
    service = run(name, settings)
    samples = service.history.snapshot()
    report = build_report(samples, service.engine.alert_log(), settings_to_dict(settings),
                          source=f"synthetic:{name}", include_system_info=False)
    report["created_at"] = _utc_iso(DEFAULT_START)
    report["created_at_epoch"] = DEFAULT_START
    if samples:
        report["summary"]["start"] = _utc_iso(samples[0].timestamp)
        report["summary"]["end"] = _utc_iso(samples[-1].timestamp)
    report["scenario"] = {"name": name, "description": SCENARIOS[name][0], "seed": SEED}
    return report


def main() -> int:
    target = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scenarios")
    os.makedirs(target, exist_ok=True)
    for name in FILES:
        report = scenario_report(name)
        path = os.path.join(target, f"{name}.json")
        write_json_report(path, report, compact=True)
        rules = ", ".join(a["rule_id"] for a in report["alerts"]) or "uyarı yok"
        print(f"{path}: {report['summary']['sample_count']} örnek — {rules}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
