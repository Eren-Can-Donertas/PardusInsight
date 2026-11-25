"""Kural motoru, uyarı yaşam döngüsü ve açıklama içeriği testleri."""
from dataclasses import replace

import pytest

from conftest import T0, build_series
from pardusinsight.analysis.engine import RuleEngine, replay
from pardusinsight.analysis.explain import alert_to_html, alert_to_text
from pardusinsight.analysis.rules import Rule, RuleOutcome, SustainedCpuRule
from pardusinsight.config import AnalysisSettings


def cpu_profile(high_from: float, high_to: float):
    return lambda i, t: dict(cpu_percent=96.0 if high_from <= t < high_to else 10.0)


def run(engine, samples):
    updates = []
    for k in range(1, len(samples) + 1):
        updates.append(engine.evaluate(samples[:k]))
    return updates


def test_alert_lifecycle_new_update_resolve():
    samples = build_series(150, cpu_profile(60, 200))
    engine = RuleEngine()
    updates = run(engine, samples)
    new = [a for u in updates for a in u.new]
    resolved = [a for u in updates for a in u.resolved]
    assert len(new) == 1 and len(resolved) == 1
    alert = engine.alert_log()[0]
    assert alert.rule_id == "sustained_cpu" and not alert.active
    assert alert.first_seen < alert.last_seen < alert.resolved_at
    # Çözülme, koşul ortadan kalktıktan sonra en az bekleme süresi kadar sonra olur
    assert alert.resolved_at - alert.last_seen >= engine.settings.resolve_grace_s
    assert engine.active_alerts() == ()


def test_alert_contains_full_explanation():
    samples = build_series(60, lambda i, t: dict(cpu_percent=97.0))
    engine = RuleEngine()
    engine.evaluate(samples)
    (alert,) = engine.active_alerts()
    assert alert.summary and alert.uncertainty and alert.suggestions
    assert alert.window_start < alert.window_end
    assert any(e.role == "trigger" and e.satisfied for e in alert.evidence)
    text = alert_to_text(alert)
    assert "Zaman aralığı" in text and "Belirsizlik" in text
    html = alert_to_html(alert)
    assert "Tetikleyici metrikler" in html and "≥" in html


class ExplodingRule(Rule):
    rule_id = "patlayan"
    title = "Hatalı kural"

    def evaluate(self, samples, settings):
        raise ZeroDivisionError("test")


def test_rule_exception_is_isolated():
    samples = build_series(60, lambda i, t: dict(cpu_percent=97.0))
    engine = RuleEngine(rules=[ExplodingRule(), SustainedCpuRule()])
    update = engine.evaluate(samples)
    assert any("Hatalı kural" in e for e in update.errors)
    assert [a.rule_id for a in update.new] == ["sustained_cpu"]
    statuses = {s.rule_id: s for s in update.statuses}
    assert statuses["patlayan"].triggered is False


def test_short_dip_does_not_flap_alert():
    class Toggle(Rule):
        rule_id = "toggle"
        title = "Dalgalı"

        def __init__(self):
            self.calls = 0

        def evaluate(self, samples, settings):
            from pardusinsight.analysis.rules import AlertDraft
            self.calls += 1
            if self.calls == 3:  # tek bir değerlendirmede koşul sağlanmadı
                return RuleOutcome(False, "geçici")
            ts = samples[-1].timestamp
            return RuleOutcome(True, "ok", AlertDraft("Dalgalı", "warning", "orta", "",
                                                      ts - 1, ts, (), (), "", ()))

    engine = RuleEngine(rules=[Toggle()])
    samples = build_series(6)
    updates = run(engine, samples)
    assert sum(len(u.new) for u in updates) == 1
    assert sum(len(u.resolved) for u in updates) == 0


