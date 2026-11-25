"""Uygulama ve analiz ayarları.

Eşikler ilk prototip için makul başlangıç değerleridir; PDF'de belirtildiği gibi
hedef Pardus 25.1 XFCE ortamında kalibre edilmelidir (docs/KURALLAR.md).
Ayarlar yalnızca bellekte tutulur ve kullanıcının verdiği JSON dosyasından
okunabilir; uygulama hiçbir sistem ayarını değiştirmez.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields, replace
from typing import Any, Dict, List, Mapping, Optional


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
        problems = _type_problems(self)
        if problems:  # tür yanlışsa aralık karşılaştırmaları TypeError fırlatırdı
            raise ValueError("; ".join(problems))
        if not 0.2 <= self.sample_interval_s <= 60:
            problems.append("örnekleme aralığı 0,2-60 sn arasında olmalı")
        if self.window_s < 2 * self.sample_interval_s:
            problems.append("pencere en az iki örnekleme aralığı uzunluğunda olmalı")
        if not 1 <= self.consecutive_windows <= 10:
            problems.append("ardışık pencere sayısı 1-10 arasında olmalı")
        if not 0 < self.min_window_coverage <= 1:
            problems.append("pencere kapsama oranı (0, 1] aralığında olmalı")
        if self.resolve_grace_s < 0:
            problems.append("çözülme bekleme süresi negatif olamaz")
        if not 0 < self.mem_available_crit_pct <= self.mem_available_warn_pct < 100:
            problems.append("bellek eşikleri: 0 < kritik <= uyarı < 100 olmalı")
        if self.swap_activity_pages_s <= 0 or self.major_faults_s <= 0:
            problems.append("swap ve major page-fault eşikleri pozitif olmalı")
        if not 0 < self.psi_memory_some_pct <= 100:
            problems.append("PSI bellek eşiği (0, 100] aralığında olmalı")
        if not 0 < self.cpu_high_pct <= 100:
            problems.append("CPU eşiği (0, 100] aralığında olmalı")
        if not 0 < self.cpu_min_fraction <= 1:
            problems.append("CPU oran eşiği (0, 1] aralığında olmalı")
        if self.disk_baseline_s <= 0:
            problems.append("disk taban dönemi pozitif olmalı")
        if not 0 < self.disk_min_baseline_coverage <= 1:
            problems.append("disk taban kapsama oranı (0, 1] aralığında olmalı")
        if self.disk_ratio <= 1:
            problems.append("disk artış oranı 1'den büyük olmalı")
        if self.disk_min_throughput_mib_s <= 0:
            problems.append("disk mutlak alt sınırı pozitif olmalı (0 iken boş diskte bile "
                            "'artış' görülür)")
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
        problems = _type_problems(self)
        if problems:
            raise ValueError("; ".join(problems))
        if not 0.2 <= self.sample_interval_s <= 60:
            raise ValueError("örnekleme aralığı 0,2-60 sn arasında olmalı")
        if not 1 <= self.history_minutes <= 240:
            raise ValueError("geçmiş süresi 1-240 dk arasında olmalı")
        if not 1 <= self.process_every <= 60:
            raise ValueError("process_every 1-60 arasında olmalı")
        if not 1 <= self.top_n <= 20:
            raise ValueError("top_n (örnek başına saklanan süreç sayısı) 1-20 arasında olmalı")
        self.analysis.validate()
        span = self.analysis.evaluation_span_s
        if span > self.history_minutes * 60:
            raise ValueError(f"analiz dönemi (pencere × ardışık pencere = {span:g} sn) geçmiş "
                             f"süresinden ({self.history_minutes * 60:g} sn) uzun olamaz; "
                             "kurallar hiç değerlendirilemezdi")
        return self

    def warnings(self) -> List[str]:
        """Geçerli ama bir kuralı kısıtlayan ayar birleşimleri (komut satırı gösterir)."""
        needed = self.analysis.lookback_s + self.analysis.window_s
        if needed > self.history_minutes * 60:
            return [f"Geçmiş süresi ({self.history_minutes:g} dk) disk kuralının önceki dönem "
                    f"karşılaştırması için gereken {needed:g} sn'den kısa; oran koşulu "
                    "çalışmaz, yalnızca meşguliyet koşulu değerlendirilir."]
        return []

    def with_interval(self, interval_s: float) -> "AppSettings":
        return replace(self, sample_interval_s=interval_s,
                       analysis=replace(self.analysis, sample_interval_s=interval_s))


_INT_FIELDS = {"consecutive_windows", "process_every", "top_n"}


def _type_problems(obj: Any) -> List[str]:
    """Sayısal alanların türünü denetler (bool ve metin kabul edilmez)."""
    problems = []
    for f in fields(obj):
        if f.name == "analysis":
            continue
        value = getattr(obj, f.name)
        if f.name in _INT_FIELDS:
            if isinstance(value, bool) or not isinstance(value, int):
                problems.append(f"{f.name} tam sayı olmalı (verilen: {value!r})")
        elif isinstance(value, bool) or not isinstance(value, (int, float)):
            problems.append(f"{f.name} sayı olmalı (verilen: {value!r})")
    return problems


def _coerce(name: str, value: Any) -> Any:
    """JSON'dan gelen değeri alan türüne çevirir. 2.0 gibi tam değerli ondalıklar
    tam sayı alanlarında kabul edilir; metin, bool ve null reddedilir."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"'{name}' sayı olmalı (verilen: {json.dumps(value, ensure_ascii=False)})")
    if name in _INT_FIELDS:
        if float(value) != int(value):
            raise ValueError(f"'{name}' tam sayı olmalı (verilen: {value})")
        return int(value)
    return float(value)


