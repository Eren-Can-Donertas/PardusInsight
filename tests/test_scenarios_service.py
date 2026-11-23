"""Entegrasyon: sentetik kaynak -> normalizasyon -> tampon -> kurallar (MonitorService)."""
from dataclasses import replace

import pytest

from pardusinsight.collectors.synthetic import (SyntheticProcessCollector, SyntheticSource,
                                                scenario_names)
from pardusinsight.config import AppSettings
from pardusinsight.core.models import RawSnapshot
from pardusinsight.core.service import MonitorService, build_synthetic_service

EXPECTED = {
    "normal": set(),
    "cpu": {"sustained_cpu"},
    "cpu_spikes": set(),
    "memory": {"memory_pressure"},
    "memory_low_quiet": set(),
    "disk": {"disk_io_anomaly"},
    "disk_steady": set(),
    "demo": {"sustained_cpu", "memory_pressure", "disk_io_anomaly"},
}


def run_scenario(name: str, seed: int = 461, settings=None):
    source = SyntheticSource(name, seed=seed, step_s=2.0)
    service = MonitorService(source, SyntheticProcessCollector(source), settings)
    ticks = int(min(source.total_duration, 1200) / 2.0) + 1
    for _ in range(ticks):
        result = service.tick()
        assert result.errors == ()
    return service


def test_every_scenario_has_an_expectation():
    assert set(EXPECTED) == set(scenario_names())


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_scenario_produces_expected_alerts(name):
    service = run_scenario(name)
    fired = {a.rule_id for a in service.engine.alert_log()}
    assert fired == EXPECTED[name]


def test_scenarios_are_deterministic_for_same_seed():
    a = [(x.rule_id, x.first_seen) for x in run_scenario("demo", seed=7).engine.alert_log()]
    b = [(x.rule_id, x.first_seen) for x in run_scenario("demo", seed=7).engine.alert_log()]
    assert a == b


def test_memory_alert_explains_with_top_memory_process():
    service = run_scenario("memory")
    alert = next(a for a in service.engine.alert_log() if a.rule_id == "memory_pressure")
    # Uyarı, koşul bittikten sonra da güncellenir; bağlam yine baskı anındaki en büyük RSS'i gösterir
    assert not alert.active
    assert alert.context[0].startswith("firefox-esr") and "4,4 GiB" in alert.context[0]
    assert alert.window_start >= service.history.snapshot()[0].timestamp


class FlakySource:
    """Her üç çağrıdan birinde istisna fırlatan kaynak."""

    source_name = "flaky"

    def __init__(self):
        self.inner = SyntheticSource("normal")
        self.calls = 0

    def collect(self) -> RawSnapshot:
        self.calls += 1
        if self.calls % 3 == 0:
            raise OSError("geçici okuma hatası")
        return self.inner.collect()


class BrokenProcesses:
    def collect(self):
        raise RuntimeError("psutil çöktü")


def test_service_tick_never_raises_on_source_failures():
    service = MonitorService(FlakySource(), BrokenProcesses())
    results = [service.tick() for _ in range(9)]
    failed = [r for r in results if r.sample is None]
    assert len(failed) == 3 and all("Ölçüm alınamadı" in r.errors[0] for r in failed)
    ok = [r for r in results if r.sample is not None]
    assert all(any("Süreç listesi alınamadı" in e for e in r.errors) for r in ok)
    assert len(service.history) == 6


def test_process_every_reuses_last_process_snapshot():
    source = SyntheticSource("normal")

    class Counting(SyntheticProcessCollector):
        calls = 0

        def collect(self):
            Counting.calls += 1
            return super().collect()

    settings = replace(AppSettings(), process_every=3)
    service = MonitorService(source, Counting(source), settings)
    results = [service.tick() for _ in range(9)]
    assert Counting.calls == 3
    assert all(r.processes is not None for r in results)


def test_service_history_respects_configured_duration():
    settings = replace(AppSettings(), history_minutes=1.0)
    service = build_synthetic_service("normal", settings, loop=True, start_time=0.0)
    for _ in range(200):
        service.tick()
    assert len(service.history) == 31  # 60 sn / 2 sn + 1
    assert service.history.duration_s() == pytest.approx(60.0)


def test_load_recording_and_reset_live():
    recorded = run_scenario("cpu").history.snapshot()
    service = build_synthetic_service("normal", loop=True)
    result = service.load_recording(recorded)
    assert service.replay_mode and result.history_len == len(recorded)
    assert [a.rule_id for a in result.alert_log] == ["sustained_cpu"]
    service.reset_live()
    assert not service.replay_mode and len(service.history) == 0
    assert service.engine.alert_log() == ()
    assert service.tick().sample is not None


def test_shorter_interval_keeps_full_history_capacity():
    service = build_synthetic_service("normal", loop=True, start_time=0.0)
    for _ in range(10):
        service.tick()
    service.apply_settings(service.settings.with_interval(0.5))
    assert len(service.history) == 10  # geçmiş korunur
    assert service.history.capacity == 3601  # 30 dk / 0,5 sn + 1
    assert service.source.step_s == 0.5
    for _ in range(4000):
        service.tick()
    assert service.history.duration_s() == pytest.approx(1800.0)


def test_apply_settings_changes_rule_thresholds():
    service = build_synthetic_service("normal", loop=True, start_time=0.0)
    new = replace(service.settings, analysis=replace(service.settings.analysis,
                                                     cpu_high_pct=10.0, cpu_min_fraction=0.5))
    service.apply_settings(new)
    for _ in range(40):
        service.tick()
    assert any(a.rule_id == "sustained_cpu" for a in service.engine.alert_log())
