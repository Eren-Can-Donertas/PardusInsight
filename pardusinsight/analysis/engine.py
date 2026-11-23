"""Kural motoru: kuralları geçmiş üzerinde çalıştırır ve uyarı yaşam döngüsünü yönetir.

Yaşam döngüsü: koşul ilk sağlandığında yeni uyarı açılır; sağlanmaya devam
ettikçe kanıtları ve zaman aralığı güncellenir; ``resolve_grace_s`` boyunca
sağlanmazsa "çözüldü" olarak kapatılır (kısa dalgalanmalarda uyarı açılıp
kapanmasını önler). Bir kuralın beklenmedik hatası diğer kuralları ve
uygulamayı etkilemez.
"""
from __future__ import annotations

from collections import OrderedDict, deque
from dataclasses import replace
from typing import Deque, Dict, Iterable, List, Optional, Sequence, Tuple

from ..config import AnalysisSettings
from ..core.history import since
from ..core.models import (SEVERITY_ORDER, Alert, EngineUpdate, RuleStatus, SystemSample)
from .rules import Rule, RuleOutcome, default_rules


class RuleEngine:
    def __init__(self, settings: Optional[AnalysisSettings] = None,
                 rules: Optional[Sequence[Rule]] = None, max_log: int = 200) -> None:
        self.settings = (settings or AnalysisSettings()).validate()
        self.rules: List[Rule] = list(rules) if rules is not None else default_rules()
        self.max_log = max_log
        self._active: Dict[str, Alert] = {}
        self._last_true: Dict[str, float] = {}
        self._log: "OrderedDict[str, Alert]" = OrderedDict()
        self._statuses: Dict[str, RuleStatus] = {}
        self._seq = 0

    def update_settings(self, settings: AnalysisSettings) -> None:
        self.settings = settings.validate()

    def reset(self) -> None:
        self._active.clear()
        self._last_true.clear()
        self._log.clear()
        self._statuses.clear()
        self._seq = 0

    # -- sorgular -------------------------------------------------------------
    def active_alerts(self) -> Tuple[Alert, ...]:
        return tuple(self._active.values())

    def alert_log(self) -> Tuple[Alert, ...]:
        return tuple(self._log.values())

    def statuses(self) -> Tuple[RuleStatus, ...]:
        return tuple(self._statuses[r.rule_id] for r in self.rules if r.rule_id in self._statuses)

    # -- değerlendirme --------------------------------------------------------
    def evaluate(self, samples: Sequence[SystemSample]) -> EngineUpdate:
        if not samples:
            return EngineUpdate(active=self.active_alerts(), statuses=self.statuses())
        now = samples[-1].timestamp
        relevant = since(list(samples), now - self.settings.lookback_s - self.settings.window_s)
        new: List[Alert] = []
        resolved: List[Alert] = []
        errors: List[str] = []
        for rule in self.rules:
            try:
                outcome = rule.evaluate(relevant, self.settings)
            except Exception as exc:  # kural hatası uygulamayı durdurmamalı
                errors.append(f"{rule.title}: değerlendirme hatası ({type(exc).__name__}: {exc})")
                outcome = RuleOutcome(False, "Kural değerlendirilemedi (hata kaydedildi).")
            self._statuses[rule.rule_id] = RuleStatus(
                rule.rule_id, rule.title, outcome.triggered, outcome.reason, now)
            active = self._active.get(rule.rule_id)
            if outcome.triggered and outcome.draft is not None:
                self._last_true[rule.rule_id] = now
                draft = outcome.draft
                if active is None:
                    self._seq += 1
                    alert = Alert(
                        alert_id=f"{rule.rule_id}-{self._seq}", rule_id=rule.rule_id,
                        title=draft.title, severity=draft.severity, confidence=draft.confidence,
                        summary=draft.summary, window_start=draft.window_start,
                        window_end=draft.window_end, evidence=draft.evidence,
                        context=draft.context, uncertainty=draft.uncertainty,
                        suggestions=draft.suggestions, first_seen=now, last_seen=now)
                    new.append(alert)
                else:
                    severity = max(active.severity, draft.severity,
                                   key=lambda sev: SEVERITY_ORDER.get(sev, 0))
                    alert = replace(
                        active, severity=severity, confidence=draft.confidence,
                        summary=draft.summary, window_start=min(active.window_start,
                                                                draft.window_start),
                        window_end=draft.window_end, evidence=draft.evidence,
                        context=draft.context, uncertainty=draft.uncertainty,
                        suggestions=draft.suggestions, last_seen=now)
                self._active[rule.rule_id] = alert
                self._put(alert)
            elif active is not None:
                last_true = self._last_true.get(rule.rule_id, active.last_seen)
                if now - last_true >= self.settings.resolve_grace_s:
                    closed = replace(active, resolved_at=now)
                    del self._active[rule.rule_id]
                    self._put(closed)
                    resolved.append(closed)
        return EngineUpdate(new=tuple(new), resolved=tuple(resolved),
                            active=self.active_alerts(), errors=tuple(errors),
                            statuses=self.statuses())

    def _put(self, alert: Alert) -> None:
        self._log[alert.alert_id] = alert
        self._log.move_to_end(alert.alert_id)
        while len(self._log) > self.max_log:
            # Önce en eski çözülmüş uyarıyı at; aktif uyarılar korunur
            for key, value in self._log.items():
                if not value.active:
                    del self._log[key]
                    break
            else:
                break


def replay(samples: Iterable[SystemSample], settings: Optional[AnalysisSettings] = None,
           rules: Optional[Sequence[Rule]] = None) -> RuleEngine:
    """Kaydedilmiş örnekleri sırayla motora besler (kayıt/senaryo analizi).

    Her adımda yalnızca kuralların ihtiyaç duyduğu geçmiş tutulur; böylece uzun
    kayıtlar da doğrusal sürede analiz edilir.
    """
    engine = RuleEngine(settings, rules)
    keep = engine.settings.lookback_s + engine.settings.window_s
    buffer: Deque[SystemSample] = deque()
    for sample in sorted(samples, key=lambda x: x.timestamp):
        buffer.append(sample)
        while buffer and buffer[0].timestamp < sample.timestamp - keep:
            buffer.popleft()
        engine.evaluate(list(buffer))
    return engine
