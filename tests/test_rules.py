"""Üç analiz kuralı için pozitif ve negatif (yanlış tetiklenme karşı-örneği) sentetik testler.

Varsayılan ayarlar: 2 sn aralık, 2 × 30 sn ardışık pencere, disk için 300 sn taban.
"""
from dataclasses import replace

import pytest

from conftest import MIB, build_series
from pardusinsight.analysis.rules import DiskIoAnomalyRule, MemoryPressureRule, SustainedCpuRule
from pardusinsight.core.models import SEVERITY_CRITICAL, SEVERITY_INFO, SEVERITY_WARNING

# ----------------------------------------------------------------------------- bellek


def test_memory_pressure_positive_low_available_with_swap(settings):
    samples = build_series(60, lambda i, t: dict(mem_available_percent=6.0,
                                                 swap_in_pages_per_s=150.0,
                                                 swap_out_pages_per_s=150.0))
    out = MemoryPressureRule().evaluate(samples, settings)
    assert out.triggered
    d = out.draft
    assert d.severity == SEVERITY_WARNING and d.confidence == "orta"
    assert d.window_end == samples[-1].timestamp
    assert d.window_end - d.window_start == pytest.approx(60.0)
    triggers = [e for e in d.evidence if e.role == "trigger"]
    assert len(triggers) == 2 and all(e.satisfied for e in triggers)
    swap = next(e for e in d.evidence if e.metric == "swap_activity")
    assert swap.satisfied and swap.value == pytest.approx(300.0)
    assert "kesin arıza tanısı değildir" in d.uncertainty


def test_memory_pressure_critical_with_multiple_supports(settings):
    samples = build_series(60, lambda i, t: dict(mem_available_percent=3.0,
                                                 swap_in_pages_per_s=400.0,
                                                 swap_out_pages_per_s=400.0,
                                                 major_faults_per_s=500.0,
                                                 psi_memory_some=30.0))
    d = MemoryPressureRule().evaluate(samples, settings).draft
    assert d.severity == SEVERITY_CRITICAL and d.confidence == "yüksek"


def test_memory_negative_low_available_without_supporting_signals(settings):
    samples = build_series(60, lambda i, t: dict(mem_available_percent=7.0))
    out = MemoryPressureRule().evaluate(samples, settings)
    assert not out.triggered and "desteklemiyor" in out.reason


def test_memory_negative_only_latest_window_low(settings):
    # İlk pencerede bellek yeterli, yalnızca son 30 sn düşük: kalıcı değil
    samples = build_series(60, lambda i, t: dict(
        mem_available_percent=6.0 if t > 88 else 40.0, swap_in_pages_per_s=500.0))
    assert not MemoryPressureRule().evaluate(samples, settings).triggered


def test_memory_positive_via_psi_when_swap_is_unavailable(settings):
    samples = build_series(60, lambda i, t: dict(
        mem_available_percent=5.5, swap_in_pages_per_s=None, swap_out_pages_per_s=None,
        swap_total_bytes=0, psi_memory_some=20.0))
    out = MemoryPressureRule().evaluate(samples, settings)
    assert out.triggered
    assert "Ölçülemeyen göstergeler: Swap etkinliği" in out.draft.uncertainty


def test_memory_insufficient_data_is_not_an_alert(settings):
    samples = build_series(60, lambda i, t: dict(
        mem_available_percent=None if i % 2 else 4.0, swap_in_pages_per_s=500.0))
    out = MemoryPressureRule().evaluate(samples, settings)
    assert not out.triggered and out.reason.startswith("Yetersiz veri")


# ----------------------------------------------------------------------------- CPU


