#!/usr/bin/env python3
"""Pardus 25.1 XFCE kabul ve doğrulama listesini (docs/PARDUS_DOGRULAMA.md) uygular.

Temiz bir Pardus VM'de standart kullanıcıyla, git deposunun kökünden çalıştırılır.
Otomatikleştirilebilen her maddeyi çalıştırır; insan gözü gerektirenleri (XFCE menüsü,
koyu tema, LibreOffice) "MANUEL" olarak yönergesiyle listeler ve docs/ altına eklenecek
bir Markdown sonuç raporu üretir. Sistemi değiştirmez, sudo kullanmaz; yalnızca kendi
açıp sildiği geçici dizinlere, --cikti raporuna ve --kayit-klasoru kayıtlarına yazar.

Kullanım:
  python3 scripts/pardus_kabul.py --cikti docs/PARDUS_SONUCLARI.md        # ~5 dk
  python3 scripts/pardus_kabul.py --hizli                                 # yavaş ölçümler yok
  python3 scripts/pardus_kabul.py --gui --cikti docs/PARDUS_SONUCLARI.md  # XFCE oturumunda
  python3 scripts/pardus_kabul.py --uzun                                  # + 35 dk (madde 4.2)
  python3 scripts/pardus_kabul.py --kalibrasyon-suresi 1800 --kayit-klasoru docs/kayitlar \\
      --cikti docs/PARDUS_SONUCLARI.md

Çıkış kodu: KALDI yoksa 0, en az bir KALDI varsa 1. Ctrl+C ile kesilirse 130: o ana kadarki
kısmi rapor standart çıktıya yazılır, --cikti dosyasına dokunulmaz.
"""
from __future__ import annotations

import argparse
import getpass
import importlib
import importlib.util
import json
import os
import platform
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence, Set, Tuple

if __name__ == "__main__":
    sys.dont_write_bytecode = True  # betik depoya __pycache__ yazmasın

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from pardusinsight.analysis.engine import replay  # noqa: E402
from pardusinsight.collectors.procfs import ProcFsReader, parse_meminfo  # noqa: E402
from pardusinsight.collectors.system import load_psutil  # noqa: E402
from pardusinsight.config import AnalysisSettings, AppSettings, settings_to_dict  # noqa: E402
from pardusinsight.core.formatting import (fmt_bytes, fmt_datetime, fmt_duration,  # noqa: E402
                                           fmt_rate, fmt_time, tr_num)
from pardusinsight.core.models import SystemSample  # noqa: E402
from pardusinsight.core.service import (MonitorService, RecordingSource,  # noqa: E402
                                        SelfUsageMonitor, build_live_service,
                                        build_synthetic_service)
from pardusinsight.export import (build_report, load_json_report, read_alerts_csv,  # noqa: E402
                                  read_samples_csv, write_alerts_csv, write_json_report,
                                  write_samples_csv)
from pardusinsight.export.atomic import atomic_write  # noqa: E402

MIB = 1024 * 1024

GECTI, KALDI, ATLANDI, MANUEL, BILGI = "GEÇTİ", "KALDI", "ATLANDI", "MANUEL", "BİLGİ"
STATUSES = (GECTI, KALDI, ATLANDI, MANUEL, BILGI)
LABELS = {GECTI: "✅ GEÇTİ", KALDI: "❌ KALDI", ATLANDI: "⏭ ATLANDI", MANUEL: "✋ MANUEL",
          BILGI: "ℹ BİLGİ"}
GROUPS = (("1", "Kurulum"), ("2", "Standart kullanıcı ve güvenlik"), ("3", "Ölçüm doğruluğu"),
          ("4", "Performans"), ("5", "İşlevler"), ("6", "Eşik kalibrasyonu"))

# Madde numaraları ve başlıkları docs/PARDUS_DOGRULAMA.md ile aynıdır.
TITLES: Dict[str, str] = {
    "1.1": "Paketler depoda: `apt-cache policy python3-pyside6.qtwidgets python3-psutil`",
    "1.2": "Kurulum: psutil ve PySide6.QtWidgets yükleniyor",
    "1.3": "Seçenek B (sanal ortam) ile kurulum",
    "1.4": "Menü kaydı (`pardusinsight.desktop`) kurulu ve geçerli",
    "1.4b": "XFCE menüsünde (Sistem) PardusInsight görünüyor ve açılıyor",
    "2.1": "Standart kullanıcıyla çalışma (root değil)",
    "2.2": "Canlı izlemede /proc okuma hatası yok",
    "2.3": "Root süreçlerinin G/Ç alanları boş (\"—\"), tarama çökmüyor",
    "2.4": "PardusInsight ağ bağlantısı açmıyor",
    "2.5": "Ev dizininde yeni dosya oluşmuyor (dışa aktarma yokken)",
    "2.6": "Güvenlik testleri: `pytest tests/test_cli_safety.py`",
    "3.1": "/proc – psutil doğrulama tablosu (10 örnek)",
    "3.2": "Canlı çapraz doğrulama testleri: `pytest tests/test_crosscheck_linux.py`",
    "3.3": "Bellek değerleri `free -b` ile tutarlı",
    "3.3b": "htop / xfce4-taskmanager ile CPU-RAM aynı mertebede",
    "3.4": "PSI (Pressure Stall Information) desteği",
    "4.1": "Performans, GUI'siz 60 sn: CPU < %5, RAM < 200 MiB",
    "4.1b": "Performans, GUI ile 60 sn: CPU < %5, RAM < 200 MiB, \"YANIT VERİYOR\"",
    "4.2": "35 dk çalışma: geçmiş tamponu sınırlı, RAM sabit",
    "4.3": "Pencere taşıma, sekme değiştirme, sıralama sırasında takılma yok",
    "5.1": "`scenarios/demo.json`: 3 uyarı (CPU, bellek, disk), kanıtlar dolu",
    "5.2": "Karşı-örnek senaryolarda uyarı yok, kural durumu nedeni açıklıyor",
    "5.3": "CSV dışa aktarma ve geri okuma (Türkçe karakterler)",
    "5.3b": "CSV'yi LibreOffice Calc'ta açın: sütunlar ve Türkçe karakterler doğru",
    "5.4": "JSON rapor dışa aktarma ve geri yükleme",
    "5.5": "Eşik ayarı çalışıyor (CPU eşiği %0,1 ile canlı uyarı)",
    "5.6": "Olağan kullanımda yanlış pozitif yok",
    "5.7": "XFCE koyu temada grafikler ve metinler okunaklı",
    "5.8": "`--headless --duration 60`: satır satır özet, Ctrl+C ile temiz çıkış",
    "6": "Eşik kalibrasyonu (olağan kullanım kaydı)",
}

LINUX_ONLY = "yalnızca Linux'ta çalışır (canlı /proc gerekir)"
CALIBRATION_CMD = ("python3 scripts/pardus_kabul.py --kalibrasyon-suresi 1800 "
                   "--kayit-klasoru docs/kayitlar")

MANUAL_1_3 = (
    "Seçenek B'yi deneyin (gerekirse önce `sudo apt install python3-venv`): "
    "`python3 -m venv .venv` → `.venv/bin/pip install -r requirements-dev.txt` → "
    "`.venv/bin/python -m pardusinsight`. Ardından bu betiği "
    "`.venv/bin/python scripts/pardus_kabul.py --hizli` ile yeniden çalıştırın; 1.3 otomatik "
    "denetlenir. GUI `Could not load the Qt platform plugin \"xcb\"` hatasıyla açılmazsa "
    "`sudo apt install libxcb-cursor0` notunun sorunu çözdüğünü doğrulayın.")
MANUAL_1_4 = (
    "`pardusinsight.desktop` bulunamadı (~/.local/share/applications, /usr/share/applications): "
    "`scripts/install_user.sh` çalıştırın veya .deb paketini kurun (`python3 scripts/build_deb.py` "
    "→ `sudo apt install ./dist/pardusinsight_*_all.deb`), sonra bu betiği yeniden çalıştırın.")
MANUAL_1_4B = (
    "Uygulamalar menüsü → Sistem → PardusInsight (veya menü aramasına \"PardusInsight\" yazın): "
    "simge görünmeli; tıklayınca pencere parola/yetki istemeden açılmalı ve canlı ölçümler "
    "akmalı.")
MANUAL_3_3B = (
    "`python3 -m pardusinsight` ile `htop`'u (veya xfce4-taskmanager'ı) yan yana açın: 1 dk "
    "boyunca toplam CPU % ve kullanılan RAM aynı büyüklük mertebesinde olmalı. Önbellek/buffers "
    "tanım farkları nedeniyle küçük farklar normaldir.")
MANUAL_4_3 = (
    "`python3 -m pardusinsight` açıkken 60 sn boyunca pencereyi sürükleyin, sekmeler arasında "
    "geçin ve Süreçler tablosunu farklı sütunlara göre sıralayın: takılma veya donma olmamalı. "
    "Nesnel ölçüm için aynı işlemleri `python3 scripts/perf_check.py --gui --duration 60` "
    "çalışırken yapın ve \"YANIT VERİYOR\" satırına bakın.")
MANUAL_5_3B = (
    "Uygulamada Dışa aktar → CSV ile (veya `python3 -m pardusinsight --headless --synthetic demo "
    "--speed 0 --ticks 251 --quiet --export-csv /tmp/pardusinsight_demo.csv`) dosya oluşturun. "
    "LibreOffice Calc'ta açarken Karakter kümesi: Unicode (UTF-8), Ayırıcı: Virgül seçin. "
    "Sütunlar ayrı ayrı görünmeli; uyarı dosyasında (`*_uyarilar.csv`) \"Kalıcı CPU yoğunluğu\", "
    "\"Bellek baskısı olasılığı\" gibi başlıklar bozulmamalı. Deneme dosyalarını sonra silin.")
MANUAL_5_6 = (
    "30 dk olağan kullanım (tarayıcı + ofis) kaydı alın: `" + CALIBRATION_CMD + "` ve kayıt "
    "sürerken masaüstünü olağan biçimde kullanın. Hiç uyarı çıkmamalı ya da her uyarı "
    "açıklanabilir olmalı.")
MANUAL_5_7 = (
    "Ayarlar Yöneticisi → Görünüm → Stil sekmesinden koyu bir tema seçin ve "
    "`python3 -m pardusinsight`'ı yeniden açın: grafik çizgileri, eksen yazıları, uyarı listesi, "
    "kanıt tablosu ve süreç tablosu okunaklı olmalı. İsterseniz ekran görüntüsünü docs/ altına "
    "ekleyin.")
MANUAL_6 = (
    "Olağan kullanım kaydıyla eşik kalibrasyonu yapın: `" + CALIBRATION_CMD + "` (30 dk; bu "
    "sürede tarayıcı + ofis ile olağan kullanım). Önerilen eşik değişikliklerini gerekçesiyle "
    "docs/KURALLAR.md'ye işleyin.")

INTRO = (
    "Bu rapor `scripts/pardus_kabul.py` ile otomatik üretildi; "
    "[PARDUS_DOGRULAMA.md](PARDUS_DOGRULAMA.md) listesindeki otomatikleştirilebilen maddeleri "
    "çalıştırır. **✅ GEÇTİ**: beklenen sağlandı · **❌ KALDI**: sağlanmadı · **⏭ ATLANDI**: bu "
    "ortamda veya seçilen seçeneklerle çalıştırılmadı (neden Ayrıntı sütununda) · **✋ MANUEL**: "
    "insan gözü gerektirir (XFCE menüsü, koyu tema, LibreOffice…); \"Elle yapılacaklar\" "
    "bölümündeki yönergelerle denenip sonucu bu dosyaya elle işlenmelidir · **ℹ BİLGİ**: yalnızca "
    "bilgi. Kullanıcı adı, makine adı ve ev dizini `<kullanıcı>`, `<makine>` ve `~` ile gizlendi.")

