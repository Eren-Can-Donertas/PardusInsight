"""Kural motoru: kuralları geçmiş üzerinde çalıştırır ve uyarı yaşam döngüsünü yönetir.

Yaşam döngüsü: koşul ilk sağlandığında yeni uyarı açılır; sağlanmaya devam
ettikçe kanıtları, önem derecesi ve zaman aralığı güncellenir; ``resolve_grace_s``
boyunca sağlanmazsa "çözüldü" olarak kapatılır (kısa dalgalanmalarda uyarı açılıp
kapanmasını önler). Veri yetersizken (örnekleme duraklaması, boşluk, kural hatası)
koşulun bittiği bilinemez; aktif uyarı açık tutulur ve yalnızca veri bir
değerlendirme dönemi + bekleme süresi boyunca yetersiz kalırsa kapatılır. Bir
kuralın beklenmedik hatası diğer kuralları ve uygulamayı etkilemez.

Kurallar pencere başına beklenen örnek sayısını örnekleme aralığından hesaplar.
Örneklerin gerçek aralığı ayardakinden belirgin farklıysa (ör. 2 sn'lik bir kayıt
1 sn ayarıyla açıldığında) değerlendirme gözlenen aralıkla yapılır.
"""
from __future__ import annotations

import logging
import statistics
from collections import OrderedDict, deque
from dataclasses import replace
from typing import Deque, Dict, Iterable, List, Optional, Sequence, Tuple

from ..config import AnalysisSettings
from ..core.history import since
from ..core.models import Alert, EngineUpdate, RuleStatus, SystemSample
from .rules import Rule, RuleOutcome, default_rules

logger = logging.getLogger(__name__)


class RuleEngine:
    def __init__(self, settings: Optional[AnalysisSettings] = None,
                 rules: Optional[Sequence[Rule]] = None, max_log: int = 200) -> None:
        self.settings = (settings or AnalysisSettings()).validate()
        self.rules: List[Rule] = list(rules) if rules is not None else default_rules()
        self.max_log = max_log
        self._active: Dict[str, Alert] = {}
        self._last_true: Dict[str, float] = {}
        self._unknown_since: Dict[str, float] = {}  # aktif uyarının verisi yetersiz kalmaya başladığı an
        self._log: "OrderedDict[str, Alert]" = OrderedDict()
        self._statuses: Dict[str, RuleStatus] = {}
        self._seq = 0
        self._failed_rules: set = set()

    def update_settings(self, settings: AnalysisSettings) -> None:
        self.settings = settings.validate()

    def reset(self) -> None:
        self._active.clear()
        self._last_true.clear()
        self._unknown_since.clear()
        self._log.clear()
        self._statuses.clear()
        self._seq = 0

    def effective_settings(self, samples: Sequence[SystemSample]) -> AnalysisSettings:
        """Örneklerin gözlenen aralığı ayardakinden belirgin farklıysa ona uyarlanmış ayarlar.

        Medyan kullanıldığı için tek bir duraklama veya boşluk sonucu değiştirmez;
        boşluklar yine "yetersiz veri" olarak yakalanır.
        """
        s = self.settings
        gaps = [b.timestamp - a.timestamp for a, b in zip(samples, samples[1:])
                if b.timestamp > a.timestamp]
        if len(gaps) < 3:
            return s
        observed = statistics.median(gaps)
        if abs(observed - s.sample_interval_s) <= 0.25 * s.sample_interval_s:
            return s
        try:
            return replace(s, sample_interval_s=round(observed, 3)).validate()
        except ValueError:  # ör. pencere gözlenen aralığın iki katından kısa
            return s

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
        settings = self.effective_settings(relevant)
        hold_s = settings.evaluation_span_s + settings.resolve_grace_s
        new: List[Alert] = []
        resolved: List[Alert] = []
        errors: List[str] = []
        for rule in self.rules:
            try:
                outcome = rule.evaluate(relevant, settings)
            except Exception as exc:  # kural hatası uygulamayı durdurmamalı
                errors.append(f"{rule.title}: değerlendirme hatası ({type(exc).__name__}: {exc})")
                if rule.rule_id not in self._failed_rules:
                    self._failed_rules.add(rule.rule_id)
                    logger.warning("Kural %s hata verdi", rule.rule_id, exc_info=True)
                outcome = RuleOutcome(False, "Kural değerlendirilemedi (hata kaydedildi).",
                                      insufficient=True)
            self._statuses[rule.rule_id] = RuleStatus(
                rule.rule_id, rule.title, outcome.triggered, outcome.reason, now)
            active = self._active.get(rule.rule_id)
            if outcome.insufficient and active is not None:
                # Koşulun bittiği bilinmiyor: uyarı açık kalır, bekleme süresi işlemez.
                started = self._unknown_since.setdefault(rule.rule_id, now)
                if now - started < hold_s:
                    self._last_true[rule.rule_id] = now
                    continue
            else:
                self._unknown_since.pop(rule.rule_id, None)
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
                    # Önem derecesi güncel kanıtla birlikte güncellenir; eski bir zirveyi
                    # korumak "Kritik" etiketini uyarı düzeyindeki kanıtla yan yana gösterirdi.
                    alert = replace(
                        active, severity=draft.severity, confidence=draft.confidence,
                        summary=draft.summary, window_start=min(active.window_start,
                                                                draft.window_start),
                        window_end=draft.window_end, evidence=draft.evidence,
                        context=draft.context, uncertainty=draft.uncertainty,
                        suggestions=draft.suggestions, last_seen=now)
                self._active[rule.rule_id] = alert
                self._put(alert)
            elif active is not None:
                last_true = self._last_true.get(rule.rule_id, active.last_seen)
                if outcome.insufficient or now - last_true >= settings.resolve_grace_s:
                    # (yetersiz veri buraya yalnızca bekletme süresi dolduğunda gelir)
                    closed = replace(active, resolved_at=now)
                    del self._active[rule.rule_id]
                    self._unknown_since.pop(rule.rule_id, None)
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