def test_cpu_sustained_positive_with_process_context(settings, brief):
    top = (brief(4100, "cc1plus", cpu=60.0), brief(1500, "firefox-esr", cpu=5.0))
    samples = build_series(60, lambda i, t: dict(cpu_percent=95.0, top_cpu=top))
    out = SustainedCpuRule().evaluate(samples, settings)
    assert out.triggered and out.draft.severity == SEVERITY_WARNING
    assert out.draft.context[0].startswith("cc1plus (PID 4100)")
    assert any(e.metric == "load1" and e.role == "context" for e in out.draft.evidence)


def test_cpu_negative_short_spikes(settings):
    # Her üç örnekten biri %99: ortalama yüksek olsa da kalıcı değil
    samples = build_series(120, lambda i, t: dict(cpu_percent=99.0 if i % 3 == 0 else 30.0))
    out = SustainedCpuRule().evaluate(samples, settings)
    assert not out.triggered and "kalıcı değil" in out.reason


def test_cpu_negative_only_latest_window_high(settings):
    samples = build_series(60, lambda i, t: dict(cpu_percent=97.0 if t > 88 else 20.0))
    assert not SustainedCpuRule().evaluate(samples, settings).triggered


def test_cpu_threshold_is_configurable(settings):
    samples = build_series(60, lambda i, t: dict(cpu_percent=80.0))
    assert not SustainedCpuRule().evaluate(samples, settings).triggered
    assert SustainedCpuRule().evaluate(samples, replace(settings, cpu_high_pct=75.0)).triggered


def test_cpu_user_defined_window_length(settings):
    # 50 sn yüksek CPU: 2×30 sn ile kalıcı sayılmaz, kullanıcı penceresi 2×20 sn ise sayılır
    samples = build_series(80, lambda i, t: dict(cpu_percent=96.0 if t >= 108 else 10.0))
    assert not SustainedCpuRule().evaluate(samples, settings).triggered
    assert SustainedCpuRule().evaluate(samples, replace(settings, window_s=20.0)).triggered


# ----------------------------------------------------------------------------- disk


def _disk(read_mib, write_mib, busy):
    return dict(disk_read_bytes_per_s=read_mib * MIB, disk_write_bytes_per_s=write_mib * MIB,
                disk_busy_percent=busy)


def test_disk_positive_burst_relative_to_previous_period(settings, brief):
    top_io = (brief(5200, "rsync", io=90 * MIB),)
    samples = build_series(240, lambda i, t: dict(
        _disk(60, 40, 90) if t >= 360 else _disk(0.6, 0.4, 3), top_io=top_io))
    out = DiskIoAnomalyRule().evaluate(samples, settings)
    assert out.triggered
    d = out.draft
    assert d.severity == SEVERITY_INFO and "gözlemsel" in d.uncertainty
    assert d.context[0].startswith("rsync")
    baseline = next(e for e in d.evidence if e.metric == "baseline_throughput")
    assert baseline.value == pytest.approx(1.0 * MIB)


def test_disk_negative_steady_high_activity(settings):
    samples = build_series(240, lambda i, t: _disk(12, 8, 35))
    out = DiskIoAnomalyRule().evaluate(samples, settings)
    assert not out.triggered


def test_disk_negative_large_ratio_but_below_absolute_floor(settings):
    # 0,1 -> 1 MiB/sn: 10 kat artış ama 5 MiB/sn alt sınırının altında
    samples = build_series(240, lambda i, t: _disk(0.5, 0.5, 4) if t >= 360 else
                           _disk(0.05, 0.05, 1))
    assert not DiskIoAnomalyRule().evaluate(samples, settings).triggered


def test_disk_positive_busy_without_baseline(settings):
    samples = build_series(35, lambda i, t: _disk(3, 1, 95))  # ~70 sn veri, taban yok
    out = DiskIoAnomalyRule().evaluate(samples, settings)
    assert out.triggered and "meşguliyeti" in out.draft.summary
    baseline = next(e for e in out.draft.evidence if e.metric == "baseline_throughput")
    assert baseline.satisfied is False and "Yetersiz taban" in baseline.note


