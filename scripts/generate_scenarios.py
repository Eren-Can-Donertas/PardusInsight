#!/usr/bin/env python3
"""scenarios/ klasöründeki önceden kaydedilmiş sentetik senaryo dosyalarını üretir.

Dosyalar deterministiktir (sabit tohum ve başlangıç zamanı); demo sırasında
"Kayıt/senaryo aç" ile yüklenip kuralların nasıl tetiklendiği gösterilir.
Kullanım: python3 scripts/generate_scenarios.py [hedef_klasör]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pardusinsight.collectors.synthetic import (SCENARIOS, SyntheticProcessCollector,  # noqa: E402
                                                SyntheticSource)
from pardusinsight.config import AppSettings, settings_to_dict  # noqa: E402
from pardusinsight.core.service import MonitorService  # noqa: E402
from pardusinsight.export import build_report, write_json_report  # noqa: E402

FILES = ["demo", "cpu", "memory", "disk", "cpu_spikes", "memory_low_quiet"]


def main() -> int:
    target = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scenarios")
    os.makedirs(target, exist_ok=True)
    settings = AppSettings()
    for name in FILES:
        source = SyntheticSource(name, seed=461, step_s=settings.sample_interval_s)
        service = MonitorService(source, SyntheticProcessCollector(source), settings)
        ticks = int(source.total_duration / settings.sample_interval_s) + 1
        for _ in range(ticks):
            service.tick()
        report = build_report(service.history.snapshot(), service.engine.alert_log(),
                              settings_to_dict(settings), source=f"synthetic:{name}",
                              include_system_info=False)
        report["scenario"] = {"name": name, "description": SCENARIOS[name][0],
                              "seed": 461}
        path = os.path.join(target, f"{name}.json")
        write_json_report(path, report, compact=True)
        rules = ", ".join(a.rule_id for a in service.engine.alert_log()) or "uyarı yok"
        print(f"{path}: {len(service.history)} örnek — {rules}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