def test_alert_log_is_bounded():
    engine = RuleEngine(max_log=3)
    samples = build_series(30 * 40, lambda i, t: dict(
        cpu_percent=96.0 if (t // 300) % 2 == 0 else 5.0))
    replay_engine = replay(samples, engine.settings)
    assert len(replay_engine.alert_log()) >= 4
    for alert in replay_engine.alert_log():
        engine._put(alert)
    assert len(engine.alert_log()) <= 3


def test_replay_is_deterministic():
    samples = build_series(300, cpu_profile(100, 400))
    a = replay(samples).alert_log()
    b = replay(list(reversed(samples))).alert_log()  # sıralama girdiye bağlı değil
    assert [(x.alert_id, x.first_seen, x.resolved_at) for x in a] == \
        [(x.alert_id, x.first_seen, x.resolved_at) for x in b]


def test_statuses_report_reason_for_every_rule():
    update = RuleEngine().evaluate(build_series(60))
    assert [s.rule_id for s in update.statuses] == ["memory_pressure", "sustained_cpu",
                                                    "disk_io_anomaly"]
    assert all(s.reason for s in update.statuses)


def test_settings_validation_rejects_inconsistent_thresholds():
    from pardusinsight.config import AnalysisSettings

    with pytest.raises(ValueError):
        AnalysisSettings(mem_available_crit_pct=20.0, mem_available_warn_pct=10.0).validate()
    with pytest.raises(ValueError):
        AnalysisSettings(window_s=2.0).validate()
    assert replace(AnalysisSettings(), cpu_high_pct=70.0).validate().cpu_high_pct == 70.0


# ----------------------------------------------------------------------------- yetersiz veri
def test_pause_in_sampling_does_not_resolve_and_reopen_alert():
    # Örnekleme 20 sn duraklıyor (ör. kullanıcı "Duraklat"a bastı); yük hiç kesilmiyor
    samples = [s for s in build_series(200, lambda i, t: dict(cpu_percent=96.0))
               if not 100 < s.timestamp - T0 <= 120]
    engine = RuleEngine()
    updates = run(engine, samples)
    assert sum(len(u.new) for u in updates) == 1
    assert sum(len(u.resolved) for u in updates) == 0
    assert [a.rule_id for a in engine.active_alerts()] == ["sustained_cpu"]


def test_prolonged_missing_data_resolves_alert_after_hold():
    samples = build_series(300, lambda i, t: dict(cpu_percent=96.0 if t < 200 else None))
    engine = RuleEngine()
    statuses = []
    for k in range(1, len(samples) + 1):
        update = engine.evaluate(samples[:k])
        cpu = next(s for s in update.statuses if s.rule_id == "sustained_cpu")
        statuses.append((samples[k - 1].timestamp, cpu.reason))
    (alert,) = engine.alert_log()
    assert not alert.active
    # Uyarı açıldıktan sonra verinin yetersiz kalmaya başladığı ilk an
    unknown_from = next(t for t, reason in statuses
                        if t > alert.last_seen and reason.startswith("Yetersiz veri"))
    hold = engine.settings.evaluation_span_s + engine.settings.resolve_grace_s
    assert hold <= alert.resolved_at - unknown_from <= hold + engine.settings.sample_interval_s


def test_rule_error_does_not_close_active_alert_immediately():
    class FlakyCpu(SustainedCpuRule):
        calls = 0

        def evaluate(self, samples, settings):
            FlakyCpu.calls += 1
            if 40 <= FlakyCpu.calls < 45:
                raise RuntimeError("geçici hata")
            return super().evaluate(samples, settings)

    engine = RuleEngine(rules=[FlakyCpu()])
    updates = run(engine, build_series(80, lambda i, t: dict(cpu_percent=97.0)))
    assert any(u.errors for u in updates)
    assert sum(len(u.resolved) for u in updates) == 0
    assert len(engine.alert_log()) == 1 and engine.alert_log()[0].active


# ----------------------------------------------------------------------------- önem ve aralık
def test_severity_follows_current_evidence():
    def profile(i, t):
        if t < 120:  # ağır baskı: kritik
            return dict(mem_available_percent=3.0, swap_in_pages_per_s=400.0,
                        swap_out_pages_per_s=400.0, major_faults_per_s=500.0,
                        psi_memory_some=30.0)
        return dict(mem_available_percent=8.0, major_faults_per_s=150.0)  # hafiflemiş: uyarı

    engine = RuleEngine()
    updates = run(engine, build_series(150, profile))
    severities = [a.severity for u in updates for a in u.active]
    assert "critical" in severities
    (alert,) = engine.active_alerts()
    assert alert.severity == "warning" and alert.confidence == "orta"


def test_recording_at_other_interval_is_analyzed_with_observed_interval():
    # 2 sn aralıklı kayıt, 1 sn ayarıyla açılıyor (ör. GUI'de aralık değiştirildikten sonra)
    samples = build_series(60, lambda i, t: dict(cpu_percent=97.0))
    settings = AnalysisSettings(sample_interval_s=1.0)
    assert [a.rule_id for a in replay(samples, settings).alert_log()] == ["sustained_cpu"]
    engine = RuleEngine(settings)
    assert engine.effective_settings(samples).sample_interval_s == 2.0


def test_effective_interval_ignores_single_gap():
    samples = [s for s in build_series(100) if not 60 < s.timestamp - T0 <= 90]
    assert RuleEngine().effective_settings(samples).sample_interval_s == 2.0
