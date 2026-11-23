"""Uygulama ve analiz ayarları.

Eşikler ilk prototip için makul başlangıç değerleridir; PDF'de belirtildiği gibi
hedef Pardus 25.1 XFCE ortamında kalibre edilmelidir (docs/KURALLAR.md).
Ayarlar yalnızca bellekte tutulur ve kullanıcının verdiği JSON dosyasından
okunabilir; uygulama hiçbir sistem ayarını değiştirmez.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields, replace
from typing import Any, Dict, Mapping


@dataclass(frozen=True)
class AnalysisSettings:
    # Ortak pencere ayarları
    sample_interval_s: float = 2.0
    window_s: float = 30.0  # tek pencere uzunluğu
    consecutive_windows: int = 2  # koşulun art arda sağlanması gereken pencere sayısı
    min_window_coverage: float = 0.6  # pencerede beklenen örneklerin en az bu oranı geçerli olmalı
    resolve_grace_s: float = 10.0  # koşul bu kadar süre sağlanmazsa uyarı "çözüldü" sayılır

    # Kural 1: bellek baskısı
    mem_available_warn_pct: float = 10.0
    mem_available_crit_pct: float = 5.0
    swap_activity_pages_s: float = 100.0  # pswpin + pswpout (4 KiB sayfa ≈ 400 KiB/sn)
    major_faults_s: float = 100.0
    psi_memory_some_pct: float = 10.0

    # Kural 2: kalıcı CPU yoğunluğu
    cpu_high_pct: float = 85.0
    cpu_min_fraction: float = 0.8  # penceredeki örneklerin en az bu oranı eşiğin üstünde

    # Kural 3: disk G/Ç anomalisi
    disk_baseline_s: float = 300.0  # karşılaştırma yapılan önceki dönem
    disk_min_baseline_coverage: float = 0.5
    disk_ratio: float = 3.0  # önceki döneme göre kat artış
    disk_min_throughput_mib_s: float = 5.0  # bunun altındaki hızlar oran ne olursa olsun yok sayılır
    disk_busy_pct: float = 80.0

    def validate(self) -> "AnalysisSettings":
        problems = []
        if not 0.2 <= self.sample_interval_s <= 60:
            problems.append("örnekleme aralığı 0,2-60 sn arasında olmalı")
        if self.window_s < 2 * self.sample_interval_s:
            problems.append("pencere en az iki örnekleme aralığı uzunluğunda olmalı")
        if not 1 <= self.consecutive_windows <= 10:
            problems.append("ardışık pencere sayısı 1-10 arasında olmalı")
        if not 0 < self.min_window_coverage <= 1:
            problems.append("pencere kapsama oranı (0, 1] aralığında olmalı")
        if not 0 < self.mem_available_crit_pct <= self.mem_available_warn_pct < 100:
            problems.append("bellek eşikleri: 0 < kritik <= uyarı < 100 olmalı")
        if not 0 < self.cpu_high_pct <= 100:
            problems.append("CPU eşiği (0, 100] aralığında olmalı")
        if not 0 < self.cpu_min_fraction <= 1:
            problems.append("CPU oran eşiği (0, 1] aralığında olmalı")
        if self.disk_ratio <= 1:
            problems.append("disk artış oranı 1'den büyük olmalı")
        if not 0 < self.disk_busy_pct <= 100:
            problems.append("disk meşguliyet eşiği (0, 100] aralığında olmalı")
        if problems:
            raise ValueError("; ".join(problems))
        return self

    @property
    def evaluation_span_s(self) -> float:
        return self.window_s * self.consecutive_windows

    @property
    def lookback_s(self) -> float:
        """Kuralların ihtiyaç duyduğu en uzun geçmiş."""
        return self.evaluation_span_s + self.disk_baseline_s


@dataclass(frozen=True)
class AppSettings:
    sample_interval_s: float = 2.0
    history_minutes: float = 30.0
    process_every: int = 1  # süreç listesini her N örnekte bir topla (yük azaltma)
    top_n: int = 5
    analysis: AnalysisSettings = field(default_factory=AnalysisSettings)

    def validate(self) -> "AppSettings":
        if not 0.2 <= self.sample_interval_s <= 60:
            raise ValueError("örnekleme aralığı 0,2-60 sn arasında olmalı")
        if not 1 <= self.history_minutes <= 240:
            raise ValueError("geçmiş süresi 1-240 dk arasında olmalı")
        if self.process_every < 1:
            raise ValueError("process_every en az 1 olmalı")
        self.analysis.validate()
        return self

    def with_interval(self, interval_s: float) -> "AppSettings":
        return replace(self, sample_interval_s=interval_s,
                       analysis=replace(self.analysis, sample_interval_s=interval_s))


def settings_to_dict(settings: AppSettings) -> Dict[str, Any]:
    return asdict(settings)


def settings_from_dict(data: Mapping[str, Any]) -> AppSettings:
    """Bilinmeyen anahtarları yok sayarak ayar nesnesi kurar."""
    analysis_keys = {f.name for f in fields(AnalysisSettings)}
    app_keys = {f.name for f in fields(AppSettings)} - {"analysis"}
    analysis = AnalysisSettings(**{k: v for k, v in dict(data.get("analysis") or {}).items()
                                   if k in analysis_keys})
    app = AppSettings(analysis=analysis,
                      **{k: v for k, v in data.items() if k in app_keys})
    # Örnekleme aralığı tek kaynaktan gelsin
    return app.with_interval(app.sample_interval_s).validate()


def load_settings_file(path: str) -> AppSettings:
    with open(path, "r", encoding="utf-8") as handle:
        return settings_from_dict(json.load(handle))