def test_disk_negative_busy_already_high_in_baseline(settings):
    samples = build_series(240, lambda i, t: _disk(2, 1, 92))
    assert not DiskIoAnomalyRule().evaluate(samples, settings).triggered


def test_disk_negative_single_short_burst(settings):
    # Yalnızca 8 sn süren sıçrama medyanı etkilemez
    samples = build_series(240, lambda i, t: _disk(80, 0, 95) if 462 <= t < 470 else
                           _disk(0.5, 0.5, 3))
    assert not DiskIoAnomalyRule().evaluate(samples, settings).triggered


# ----------------------------------------------------------------------------- açıklama metinleri
def test_insufficient_outcome_is_flagged_as_unknown(settings):
    sparse = build_series(60, lambda i, t: dict(cpu_percent=None if i % 2 else 97.0))
    out = SustainedCpuRule().evaluate(sparse, settings)
    assert out.reason.startswith("Yetersiz veri") and out.insufficient
    normal = SustainedCpuRule().evaluate(build_series(60), settings)
    assert not normal.triggered and not normal.insufficient


def test_memory_value_near_threshold_is_not_rounded_onto_it(settings):
    samples = build_series(60, lambda i, t: dict(mem_available_percent=9.97,
                                                 swap_in_pages_per_s=200.0))
    out = MemoryPressureRule().evaluate(samples, settings)
    assert out.triggered and "son medyan %9,97" in out.draft.summary


def test_disk_floor_note_keeps_fraction(settings):
    s = replace(settings, disk_min_throughput_mib_s=2.5)
    samples = build_series(240, lambda i, t: _disk(2, 1, 5) if t >= 360 else _disk(0.05, 0.05, 1))
    out = DiskIoAnomalyRule().evaluate(samples, s)
    assert out.triggered
    notes = [e.note for e in out.draft.evidence if e.metric == "disk_total_bytes_per_s"]
    assert notes and all("2,5 MiB/sn" in n for n in notes)


def test_disk_negative_reason_names_the_failing_window(settings):
    # Sıçrama yalnızca son pencerede: neden metni geçen değil, geçemeyen pencereyi göstermeli
    samples = build_series(240, lambda i, t: _disk(60, 40, 90) if t >= 440 else _disk(0.6, 0.4, 3))
    out = DiskIoAnomalyRule().evaluate(samples, settings)
    assert not out.triggered
    assert "ilk pencere okuma+yazma medyanı 1,0 MiB/sn" in out.reason
    assert "ilk pencere meşguliyet medyanı %3,0" in out.reason


def test_disk_busy_alert_reports_baseline_busy(settings):
    samples = build_series(240, lambda i, t: _disk(1.5, 0.5, 92) if t >= 360 else
                           _disk(0.6, 0.4, 10))
    out = DiskIoAnomalyRule().evaluate(samples, settings)
    assert out.triggered and "önceki dönem medyanı %10,0" in out.draft.summary
    baseline = next(e for e in out.draft.evidence if e.metric == "baseline_busy_percent")
    assert baseline.value == 10.0 and baseline.satisfied


def test_cpu_summary_has_no_fixed_turkish_suffix(settings):
    s = replace(settings, cpu_min_fraction=0.5)
    out = SustainedCpuRule().evaluate(build_series(60, lambda i, t: dict(cpu_percent=96.0)), s)
    assert "örneklerin en az %50 kadarında %85 eşiğinin üzerindeydi" in out.draft.summary
    assert "'i " not in out.draft.summary


def test_process_context_averages_over_appearances(settings, brief):
    top = (brief(4100, "cc1plus", cpu=20.0),)
    samples = build_series(60, lambda i, t: dict(cpu_percent=96.0,
                                                 top_cpu=top if i % 2 == 0 else ()))
    out = SustainedCpuRule().evaluate(samples, settings)
    (line,) = out.draft.context
    assert line.startswith("cc1plus (PID 4100): ortalama %20,0 CPU")
    assert "15/30 örnekte" in line