def settings_to_dict(settings: AppSettings) -> Dict[str, Any]:
    return asdict(settings)


def unknown_setting_keys(data: Mapping[str, Any]) -> List[str]:
    """Ayar nesnesinde karşılığı olmayan anahtarlar (yazım hatalarını göstermek için)."""
    app_keys = {f.name for f in fields(AppSettings)}
    analysis_keys = {f.name for f in fields(AnalysisSettings)}
    unknown = [k for k in data if k not in app_keys]
    nested = data.get("analysis")
    if isinstance(nested, Mapping):
        unknown += [f"analysis.{k}" for k in nested if k not in analysis_keys]
    return unknown


def settings_from_dict(data: Mapping[str, Any]) -> AppSettings:
    """Ayar nesnesi kurar. Bilinmeyen anahtarlar yok sayılır (raporlardaki ayarlarla ileri
    uyumluluk); biçim veya tür hatası açıklayıcı bir ValueError olarak bildirilir."""
    if not isinstance(data, Mapping):
        raise ValueError("ayar dosyasının kökü bir JSON nesnesi olmalı")
    nested = data.get("analysis")
    if nested is None:
        nested = {}
    if not isinstance(nested, Mapping):
        raise ValueError("'analysis' bir JSON nesnesi olmalı")
    analysis_keys = {f.name for f in fields(AnalysisSettings)}
    app_keys = {f.name for f in fields(AppSettings)} - {"analysis"}
    analysis = AnalysisSettings(**{k: _coerce(k, v) for k, v in nested.items()
                                   if k in analysis_keys})
    app = AppSettings(analysis=analysis,
                      **{k: _coerce(k, v) for k, v in data.items() if k in app_keys})
    # Örnekleme aralığı tek kaynaktan gelsin
    return app.with_interval(app.sample_interval_s).validate()


def load_settings_file(path: str, warnings: Optional[List[str]] = None) -> AppSettings:
    """JSON ayar dosyasını okur. ``warnings`` verilirse bilinmeyen anahtarlar eklenir."""
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    settings = settings_from_dict(data)
    if warnings is not None:
        unknown = unknown_setting_keys(data)
        if unknown:
            warnings.append("Bilinmeyen ayar anahtarları yok sayıldı: " + ", ".join(unknown))
    return settings