APT_PACKAGES = ("python3-pyside6.qtwidgets", "python3-psutil")
BAD_WORDS = ("okunamadı", "alınamadı", "Traceback")
EXPECTED_DEMO = {"sustained_cpu", "memory_pressure", "disk_io_anomaly"}
COUNTER_EXAMPLES = (("cpu_spikes.json", "sustained_cpu"),
                    ("memory_low_quiet.json", "memory_pressure"),
                    ("disk_steady.json", "disk_io_anomaly"))  # sonuncusu varsa
OPTIONAL_SCENARIOS = {"disk_steady.json"}
DEMO_TICKS = 251
DEMO_START = 1_767_225_600.0  # sabit başlangıç: belirlenimci zaman damgaları
# %0,1: boşta duran bir sunucuda bile (CI kapsayıcısında örneklerin bir kısmı %1 altında)
# kesin tetiklenir; amaç yalnızca eşik ayarının canlı veride etkili olduğunu göstermek.
THRESHOLD_CONFIG = {"analysis": {"cpu_high_pct": 0.1, "cpu_min_fraction": 0.1, "window_s": 20}}
LONG_RUN_MINUTES = 35
HOME_DIRS = (("~", ()), ("~/.config", (".config",)), ("~/.local/share", (".local", "share")),
             ("~/.cache", (".cache",)))
# Kimlik belirtmeyen, metinde başka anlamda da geçen adlar gizlenmez (ör. "depo.pardus.org.tr")
GENERIC_NAMES = frozenset({"root", "pardus", "debian", "ubuntu", "user", "admin", "localhost",
                           "localhost.localdomain"})

_sleep = time.sleep  # testlerde sahte saatle değiştirilir
_clock = time.monotonic


# ---------------------------------------------------------------------------
# Veri modeli ve ortak yardımcılar
# ---------------------------------------------------------------------------


@dataclass
class Check:
    """Tek bir kabul maddesinin sonucu."""

    no: str
    baslik: str
    durum: str  # GEÇTİ, KALDI, ATLANDI, MANUEL, BİLGİ
    ayrinti: str = ""
    cikti: str = ""  # ham çıktı; raporun Ekler bölümüne konur
    cikti_md: bool = False  # True: çıktı kod bloğu olmadan, Markdown olarak eklenir


@dataclass
class CommandResult:
    code: Optional[int]
    output: str  # stdout + stderr
    duration_s: float = 0.0
    timed_out: bool = False
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.code == 0 and not self.timed_out and not self.error

    def describe(self) -> str:
        if self.error:
            return self.error
        if self.timed_out:
            return f"zaman aşımı ({tr_num(self.duration_s, 0)} sn)"
        return f"çıkış kodu {self.code}"


@dataclass
class LiveRecording:
    """Kalibrasyon için alınan canlı olağan kullanım kaydı (5.6 ve 6 paylaşır)."""

    samples: List[SystemSample]
    duration_s: float
    path: Optional[str] = None  # --kayit-klasoru ile saklandıysa dosya yolu


class Context:
    """Kontrollerin paylaştığı durum: seçenekler, geçici dizinler ve önbellekler."""

    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.partial: Optional[Check] = None  # Ctrl+C'de kısmi rapora eklenecek yarım kontrol
        self.recording: Optional[LiveRecording] = None
        self.recording_error: Optional[Exception] = None
        self.demo: Optional[Tuple[List[SystemSample], list, MonitorService]] = None
        self._root: Optional[str] = None

    def tempdir(self, name: str) -> str:
        """Kontrole özel yeni geçici dizin; tümü cleanup() ile silinir."""
        if self._root is None:
            self._root = tempfile.mkdtemp(prefix="pardus-kabul-")
        return tempfile.mkdtemp(prefix=f"{name}-", dir=self._root)

    def cleanup(self) -> None:
        if self._root is not None:
            shutil.rmtree(self._root, ignore_errors=True)
            self._root = None


def is_linux() -> bool:
    return sys.platform.startswith("linux") and os.path.isfile("/proc/stat")


def has_display() -> bool:
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def in_venv() -> bool:
    return sys.prefix != getattr(sys, "base_prefix", sys.prefix)


def _write(stream: Any, text: str) -> None:
    try:
        stream.write(text)
    except UnicodeEncodeError:  # ör. UTF-8 olmayan konsol
        encoding = getattr(stream, "encoding", None) or "ascii"
        stream.write(text.encode(encoding, "replace").decode(encoding, "replace"))
    stream.flush()


def progress(message: str) -> None:
    """İlerleme iletisi; rapor standart çıktıya yazılırken karışmasın diye stderr'e."""
    _write(sys.stderr, message + "\n")


def _short(text: str, limit: int = 110) -> str:
    line = text.strip().splitlines()[0] if text.strip() else ""
    return line if len(line) <= limit else line[:limit - 1] + "…"


def tail_lines(text: str, n: int) -> str:
    return "\n".join(text.rstrip().splitlines()[-n:])


def module_version(name: str) -> Tuple[Optional[str], str]:
    """Modülü içe aktarır: (sürüm, hata). Yüklenemezse sürüm None."""
    try:
        module = importlib.import_module(name)
    except Exception as exc:  # ImportError veya eksik sistem kütüphanesi (OSError)
        return None, f"{type(exc).__name__}: {exc}"
    return str(getattr(module, "__version__", "?")), ""


def pytest_available() -> bool:
    return importlib.util.find_spec("pytest") is not None


def child_env(extra: Optional[Dict[str, str]] = None, real_gui: bool = False) -> Dict[str, str]:
    """Alt süreç ortamı: ayrıştırılabilir (C yereli) araç çıktısı, UTF-8 Python, depo yolu."""
    env = dict(os.environ)
    env.update({"LC_ALL": "C.UTF-8", "LANG": "C.UTF-8", "PYTHONUTF8": "1",
                "PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1"})
    env.pop("LANGUAGE", None)  # gettext C.UTF-8'de bile LANGUAGE'a bakabilir
    old = env.get("PYTHONPATH")
    env["PYTHONPATH"] = ROOT + (os.pathsep + old if old else "")
    if real_gui and env.get("QT_QPA_PLATFORM") == "offscreen":
        del env["QT_QPA_PLATFORM"]  # GUI ölçümü gerçek pencerede yapılsın
    if extra:
        env.update(extra)
    return env


