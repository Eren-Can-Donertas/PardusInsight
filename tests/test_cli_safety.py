"""Komut satırı modu ve güvenlik sınırlarının (salt-okunur çalışma) denetimi."""
import ast
import io
import os
from pathlib import Path

import pytest


from pardusinsight import cli
from pardusinsight.export import load_json_report, read_samples_csv

PACKAGE = Path(__file__).resolve().parents[1] / "pardusinsight"


# ----------------------------------------------------------------------------- CLI
def test_cli_headless_synthetic_exports_csv_and_json(tmp_path, capsys):
    csv_path, json_path = tmp_path / "o.csv", tmp_path / "r.json"
    code = cli.main(["--headless", "--synthetic", "demo", "--speed", "0", "--ticks", "251",
                     "--quiet", "--export-csv", str(csv_path), "--export-json", str(json_path)])
    out = capsys.readouterr().out
    assert code == 0
    assert "Kalıcı CPU yoğunluğu" in out and "Bellek baskısı olasılığı" in out
    assert len(read_samples_csv(str(csv_path))) == 251
    assert (tmp_path / "o_uyarilar.csv").exists()
    assert {a.rule_id for a in load_json_report(str(json_path)).alerts} == {
        "sustained_cpu", "memory_pressure", "disk_io_anomaly"}


def test_cli_replay_reanalyzes_recording(tmp_path, capsys):
    json_path = tmp_path / "kayit.json"
    cli.main(["--headless", "--synthetic", "memory", "--speed", "0", "--ticks", "211",
              "--quiet", "--export-json", str(json_path)])
    capsys.readouterr()
    assert cli.main(["--headless", "--replay", str(json_path)]) == 0
    out = capsys.readouterr().out
    assert "211 örnek yüklendi" in out and "Bellek baskısı olasılığı" in out


def test_cli_rejects_unknown_scenario_and_bad_settings(capsys):
    assert cli.main(["--headless", "--synthetic", "yok"]) == 2
    assert cli.main(["--headless", "--synthetic", "normal", "--interval", "0.01"]) == 2
    assert "geçersiz" in capsys.readouterr().err.lower()


def test_cli_lists_scenarios(capsys):
    assert cli.main(["--list-scenarios"]) == 0
    assert "demo" in capsys.readouterr().out