def test_context_says_so_when_no_process_information(settings):
    from pardusinsight.analysis.rules import NO_PROCESS_INFO

    cpu = SustainedCpuRule().evaluate(build_series(60, lambda i, t: dict(cpu_percent=96.0)),
                                      settings)
    disk = DiskIoAnomalyRule().evaluate(build_series(35, lambda i, t: _disk(3, 1, 95)), settings)
    assert cpu.draft.context == (NO_PROCESS_INFO,) == disk.draft.context


# ----------------------------------------------------------------------------- sınırlar ve karşı-örnekler
# (Mutasyon denemesi: aşağıdaki testler olmadan "her pencerede" -> "herhangi bir pencerede",
#  medyan -> ortalama, < -> <= gibi değişiklikler hiçbir testi düşürmüyordu.)
@pytest.mark.parametrize("value, fires", [(10.0, False), (9.99, True)])
def test_memory_available_threshold_is_strict(settings, value, fires):
    samples = build_series(60, lambda i, t: dict(mem_available_percent=value,
                                                 swap_in_pages_per_s=500.0))
    assert MemoryPressureRule().evaluate(samples, settings).triggered is fires


def test_memory_support_threshold_is_inclusive(settings):
    samples = build_series(60, lambda i, t: dict(mem_available_percent=6.0,
                                                 swap_in_pages_per_s=50.0,
                                                 swap_out_pages_per_s=50.0))  # tam 100 sayfa/sn
    assert MemoryPressureRule().evaluate(samples, settings).triggered


@pytest.mark.parametrize("value, severity", [(5.0, SEVERITY_WARNING), (4.99, SEVERITY_CRITICAL)])
def test_memory_critical_threshold_is_strict(settings, value, severity):
    samples = build_series(60, lambda i, t: dict(mem_available_percent=value,
                                                 swap_in_pages_per_s=400.0,
                                                 swap_out_pages_per_s=400.0,
                                                 major_faults_per_s=500.0))
    assert MemoryPressureRule().evaluate(samples, settings).draft.severity == severity


def test_memory_single_support_stays_warning_even_when_very_low(settings):
    samples = build_series(60, lambda i, t: dict(mem_available_percent=3.0,
                                                 swap_in_pages_per_s=150.0,
                                                 swap_out_pages_per_s=150.0))
    d = MemoryPressureRule().evaluate(samples, settings).draft
    assert d.severity == SEVERITY_WARNING and d.confidence == "orta"


def test_memory_critical_requires_every_window_below_critical(settings):
    samples = build_series(60, lambda i, t: dict(
        mem_available_percent=3.0 if t > 88 else 7.0, swap_in_pages_per_s=400.0,
        swap_out_pages_per_s=400.0, major_faults_per_s=500.0, psi_memory_some=30.0))
    d = MemoryPressureRule().evaluate(samples, settings).draft
    assert d.severity == SEVERITY_WARNING and d.confidence == "yüksek"


def test_memory_major_faults_alone_support_the_alert(settings):
    samples = build_series(60, lambda i, t: dict(mem_available_percent=6.0,
                                                 major_faults_per_s=400.0))
    out = MemoryPressureRule().evaluate(samples, settings)
    assert out.triggered
    support = {e.metric: e.satisfied for e in out.draft.evidence if e.role == "support"}
    assert support == {"swap_activity": False, "major_faults_per_s": True,
                       "psi_memory_some": False}


def test_cpu_fraction_and_threshold_are_inclusive(settings):
    # Her pencerede 15 örneğin 12'si tam %85: oran tam %80 -> tetiklenir
    samples = build_series(60, lambda i, t: dict(cpu_percent=85.0 if i % 5 else 10.0))
    out = SustainedCpuRule().evaluate(samples, settings)
    assert out.triggered
    triggers = [e for e in out.draft.evidence if e.role == "trigger"]
    assert [e.value for e in triggers] == [80.0, 80.0] and all(e.satisfied for e in triggers)