def _decode(data: Any) -> str:
    if not data:
        return ""
    text = data if isinstance(data, str) else data.decode("utf-8", errors="replace")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def run_command(cmd: Sequence[str], timeout: float, cwd: Optional[str] = None,
                env: Optional[Dict[str, str]] = None) -> CommandResult:
    """Komutu zaman aşımıyla çalıştırır; hiçbir durumda istisna fırlatmaz (Ctrl+C hariç)."""
    started = time.monotonic()
    try:
        proc = subprocess.run(list(cmd), cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        return CommandResult(None, _decode(exc.output), time.monotonic() - started,
                             timed_out=True)
    except OSError as exc:  # FileNotFoundError, PermissionError...
        return CommandResult(None, "", time.monotonic() - started,
                             error=f"çalıştırılamadı ({type(exc).__name__}: "
                                   f"{exc.strerror or exc})")
    return CommandResult(proc.returncode, _decode(proc.stdout), time.monotonic() - started)


def app_cmd(*args: str) -> List[str]:
    """Depodaki PardusInsight'ı çalıştıran komut (PYTHONPATH child_env() ile verilir)."""
    return [sys.executable, "-m", "pardusinsight", *args]


def script_cmd(name: str, *args: str) -> List[str]:
    return [sys.executable, os.path.join(ROOT, "scripts", name), *args]


def stop_process(proc: "subprocess.Popen[bytes]", sig: Optional[int] = None,
                 timeout: float = 30.0) -> Tuple[Optional[int], str]:
    """İsteğe bağlı sinyal gönderir, sürecin bitmesini bekler; süre dolarsa sonlandırır."""
    if sig is not None and proc.poll() is None:
        proc.send_signal(sig)
    try:
        out, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.terminate()
        try:
            out, _ = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            out, _ = proc.communicate()
    return proc.returncode, _decode(out)


def kill_if_alive(proc: "subprocess.Popen[bytes]") -> None:
    if proc.poll() is None:
        proc.kill()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            pass
    if proc.stdout is not None:
        proc.stdout.close()


def safe_run(no: str, fn: Callable[[Context], Any], ctx: Any) -> List[Check]:
    """Kontrolü çalıştırır; beklenmeyen istisnayı KALDI sonucuna çevirir (Ctrl+C hariç)."""
    title = TITLES.get(no, no)
    try:
        result = fn(ctx)
    except Exception as exc:  # KeyboardInterrupt bilerek yakalanmaz
        return [Check(no, title, KALDI, f"beklenmeyen hata: {type(exc).__name__}: {exc}")]
    if isinstance(result, Check):
        return [result]
    if isinstance(result, (list, tuple)) and result and all(isinstance(c, Check) for c in result):
        return list(result)
    return [Check(no, title, KALDI,
                  f"beklenmeyen hata: kontrol geçersiz sonuç döndürdü ({type(result).__name__})")]


# ---------------------------------------------------------------------------
# Saf ayrıştırıcılar (birim testli)
# ---------------------------------------------------------------------------

_APT_CANDIDATE_KEYS = ("Candidate:", "Aday:")
_APT_NONE = {"(none)", "(hiçbiri)"}


def parse_apt_policy(text: str) -> Dict[str, Optional[str]]:
    """`apt-cache policy P1 P2` çıktısı -> {paket: aday sürüm veya None}.

    Depoda hiç bulunmayan paketler çıktıda yer almaz (sözlükte de olmaz).
    """
    result: Dict[str, Optional[str]] = {}
    package: Optional[str] = None
    for line in text.splitlines():
        if not line.strip():
            continue
        if not line[0].isspace() and line.rstrip().endswith(":"):
            package = line.rstrip()[:-1].strip()
            result.setdefault(package, None)
            continue
        if package is None:
            continue
        stripped = line.strip()
        for key in _APT_CANDIDATE_KEYS:
            if stripped.startswith(key):
                value = stripped[len(key):].strip()
                result[package] = None if (not value or value in _APT_NONE) else value
    return result


def parse_validate_table(text: str) -> List[Dict[str, str]]:
    """scripts/validate_metrics.py Markdown tablosu -> satır sözlükleri (başlık: hücre)."""
    headers: Optional[List[str]] = None
    rows: List[Dict[str, str]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            if rows:
                break  # tablo bitti
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if headers is None:
            if cells and cells[0] == "#":
                headers = cells
            continue
        if all(c and set(c) <= set("-: ") for c in cells):
            continue  # ayırıcı satır
        if len(cells) == len(headers):
            rows.append(dict(zip(headers, cells)))
    return rows


def _column(row: Dict[str, str], prefix: str) -> Optional[str]:
    for key, value in row.items():
        if key.startswith(prefix):
            return value
    return None


def _number(text: Optional[str]) -> float:
    if text is None:
        raise ValueError("değer yok")
    return float(text.replace(",", ".").strip().lstrip("%"))


def evaluate_validate_rows(rows: Sequence[Dict[str, str]], min_rows: int = 10,
                           cpu_tolerance: float = 2.0) -> Tuple[bool, str]:
    """MemTotal/SwapTotal eşit ve |CPU %(/proc) − CPU %(psutil)| < 2 puan mı? -> (geçti, özet)."""
    if not rows:
        return False, "doğrulama tablosu bulunamadı"
    problems: List[str] = []
    if len(rows) < min_rows:
        problems.append(f"tabloda {len(rows)} satır var, en az {min_rows} gerekli")
    worst_cpu, worst_avail = 0.0, 0.0
    for row in rows:
        no = row.get("#", "?")
        for prefix in ("MemTotal", "SwapTotal"):
            if (_column(row, prefix) or "").lower() != "evet":
                problems.append(f"#{no}: {prefix} eşit değil")
        try:
            diff = abs(_number(_column(row, "CPU % (/proc"))
                       - _number(_column(row, "CPU % (psutil")))
        except ValueError:
            problems.append(f"#{no}: CPU % değerleri okunamadı")
            continue
        worst_cpu = max(worst_cpu, diff)
        if diff >= cpu_tolerance:
            problems.append(f"#{no}: CPU % farkı {tr_num(diff)} puan "
                            f"(sınır < {tr_num(cpu_tolerance)})")
        try:
            worst_avail = max(worst_avail, _number(_column(row, "MemAvailable")))
        except ValueError:
            pass
    totals = "FARKLI" if any("eşit değil" in p for p in problems) else "her satırda eşit"
    summary = (f"{len(rows)} satır; MemTotal/SwapTotal {totals}; en büyük CPU % farkı "
               f"{tr_num(worst_cpu)} puan; en büyük MemAvailable farkı "
               f"{tr_num(worst_avail, 2)} MiB")
    if problems:
        return False, summary + "; sorunlar: " + "; ".join(problems[:6])
    return True, summary


_PERF_CPU = re.compile(r"Hedef CPU < %5 \(tek çekirdek\): (SAĞLANDI|SAĞLANMADI)")
_PERF_RAM = re.compile(r"Hedef RAM < 200 MiB: (SAĞLANDI|SAĞLANMADI|ölçülemedi)")
_PERF_GUI = re.compile(r"(YANIT VERİYOR|DONMA ŞÜPHESİ)")
_PERF_AVG = re.compile(r"Ortalama CPU: %([\d.,]+) \(tek çekirdek")
_PERF_RSS = re.compile(r"en yüksek ([\d.,]+) MiB")


def parse_perf(text: str) -> Dict[str, Optional[str]]:
    """scripts/perf_check.py çıktısındaki hedef satırları -> sözlük (bulunamayan: None)."""
    def first(pattern: "re.Pattern[str]") -> Optional[str]:
        match = pattern.search(text)
        return match.group(1) if match else None

    return {"cpu": first(_PERF_CPU), "ram": first(_PERF_RAM), "gui": first(_PERF_GUI),
            "avg_cpu": first(_PERF_AVG), "peak_rss_mib": first(_PERF_RSS)}


def perf_status(perf: Dict[str, Optional[str]], gui: bool = False) -> Tuple[str, str]:
    parts: List[str] = []
    if perf.get("avg_cpu"):
        avg = str(perf["avg_cpu"]).replace(".", ",")
        parts.append(f"ortalama CPU %{avg} (tek çekirdek = %100)")
    if perf.get("peak_rss_mib"):
        parts.append(f"en yüksek RSS {str(perf['peak_rss_mib']).replace('.', ',')} MiB")
    parts.append(f"hedef CPU < %5: {perf.get('cpu') or 'satır bulunamadı'}")
    parts.append(f"hedef RAM < 200 MiB: {perf.get('ram') or 'satır bulunamadı'}")
    ok = perf.get("cpu") == "SAĞLANDI" and perf.get("ram") == "SAĞLANDI"
    if gui:
        parts.append(f"olay döngüsü: {perf.get('gui') or 'satır bulunamadı'}")
        ok = ok and perf.get("gui") == "YANIT VERİYOR"
    return (GECTI if ok else KALDI), "; ".join(parts)


_PYTEST_COUNT = re.compile(r"(\d+) (passed|failed|skipped|errors?|xfailed|xpassed|deselected)")


def pytest_counts(text: str) -> Dict[str, int]:
    """pytest özet satırı ("4 passed, 1 skipped in 2.1s") -> {"passed": 4, "skipped": 1}."""
    for line in reversed([ln for ln in text.splitlines() if ln.strip()]):
        found = _PYTEST_COUNT.findall(line)
        if found and (" in " in line or "no tests ran" in line):
            return {("error" if kind.startswith("error") else kind): int(n) for n, kind in found}
    return {}


def pytest_status(res: CommandResult) -> Tuple[str, str]:
    counts = pytest_counts(res.output)
    summary = ", ".join(f"{n} {kind}" for kind, n in counts.items()) or "özet satırı yok"
    if res.timed_out or res.error:
        return KALDI, f"pytest {res.describe()}"
    if res.code == 0 and counts.get("passed", 0) == 0 and counts.get("skipped", 0) > 0:
        return ATLANDI, f"tüm testler atlandı ({summary}); Linux ve psutil gerekir"
    if res.code == 0:
        return GECTI, summary
    if res.code == 5:
        return KALDI, "hiç test bulunamadı (pytest çıkış kodu 5)"
    return KALDI, f"pytest çıkış kodu {res.code}: {summary}"


def parse_free(text: str) -> Optional[Dict[str, int]]:
    """`free -b` (LC_ALL=C) çıktısının "Mem:" satırı -> {"total": ..., "available": ...}."""
    header: Optional[List[str]] = None
    for line in text.splitlines():
        parts = line.split()
        if not parts:
            continue
        if header is None and "total" in parts:
            header = parts
            continue
        if parts[0] == "Mem:" and header is not None:
            values = parts[1:]
            result: Dict[str, int] = {}
            for key in ("total", "available"):
                if key in header and header.index(key) < len(values):
                    try:
                        result[key] = int(values[header.index(key)])
                    except ValueError:
                        pass
            return result if "total" in result else None
    return None


def parse_os_release(text: str) -> Dict[str, str]:
    result: Dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        result[key.strip()] = value
    return result


def desktop_entry_problems(text: str) -> List[str]:
    """Menü dosyasının [Desktop Entry] bölümünü ve Exec/Path hedeflerinin varlığını denetler."""
    entries: Dict[str, str] = {}
    in_main = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("["):
            in_main = stripped == "[Desktop Entry]"
        elif in_main and "=" in stripped and not stripped.startswith("#"):
            key, value = stripped.split("=", 1)
            entries.setdefault(key.strip(), value.strip())
    if not entries:
        return ["[Desktop Entry] bölümü yok"]
    problems: List[str] = []
    exec_line = entries.get("Exec", "")
    try:
        program = shlex.split(exec_line)[0] if exec_line else ""
    except ValueError:
        program = ""
    if not program:
        problems.append("Exec= satırı yok veya okunamadı")
    elif os.path.isabs(program):
        if not os.path.isfile(program):
            problems.append(f"Exec programı bulunamadı: {program}")
    elif shutil.which(program) is None:
        problems.append(f"Exec programı PATH'te yok: {program}")
    work_dir = entries.get("Path")
    if work_dir and not os.path.isdir(work_dir):
        problems.append(f"Path= dizini yok: {work_dir} (depo taşınmış olabilir; "
                        "scripts/install_user.sh'yi yeniden çalıştırın)")
    return problems


# ---------------------------------------------------------------------------
# Gizlilik
# ---------------------------------------------------------------------------


def _safe_call(fn: Callable[[], Any]) -> str:
    try:
        return str(fn() or "")
    except Exception:
        return ""


def _scrubbable(name: str) -> bool:
    return len(name) >= 3 and name.lower() not in GENERIC_NAMES


def _word_pattern(name: str) -> "re.Pattern[str]":
    # Ad başka bir sözcüğün parçasıysa (ör. "can" -> "canlı") değiştirilmez
    return re.compile(r"(?<![\w-])" + re.escape(name) + r"(?![\w-])")


class Scrubber:
    """Metinden ev dizini yolunu, makine adını ve kullanıcı adını gizler.

    Değiştirme büyük/küçük harf duyarlıdır. Kullanıcı ve makine adı yalnızca ayrı bir
    sözcük olarak geçtiğinde değiştirilir; 3 karakterden kısa ve kimlik belirtmeyen genel
    adlar (GENERIC_NAMES) metni bozmamak için olduğu gibi bırakılır.
    """

    def __init__(self) -> None:
        self.rules: List[Tuple["re.Pattern[str]", str]] = []
        home = _safe_call(lambda: os.path.expanduser("~"))
        homes: List[str] = []
        for path in (home, _safe_call(lambda: os.path.realpath(home)) if home else ""):
            for variant in (path, path.replace("\\", "/")):
                variant = variant.rstrip("/\\")
                if len(variant) >= 3 and variant not in homes:
                    homes.append(variant)
        for path in sorted(homes, key=len, reverse=True):
            self.rules.append((re.compile(re.escape(path) + r"(?![\w.-])"), "~"))
        host = _safe_call(platform.node)
        for name in sorted({host, host.split(".")[0]} if host else set(), key=len, reverse=True):
            if _scrubbable(name):
                self.rules.append((_word_pattern(name), "<makine>"))
        user = _safe_call(getpass.getuser)
        if _scrubbable(user):
            self.rules.append((_word_pattern(user), "<kullanıcı>"))

    def __call__(self, text: str) -> str:
        for pattern, replacement in self.rules:
            text = pattern.sub(replacement, text)
        return text


def scrub(text: str) -> str:
    """Kullanıcı adını, makine adını ve ev dizini yolunu gizler."""
    return Scrubber()(text)


# ---------------------------------------------------------------------------
# Ortam bilgisi
# ---------------------------------------------------------------------------


def os_description() -> str:
    try:
        with open("/etc/os-release", "r", encoding="utf-8", errors="replace") as handle:
            info = parse_os_release(handle.read())
    except OSError:
        return platform.platform()
    pretty = info.get("PRETTY_NAME") or info.get("NAME") or "?"
    version = info.get("VERSION_ID")
    return f"{pretty} (VERSION_ID={version})" if version else pretty


def memory_description() -> str:
    try:
        with open("/proc/meminfo", "r", encoding="ascii", errors="replace") as handle:
            info = parse_meminfo(handle.read())
        total, swap = info.get("MemTotal"), info.get("SwapTotal")
    except OSError:
        ps = load_psutil()
        if ps is None:
            return "—"
        total, swap = ps.virtual_memory().total, ps.swap_memory().total
    return f"{fmt_bytes(total)} / swap {fmt_bytes(swap) if swap else 'yok'}"


def virtualization_hint() -> str:
    parts: List[str] = []
    for name in ("sys_vendor", "product_name"):
        try:
            with open(f"/sys/class/dmi/id/{name}", "r", encoding="utf-8",
                      errors="replace") as handle:
                value = handle.read().strip()
        except OSError:
            continue
        if value and value not in parts:
            parts.append(value)
    return " ".join(parts) or "—"


def environment_rows() -> List[Tuple[str, str]]:
    def safe(fn: Callable[[], Any]) -> str:
        return _safe_call(fn) or "—"

    return [
        ("Pardus / işletim sistemi", safe(os_description)),
        ("Çekirdek", safe(platform.release)),
        ("Mimari", safe(platform.machine)),
        ("Python", safe(lambda: f"{platform.python_version()} "
                                f"({'sanal ortam' if in_venv() else 'sistem'})")),
        ("psutil", safe(lambda: module_version("psutil")[0] or "yok")),
        ("PySide6", safe(lambda: module_version("PySide6")[0] or "yok")),
        ("Mantıksal CPU", safe(os.cpu_count)),
        ("RAM / swap", safe(memory_description)),
        ("Masaüstü", os.environ.get("XDG_CURRENT_DESKTOP") or "—"),
        ("Oturum türü", os.environ.get("XDG_SESSION_TYPE") or "—"),
        ("Grafik ekran", ", ".join(n for n in ("DISPLAY", "WAYLAND_DISPLAY")
                                   if os.environ.get(n)) or "yok"),
        ("Sanallaştırma", safe(virtualization_hint)),
        ("Kapsayıcı", "evet" if any(os.path.exists(p) for p in ("/.dockerenv",
                                                               "/run/.containerenv")) else "hayır"),
        ("PSI", "var" if os.path.exists("/proc/pressure/memory") else "yok"),
        ("Çalıştırma tarihi", time.strftime("%Y-%m-%d %H:%M")),
    ]


# ---------------------------------------------------------------------------
# 1. Kurulum
# ---------------------------------------------------------------------------


def check_1_1(ctx: Context) -> Check:
    no = "1.1"
    apt = shutil.which("apt-cache")
    if not apt:
        return Check(no, TITLES[no], ATLANDI, "apt-cache bulunamadı (Debian/Pardus dışı sistem)")
    res = run_command([apt, "policy", *APT_PACKAGES], timeout=120, cwd=ctx.tempdir("apt"),
                      env=child_env())
    candidates = parse_apt_policy(res.output)
    found = "; ".join(f"`{p}`: aday {candidates.get(p) or 'yok'}" for p in APT_PACKAGES)
    missing = [p for p in APT_PACKAGES if not candidates.get(p)]
    if not res.ok:
        return Check(no, TITLES[no], KALDI, f"apt-cache policy {res.describe()}; {found}",
                     cikti=res.output)
    if missing:
        return Check(no, TITLES[no], KALDI,
                     f"{found}. Depoda adayı olmayan: {', '.join(missing)} (`sudo apt update` "
                     "sonrası yeniden deneyin)", cikti=res.output)
    return Check(no, TITLES[no], GECTI, found, cikti=res.output)


QT_PROBE = ("import sys\n"
            "from PySide6.QtWidgets import QApplication\n"
            "app = QApplication(sys.argv[:1])\n"
            "print('QPA=' + app.platformName())\n")


def qt_platform_probe(ctx: Context) -> Tuple[bool, str]:
    """Grafik oturumda QApplication açılabiliyor mu (Qt platform eklentisi)?"""
    res = run_command([sys.executable, "-c", QT_PROBE], timeout=60, cwd=ctx.tempdir("qt"),
                      env=child_env(real_gui=True))
    match = re.search(r"QPA=(\S+)", res.output)
    if res.ok and match:
        return True, f"GUI açılış denemesi: Qt platform eklentisi \"{match.group(1)}\" yüklendi"
    hint = ("`sudo apt install libxcb-cursor0` (pip ile kurulan PySide6; KURULUM.md seçenek B "
            "notu)" if in_venv() else "`sudo apt install qt6-qpa-plugins`")
    last = _short(tail_lines(res.output, 1), 160)
    return False, (f"GUI açılış denemesi başarısız ({res.describe()}"
                   f"{': ' + last if last else ''}); öneri: {hint}")


def check_1_2(ctx: Context) -> Check:
    no = "1.2"
    interpreter = "sanal ortam (seçenek B)" if in_venv() else "sistem Python'u (seçenek A)"
    details = [f"yorumlayıcı: {interpreter}, Python {platform.python_version()}"]
    status = GECTI
    ps_version, ps_error = module_version("psutil")
    if ps_version:
        details.append(f"psutil {ps_version}")
    else:
        status = KALDI
        details.append(f"psutil yok ({ps_error}): canlı izleme ve süreç listesi çalışmaz; "
                       "KURULUM.md seçenek A/B")
    qt_version, qt_error = module_version("PySide6")
    if qt_version:
        widgets, widgets_error = module_version("PySide6.QtWidgets")
        if widgets is None:
            qt_version, qt_error = None, widgets_error
    if qt_version:
        details.append(f"PySide6 {qt_version} (QtWidgets yüklendi)")
        if has_display():
            ok, text = qt_platform_probe(ctx)
            details.append(text)
            if not ok:
                status = KALDI
        else:
            details.append("grafik oturum yok (DISPLAY/WAYLAND_DISPLAY tanımsız): GUI açılış "
                           "denemesi yapılmadı")
    else:
        status = KALDI
        details.append(f"PySide6.QtWidgets yüklenemedi ({qt_error}): GUI açılmaz; --headless "
                       "çalışır; KURULUM.md seçenek A/B")
    return Check(no, TITLES[no], status, "; ".join(details))


def check_1_3(ctx: Context) -> Check:
    no = "1.3"
    if in_venv():
        return Check(no, TITLES[no], GECTI,
                     "betik sanal ortamda çalışıyor (sys.prefix ≠ sys.base_prefix); bu ortamdaki "
                     "paketler ve GUI açılış denemesi için bkz. 1.2")
    return Check(no, TITLES[no], MANUEL, MANUAL_1_3)


def desktop_candidates() -> List[str]:
    data_homes = [os.environ.get("XDG_DATA_HOME") or "",
                  os.path.join(os.path.expanduser("~"), ".local", "share")]
    paths = [os.path.join(h, "applications", "pardusinsight.desktop") for h in data_homes if h]
    paths.append("/usr/share/applications/pardusinsight.desktop")
    return list(dict.fromkeys(paths))


def check_1_4(ctx: Context) -> List[Check]:
    no = "1.4"
    manual = Check("1.4b", TITLES["1.4b"], MANUEL, MANUAL_1_4B)
    found = [p for p in desktop_candidates() if os.path.isfile(p)]
    if not found:
        return [Check(no, TITLES[no], MANUEL, MANUAL_1_4), manual]
    validator = shutil.which("desktop-file-validate")
    problems: List[str] = []
    outputs: List[str] = []
    for path in found:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as handle:
                text = handle.read()
        except OSError as exc:
            problems.append(f"{path}: okunamadı ({exc.strerror or exc})")
            continue
        problems += [f"{path}: {p}" for p in desktop_entry_problems(text)]
        if validator:
            res = run_command([validator, path], timeout=60, cwd=ctx.tempdir("desktop"),
                              env=child_env())
            outputs.append(f"$ desktop-file-validate {path}\n"
                           f"{res.output.strip() or '(çıktı yok: dosya geçerli)'}")
            if not res.ok:
                problems.append(f"{path}: desktop-file-validate {res.describe()}")
    how = ("desktop-file-validate ile doğrulandı" if validator else
           "desktop-file-validate yok (desktop-file-utils paketi); yalnızca varlık ve Exec/Path "
           "hedefleri denetlendi")
    detail = f"bulundu: {', '.join(found)}; {how}"
    if problems:
        return [Check(no, TITLES[no], KALDI, detail + "; sorunlar: " + "; ".join(problems),
                      cikti="\n\n".join(outputs)), manual]
    return [Check(no, TITLES[no], GECTI, detail, cikti="\n\n".join(outputs)), manual]


# ---------------------------------------------------------------------------
# 2. Standart kullanıcı ve güvenlik
# ---------------------------------------------------------------------------


def admin_group() -> Optional[str]:
    """Kullanıcı sudo/wheel/admin grubundaysa grup adı, değilse "", bilinmiyorsa None."""
    try:
        import grp
    except ImportError:
        return None
    names: Set[str] = set()
    for gid in set(os.getgroups()) | {os.getegid()}:
        try:
            names.add(grp.getgrgid(gid).gr_name)
        except KeyError:
            continue
    user = _safe_call(getpass.getuser)
    for group in ("sudo", "wheel", "admin"):
        if group in names:
            return group
        try:
            if user and user in grp.getgrnam(group).gr_mem:
                return group
        except KeyError:
            continue
    return ""


def check_2_1(ctx: Context) -> Check:
    no = "2.1"
    geteuid = getattr(os, "geteuid", None)
    if geteuid is None or not is_linux():
        return Check(no, TITLES[no], ATLANDI, "yalnızca Linux (os.geteuid yok veya Linux dışı)")
    if geteuid() == 0:
        return Check(no, TITLES[no], KALDI, "betik root olarak (euid 0) çalışıyor: standart "
                                            "kullanıcıyla çalıştırın, sudo kullanmayın")
    group = admin_group()
    if group is None:
        info = "Bilgi: grup üyeliği belirlenemedi."
    elif group:
        info = (f"Bilgi: kullanıcı '{group}' grubunda (gerektiğinde yönetici yetkisi alabilir); "
                f"listedeki \"sudo yetkisi olmayan kullanıcı\" koşulu için betiği {group} "
                "grubunda olmayan bir hesapla da çalıştırın.")
    else:
        info = "Bilgi: kullanıcı sudo/wheel/admin grubunda değil (yetkisiz standart kullanıcı)."
    return Check(no, TITLES[no], GECTI, f"betik standart kullanıcıyla çalışıyor (euid ≠ 0). {info}")


def check_2_2(ctx: Context) -> Check:
    no = "2.2"
    if not is_linux():
        return Check(no, TITLES[no], ATLANDI, LINUX_ONLY)
    res = run_command(app_cmd("--headless", "--ticks", "5", "--interval", "1"), timeout=90,
                      cwd=ctx.tempdir("2.2"), env=child_env())
    bad = [w for w in BAD_WORDS if w in res.output]
    lines = sum(1 for line in res.output.splitlines() if "CPU" in line)
    if res.ok and not bad:
        return Check(no, TITLES[no], GECTI,
                     f"`python3 -m pardusinsight --headless --ticks 5 --interval 1`: çıkış kodu 0, "
                     f"{lines} ölçüm satırı; çıktıda \"okunamadı\" / \"alınamadı\" / Traceback yok",
                     cikti=res.output)
    problems = [] if res.ok else [res.describe()]
    if bad:
        problems.append("çıktıda " + ", ".join(f"\"{w}\"" for w in bad) + " var")
    return Check(no, TITLES[no], KALDI, "; ".join(problems) + " (çıktı ekte)", cikti=res.output)


def _root_username() -> str:
    try:
        import pwd

        return pwd.getpwuid(0).pw_name
    except (ImportError, KeyError):
        return "root"


def check_2_3(ctx: Context) -> Check:
    no = "2.3"
    if not is_linux():
        return Check(no, TITLES[no], ATLANDI, LINUX_ONLY)
    ps = load_psutil()
    if ps is None:
        return Check(no, TITLES[no], ATLANDI, "psutil yok (bkz. 1.2)")
    from pardusinsight.collectors.processes import ProcessCollector

    collector = ProcessCollector(ps)
    collector.collect()
    _sleep(1.0)
    snap = collector.collect()
    me = os.getpid()
    root_name = _root_username()
    own = next((p for p in snap.processes if p.pid == me), None)
    roots = [p for p in snap.processes if p.pid != me and p.username == root_name]
    leaked = [p for p in roots if p.read_bytes_per_s is not None or p.write_bytes_per_s is not None]
    is_root = os.geteuid() == 0
    problems: List[str] = []
    if snap.error:
        problems.append(snap.error)
    if own is None:
        problems.append("betiğin kendi süreci listede yok")
    elif own.read_bytes_per_s is None:
        problems.append("betiğin kendi sürecinin G/Ç hızı hesaplanamadı")
    if not is_root and leaked:
        problems.append(f"{len(leaked)} root sürecinin G/Ç değeri okunabildi (beklenen: \"—\")")
    parts = [f"iki tarama (~1 sn arayla) istisnasız tamamlandı: görülen {snap.total_seen}, kısmi "
             f"erişim {snap.partial_access}, erişim reddi {snap.access_denied}, tarama sırasında "
             f"sonlanan {snap.vanished} süreç"]
    if is_root:
        parts.append("betik root olarak çalıştığından root süreçleri denetlenmedi")
    else:
        parts.append(f"{len(roots)} root sürecinin {len(roots) - len(leaked)} tanesinde G/Ç "
                     "alanları boş (arayüzde \"—\")")
    if own is not None and own.read_bytes_per_s is not None:
        parts.append(f"betiğin kendi süreci için G/Ç okuma hızı sayısal "
                     f"({fmt_rate(own.read_bytes_per_s)})")
    if problems:
        return Check(no, TITLES[no], KALDI, "; ".join(parts) + "; sorunlar: " + "; ".join(problems))
    return Check(no, TITLES[no], GECTI, "; ".join(parts))


def inet_connection_count(ps: Any, pid: int) -> int:
    """Sürecin ve alt süreçlerinin TCP/UDP (IPv4/IPv6) bağlantı sayısı."""
    root = ps.Process(pid)
    total = 0
    for proc in [root, *root.children(recursive=True)]:
        getter = getattr(proc, "net_connections", None) or proc.connections  # psutil < 6
        total += len(getter(kind="inet"))
    return total


def check_2_4(ctx: Context) -> Check:
    no = "2.4"
    if not is_linux():
        return Check(no, TITLES[no], ATLANDI, LINUX_ONLY)
    ps = load_psutil()
    if ps is None:
        return Check(no, TITLES[no], ATLANDI,
                     "psutil yok (bkz. 1.2); elle: uygulama açıkken `ss -tunap | grep python`")
    proc = subprocess.Popen(app_cmd("--headless", "--ticks", "6", "--interval", "1"),
                            cwd=ctx.tempdir("2.4"), env=child_env(), stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        _sleep(2.5)
        if proc.poll() is not None:
            code, out = stop_process(proc)
            return Check(no, TITLES[no], KALDI,
                         f"uygulama denetimden önce sonlandı (çıkış kodu {code})", cikti=out)
        try:
            count = inet_connection_count(ps, proc.pid)
        except ps.AccessDenied:
            stop_process(proc)
            return Check(no, TITLES[no], ATLANDI, "bağlantılar okunamadı (psutil AccessDenied); "
                                                  "elle: `ss -tunap | grep python`")
        code, out = stop_process(proc, timeout=30)
    finally:
        kill_if_alive(proc)
    detail = (f"canlı izleme yapan headless süreçte (ve alt süreçlerinde) 2,5. saniyede {count} "
              f"ağ bağlantısı (psutil, kind=inet: TCP/UDP, IPv4/IPv6); süreç çıkış kodu {code}")
    if count == 0 and code == 0:
        return Check(no, TITLES[no], GECTI, detail)
    return Check(no, TITLES[no], KALDI, detail, cikti=out)


def home_snapshot(home: str) -> Dict[str, Set[str]]:
    """Ev dizininin ve seçili alt dizinlerinin giriş adları (içerikler okunmaz)."""
    snap: Dict[str, Set[str]] = {}
    for label, parts in HOME_DIRS:
        try:
            snap[label] = set(os.listdir(os.path.join(home, *parts)))
        except OSError:
            snap[label] = set()
    return snap


def new_pardus_entries(before: Dict[str, Set[str]],
                       after: Dict[str, Set[str]]) -> Tuple[List[str], int]:
    """(adında "pardus" geçen yeni girişler, toplam yeni giriş sayısı)."""
    found: List[str] = []
    total = 0
    for label, names in after.items():
        new = names - before.get(label, set())
        total += len(new)
        found += [f"{label}/{name}" for name in sorted(new) if "pardus" in name.lower()]
    return found, total


def check_2_5(ctx: Context) -> Check:
    no = "2.5"
    if not is_linux():
        return Check(no, TITLES[no], ATLANDI, LINUX_ONLY)
    home = os.path.expanduser("~")
    if not os.path.isdir(home):
        return Check(no, TITLES[no], ATLANDI, "ev dizini bulunamadı")
    before = home_snapshot(home)
    res = run_command(app_cmd("--headless", "--ticks", "5", "--interval", "1"), timeout=90,
                      cwd=home, env=child_env())
    found, total = new_pardus_entries(before, home_snapshot(home))
    compared = "~, ~/.config, ~/.local/share ve ~/.cache çalıştırma öncesi/sonrası karşılaştırıldı"
    if found:
        return Check(no, TITLES[no], KALDI,
                     f"{compared}; PardusInsight'a ait olabilecek yeni giriş: {', '.join(found)}")
    if not res.ok:
        return Check(no, TITLES[no], KALDI, f"headless çalıştırma başarısız ({res.describe()})",
                     cikti=res.output)
    others = total - len(found)
    return Check(no, TITLES[no], GECTI,
                 f"`--headless --ticks 5` ev dizininde (cwd=~) dışa aktarmasız çalıştı; "
                 f"{compared}; adında \"pardus\" geçen yeni giriş yok"
                 + (f" (başka uygulamalardan kaynaklanabilecek {others} yeni giriş sayıldı; adları "
                    "rapora yazılmadı)" if others else ""))


def run_pytest(ctx: Context, test_file: str) -> CommandResult:
    # --basetemp: testlerin geçici dosyaları da betiğin sildiği geçici dizinde kalsın;
    # -p no:cacheprovider: depoya .pytest_cache yazılmasın
    basetemp = os.path.join(ctx.tempdir("pytest"), "basetemp")
    return run_command([sys.executable, "-m", "pytest", "-q", "-rs", "-p", "no:cacheprovider",
                        f"--basetemp={basetemp}", test_file], timeout=600, cwd=ROOT,
                       env=child_env({"QT_QPA_PLATFORM": "offscreen"}))


def check_2_6(ctx: Context) -> Check:
    no = "2.6"
    if not pytest_available():
        return Check(no, TITLES[no], ATLANDI, "pytest yok (`sudo apt install python3-pytest` veya "
                                              "requirements-dev.txt)")
    res = run_pytest(ctx, "tests/test_cli_safety.py")
    status, detail = pytest_status(res)
    return Check(no, TITLES[no], status, detail, cikti=tail_lines(res.output, 15))


# ---------------------------------------------------------------------------
# 3. Ölçüm doğruluğu
# ---------------------------------------------------------------------------


def check_3_1(ctx: Context) -> Check:
    no = "3.1"
    if not is_linux():
        return Check(no, TITLES[no], ATLANDI, LINUX_ONLY)
    res = run_command(script_cmd("validate_metrics.py", "--rounds", "10", "--interval", "1"),
                      timeout=180, cwd=ctx.tempdir("3.1"), env=child_env())
    ok, detail = evaluate_validate_rows(parse_validate_table(res.output))
    if not res.ok:
        ok, detail = False, f"validate_metrics.py {res.describe()}; {detail}"
    return Check(no, TITLES[no], GECTI if ok else KALDI,
                 detail + " (tablo ekte; TEST_RAPORU.md'ye ekleyin)", cikti=res.output)


def check_3_2(ctx: Context) -> Check:
    no = "3.2"
    if not is_linux():
        return Check(no, TITLES[no], ATLANDI, "yalnızca Linux (bu testler Linux dışında atlanır)")
    if not pytest_available():
        return Check(no, TITLES[no], ATLANDI, "pytest yok (`sudo apt install python3-pytest`)")
    res = run_pytest(ctx, "tests/test_crosscheck_linux.py")
    status, detail = pytest_status(res)
    return Check(no, TITLES[no], status, detail, cikti=tail_lines(res.output, 15))


def check_3_3(ctx: Context) -> List[Check]:
    no = "3.3"
    manual = Check("3.3b", TITLES["3.3b"], MANUEL, MANUAL_3_3B)
    if not is_linux():
        return [Check(no, TITLES[no], ATLANDI, LINUX_ONLY), manual]
    free = shutil.which("free")
    if not free:
        return [Check(no, TITLES[no], ATLANDI, "`free` (procps) bulunamadı"), manual]
    mem = ProcFsReader().read_memory()
    res = run_command([free, "-b"], timeout=30, cwd=ctx.tempdir("3.3"), env=child_env())
    ref = parse_free(res.output)
    ours = (f"PardusInsight (/proc/meminfo): MemTotal {mem.total} B, MemAvailable "
            f"{mem.available} B")
    output = res.output.rstrip() + "\n" + ours
    if not res.ok or ref is None or "available" not in ref:
        return [Check(no, TITLES[no], KALDI, f"`free -b` çıktısı ayrıştırılamadı "
                                             f"({res.describe()})", cikti=output), manual]
    equal = mem.total == ref["total"]
    diff = abs(mem.available - ref["available"])
    pct = diff / max(ref["available"], 1) * 100.0
    detail = (f"MemTotal {fmt_bytes(mem.total)}: free ile {'eşit' if equal else 'FARKLI'} "
              f"({mem.total} / {ref['total']} B); MemAvailable farkı {fmt_bytes(diff)} "
              f"(%{tr_num(pct, 2)}; sınır %5)")
    status = GECTI if equal and pct < 5.0 else KALDI
    return [Check(no, TITLES[no], status, detail, cikti=output), manual]


def check_3_4(ctx: Context) -> Check:
    no = "3.4"
    if not is_linux():
        return Check(no, TITLES[no], ATLANDI, LINUX_ONLY)
    exists = os.path.exists("/proc/pressure/memory")
    try:
        readable = ProcFsReader().read_pressure() is not None
    except Exception:
        readable = False
    try:
        with open("/proc/cmdline", "r", encoding="ascii", errors="replace") as handle:
            psi_args = [t for t in handle.read().split() if t.startswith("psi=")]
    except OSError:
        psi_args = []
    parts = [f"çekirdek {platform.release()}"]
    if exists and readable:
        parts.append("PSI var: /proc/pressure/memory okunabiliyor; durum çubuğunda \"PSI: mevcut\" "
                     "görünmeli ve bellek kuralı PSI göstergesini de kullanır")
    elif exists:
        parts.append("/proc/pressure var ama okunamadı; bellek kuralı swap ve major page fault "
                     "göstergeleriyle çalışır")
    else:
        parts.append("PSI yok (/proc/pressure/memory bulunamadı); bellek kuralı swap ve major page "
                     "fault göstergeleriyle çalışır, durum çubuğunda \"PSI: yok\" görünmeli")
    if psi_args:
        parts.append(f"çekirdek komut satırında {' '.join(psi_args)} var")
    return Check(no, TITLES[no], BILGI, "; ".join(parts))


# ---------------------------------------------------------------------------
# 4. Performans
# ---------------------------------------------------------------------------


def _gui_perf_check(ctx: Context) -> Check:
    no = "4.1b"
    if not ctx.args.gui:
        return Check(no, TITLES[no], ATLANDI, "--gui ile çalıştırın (XFCE oturumunda, 60 sn)")
    if not has_display():
        return Check(no, TITLES[no], ATLANDI,
                     "grafik oturum yok (DISPLAY/WAYLAND_DISPLAY tanımsız)")
    if module_version("PySide6.QtWidgets")[0] is None:
        return Check(no, TITLES[no], ATLANDI, "PySide6 yok (bkz. 1.2)")
    progress("      GUI ölçümü: 60 sn boyunca bir PardusInsight penceresi açık kalacak; "
             "kapatmayın.")
    res = run_command(script_cmd("perf_check.py", "--gui", "--duration", "60"), timeout=300,
                      cwd=ctx.tempdir("4.1b"), env=child_env(real_gui=True))
    status, detail = perf_status(parse_perf(res.output), gui=True)
    if not res.ok:
        status, detail = KALDI, f"perf_check.py --gui {res.describe()}; {detail}"
    return Check(no, TITLES[no], status, detail, cikti=res.output)


def check_4_1(ctx: Context) -> List[Check]:
    no = "4.1"
    if ctx.args.hizli:
        gui = "--hizli" if ctx.args.gui else "--gui ile çalıştırın (XFCE oturumunda, 60 sn)"
        return [Check(no, TITLES[no], ATLANDI, "--hizli: 60 sn'lik performans ölçümü atlandı"),
                Check("4.1b", TITLES["4.1b"], ATLANDI, gui)]
    if not is_linux():
        return [Check(no, TITLES[no], ATLANDI, LINUX_ONLY),
                Check("4.1b", TITLES["4.1b"], ATLANDI, LINUX_ONLY)]
    res = run_command(script_cmd("perf_check.py", "--duration", "60"), timeout=240,
                      cwd=ctx.tempdir("4.1"), env=child_env())
    status, detail = perf_status(parse_perf(res.output))
    if not res.ok:
        status, detail = KALDI, f"perf_check.py {res.describe()}; {detail}"
    return [Check(no, TITLES[no], status, detail, cikti=res.output), _gui_perf_check(ctx)]


def long_run_readings(service: MonitorService, minutes: int = LONG_RUN_MINUTES,
                      minute_s: float = 60.0,
                      rss: Callable[[], Optional[int]] = SelfUsageMonitor.rss_bytes,
                      on_minute: Optional[Callable[[List[Tuple[int, int, Optional[int]]]], None]]
                      = None) -> List[Tuple[int, int, Optional[int]]]:
    """Servisi örnekleme aralığıyla çalıştırır; her dakika (dakika, tampon, RSS) kaydeder."""
    interval = service.settings.sample_interval_s
    readings: List[Tuple[int, int, Optional[int]]] = []
    start = _clock()
    next_tick = start
    while len(readings) < minutes:
        service.tick()
        elapsed = _clock() - start
        while len(readings) < minutes and elapsed >= (len(readings) + 1) * minute_s:
            readings.append((len(readings) + 1, len(service.history), rss()))
            if on_minute is not None:
                on_minute(readings)
        next_tick += interval
        _sleep(max(0.0, next_tick - _clock()))
    return readings


def long_run_table(readings: Sequence[Tuple[int, int, Optional[int]]], capacity: int) -> str:
    lines = [f"Tampon kapasitesi: {capacity} örnek", "",
             "| Dakika | Tampondaki örnek | RSS (MiB) |", "|---|---|---|"]
    lines += [f"| {m} | {n} | {'—' if r is None else tr_num(r / MIB, 1)} |" for m, n, r in readings]
    return "\n".join(lines)


def evaluate_long_run(readings: Sequence[Tuple[int, int, Optional[int]]], capacity: int,
                      max_rss_growth: int = 10 * MIB) -> Tuple[bool, str]:
    """Tampon kapasiteyi aşmadı mı, son 5 dk'da sabit mi, RSS son 5 dk'da < 10 MiB mı büyüdü?"""
    if len(readings) < 5:
        return False, f"yalnızca {len(readings)} dakikalık ölçüm var (en az 5 gerekli)"
    lengths = [n for _m, n, _r in readings]
    last5 = lengths[-5:]
    problems: List[str] = []
    if max(lengths) > capacity:
        problems.append(f"tampon kapasiteyi aştı ({max(lengths)} > {capacity})")
    if any(abs(n - last5[-1]) > 2 for n in last5):
        problems.append(f"tampon son 5 dk'da büyümeye devam etti ({last5})")
    first_rss, last_rss = readings[-5][2], readings[-1][2]
    if first_rss is None or last_rss is None:
        problems.append("RSS ölçülemedi (/proc/self/status)")
        rss_text = "RSS ölçülemedi"
    else:
        growth = last_rss - first_rss
        rss_text = (f"RSS {readings[-5][0]}. dk {fmt_bytes(first_rss)} → {readings[-1][0]}. dk "
                    f"{fmt_bytes(last_rss)} (artış {fmt_bytes(growth)}; sınır 10 MiB)")
        if growth >= max_rss_growth:
            problems.append("RSS son 5 dk'da 10 MiB'den fazla büyüdü")
    detail = (f"{len(readings)} dk; tampon en çok {max(lengths)} örnek (kapasite {capacity}); "
              f"son 5 dk tampon uzunlukları {', '.join(map(str, last5))}; {rss_text}")
    if problems:
        return False, detail + "; sorunlar: " + "; ".join(problems)
    return True, detail


def check_4_2(ctx: Context) -> Check:
    no = "4.2"
    if not ctx.args.uzun:
        return Check(no, TITLES[no], ATLANDI, "--uzun ile çalıştırın (35 dk)")
    if not is_linux():
        return Check(no, TITLES[no], ATLANDI, LINUX_ONLY)
    service = build_live_service(AppSettings())
    capacity = service.history.capacity
    progress(f"      {LONG_RUN_MINUTES} dk sürecek; Ctrl+C ile kesilirse o ana kadarki tablo kısmi "
             "rapora eklenir.")

    def on_minute(readings: List[Tuple[int, int, Optional[int]]]) -> None:
        minute, length, rss = readings[-1]
        ctx.partial = Check(no, TITLES[no], ATLANDI,
                            f"Ctrl+C ile {minute}. dakikadan sonra kesildi",
                            cikti=long_run_table(readings, capacity))
        progress(f"      4.2: {minute}/{LONG_RUN_MINUTES} dk · tampon {length} örnek · RSS "
                 f"{fmt_bytes(rss)}")

    readings = long_run_readings(service, on_minute=on_minute)
    ok, detail = evaluate_long_run(readings, capacity)
    detail += f"; tampondaki süre {fmt_duration(service.history.duration_s())} (30 dk sınırı)"
    return Check(no, TITLES[no], GECTI if ok else KALDI, detail,
                 cikti=long_run_table(readings, capacity))


def check_4_3(ctx: Context) -> Check:
    return Check("4.3", TITLES["4.3"], MANUEL, MANUAL_4_3)


# ---------------------------------------------------------------------------
# 5. İşlevler
# ---------------------------------------------------------------------------


def replay_file(path: str, settings: Optional[AppSettings] = None) -> Tuple[Any, MonitorService,
                                                                             Any]:
    """Kayıt/senaryo dosyasını "Kayıt/senaryo aç" gibi yükler ve kuralları yeniden çalıştırır."""
    data = load_json_report(path)
    service = MonitorService(RecordingSource(os.path.basename(path)), None,
                             settings or AppSettings())
    return data, service, service.load_recording(data.samples)


def check_5_1(ctx: Context) -> Check:
    no = "5.1"
    path = os.path.join(ROOT, "scenarios", "demo.json")
    if not os.path.isfile(path):
        return Check(no, TITLES[no], KALDI, "scenarios/demo.json bulunamadı")
    data, _service, result = replay_file(path)
    alerts = list(result.alert_log)
    ids = {a.rule_id for a in alerts}
    empty = [a.title for a in alerts if not a.evidence]
    detail = (f"{len(data.samples)} örnek yeniden analiz edildi; {len(alerts)} uyarı: "
              + ", ".join(f"{a.title} ({len(a.evidence)} kanıt satırı)" for a in alerts))
    if ids == EXPECTED_DEMO and not empty:
        return Check(no, TITLES[no], GECTI, detail)
    detail += (f"; beklenen kurallar {', '.join(sorted(EXPECTED_DEMO))}, üretilen "
               f"{', '.join(sorted(ids)) or 'yok'}" + (f"; kanıtı boş: {', '.join(empty)}"
                                                      if empty else ""))
    return Check(no, TITLES[no], KALDI, detail)


def check_5_2(ctx: Context) -> Check:
    no = "5.2"
    parts: List[str] = []
    problems: List[str] = []
    output: List[str] = []
    for name, rule_id in COUNTER_EXAMPLES:
        path = os.path.join(ROOT, "scenarios", name)
        if not os.path.isfile(path):
            if name not in OPTIONAL_SCENARIOS:
                problems.append(f"scenarios/{name} bulunamadı")
            continue
        data, service, result = replay_file(path)
        alerts = list(result.alert_log)
        statuses = list(service.engine.statuses())
        status = next((s for s in statuses if s.rule_id == rule_id), None)
        if alerts:
            problems.append(f"{name}: {len(alerts)} uyarı üretildi "
                            f"({', '.join(a.title for a in alerts)})")
        reason = (f"{status.title}: {status.reason.rstrip('.')}" if status
                  else f"{rule_id}: durum yok")
        verdict = f"{len(alerts)} UYARI" if alerts else "uyarı yok"
        parts.append(f"{name}: {verdict} — {reason}")
        output.append(f"{name} ({len(data.samples)} örnek, {len(alerts)} uyarı); "
                      "son kural durumları:")
        output += [f"  {s.title}: {s.reason}" for s in statuses]
    if not parts and not problems:
        problems.append("karşı-örnek senaryo bulunamadı")
    detail = "; ".join(parts) + ("; sorunlar: " + "; ".join(problems) if problems else "")
    return Check(no, TITLES[no], KALDI if problems else GECTI, detail, cikti="\n".join(output))


def demo_recording(ctx: Context) -> Tuple[List[SystemSample], list, MonitorService]:
    """Sentetik demo kaydı (5.3 ve 5.4 paylaşır; belirlenimci zaman damgaları)."""
    if ctx.demo is None:
        service = build_synthetic_service("demo", loop=False, start_time=DEMO_START)
        for _ in range(DEMO_TICKS):
            service.tick()
        ctx.demo = (service.history.snapshot(), list(service.engine.alert_log()), service)
    return ctx.demo


def check_5_3(ctx: Context) -> List[Check]:
    no = "5.3"
    manual = Check("5.3b", TITLES["5.3b"], MANUEL, MANUAL_5_3B)
    samples, alerts, _service = demo_recording(ctx)
    folder = ctx.tempdir("5.3")
    samples_path = os.path.join(folder, "ornekler.csv")
    alerts_path = os.path.join(folder, "ornekler_uyarilar.csv")
    write_samples_csv(samples_path, samples)
    write_alerts_csv(alerts_path, alerts)
    back = read_samples_csv(samples_path)
    rows = read_alerts_csv(alerts_path)
    with open(samples_path, "r", encoding="utf-8") as handle:  # katı UTF-8 çözümleme
        columns = handle.readline().count(",") + 1
    titles = [r.get("title", "") for r in rows]
    problems: List[str] = []
    if len(back) != len(samples):
        problems.append(f"örnek sayısı farklı ({len(samples)} yazıldı, {len(back)} okundu)")
    if titles != [a.title for a in alerts]:
        problems.append("uyarı başlıkları geri okunduğunda farklı")
    if "Kalıcı CPU yoğunluğu" not in titles:
        problems.append("\"Kalıcı CPU yoğunluğu\" başlığı bulunamadı")
    detail = (f"sentetik demo kaydı CSV'ye yazılıp geri okundu: {len(back)}/{len(samples)} örnek, "
              f"{columns} sütun (UTF-8, virgül ayırıcı); {len(rows)} uyarı satırı, başlıklar "
              f"korundu: {', '.join(titles)}")
    if problems:
        return [Check(no, TITLES[no], KALDI, detail + "; sorunlar: " + "; ".join(problems)), manual]
    return [Check(no, TITLES[no], GECTI, detail), manual]


def check_5_4(ctx: Context) -> Check:
    no = "5.4"
    samples, alerts, service = demo_recording(ctx)
    path = os.path.join(ctx.tempdir("5.4"), "rapor.json")
    write_json_report(path, build_report(samples, alerts, settings_to_dict(service.settings),
                                         source=service.source_name))
    data, _replayed, result = replay_file(path, service.settings)
    expected = sorted({a.rule_id for a in alerts})
    reanalysed = sorted({a.rule_id for a in result.alert_log})
    detail = (f"JSON rapor yazılıp \"Kayıt/senaryo aç\" ile aynı yoldan geri yüklendi: "
              f"{len(data.samples)}/{len(samples)} örnek, {len(data.alerts)}/{len(alerts)} uyarı; "
              f"yeniden analizde uyarı veren kurallar: {', '.join(reanalysed) or 'yok'}")
    ok = (len(data.samples) == len(samples) and len(data.alerts) == len(alerts)
          and reanalysed == expected)
    if not ok:
        detail += f"; beklenen kurallar: {', '.join(expected) or 'yok'}"
    return Check(no, TITLES[no], GECTI if ok else KALDI, detail)


def check_5_5(ctx: Context) -> Check:
    no = "5.5"
    if ctx.args.hizli:
        return Check(no, TITLES[no], ATLANDI, "--hizli: 70 sn'lik canlı eşik denemesi atlandı")
    if not is_linux():
        return Check(no, TITLES[no], ATLANDI, LINUX_ONLY)
    folder = ctx.tempdir("5.5")
    config = os.path.join(folder, "esik.json")
    with open(config, "w", encoding="utf-8") as handle:
        json.dump(THRESHOLD_CONFIG, handle)
    res = run_command(app_cmd("--headless", "--duration", "70", "--interval", "2", "--quiet",
                              "--config", config), timeout=200, cwd=folder, env=child_env())
    fired = "Kalıcı CPU yoğunluğu" in res.output
    setting = ("`--config` ile CPU eşiği %0,1, oran 0,1, pencere 20 sn; 70 sn canlı izleme "
               "(`--headless --interval 2 --quiet`)")
    if fired and res.ok:
        return Check(no, TITLES[no], GECTI,
                     f"{setting}: \"Kalıcı CPU yoğunluğu\" uyarısı üretildi; eşik ayarı çalışıyor",
                     cikti=res.output)
    return Check(no, TITLES[no], KALDI,
                 f"{setting}: {res.describe()}; uyarı {'üretildi' if fired else 'ÜRETİLMEDİ'}",
                 cikti=res.output)


def record_samples(service: MonitorService, seconds: float,
                   on_progress: Optional[Callable[[float, int], None]] = None
                   ) -> List[SystemSample]:
    """Servisi örnekleme aralığıyla `seconds` boyunca çalıştırır ve tüm örnekleri döndürür.

    Örnekler geçmiş tamponundan değil doğrudan turlardan toplanır; böylece 30 dk'dan uzun
    kayıtlarda da hiçbir örnek düşmez.
    """
    interval = service.settings.sample_interval_s
    samples: List[SystemSample] = []
    start = _clock()
    next_tick = start
    next_report = 60.0
    while True:
        result = service.tick()
        if result.sample is not None:
            samples.append(result.sample)
        elapsed = _clock() - start
        if on_progress is not None and elapsed >= next_report:
            on_progress(elapsed, len(samples))
            next_report += 60.0
        if elapsed >= seconds:
            return samples
        next_tick += interval
        _sleep(max(0.0, next_tick - _clock()))


def take_recording(ctx: Context) -> LiveRecording:
    seconds = float(ctx.args.kalibrasyon_suresi)
    settings = AppSettings()
    service = build_live_service(settings)
    no = "5.6"
    ctx.partial = Check(no, TITLES[no], ATLANDI, "kalibrasyon kaydı Ctrl+C ile kesildi; kayıt "
                                                 "saklanmadı")
    progress(f"      Kalibrasyon kaydı başladı ({fmt_duration(seconds)}): bu sürede masaüstünü "
             "olağan biçimde kullanın (tarayıcı + ofis). İptal: Ctrl+C.")

    def on_progress(elapsed: float, count: int) -> None:
        ctx.partial = Check(no, TITLES[no], ATLANDI,
                            f"kalibrasyon kaydı Ctrl+C ile {fmt_duration(elapsed)} sonra kesildi "
                            f"({count} örnek); kayıt saklanmadı")
        progress(f"      kayıt: {fmt_duration(elapsed)} / {fmt_duration(seconds)} · {count} örnek")

    samples = record_samples(service, seconds, on_progress)
    folder = ctx.args.kayit_klasoru
    if folder:
        os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder or ctx.tempdir("kayit"),
                        time.strftime("olagan_kullanim_%Y%m%d_%H%M%S.json"))
    alerts = replay(samples, settings.analysis).alert_log()
    write_json_report(path, build_report(samples, alerts, settings_to_dict(settings),
                                         source="linux (pardus_kabul.py kalibrasyon kaydı)"),
                      compact=True)
    data = load_json_report(path)  # kaydedilen dosya geri okunabiliyor mu
    ctx.partial = None
    stamps = [s.timestamp for s in data.samples]
    duration = stamps[-1] - stamps[0] if len(stamps) > 1 else 0.0
    if folder:
        progress(f"      kayıt saklandı: {path}")
    return LiveRecording(samples=data.samples, duration_s=duration,
                         path=os.path.abspath(path) if folder else None)


def calibration_recording(ctx: Context) -> Optional[LiveRecording]:
    """Canlı kaydı bir kez alır (5.6 ve 6 paylaşır). Linux dışında None."""
    if ctx.recording_error is not None:
        raise ctx.recording_error  # 5.6'da başarısız olan kayıt 6'da yeniden denenmez
    if ctx.recording is not None:
        return ctx.recording
    if not is_linux():
        return None
    try:
        ctx.recording = take_recording(ctx)
    except Exception as exc:
        ctx.recording_error = exc
        raise
    return ctx.recording


def _recording_location(rec: LiveRecording) -> str:
    if rec.path:
        return f"kayıt: {rec.path} (süreç adları içerir; depoya eklemeden önce göz atın)"
    return "kayıt geçici dizindeydi ve silindi (saklamak için --kayit-klasoru)"


def check_5_6(ctx: Context) -> Check:
    no = "5.6"
    if ctx.args.kalibrasyon_suresi is None:
        return Check(no, TITLES[no], MANUEL, MANUAL_5_6)
    rec = calibration_recording(ctx)
    if rec is None:
        return Check(no, TITLES[no], ATLANDI, "canlı kayıt yalnızca Linux'ta alınabilir")
    if len(rec.samples) < 2:
        return Check(no, TITLES[no], KALDI, f"kayıtta yeterli örnek yok ({len(rec.samples)}); "
                                            "--kalibrasyon-suresi en az birkaç dakika olmalı")
    alerts = list(replay(rec.samples, AnalysisSettings()).alert_log())
    span = f"{len(rec.samples)} örneklik ({fmt_duration(rec.duration_s)}) olağan kullanım kaydı"
    short = ("; not: kayıt 30 dk'dan kısa, liste 5.6 için 30 dk önerir"
             if rec.duration_s < 1800 - 60 else "")
    if not alerts:
        return Check(no, TITLES[no], GECTI, f"{span}nda varsayılan kurallar hiç uyarı üretmedi: "
                                            f"olağan kullanımda yanlış pozitif yok{short}; "
                                            f"{_recording_location(rec)}")
    listing = "; ".join(f"{a.title} ({fmt_datetime(a.first_seen)} – "
                        f"{fmt_time(a.resolved_at or a.last_seen)}, {a.severity_label})"
                        for a in alerts)
    return Check(no, TITLES[no], MANUEL,
                 f"{span}nda {len(alerts)} uyarı üretildi; her birinin açıklanabilir olup "
                 f"olmadığını inceleyin (o sırada ne yapılıyordu?) ve sonucu KURALLAR.md'ye "
                 f"yazın: {listing}; {_recording_location(rec)}")


def check_5_7(ctx: Context) -> Check:
    return Check("5.7", TITLES["5.7"], MANUEL, MANUAL_5_7)


def check_5_8(ctx: Context) -> Check:
    no = "5.8"
    if ctx.args.hizli:
        return Check(no, TITLES[no], ATLANDI, "--hizli: 60 sn'lik headless çalıştırma atlandı")
    if not is_linux():
        return Check(no, TITLES[no], ATLANDI, LINUX_ONLY)
    folder = ctx.tempdir("5.8")
    res = run_command(app_cmd("--headless", "--duration", "60"), timeout=200, cwd=folder,
                      env=child_env())
    lines = sum(1 for line in res.output.splitlines() if "CPU" in line)
    ok_a = res.ok and lines >= 25
    proc = subprocess.Popen(app_cmd("--headless"), cwd=folder, env=child_env(),
                            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT)
    try:
        _sleep(3.0)
        code, out = stop_process(proc, signal.SIGINT, timeout=20)
    finally:
        kill_if_alive(proc)
    stopped = "Durduruldu" in out
    ok_b = code == 0 and stopped
    verdict_a, verdict_b = ("tamam" if ok_a else "SORUN"), ("tamam" if ok_b else "SORUN")
    detail = (f"(a) `--headless --duration 60`: {res.describe()}, {lines} ölçüm satırı (en az 25) "
              f"→ {verdict_a}; (b) 3 sn sonra SIGINT (Ctrl+C): çıkış kodu {code}, \"Durduruldu\" "
              f"iletisi {'var' if stopped else 'YOK'} → {verdict_b}")
    output = ("(a) son satırlar:\n" + tail_lines(res.output, 8) + "\n\n(b) Ctrl+C denemesi:\n"
              + out.strip())
    return Check(no, TITLES[no], GECTI if ok_a and ok_b else KALDI, detail, cikti=output)


# ---------------------------------------------------------------------------
# 6. Eşik kalibrasyonu
# ---------------------------------------------------------------------------


def _fmt_param(value: Any) -> str:
    try:
        return f"{float(value):g}".replace(".", ",")
    except (TypeError, ValueError):
        return str(value)


def summarize_recommendations(recommendations: Sequence[Any]) -> str:
    """Kalibrasyon önerilerinin tek satırlık özeti."""
    if not recommendations:
        return "kalibrasyon öneri üretmedi"
    changed = []
    for rec in recommendations:
        try:
            if abs(float(rec.recommended) - float(rec.current)) > 1e-9:
                changed.append(rec)
        except (TypeError, ValueError):
            if rec.recommended != rec.current:
                changed.append(rec)
    if not changed:
        return (f"{len(recommendations)} eşik incelendi; mevcut eşikler korunabilir "
                "(değişiklik önerisi yok)")
    items = ", ".join(f"{r.parameter} {_fmt_param(r.current)} → {_fmt_param(r.recommended)}"
                      for r in changed)
    return (f"{len(recommendations)} eşikten {len(changed)} tanesi için değişiklik önerildi: "
            f"{items} (gerekçeler ekte)")


def check_6(ctx: Context) -> Check:
    no = "6"
    try:
        from pardusinsight.analysis.calibration import Recording, calibrate, render_markdown
    except ImportError as exc:
        return Check(no, TITLES[no], ATLANDI, f"kalibrasyon modülü bulunamadı ({exc})")
    if ctx.args.kalibrasyon_suresi is None:
        return Check(no, TITLES[no], MANUEL, MANUAL_6)
    rec = calibration_recording(ctx)
    if rec is None:
        return Check(no, TITLES[no], ATLANDI, "canlı kayıt yalnızca Linux'ta alınabilir")
    result = calibrate([Recording(label=f"olağan kullanım ({fmt_duration(rec.duration_s)})",
                                  samples=rec.samples, heavy=False)], base=None)
    summary = summarize_recommendations(list(getattr(result, "recommendations", ()) or ()))
    return Check(no, TITLES[no], BILGI, f"{summary}; {_recording_location(rec)}",
                 cikti=render_markdown(result), cikti_md=True)


# ---------------------------------------------------------------------------
# Rapor
# ---------------------------------------------------------------------------


def group_of(no: str) -> str:
    return no.split(".")[0]


def fenced(text: str, info: str = "text") -> List[str]:
    longest = max((len(run) for run in re.findall(r"`+", text)), default=0)
    fence = "`" * max(3, longest + 1)
    return [fence + info, text, fence]


def render_markdown(checks: Sequence[Check], env_rows: Sequence[Tuple[str, str]] = (),
                    interrupted: bool = False, command: str = "",
                    duration_s: Optional[float] = None) -> str:
    """Sonuçlardan Markdown rapor üretir; tüm metinler gizlilik süzgecinden geçer."""
    clean = Scrubber()

    def cell(value: Any) -> str:
        text = clean(str(value)).replace("\r\n", "\n").replace("\r", "\n").strip()
        return text.replace("|", "\\|").replace("\n", "<br>") or "—"

    def inline(value: Any) -> str:
        return " ".join(clean(str(value)).split())

    lines = ["# Pardus Kabul ve Doğrulama Sonuçları", ""]
    if interrupted:
        lines += ["> **Uyarı:** Çalıştırma Ctrl+C ile yarıda kesildi. Aşağıda yalnızca kesilmeden "
                  "önce tamamlanan kontroller var; rapor eksiktir.", ""]
    lines += [INTRO, ""]
    meta = []
    if command:
        meta.append(f"Komut: `{inline(command)}`")
    if duration_s is not None:
        meta.append(f"süre: {fmt_duration(duration_s)}")
    if meta:
        lines += [" · ".join(meta), ""]

    lines += ["## Ortam", ""]
    if env_rows:
        lines += ["| Özellik | Değer |", "|---|---|"]
        lines += [f"| {cell(k)} | {cell(v)} |" for k, v in env_rows]
    else:
        lines.append("_Ortam bilgisi toplanmadı._")
    lines.append("")

    known = {g for g, _ in GROUPS}
    sections: List[Tuple[str, str]] = [(f"{g}. {t}", g) for g, t in GROUPS]
    if any(group_of(c.no) not in known for c in checks):
        sections.append(("Diğer", ""))
    for heading, group in sections:
        members = [c for c in checks
                   if (group_of(c.no) == group if group else group_of(c.no) not in known)]
        lines += [f"## {heading}", ""]
        if not members:
            lines += ["_Bu bölümdeki kontroller çalıştırılmadı._", ""]
            continue
        lines += ["| # | Kontrol | Sonuç | Ayrıntı |", "|---|---|---|---|"]
        lines += [f"| {cell(c.no)} | {cell(c.baslik)} | {LABELS.get(c.durum, cell(c.durum))} | "
                  f"{cell(c.ayrinti)} |" for c in members]
        lines.append("")

    counts = {s: sum(1 for c in checks if c.durum == s) for s in STATUSES}
    failed = [c.no for c in checks if c.durum == KALDI]
    if interrupted:
        overall = "**Genel sonuç:** çalıştırma yarıda kesildi (çıkış kodu 130)."
    elif failed:
        overall = (f"**Genel sonuç:** {len(failed)} madde KALDI ({', '.join(failed)}); "
                   "çıkış kodu 1.")
    else:
        overall = ("**Genel sonuç:** KALDI olan madde yok (çıkış kodu 0); MANUEL maddeleri elle "
                   "tamamlayın.")
    lines += ["## Özet", "", "| Sonuç | Sayı |", "|---|---|"]
    lines += [f"| {LABELS[s]} | {counts[s]} |" for s in STATUSES]
    lines += [f"| **Toplam** | **{len(checks)}** |", "", overall, ""]

    manual = [c for c in checks if c.durum == MANUEL]
    lines += ["## Elle yapılacaklar", ""]
    if manual:
        lines += [f"{i}. **{c.no} – {inline(c.baslik)}:** {inline(c.ayrinti)}"
                  for i, c in enumerate(manual, 1)]
        lines += ["", "Elle denediğiniz maddelerin sonucunu ve tarihini bu dosyaya işleyin."]
    else:
        lines.append("_Elle yapılacak madde yok._")
    lines.append("")

    lines += ["## Ekler", ""]
    attached = [c for c in checks if c.cikti.strip()]
    if not attached:
        lines += ["_Ek çıktı yok._", ""]
    for c in attached:
        body = clean(c.cikti).replace("\r\n", "\n").strip("\n")
        if c.cikti_md:
            if not body.lstrip().startswith("#"):  # kendi başlığı yoksa madde başlığı eklenir
                lines += [f"### {c.no} – {inline(c.baslik)}", ""]
            lines += [body, ""]
        else:
            lines += [f"### {c.no} – {inline(c.baslik)}", ""] + fenced(body) + [""]
    return "\n".join(lines).rstrip("\n") + "\n"


# ---------------------------------------------------------------------------
# Ana akış
# ---------------------------------------------------------------------------


def plan() -> List[Tuple[str, Callable[[Context], Any]]]:
    """Madde sırası (adlar çağrı anında çözülür; testlerde tek tek değiştirilebilir)."""
    return [("1.1", check_1_1), ("1.2", check_1_2), ("1.3", check_1_3), ("1.4", check_1_4),
            ("2.1", check_2_1), ("2.2", check_2_2), ("2.3", check_2_3), ("2.4", check_2_4),
            ("2.5", check_2_5), ("2.6", check_2_6),
            ("3.1", check_3_1), ("3.2", check_3_2), ("3.3", check_3_3), ("3.4", check_3_4),
            ("4.1", check_4_1), ("4.2", check_4_2), ("4.3", check_4_3),
            ("5.1", check_5_1), ("5.2", check_5_2), ("5.3", check_5_3), ("5.4", check_5_4),
            ("5.5", check_5_5), ("5.6", check_5_6), ("5.7", check_5_7), ("5.8", check_5_8),
            ("6", check_6)]


def estimated_seconds(args: argparse.Namespace) -> float:
    total = 45.0
    if not args.hizli:
        total += 65 + 75 + 70 + (70 if args.gui else 0)  # 4.1, 5.5, 5.8, 4.1b
    if args.uzun:
        total += LONG_RUN_MINUTES * 60
    if args.kalibrasyon_suresi:
        total += args.kalibrasyon_suresi
    return total


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="pardus_kabul.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--cikti", metavar="DOSYA.md",
                   help="Markdown raporu bu dosyaya yaz (atomik); verilmezse standart çıktıya")
    p.add_argument("--hizli", action="store_true",
                   help="yavaş kontrolleri atla (60 sn performans, 70 sn eşik, 60 sn headless)")
    p.add_argument("--gui", action="store_true",
                   help="grafik oturum varsa GUI performans ölçümünü de yap (60 sn, madde 4.1b)")
    p.add_argument("--uzun", action="store_true",
                   help="35 dakikalık bellek sınırı denetimini çalıştır (madde 4.2)")
    p.add_argument("--kalibrasyon-suresi", type=float, metavar="SN",
                   help="SN saniye canlı olağan kullanım kaydı al ve eşik kalibrasyonu yap "
                        "(madde 5.6 ve 6)")
    p.add_argument("--kayit-klasoru", metavar="KLASOR",
                   help="kalibrasyon kaydını bu klasöre JSON rapor olarak kaydet")
    return p


def _check_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if args.kalibrasyon_suresi is not None and args.kalibrasyon_suresi <= 0:
        parser.error("--kalibrasyon-suresi pozitif bir saniye değeri olmalı")
    if args.kayit_klasoru:
        if args.kalibrasyon_suresi is None:
            parser.error("--kayit-klasoru yalnızca --kalibrasyon-suresi ile kullanılır")
        if os.path.exists(args.kayit_klasoru) and not os.path.isdir(args.kayit_klasoru):
            parser.error(f"--kayit-klasoru bir klasör olmalı: {args.kayit_klasoru}")
    if args.cikti:
        if os.path.isdir(args.cikti):
            parser.error("--cikti bir dosya yolu olmalı, klasör değil")
        parent = os.path.dirname(os.path.abspath(args.cikti))
        if not os.path.isdir(parent):
            parser.error(f"--cikti: klasör yok: {parent}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _check_args(parser, args)
    arguments = list(sys.argv[1:] if argv is None else argv)
    command = " ".join(["python3 scripts/pardus_kabul.py", *map(shlex.quote, arguments)])
    ctx = Context(args)
    results: List[Check] = []
    env_rows: List[Tuple[str, str]] = []
    interrupted = False
    started = time.monotonic()
    if is_linux():
        progress(f"PardusInsight kabul denetimi başlıyor; tahmini süre "
                 f"~{fmt_duration(estimated_seconds(args))}. Rapor sonda yazılır.")
    else:
        progress("PardusInsight kabul denetimi başlıyor (Linux dışı sistem: canlı ölçüm gerektiren "
                 "maddeler ATLANDI olur).")
    try:
        env_rows = environment_rows()
        for no, fn in plan():
            progress(f"[{no}] {TITLES.get(no, no)}")
            ctx.partial = None
            checks = safe_run(no, fn, ctx)
            ctx.partial = None
            results.extend(checks)
            for c in checks:
                progress(f"      {c.no}: {c.durum}" + (f" — {_short(c.ayrinti)}" if c.ayrinti
                                                         and c.durum != MANUEL else ""))
    except KeyboardInterrupt:
        interrupted = True
        if ctx.partial is not None:
            results.append(ctx.partial)
        progress("\nCtrl+C: denetim durduruldu; kısmi rapor standart çıktıya yazılıyor.")
    finally:
        ctx.cleanup()
    text = render_markdown(results, env_rows, interrupted=interrupted, command=command,
                           duration_s=time.monotonic() - started)
    if interrupted:
        _write(sys.stdout, text)
        return 130
    counts = " · ".join(f"{sum(1 for c in results if c.durum == s)} {s}" for s in STATUSES)
    code = 1 if any(c.durum == KALDI for c in results) else 0
    if args.cikti:
        try:
            with atomic_write(args.cikti, newline="\n") as handle:
                handle.write(text)
        except OSError as exc:
            progress(f"Rapor yazılamadı ({exc}); rapor standart çıktıya yazılıyor.")
            _write(sys.stdout, text)
            return 2
        progress(f"Rapor yazıldı: {args.cikti}")
    else:
        _write(sys.stdout, text)
    progress(f"Sonuç: {counts} → çıkış kodu {code}")
    return code


if __name__ == "__main__":
    sys.exit(main())