def test_no_files_are_written_without_explicit_export(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    cli.main(["--headless", "--synthetic", "demo", "--speed", "0", "--ticks", "60", "--quiet"])
    assert list(tmp_path.iterdir()) == []


# ----------------------------------------------------------------------------- güvenlik
FORBIDDEN_MODULES = {"subprocess", "socket", "urllib", "http", "requests", "ftplib", "smtplib",
                     "ctypes", "shutil", "signal", "multiprocessing"}
FORBIDDEN_ATTRS = {"kill", "terminate", "suspend", "send_signal", "nice", "ionice",
                   "cpu_affinity", "rlimit", "system", "popen", "remove", "rmdir", "chmod",
                   "chown", "setpriority", "sched_setaffinity"}
WRITE_ALLOWED = {"export/atomic.py"}  # kullanıcı isteğiyle rapor yazan tek modül


def _python_files():
    return sorted(p for p in PACKAGE.rglob("*.py"))


def _imports(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            yield node.module.split(".")[0]


def test_no_dangerous_modules_are_imported():
    for path in _python_files():
        found = set(_imports(ast.parse(path.read_text(encoding="utf-8")))) & FORBIDDEN_MODULES
        assert not found, f"{path.relative_to(PACKAGE)}: {found}"


def test_no_process_control_or_destructive_calls():
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                assert node.func.attr not in FORBIDDEN_ATTRS, \
                    f"{path.relative_to(PACKAGE)}:{node.lineno} .{node.func.attr}()"


def test_open_calls_are_read_only_outside_export():
    for path in _python_files():
        # as_posix(): Windows'ta da "export/atomic.py" biçiminde karşılaştırılsın
        rel = path.relative_to(PACKAGE).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and getattr(node.func, "id", None) == "open"):
                continue
            mode = node.args[1] if len(node.args) > 1 else next(
                (k.value for k in node.keywords if k.arg == "mode"), None)
            mode_value = "r" if mode is None else getattr(mode, "value", None)
            assert mode_value in ("r", "rb"), f"{rel}:{node.lineno} open(mode={mode_value!r})"
        if rel not in WRITE_ALLOWED:
            source = path.read_text(encoding="utf-8")
            assert "os.fdopen" not in source and "mkstemp" not in source, rel


def test_no_privilege_escalation_strings():
    for path in _python_files():
        text = path.read_text(encoding="utf-8")
        for word in ("sudo ", "pkexec", "setuid", "/etc/sudoers", "modprobe", "insmod",
                     "sysctl -w", "echo > /proc", "/proc/sys/vm/drop_caches"):
            assert word not in text, f"{path.relative_to(PACKAGE)}: {word}"


# ----------------------------------------------------------------------------- genişletilmiş denetim
# Yukarıdaki denetimler yalnızca çıplak open() kipine ve öznitelik çağrılarına bakıyordu;
# Path.write_text(), io.open(..., "w"), "from os import kill; kill(...)", getattr ile
# çağrı veya PySide6.QtNetwork gibi yollar fark edilmiyordu.
EXTRA_FORBIDDEN_CALLS = {"killpg", "execv", "execve", "execvp", "execvpe", "execl", "execlp",
                         "spawnl", "spawnv", "spawnvp", "posix_spawn", "startDetached",
                         "setrlimit", "prlimit", "sched_setscheduler"}
EXTRA_FORBIDDEN_MODULES = {"urllib3", "httpx", "aiohttp", "telnetlib", "xmlrpc", "webbrowser",
                           "paramiko"}
FORBIDDEN_DOTTED_MODULES = {"PySide6.QtNetwork", "PySide6.QtWebSockets",
                            "PySide6.QtWebEngineCore"}
# Dosya sistemini değiştiren yardımcılar: yalnızca kullanıcı isteğiyle rapor yazan modülde
WRITE_HELPERS = {"write_text", "write_bytes", "touch", "mkdir", "makedirs", "unlink", "rmtree",
                 "rename", "symlink_to", "truncate", "mkstemp", "mkdtemp", "NamedTemporaryFile",
                 "TemporaryDirectory"}
MODULE_OPENERS = {"io", "codecs", "builtins"}  # modül.open(dosya, kip)


def _call_name(func):
    return func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)


def _constant(node):
    return node.value if isinstance(node, ast.Constant) else None


def safety_violations(source, write_allowed=False):
    """Kaynak kodda salt-okunur ilkeyi çiğneyen kullanımlar ("satır: açıklama")."""
    calls = FORBIDDEN_ATTRS | EXTRA_FORBIDDEN_CALLS
    modules = FORBIDDEN_MODULES | EXTRA_FORBIDDEN_MODULES
    names = calls | (set() if write_allowed else WRITE_HELPERS)
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in FORBIDDEN_DOTTED_MODULES or alias.name.split(".")[0] in modules:
                    found.append(f"{node.lineno}: yasak modül {alias.name}")
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            if node.module in FORBIDDEN_DOTTED_MODULES or node.module.split(".")[0] in modules:
                found.append(f"{node.lineno}: yasak modül {node.module}")
            for alias in node.names:
                if f"{node.module}.{alias.name}" in FORBIDDEN_DOTTED_MODULES:
                    found.append(f"{node.lineno}: yasak modül {node.module}.{alias.name}")
                if alias.name in names:
                    found.append(f"{node.lineno}: yasak ad içe aktarılıyor: {alias.name}")
        elif (isinstance(node, ast.Name) and node.id == "QSettings") or \
                (isinstance(node, ast.Attribute) and node.attr == "QSettings"):
            found.append(f"{node.lineno}: QSettings (kalıcı ayar yazımı)")
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node.func)
        if name in names:
            found.append(f"{node.lineno}: {name}()")
        inner = node.func if isinstance(node.func, ast.Call) else None
        if inner is not None and _call_name(inner.func) == "getattr" and len(inner.args) > 1 \
                and _constant(inner.args[1]) in names:  # getattr(p, "kill")() çağrısı
            found.append(f"{node.lineno}: getattr(..., {_constant(inner.args[1])!r})()")
        if name in ("__import__", "import_module") and node.args:
            target = _constant(node.args[0])
            if isinstance(target, str) and (target.split(".")[0] in modules
                                            or target in FORBIDDEN_DOTTED_MODULES):
                found.append(f"{node.lineno}: dinamik içe aktarma {target}")
        if name == "open":
            receiver = node.func.value if isinstance(node.func, ast.Attribute) else None
            if isinstance(receiver, ast.Name) and receiver.id == "os":
                if not write_allowed:
                    found.append(f"{node.lineno}: os.open()")
                continue
            module_style = receiver is None or (isinstance(receiver, ast.Name)
                                                and receiver.id in MODULE_OPENERS)
            position = 1 if module_style else 0  # Path(...).open(kip)
            mode = node.args[position] if len(node.args) > position else next(
                (k.value for k in node.keywords if k.arg == "mode"), None)
            value = "r" if mode is None else _constant(mode)
            if value not in ("r", "rb", "rt"):
                found.append(f"{node.lineno}: open(kip={value!r})")
    return found


