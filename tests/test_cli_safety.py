"""Komut satırı modu ve güvenlik sınırlarının (salt-okunur çalışma) denetimi."""
import ast
import io
import os
from pathlib import Path


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
        rel = str(path.relative_to(PACKAGE))
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
