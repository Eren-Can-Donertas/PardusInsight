"""Entegrasyon: sentetik kaynak -> normalizasyon -> tampon -> kurallar (MonitorService)."""
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from pardusinsight.collectors.synthetic import (SyntheticProcessCollector, SyntheticSource,
                                                scenario_names)
from pardusinsight.config import AppSettings
from pardusinsight.core.models import RawSnapshot
from pardusinsight.core.service import MonitorService, build_synthetic_service
from pardusinsight.export import load_json_report

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
    # Uyarı koşul bittikten sonra da güncellenir; bağlam baskı anındaki en büyük RSS'i gösterir
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


# ----------------------------------------------------------------------------- kayıtlı senaryolar
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import generate_scenarios  # noqa: E402


@pytest.mark.parametrize("name", generate_scenarios.FILES)
def test_recorded_scenario_files_match_current_code(name):
    path = ROOT / "scenarios" / f"{name}.json"
    assert path.exists(), f"{path.name} yok: python3 scripts/generate_scenarios.py"
    stored = load_json_report(str(path))
    service = generate_scenarios.run(name)
    assert stored.samples == service.history.snapshot(), \
        "senaryo dosyası güncel değil: python3 scripts/generate_scenarios.py"
    fresh = [(a.rule_id, a.first_seen, a.last_seen, a.resolved_at)
             for a in service.engine.alert_log()]
    assert [(a.rule_id, a.first_seen, a.last_seen, a.resolved_at) for a in stored.alerts] == fresh
    assert {a.rule_id for a in stored.alerts} == EXPECTED[name]


def test_each_rule_has_recorded_positive_and_negative_scenario():
    files = set(generate_scenarios.FILES)
    for rule in ("memory_pressure", "sustained_cpu", "disk_io_anomaly"):
        assert any(EXPECTED[n] == {rule} for n in files), f"{rule}: pozitif kayıt yok"
    for counter in ("memory_low_quiet", "cpu_spikes", "disk_steady"):
        assert counter in files and EXPECTED[counter] == set()


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_expectations_do_not_depend_on_seed(seed):
    for name, expected in EXPECTED.items():
        fired = {a.rule_id for a in run_scenario(name, seed=seed).engine.alert_log()}
        assert fired == expected, f"{name}, tohum {seed}"


def test_coarse_interval_does_not_alias_short_spikes():
    # 30 sn aralıkta her örnek tüm aralığın ortalamasını yansıtmalı; 8 sn'lik sıçramalar
    # aralığın sonuna denk geldi diye kalıcı yük gibi görünmemeli
    settings = AppSettings().with_interval(30.0)
    settings = replace(settings, analysis=replace(settings.analysis, window_s=60.0))
    source = SyntheticSource("cpu_spikes", step_s=30.0)
    service = MonitorService(source, SyntheticProcessCollector(source), settings)
    for _ in range(23):
        service.tick()
    cpu = [s.cpu_percent for s in service.history.snapshot() if s.cpu_percent is not None]
    assert max(cpu) < 60.0  # 8/30 sn %98 + 22/30 sn %15 ≈ %37
    assert service.engine.alert_log() == ()


def test_phase_mixing_weights_overlap():
    source = SyntheticSource("cpu", noise=False)
    inside = source.mixed_phase(10.0, 12.0)
    assert inside.name == "normal" and inside.cpu_percent == 15.0
    half = source.mixed_phase(119.0, 121.0)  # 1 sn normal + 1 sn cpu-yogun
    assert half.cpu_percent == pytest.approx((15.0 + 95.0) / 2)
    assert source.mixed_phase(120.0, 122.0).name == "cpu-yogun"


def test_process_collection_does_not_change_system_metrics():
    def cpu_series(process_every, with_processes=True):
        source = SyntheticSource("demo", seed=461)
        settings = replace(AppSettings(), process_every=process_every)
        collector = SyntheticProcessCollector(source) if with_processes else None
        service = MonitorService(source, collector, settings)
        for _ in range(60):
            service.tick()
        return [s.cpu_percent for s in service.history.snapshot()]

    reference = cpu_series(1)
    assert cpu_series(3) == reference
    assert cpu_series(1, with_processes=False) == reference


def test_subsecond_recording_is_loaded_completely():
    """0,5 sn aralıklı 40 dk'lık kayıt kesilmeden yüklenmeli.

    Eskiden kapasite 1 sn aralık varsayımıyla hesaplanıyor ve kayıt kesiliyordu.
    """
    settings = replace(AppSettings().with_interval(0.5), history_minutes=40)
    recorder = MonitorService(SyntheticSource("normal", step_s=0.5), None, settings)
    for _ in range(4800):
        recorder.tick()
    recorded = recorder.history.snapshot()
    service = build_synthetic_service("normal", loop=True)
    result = service.load_recording(recorded, "synthetic:normal")
    assert result.history_len == len(recorded) == 4800


def test_threshold_change_reanalyzes_loaded_recording():
    recorded = run_scenario("cpu").history.snapshot()
    service = build_synthetic_service("normal", loop=True)
    service.load_recording(recorded, "synthetic:cpu")
    assert [a.rule_id for a in service.engine.alert_log()] == ["sustained_cpu"]
    stricter = replace(service.settings, analysis=replace(service.settings.analysis,
                                                          cpu_high_pct=99.0))
    result = service.apply_settings(stricter)
    assert result is not None and result.alert_log == ()
    assert service.replay_mode and service.recording_source == "synthetic:cpu"