def test_package_has_no_safety_violations():
    for path in _python_files():
        rel = path.relative_to(PACKAGE).as_posix()
        assert safety_violations(path.read_text(encoding="utf-8"), rel in WRITE_ALLOWED) == [], rel


@pytest.mark.parametrize("code", [
    "from os import kill\nkill(1, 9)",
    "import os\nos.killpg(1, 15)",
    "getattr(proc, 'kill')()",
    "from pathlib import Path\nPath('/proc/sys/vm/swappiness').write_text('10')",
    "import io\nio.open('/sys/block/sda/queue/scheduler', 'w')",
    "from pathlib import Path\nPath('x').open('w')",
    "import os\nos.open('/proc/sys/vm/swappiness', 1)",
    "open('/etc/x', mode='a')",
    "from PySide6.QtNetwork import QNetworkAccessManager",
    "from PySide6 import QtNetwork",
    "__import__('subprocess')",
    "import importlib\nimportlib.import_module('socket')",
    "from PySide6.QtCore import QSettings\nQSettings('a', 'b').setValue('k', 1)",
    "import tempfile\ntempfile.NamedTemporaryFile(delete=False)",
    "import os\nos.makedirs('/tmp/x')",
])
def test_safety_checker_detects_violation(code):
    assert safety_violations(code), code


@pytest.mark.parametrize("code", [
    "open('/proc/stat')",
    "open(path, 'rb')",
    "from pathlib import Path\nPath(p).open()",
    "import io\nio.open(p, encoding='utf-8')",
    "text.replace('a', 'b')",
    "import os\ngetattr(os, 'geteuid', None)",
])
def test_safety_checker_accepts_read_only_code(code):
    assert safety_violations(code) == []


def test_root_warning_is_informational(monkeypatch):
    monkeypatch.setattr(os, "geteuid", lambda: 0, raising=False)
    buf = io.StringIO()
    cli.warn_if_root(buf)
    assert "root yetkisi gerektirmez" in buf.getvalue()


def test_synthetic_headless_output_is_clearly_labelled(capsys):
    cli.main(["--headless", "--synthetic", "normal", "--speed", "0", "--ticks", "2"])
    out = capsys.readouterr().out
    assert "DEMO / SENTETİK VERİ" in out
    assert all(line.startswith("[SENTETİK]") for line in out.splitlines() if "CPU" in line
               and "RAM" in line)


def test_methodology_lists_sources_rules_and_current_thresholds():
    from dataclasses import replace

    from pardusinsight.analysis.methodology import methodology_html
    from pardusinsight.config import AppSettings

    settings = AppSettings()
    settings = replace(settings, analysis=replace(settings.analysis, cpu_high_pct=91.0))
    html = methodology_html(settings)
    for text in ("/proc/stat", "/proc/vmstat", "/proc/diskstats", "Bellek baskısı olasılığı",
                 "Kalıcı CPU yoğunluğu", "Disk G/Ç etkinliği anomalisi", "%91",
                 "kesin arıza tanısı değildir"):
        assert text in html, text


def test_replay_with_different_interval_still_finds_alerts(capsys):
    scenario = Path(__file__).resolve().parents[1] / "scenarios" / "demo.json"
    assert cli.main(["--headless", "--replay", str(scenario), "--interval", "1"]) == 0
    out = capsys.readouterr().out
    for title in ("Kalıcı CPU yoğunluğu", "Bellek baskısı olasılığı",
                  "Disk G/Ç etkinliği anomalisi"):
        assert title in out