def test_cpu_high_average_without_sustained_fraction_does_not_trigger(settings):
    # Örneklerin %60'ı %100, %40'ı %70: pencere ortalaması %88 ama eşik üstü oran %60
    samples = build_series(60, lambda i, t: dict(cpu_percent=100.0 if i % 5 < 3 else 70.0))
    out = SustainedCpuRule().evaluate(samples, settings)
    assert not out.triggered and "kalıcı değil" in out.reason


def test_disk_ratio_condition_alone_triggers_with_low_confidence(settings):
    # SSD/NVMe: hız 50 kat arttı ama meşguliyet %40'ta kaldı
    samples = build_series(240, lambda i, t: _disk(30, 20, 40) if t >= 360 else
                           _disk(0.6, 0.4, 3))
    d = DiskIoAnomalyRule().evaluate(samples, settings).draft
    assert d.confidence == "düşük" and "kat arttı" in d.summary
    assert "meşguliyeti" not in d.summary


def test_disk_both_conditions_give_medium_confidence(settings):
    samples = build_series(240, lambda i, t: _disk(60, 40, 90) if t >= 360 else
                           _disk(0.6, 0.4, 3))
    d = DiskIoAnomalyRule().evaluate(samples, settings).draft
    assert d.confidence == "orta" and "kat arttı" in d.summary and "meşguliyeti" in d.summary


def test_disk_periodic_short_bursts_do_not_trigger(settings):
    # Her 30 sn'de 8 sn'lik kopyalama: pencere ortalaması ~22 MiB/sn, medyan ~1 MiB/sn
    samples = build_series(240, lambda i, t: _disk(80, 0, 95) if (t % 30) < 8 else
                           _disk(0.5, 0.5, 3))
    assert not DiskIoAnomalyRule().evaluate(samples, settings).triggered


@pytest.mark.parametrize("now", [_disk(2.5, 2.5, 10), _disk(1, 1, 80)])
def test_disk_thresholds_are_inclusive(settings, now):
    # (1) medyan tam 5 MiB/sn = max(3 × 1 MiB/sn, 5 MiB/sn); (2) meşguliyet tam %80
    samples = build_series(240, lambda i, t: now if t >= 360 else _disk(0.5, 0.5, 3))
    assert DiskIoAnomalyRule().evaluate(samples, settings).triggered


# ----------------------------------------------------------------------------- CPU kaynağı


def test_cpu_load_attributed_to_dominant_process_group(settings, brief):
    top = tuple(brief(4100 + k, "cc1plus", cpu=30.0) for k in range(3)) + \
        (brief(1500, "firefox-esr", cpu=3.0),)
    samples = build_series(60, lambda i, t: dict(cpu_percent=96.0, top_cpu=top))
    draft = SustainedCpuRule().evaluate(samples, settings).draft
    assert "kadarı cc1plus (3 süreç) kaynaklı" in draft.summary
    share = next(e for e in draft.evidence if e.metric == "top_process_share")
    assert share.satisfied and share.value == pytest.approx(93.8, abs=0.1)


def test_cpu_load_reported_as_distributed_across_processes(settings, brief):
    top = tuple(brief(100 + k, f"is-{k}", cpu=18.0) for k in range(5))
    samples = build_series(60, lambda i, t: dict(cpu_percent=92.0, top_cpu=top))
    draft = SustainedCpuRule().evaluate(samples, settings).draft
    assert "birden fazla sürece dağılmış" in draft.summary


def test_cpu_source_unknown_without_process_data(settings):
    samples = build_series(60, lambda i, t: dict(cpu_percent=95.0))
    draft = SustainedCpuRule().evaluate(samples, settings).draft
    assert "belirlenemedi" in draft.summary
    assert not any(e.metric == "top_process_share" for e in draft.evidence)
