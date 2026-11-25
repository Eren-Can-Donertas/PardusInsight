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


def test_root_warning_is_informational(monkeypatch):
    monkeypatch.setattr(os, "geteuid", lambda: 0, raising=False)
    buf = io.StringIO()
    cli.warn_if_root(buf)
    assert "root yetkisi gerektirmez" in buf.getvalue()


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