# ----------------------------------------------------------------------------- dışa aktarma ve ayarlar
def test_missing_export_folder_is_reported_before_monitoring(tmp_path, capsys):
    target = tmp_path / "yok" / "o.csv"
    code = cli.main(["--headless", "--synthetic", "normal", "--speed", "0", "--ticks", "5",
                     "--quiet", "--export-csv", str(target)])
    captured = capsys.readouterr()
    assert code == 2 and "Dışa aktarma klasörü yok" in captured.err
    assert "tur" not in captured.out  # izleme hiç başlamadı


def test_failed_csv_export_still_writes_json_and_returns_error(tmp_path, capsys, monkeypatch):
    def broken(*_args, **_kwargs):
        raise PermissionError(13, "Erişim engellendi")

    monkeypatch.setattr(cli, "write_samples_csv", broken)
    json_path = tmp_path / "r.json"
    code = cli.main(["--headless", "--synthetic", "normal", "--speed", "0", "--ticks", "5",
                     "--quiet", "--export-csv", str(tmp_path / "o.csv"),
                     "--export-json", str(json_path)])
    assert code == 1 and json_path.exists()
    assert "CSV yazılamadı" in capsys.readouterr().err


def test_long_headless_export_keeps_whole_run(tmp_path, capsys):
    json_path = tmp_path / "uzun.json"
    # 1000 örnek × 2 sn = 33 dk: varsayılan 30 dk'lık tampon ilk kısmı atardı
    assert cli.main(["--headless", "--synthetic", "normal", "--speed", "0", "--ticks", "1000",
                     "--quiet", "--export-json", str(json_path)]) == 0
    assert "Geçmiş tamponu" in capsys.readouterr().err
    assert len(load_json_report(str(json_path)).samples) == 1000


def test_bad_config_types_exit_cleanly(tmp_path, capsys):
    path = tmp_path / "ayar.json"
    for content in ("[]", '{"analysis": {"cpu_high_pct": "90"}}', '{"top_n": 5.5}'):
        path.write_text(content, encoding="utf-8")
        assert cli.main(["--headless", "--synthetic", "normal", "--config", str(path)]) == 2
        assert "Ayarlar geçersiz" in capsys.readouterr().err


def test_unknown_config_key_is_warned(tmp_path, capsys):
    path = tmp_path / "ayar.json"
    path.write_text('{"analysis": {"cpu_hgh_pct": 50}}', encoding="utf-8")
    assert cli.main(["--headless", "--synthetic", "normal", "--speed", "0", "--ticks", "2",
                     "--quiet", "--config", str(path)]) == 0
    assert "analysis.cpu_hgh_pct" in capsys.readouterr().err


def test_headless_loop_does_not_burst_after_a_stall(monkeypatch):
    from types import SimpleNamespace

    from pardusinsight.core.service import build_synthetic_service

    clock = [0.0]
    sleeps = []
    monkeypatch.setattr(cli.time, "monotonic", lambda: clock[0])

    def fake_sleep(seconds):
        sleeps.append(seconds)
        clock[0] += seconds

    monkeypatch.setattr(cli.time, "sleep", fake_sleep)
    service = build_synthetic_service("normal", loop=True, start_time=0.0)
    real_tick = service.tick
    calls = [0]

    def tick():
        calls[0] += 1
        if calls[0] == 3:
            clock[0] += 20.0  # tek bir tur 20 sn takıldı
        return real_tick()

    service.tick = tick
    args = SimpleNamespace(synthetic=None, speed=1.0, quiet=True, ticks=12, duration=None,
                           export_csv=None, export_json=None)
    assert cli.run_headless(service, args, out=io.StringIO()) == 0
    after = sleeps[2:]  # takılan turdan sonraki beklemeler
    # Gecikmiş tek tur hemen çalışır, sonra düzenli aralık sürer; 10 turluk yığılma olmaz
    assert after[0] == 0.0 and after[1:] and all(s == pytest.approx(2.0) for s in after[1:])


def test_output_survives_console_encoding_without_symbols(monkeypatch):
    raw = io.BytesIO()
    stream = io.TextIOWrapper(raw, encoding="cp1254", errors="strict")
    monkeypatch.setattr("sys.stdout", stream)
    code = cli.main(["--headless", "--synthetic", "cpu", "--speed", "0", "--ticks", "130",
                     "--quiet"])
    stream.flush()
    assert code == 0
    assert "Kalıcı CPU yoğunluğu".encode("cp1254") in raw.getvalue()
