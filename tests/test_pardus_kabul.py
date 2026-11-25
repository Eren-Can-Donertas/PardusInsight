"""scripts/pardus_kabul.py (Pardus kabul ve doğrulama betiği) testleri.

Linux'a özgü maddeler gerçek Pardus VM'de ve CI'daki Pardus kapsayıcısında çalışır. Burada
saf ayrıştırıcılar, rapor üretimi, gizlilik süzgeci, platformdan bağımsız maddeler, uçtan
uca akış ve (sahte komut çıktılarıyla) Linux dallarının karar mantığı denetlenir.
"""
import json
import os
import re
import sys
import tempfile
import types
from collections import namedtuple
from dataclasses import dataclass
from pathlib import Path

import pytest

from pardusinsight.core.service import build_synthetic_service

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import pardus_kabul as kabul  # noqa: E402

MIB = 1024 * 1024
LINUX_ONLY = ("2.1", "2.2", "2.3", "2.4", "2.5", "3.1", "3.2", "3.3", "3.4")


def make_ctx(*argv):
    return kabul.Context(kabul.build_parser().parse_args(list(argv)))


@pytest.fixture
def ctx():
    context = make_ctx()
    yield context
    context.cleanup()


def synthetic_samples(scenario, ticks):
    service = build_synthetic_service(scenario, loop=False, start_time=kabul.DEMO_START)
    for _ in range(ticks):
        service.tick()
    return service.history.snapshot()


def report_rows(text):
    """Rapor tablolarındaki madde satırları: {madde no: satır}."""
    rows = {}
    for line in text.splitlines():
        match = re.match(r"\| (\d+(?:\.\d+)?[a-z]?) \| ", line)
        if match:
            rows[match.group(1)] = line
    return rows


def section(text, heading):
    body = text.split(heading + "\n", 1)[1]
    return body.split("\n## ", 1)[0]


# ----------------------------------------------------------------------------- örnek çıktılar
APT_POLICY = """\
python3-pyside6.qtwidgets:
  Installed: (none)
  Candidate: 6.8.2.1-1
  Version table:
     6.8.2.1-1 500
        500 http://depo.pardus.org.tr/pardus yirmibes/main amd64 Packages
python3-psutil:
  Installed: 7.0.0-2
  Candidate: 7.0.0-2
  Version table:
 *** 7.0.0-2 500
        500 http://depo.pardus.org.tr/pardus yirmibes/main amd64 Packages
        100 /var/lib/dpkg/status
python3-olmayan-aday:
  Installed: (none)
  Candidate: (none)
  Version table:
"""

# docs/TEST_RAPORU.md bölüm 2'deki gerçek doğrulama tablosu
VALIDATE_OUTPUT = """\
Ortam: Ubuntu 24.04.4 LTS · çekirdek 7.0.0-42-generic · Python 3.12.3 · psutil 7.2.2 · \
16 mantıksal CPU

| # | MemTotal eşit | MemAvailable farkı (MiB) | SwapTotal eşit | Swap kullanılan farkı (MiB) | \
CPU user farkı (sn) | CPU % (/proc) | CPU % (psutil) | Disk okuma farkı (MiB) |
|---|---|---|---|---|---|---|---|---|
| 1 | evet | 0.00 | evet | 0.00 | 0.00 | 20.1 | 20.2 | 0.00 |
| 2 | evet | 0.00 | evet | 0.00 | 0.00 | 16.7 | 16.8 | 0.00 |
| 3 | evet | 0.00 | evet | 0.00 | 0.00 | 11.5 | 11.4 | 0.00 |
| 4 | evet | 0.00 | evet | 0.00 | 0.00 | 14.1 | 14.1 | 0.00 |
| 5 | evet | 0.00 | evet | 0.00 | 0.00 | 16.8 | 16.8 | 0.00 |
| 6 | evet | 0.00 | evet | 0.00 | 0.00 | 18.3 | 18.3 | 0.00 |
| 7 | evet | 0.00 | evet | 0.00 | 0.00 | 16.1 | 16.2 | 0.00 |
| 8 | evet | 1.27 | evet | 0.00 | 0.00 | 15.3 | 15.2 | 0.00 |
| 9 | evet | 0.00 | evet | 0.00 | 0.00 | 16.2 | 16.2 | 0.00 |
| 10 | evet | 0.00 | evet | 0.00 | 0.00 | 14.3 | 14.4 | 0.00 |

En büyük farklar: MemAvailable 1.27 MiB, swap 0.00 MiB, CPU user 0.00 sn, CPU % 0.1 puan.
"""

PERF_HEADLESS = """\

== GUI'siz izleme ==
Süre: 60.0 sn · tur sayısı: 30
Ortalama CPU: %2.07 (tek çekirdek = %100) · %0.13 (toplam 16 çekirdek kapasitesine göre)
RSS: başlangıç 18.9 MiB · en yüksek 19.3 MiB · son 19.3 MiB
Tur süresi: medyan 38.5 ms · en yüksek 59.8 ms
Tampondaki örnek: 30
Hedef CPU < %5 (tek çekirdek): SAĞLANDI · Hedef RAM < 200 MiB: SAĞLANDI
"""

PERF_GUI = """\

== GUI + arka plan örnekleme ==
Süre: 60.0 sn · tur sayısı: 30
Ortalama CPU: %4.65 (tek çekirdek = %100) · %0.29 (toplam 16 çekirdek kapasitesine göre)
RSS: başlangıç 80.2 MiB · en yüksek 81.3 MiB · son 81.3 MiB
Tur süresi: medyan 47.7 ms · en yüksek 117.3 ms
Olay döngüsü kalp atışı (20 ms): en uzun aralık 33 ms, 100 ms'yi aşan 0/3022 aralık → YANIT VERİYOR
Hedef CPU < %5 (tek çekirdek): SAĞLANDI · Hedef RAM < 200 MiB: SAĞLANDI
"""


# ----------------------------------------------------------------------------- ayrıştırıcılar
def test_parse_apt_policy_candidates():
    result = kabul.parse_apt_policy(APT_POLICY)
    assert result == {"python3-pyside6.qtwidgets": "6.8.2.1-1", "python3-psutil": "7.0.0-2",
                      "python3-olmayan-aday": None}
    assert result.get("python3-depoda-yok") is None  # bilinmeyen paket çıktıda hiç yer almaz
    assert kabul.parse_apt_policy("N: Unable to locate package x\n") == {}
    turkish = "python3-psutil:\n  Kurulu: (hiçbiri)\n  Aday: 7.0.0-2\n"
    assert kabul.parse_apt_policy(turkish) == {"python3-psutil": "7.0.0-2"}


def test_parse_validate_table_from_test_report():
    rows = kabul.parse_validate_table(VALIDATE_OUTPUT)
    assert len(rows) == 10 and rows[0]["#"] == "1" and rows[-1]["#"] == "10"
    assert rows[7]["MemAvailable farkı (MiB)"] == "1.27" and rows[2]["CPU % (psutil)"] == "11.4"
    ok, detail = kabul.evaluate_validate_rows(rows)
    assert ok, detail
    assert "10 satır" in detail and "her satırda eşit" in detail
    assert "en büyük CPU % farkı 0,1 puan" in detail and "1,27 MiB" in detail


def test_validate_table_failures_are_reported():
    lines = VALIDATE_OUTPUT.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("| 3 |"):
            lines[i] = line.replace("| 3 | evet |", "| 3 | HAYIR |")
        if line.startswith("| 5 |"):
            lines[i] = line.replace("| 16.8 | 16.8 |", "| 16.8 | 19.9 |")
    ok, detail = kabul.evaluate_validate_rows(kabul.parse_validate_table("\n".join(lines)))
    assert not ok
    assert "#3: MemTotal eşit değil" in detail and "#5: CPU % farkı 3,1 puan" in detail
    short = "\n".join(VALIDATE_OUTPUT.splitlines()[:9])  # yalnızca 5 satır
    ok, detail = kabul.evaluate_validate_rows(kabul.parse_validate_table(short))
    assert not ok and "en az 10 gerekli" in detail
    assert kabul.evaluate_validate_rows([]) == (False, "doğrulama tablosu bulunamadı")


def test_parse_perf_pass_fail_and_unmeasured():
    headless = kabul.parse_perf(PERF_HEADLESS)
    assert headless == {"cpu": "SAĞLANDI", "ram": "SAĞLANDI", "gui": None, "avg_cpu": "2.07",
                        "peak_rss_mib": "19.3"}
    status, detail = kabul.perf_status(headless)
    assert status == kabul.GECTI and "ortalama CPU %2,07" in detail and "19,3 MiB" in detail
    gui = kabul.parse_perf(PERF_GUI)
    assert gui["gui"] == "YANIT VERİYOR" and gui["peak_rss_mib"] == "81.3"
    assert kabul.perf_status(gui, gui=True)[0] == kabul.GECTI

    slow = PERF_HEADLESS.replace("(tek çekirdek): SAĞLANDI", "(tek çekirdek): SAĞLANMADI")
    assert kabul.parse_perf(slow)["cpu"] == "SAĞLANMADI"
    assert kabul.perf_status(kabul.parse_perf(slow))[0] == kabul.KALDI
    unmeasured = PERF_HEADLESS.replace("200 MiB: SAĞLANDI", "200 MiB: ölçülemedi")
    assert kabul.parse_perf(unmeasured)["ram"] == "ölçülemedi"
    assert kabul.perf_status(kabul.parse_perf(unmeasured))[0] == kabul.KALDI
    frozen = PERF_GUI.replace("YANIT VERİYOR", "DONMA ŞÜPHESİ")
    assert kabul.perf_status(kabul.parse_perf(frozen), gui=True)[0] == kabul.KALDI
    status, detail = kabul.perf_status(kabul.parse_perf("Traceback ..."))
    assert status == kabul.KALDI and "satır bulunamadı" in detail


def test_pytest_summary_and_status():
    ok = kabul.CommandResult(0, "..........\n10 passed in 1.20s\n")
    assert kabul.pytest_status(ok) == (kabul.GECTI, "10 passed")
    partly = kabul.CommandResult(0, "....s\nSKIPPED [1] tests/x.py:3: disk yok\n"
                                    "4 passed, 1 skipped in 2.10s\n")
    assert kabul.pytest_status(partly) == (kabul.GECTI, "4 passed, 1 skipped")
    skipped = kabul.CommandResult(0, "sssss\n5 skipped in 0.04s\n")
    assert kabul.pytest_status(skipped)[0] == kabul.ATLANDI
    failed = kabul.CommandResult(1, "F....\n1 failed, 4 passed, 2 errors in 0.5s\n")
    assert kabul.pytest_counts(failed.output) == {"failed": 1, "passed": 4, "error": 2}
    assert kabul.pytest_status(failed) == (kabul.KALDI,
                                           "pytest çıkış kodu 1: 1 failed, 4 passed, 2 error")
    assert kabul.pytest_status(kabul.CommandResult(5, "no tests ran in 0.01s"))[0] == kabul.KALDI
    timeout = kabul.CommandResult(None, "", 600.0, timed_out=True)
    assert kabul.pytest_status(timeout) == (kabul.KALDI, "pytest zaman aşımı (600 sn)")


def test_parse_free_and_os_release():
    free = ("               total        used        free      shared  buff/cache   available\n"
            "Mem:      8148172800  2147483648  1073741824   104857600  4927946752  5704253440\n"
            "Swap:     2147479552           0  2147479552\n")
    assert kabul.parse_free(free) == {"total": 8148172800, "available": 5704253440}
    assert kabul.parse_free("") is None
    release = 'PRETTY_NAME="Pardus 25.1"\nNAME="Pardus"\nVERSION_ID="25.1"\n# yorum\nID=pardus\n'
    assert kabul.parse_os_release(release) == {"PRETTY_NAME": "Pardus 25.1", "NAME": "Pardus",
                                               "VERSION_ID": "25.1", "ID": "pardus"}


def test_desktop_entry_problems(tmp_path):
    exe = Path(sys.executable).as_posix()
    good = (f"[Desktop Entry]\nType=Application\nName=PardusInsight\nPath={tmp_path.as_posix()}\n"
            f'Exec="{exe}" -m pardusinsight\n')
    assert kabul.desktop_entry_problems(good) == []
    moved = (f"[Desktop Entry]\nPath={(tmp_path / 'tasindi').as_posix()}\n"
             f'Exec="{(tmp_path / "yok" / "python3").as_posix()}" -m pardusinsight\n')
    problems = kabul.desktop_entry_problems(moved)
    assert len(problems) == 2
    assert "Exec programı bulunamadı" in problems[0] and "Path= dizini yok" in problems[1]
    assert kabul.desktop_entry_problems("Name=x\n") == ["[Desktop Entry] bölümü yok"]


# ----------------------------------------------------------------------------- gizlilik
def test_scrub_hides_user_host_and_home(monkeypatch):
    monkeypatch.setattr(kabul.getpass, "getuser", lambda: "ogrenci")
    monkeypatch.setattr(kabul.platform, "node", lambda: "pardus-vm")
    monkeypatch.setenv("HOME", "/home/ogrenci")
    monkeypatch.setattr(kabul.os.path, "expanduser",
                        lambda path: path.replace("~", "/home/ogrenci", 1))
    text = ("rootdir: /home/ogrenci/PardusInsight\n"
            "ogrenci@pardus-vm:~$ ls /home/ogrenci2 ogrenciler")
    assert kabul.scrub(text) == ("rootdir: ~/PardusInsight\n"
                                 "<kullanıcı>@<makine>:~$ ls /home/ogrenci2 ogrenciler")
    report = kabul.render_markdown([kabul.Check("1.4", "Menü", kabul.GECTI,
                                                "bulundu: /home/ogrenci/.local/share/x",
                                                cikti="ogrenci@pardus-vm")])
    assert "ogrenci" not in report.replace("ogrenciler", "") and "pardus-vm" not in report
    assert "bulundu: ~/.local/share/x" in report


def test_scrub_keeps_short_generic_and_embedded_names(monkeypatch):
    monkeypatch.setattr(kabul.getpass, "getuser", lambda: "can")
    monkeypatch.setattr(kabul.platform, "node", lambda: "pardus")
    text = "canlı izleme can@pardus depo.pardus.org.tr"
    assert kabul.scrub(text) == "canlı izleme <kullanıcı>@pardus depo.pardus.org.tr"
    monkeypatch.setattr(kabul.getpass, "getuser", lambda: "ab")
    assert kabul.scrub("ab cd") == "ab cd"


# ----------------------------------------------------------------------------- rapor
def test_render_markdown_tables_summary_manual_list_and_appendix():
    checks = [
        kabul.Check("1.1", "Paketler", kabul.GECTI, "a | b", cikti="satır 1\n``` içeride"),
        kabul.Check("1.4b", "Menü", kabul.MANUEL, "Menüyü açın\nve bakın"),
        kabul.Check("2.2", "Canlı", kabul.KALDI, "çıktıda \"okunamadı\" var"),
        kabul.Check("3.1", "Doğrulama", kabul.ATLANDI, "yalnızca Linux"),
        kabul.Check("3.4", "PSI", kabul.BILGI, "PSI var"),
        kabul.Check("6", "Kalibrasyon", kabul.BILGI, "öneri yok",
                    cikti="## Eşik kalibrasyonu\n\n| a | b |", cikti_md=True),
    ]
    text = kabul.render_markdown(checks, [("Çekirdek", "6.12.0-1-amd64")],
                                 command="python3 scripts/pardus_kabul.py --hizli", duration_s=75)
    assert text.startswith("# Pardus Kabul ve Doğrulama Sonuçları\n")
    assert "Komut: `python3 scripts/pardus_kabul.py --hizli` · süre: 1 dk 15 sn" in text
    assert "| Çekirdek | 6.12.0-1-amd64 |" in section(text, "## Ortam")
    rows = report_rows(text)
    assert rows["1.1"] == "| 1.1 | Paketler | ✅ GEÇTİ | a \\| b |"
    assert rows["1.4b"] == "| 1.4b | Menü | ✋ MANUEL | Menüyü açın<br>ve bakın |"
    assert "❌ KALDI" in rows["2.2"] and "⏭ ATLANDI" in rows["3.1"] and "ℹ BİLGİ" in rows["3.4"]
    for number, title in kabul.GROUPS:
        assert f"## {number}. {title}\n" in text
    assert "_Bu bölümdeki kontroller çalıştırılmadı._" in section(text, "## 4. Performans")

    summary = section(text, "## Özet")
    for label, count in (("✅ GEÇTİ", 1), ("❌ KALDI", 1), ("⏭ ATLANDI", 1), ("✋ MANUEL", 1),
                         ("ℹ BİLGİ", 2)):
        assert f"| {label} | {count} |" in summary
    assert "| **Toplam** | **6** |" in summary and "1 madde KALDI (2.2)" in summary
    manual = section(text, "## Elle yapılacaklar")
    assert "1. **1.4b – Menü:** Menüyü açın ve bakın" in manual and "2." not in manual
    appendix = text.split("## Ekler\n", 1)[1]
    assert "### 1.1 – Paketler\n\n````text\nsatır 1\n``` içeride\n````" in appendix
    assert "## Eşik kalibrasyonu\n\n| a | b |" in appendix and "### 6 " not in appendix

    partial = kabul.render_markdown(checks[:1], interrupted=True)
    assert "Ctrl+C ile yarıda kesildi" in partial and "(çıkış kodu 130)" in partial


# ----------------------------------------------------------------------------- maddeler
@pytest.mark.parametrize("name", ["check_5_1", "check_5_2", "check_5_3", "check_5_4"])
def test_platform_independent_checks_pass_on_any_os(ctx, name):
    number = name[len("check_"):].replace("_", ".")
    results = kabul.safe_run(number, getattr(kabul, name), ctx)
    automatic = [c for c in results if c.durum != kabul.MANUEL]
    assert automatic and all(c.durum == kabul.GECTI for c in automatic), results
    if number == "5.2":
        assert "cpu_spikes.json: uyarı yok" in results[0].ayrinti
        assert "memory_low_quiet.json: uyarı yok" in results[0].ayrinti
    if number == "5.3":
        assert [c.no for c in results] == ["5.3", "5.3b"] and results[1].durum == kabul.MANUEL
        assert "Kalıcı CPU yoğunluğu" in results[0].ayrinti


def test_safe_run_turns_unexpected_errors_into_kaldi():
    def broken(_ctx):
        raise ValueError("bozuk veri")

    [check] = kabul.safe_run("5.1", broken, None)
    assert (check.no, check.baslik, check.durum, check.ayrinti) == (
        "5.1", kabul.TITLES["5.1"], kabul.KALDI, "beklenmeyen hata: ValueError: bozuk veri")
    [check] = kabul.safe_run("5.1", lambda _ctx: None, None)
    assert check.durum == kabul.KALDI and "geçersiz sonuç" in check.ayrinti

    def interrupted(_ctx):
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        kabul.safe_run("5.1", interrupted, None)


@pytest.fixture
def simulated_linux(monkeypatch):
    """Linux dalları için: is_linux() doğru, komutlar kaydedilir ve sahte çıktı döner."""
    state = {"calls": [], "responder": lambda cmd, cwd, env: kabul.CommandResult(0, "")}

    def fake_run(cmd, timeout, cwd=None, env=None):
        state["calls"].append({"cmd": list(cmd), "cwd": cwd, "env": env})
        return state["responder"](list(cmd), cwd, env)

    monkeypatch.setattr(kabul, "is_linux", lambda: True)
    monkeypatch.setattr(kabul, "run_command", fake_run)
    return state


def test_apt_policy_check(simulated_linux, ctx, monkeypatch):
    monkeypatch.setattr(kabul.shutil, "which",
                        lambda name: "/usr/bin/apt-cache" if name == "apt-cache" else None)
    simulated_linux["responder"] = lambda cmd, cwd, env: kabul.CommandResult(0, APT_POLICY)
    check = kabul.check_1_1(ctx)
    assert check.durum == kabul.GECTI and "6.8.2.1-1" in check.ayrinti and check.cikti == APT_POLICY
    call = simulated_linux["calls"][-1]
    assert call["cmd"] == ["/usr/bin/apt-cache", "policy", *kabul.APT_PACKAGES]
    assert call["env"]["LC_ALL"] == "C.UTF-8"  # İngilizce "Candidate:" satırı için
    missing = APT_POLICY.replace("Candidate: 7.0.0-2", "Candidate: (none)")
    simulated_linux["responder"] = lambda cmd, cwd, env: kabul.CommandResult(0, missing)
    check = kabul.check_1_1(ctx)
    assert check.durum == kabul.KALDI and "adayı olmayan: python3-psutil" in check.ayrinti
    monkeypatch.setattr(kabul.shutil, "which", lambda name: None)
    assert kabul.check_1_1(ctx).durum == kabul.ATLANDI


def test_desktop_entry_check(ctx, tmp_path, monkeypatch):
    desktop = tmp_path / "pardusinsight.desktop"
    monkeypatch.setattr(kabul, "desktop_candidates", lambda: [str(desktop)])
    monkeypatch.setattr(kabul.shutil, "which", lambda name: None)  # desktop-file-validate yok
    main, manual = kabul.check_1_4(ctx)
    assert main.durum == kabul.MANUEL and "install_user.sh" in main.ayrinti
    assert (manual.no, manual.durum) == ("1.4b", kabul.MANUEL)
    exe = Path(sys.executable).as_posix()
    desktop.write_text(f"[Desktop Entry]\nName=PardusInsight\nPath={tmp_path.as_posix()}\n"
                       f'Exec="{exe}" -m pardusinsight\n', encoding="utf-8")
    main, _manual = kabul.check_1_4(ctx)
    assert main.durum == kabul.GECTI and "yalnızca varlık" in main.ayrinti
    desktop.write_text(f"[Desktop Entry]\nPath={(tmp_path / 'tasindi').as_posix()}\n"
                       f'Exec="{exe}" -m pardusinsight\n', encoding="utf-8")
    main, _manual = kabul.check_1_4(ctx)
    assert main.durum == kabul.KALDI and "Path= dizini yok" in main.ayrinti


def test_root_check_reports_group_without_user_name(simulated_linux, ctx, monkeypatch):
    monkeypatch.setattr(kabul.getpass, "getuser", lambda: "ogrenci")
    monkeypatch.setattr(kabul.os, "geteuid", lambda: 1000, raising=False)
    monkeypatch.setattr(kabul, "admin_group", lambda: "sudo")
    check = kabul.check_2_1(ctx)
    assert check.durum == kabul.GECTI and "'sudo' grubunda" in check.ayrinti
    assert "ogrenci" not in check.ayrinti
    monkeypatch.setattr(kabul, "admin_group", lambda: "")
    assert "grubunda değil" in kabul.check_2_1(ctx).ayrinti
    monkeypatch.setattr(kabul.os, "geteuid", lambda: 0, raising=False)
    assert kabul.check_2_1(ctx).durum == kabul.KALDI


def test_live_headless_check_flags_proc_errors(simulated_linux, ctx):
    good = ("PardusInsight 0.1.0 — kaynak: linux, aralık 1.0 sn. Durdurmak için Ctrl+C.\n"
            "21:00:01  CPU     %3,1 | RAM  %41,0 (kullanılabilir 2,3 GiB) | Swap %0,0\n")
    simulated_linux["responder"] = lambda cmd, cwd, env: kabul.CommandResult(0, good)
    check = kabul.check_2_2(ctx)
    assert check.durum == kabul.GECTI and "1 ölçüm satırı" in check.ayrinti
    call = simulated_linux["calls"][-1]
    assert call["cmd"][1:] == ["-m", "pardusinsight", "--headless", "--ticks", "5", "--interval",
                               "1"]
    assert call["env"]["PYTHONPATH"].split(os.pathsep)[0] == kabul.ROOT
    bad = good + "  ! Disk (/proc/diskstats): /proc okunamadı (PermissionError); psutil yedeği\n"
    simulated_linux["responder"] = lambda cmd, cwd, env: kabul.CommandResult(0, bad)
    check = kabul.check_2_2(ctx)
    assert check.durum == kabul.KALDI and "\"okunamadı\"" in check.ayrinti
    simulated_linux["responder"] = lambda cmd, cwd, env: kabul.CommandResult(None, "", 90.0,
                                                                             timed_out=True)
    assert kabul.check_2_2(ctx).durum == kabul.KALDI


def test_home_check_names_only_pardus_entries(simulated_linux, ctx, tmp_path, monkeypatch):
    home = tmp_path / "ev"
    (home / ".config").mkdir(parents=True)
    monkeypatch.setattr(kabul.os.path, "expanduser", lambda path: path.replace("~", str(home), 1))

    def leaves(name):
        def responder(cmd, cwd, env):
            assert cwd == str(home) and "--export-json" not in cmd and "--export-csv" not in cmd
            (home / ".config" / name).write_text("x", encoding="utf-8")
            return kabul.CommandResult(0, "")
        return responder

    simulated_linux["responder"] = leaves("tarayici-onbellegi")
    check = kabul.check_2_5(ctx)
    assert check.durum == kabul.GECTI and "1 yeni giriş sayıldı" in check.ayrinti
    assert "tarayici-onbellegi" not in check.ayrinti  # başka uygulamaların dosya adları yazılmaz
    simulated_linux["responder"] = leaves("PardusInsight")
    check = kabul.check_2_5(ctx)
    assert check.durum == kabul.KALDI and "~/.config/PardusInsight" in check.ayrinti


def test_pytest_checks_run_isolated(simulated_linux, ctx):
    simulated_linux["responder"] = lambda cmd, cwd, env: kabul.CommandResult(0, "5 skipped in 0.1s")
    assert kabul.check_3_2(ctx).durum == kabul.ATLANDI
    call = simulated_linux["calls"][-1]
    assert call["cwd"] == kabul.ROOT and call["cmd"][-1] == "tests/test_crosscheck_linux.py"
    assert "no:cacheprovider" in call["cmd"]  # depoya .pytest_cache yazılmaz
    assert any(arg.startswith("--basetemp=") for arg in call["cmd"])
    simulated_linux["responder"] = lambda cmd, cwd, env: kabul.CommandResult(0, "18 passed in 3s")
    check = kabul.check_2_6(ctx)
    assert check.durum == kabul.GECTI and check.ayrinti == "18 passed"


def test_validate_metrics_check(simulated_linux, ctx):
    simulated_linux["responder"] = lambda cmd, cwd, env: kabul.CommandResult(0, VALIDATE_OUTPUT)
    check = kabul.check_3_1(ctx)
    assert check.durum == kabul.GECTI and check.cikti == VALIDATE_OUTPUT
    assert simulated_linux["calls"][-1]["cmd"][-4:] == ["--rounds", "10", "--interval", "1"]
    simulated_linux["responder"] = lambda cmd, cwd, env: kabul.CommandResult(
        2, "Bu betik Linux ve psutil gerektirir.\n")
    check = kabul.check_3_1(ctx)
    assert check.durum == kabul.KALDI and "çıkış kodu 2" in check.ayrinti


def test_perf_checks_headless_and_gui(simulated_linux, monkeypatch):
    def responder(cmd, cwd, env):
        if "--gui" in cmd:
            assert env.get("QT_QPA_PLATFORM") != "offscreen"  # gerçek pencerede ölçülür
            return kabul.CommandResult(0, PERF_GUI)
        return kabul.CommandResult(0, PERF_HEADLESS)

    simulated_linux["responder"] = responder
    monkeypatch.setattr(kabul, "module_version", lambda name: ("6.8.2", ""))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("DISPLAY", ":0")
    for argv, expected in ((["--gui"], (kabul.GECTI, kabul.GECTI)),
                           ([], (kabul.GECTI, kabul.ATLANDI)),
                           (["--hizli", "--gui"], (kabul.ATLANDI, kabul.ATLANDI))):
        context = make_ctx(*argv)
        try:
            headless, gui = kabul.check_4_1(context)
        finally:
            context.cleanup()
        assert (headless.no, gui.no) == ("4.1", "4.1b")
        assert (headless.durum, gui.durum) == expected, argv
    monkeypatch.delenv("DISPLAY")
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    context = make_ctx("--gui")
    try:
        _headless, gui = kabul.check_4_1(context)
    finally:
        context.cleanup()
    assert gui.durum == kabul.ATLANDI and "grafik oturum yok" in gui.ayrinti


def test_threshold_check_uses_config_file(simulated_linux, ctx):
    seen = {}

    def responder(cmd, cwd, env):
        seen["config"] = json.loads(Path(cmd[cmd.index("--config") + 1]).read_text("utf-8"))
        return kabul.CommandResult(0, "[Uyarı] Kalıcı CPU yoğunluğu (AKTİF, güven: orta)\n")

    simulated_linux["responder"] = responder
    check = kabul.check_5_5(ctx)
    assert check.durum == kabul.GECTI and seen["config"] == kabul.THRESHOLD_CONFIG
    assert simulated_linux["calls"][-1]["cmd"][3:9] == ["--headless", "--duration", "70",
                                                        "--interval", "2", "--quiet"]
    simulated_linux["responder"] = lambda cmd, cwd, env: kabul.CommandResult(0, "Özet: 35 tur")
    assert kabul.check_5_5(ctx).durum == kabul.KALDI


def test_child_env(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("LANGUAGE", "tr_TR:tr")
    env = kabul.child_env()
    assert env["LC_ALL"] == "C.UTF-8" and env["PYTHONUTF8"] == "1" and "LANGUAGE" not in env
    assert env["PYTHONDONTWRITEBYTECODE"] == "1"
    assert env["PYTHONPATH"].split(os.pathsep)[0] == kabul.ROOT
    assert env["QT_QPA_PLATFORM"] == "offscreen"
    assert "QT_QPA_PLATFORM" not in kabul.child_env(real_gui=True)


def test_run_command_with_real_subprocesses(tmp_path):
    env = kabul.child_env()
    res = kabul.run_command([sys.executable, "-c", "print('Kalıcı CPU yoğunluğu ✓')"],
                            timeout=60, cwd=str(tmp_path), env=env)
    assert res.ok and res.output.strip() == "Kalıcı CPU yoğunluğu ✓"
    version = kabul.run_command(kabul.app_cmd("--version"), timeout=60, cwd=str(tmp_path), env=env)
    assert version.ok and "PardusInsight" in version.output  # PYTHONPATH depo kökünü gösteriyor
    slow = kabul.run_command([sys.executable, "-c", "import time; time.sleep(30)"], timeout=1,
                             cwd=str(tmp_path), env=env)
    assert slow.timed_out and not slow.ok and "zaman aşımı" in slow.describe()
    missing = kabul.run_command([str(tmp_path / "olmayan-komut")], timeout=5)
    assert not missing.ok and "çalıştırılamadı" in missing.error
    assert list(tmp_path.iterdir()) == []  # alt süreçler çalışma dizinine dosya yazmadı


# ----------------------------------------------------------------------------- uzun ölçümler
@pytest.fixture
def fake_clock(monkeypatch):
    now = [0.0]
    monkeypatch.setattr(kabul, "_clock", lambda: now[0])
    monkeypatch.setattr(kabul, "_sleep", lambda seconds: now.__setitem__(0, now[0] + seconds))
    return now


def test_record_samples_follows_sampling_interval(fake_clock):
    service = build_synthetic_service("normal", start_time=kabul.DEMO_START)
    reports = []
    samples = kabul.record_samples(service, 130.0, lambda elapsed, n: reports.append((elapsed, n)))
    assert len(samples) == 66 and fake_clock[0] == pytest.approx(130.0)  # 0, 2, ..., 130 sn
    assert reports == [(60.0, 31), (120.0, 61)]


def test_long_run_shows_bounded_history(fake_clock):
    service = build_synthetic_service("normal", start_time=kabul.DEMO_START)
    readings = kabul.long_run_readings(service, rss=lambda: 50 * MIB)
    assert [minute for minute, _n, _rss in readings] == list(range(1, 36))
    assert readings[0][1] == 31 and readings[-5][1] == readings[-1][1] == 901  # 30 dk / 2 sn + 1
    ok, detail = kabul.evaluate_long_run(readings, service.history.capacity)
    assert ok, detail
    assert "| 35 | 901 | 50,0 |" in kabul.long_run_table(readings, service.history.capacity)


def test_evaluate_long_run_detects_growth():
    growing = [(m, 30 * m, (40 + m) * MIB) for m in range(1, 36)]
    ok, detail = kabul.evaluate_long_run(growing, capacity=1801)
    assert not ok and "büyümeye devam etti" in detail
    leaking = [(m, min(30 * m, 901), (40 + 3 * m) * MIB) for m in range(1, 36)]
    ok, detail = kabul.evaluate_long_run(leaking, capacity=1801)
    assert not ok and "RSS son 5 dk'da 10 MiB'den fazla büyüdü" in detail
    over = [(m, 2000, 40 * MIB) for m in range(1, 36)]
    assert "kapasiteyi aştı" in kabul.evaluate_long_run(over, capacity=1801)[1]
    assert not kabul.evaluate_long_run(over[:3], capacity=1801)[0]
    unmeasured = [(m, 901, None) for m in range(1, 36)]
    assert "RSS ölçülemedi" in kabul.evaluate_long_run(unmeasured, capacity=1801)[1]


# ----------------------------------------------------------------------------- kalibrasyon
Rec = namedtuple("Rec", "parameter current recommended reason")


def install_fake_calibration(monkeypatch, recommendations):
    """pardusinsight.analysis.calibration sözleşmesinin sahte uygulaması."""
    calls = []
    module = types.ModuleType("pardusinsight.analysis.calibration")

    @dataclass(frozen=True)
    class Recording:
        label: str
        samples: tuple
        heavy: bool = False

    def calibrate(recordings, base=None):
        calls.append((list(recordings), base))
        return types.SimpleNamespace(recommendations=tuple(recommendations))

    module.Recording = Recording
    module.calibrate = calibrate
    module.render_markdown = lambda result: "## Eşik kalibrasyonu\n\n| cpu_high_pct | 90 |\n"
    monkeypatch.setitem(sys.modules, "pardusinsight.analysis.calibration", module)
    return calls


def test_calibration_check_uses_api_on_recording(monkeypatch):
    calls = install_fake_calibration(monkeypatch, [Rec("cpu_high_pct", 85.0, 90.0, "yanlış poz."),
                                                   Rec("window_s", 30.0, 30.0, "korunur")])
    context = make_ctx("--kalibrasyon-suresi", "240")
    samples = synthetic_samples("normal", 121)
    context.recording = kabul.LiveRecording(samples=samples, duration_s=240.0)
    check = kabul.check_6(context)
    assert check.durum == kabul.BILGI and check.cikti_md
    assert "2 eşikten 1 tanesi için değişiklik önerildi: cpu_high_pct 85 → 90" in check.ayrinti
    assert check.cikti.startswith("## Eşik kalibrasyonu")
    [(recordings, base)] = calls
    assert base is None and len(recordings) == 1
    assert recordings[0].heavy is False and list(recordings[0].samples) == samples


def test_calibration_check_without_module_option_or_linux(monkeypatch):
    monkeypatch.setitem(sys.modules, "pardusinsight.analysis.calibration", None)
    check = kabul.check_6(make_ctx("--kalibrasyon-suresi", "60"))
    assert check.durum == kabul.ATLANDI and "kalibrasyon modülü bulunamadı" in check.ayrinti
    install_fake_calibration(monkeypatch, [])
    check = kabul.check_6(make_ctx())
    assert check.durum == kabul.MANUEL and kabul.CALIBRATION_CMD in check.ayrinti
    monkeypatch.setattr(kabul, "is_linux", lambda: False)
    assert kabul.check_6(make_ctx("--kalibrasyon-suresi", "60")).durum == kabul.ATLANDI
    assert kabul.check_5_6(make_ctx("--kalibrasyon-suresi", "60")).durum == kabul.ATLANDI


def test_calibration_check_with_real_module():
    pytest.importorskip("pardusinsight.analysis.calibration")
    context = make_ctx("--kalibrasyon-suresi", "240")
    context.recording = kabul.LiveRecording(samples=synthetic_samples("normal", 121),
                                            duration_s=240.0)
    check = kabul.check_6(context)
    assert check.durum == kabul.BILGI and check.cikti_md and check.cikti.lstrip().startswith("#")


def test_false_positive_check_counts_default_rule_alerts():
    context = make_ctx("--kalibrasyon-suresi", "600")
    context.recording = kabul.LiveRecording(samples=synthetic_samples("normal", 150),
                                            duration_s=298.0)
    check = kabul.check_5_6(context)
    assert check.durum == kabul.GECTI and "yanlış pozitif yok" in check.ayrinti
    assert "30 dk'dan kısa" in check.ayrinti
    context.recording = kabul.LiveRecording(samples=synthetic_samples("normal", 1), duration_s=0.0)
    assert kabul.check_5_6(context).durum == kabul.KALDI
    context.recording = kabul.LiveRecording(samples=synthetic_samples("cpu", 211),
                                            duration_s=420.0, path="/kayitlar/olagan.json")
    check = kabul.check_5_6(context)
    assert check.durum == kabul.MANUEL
    assert re.search(r"\d+ uyarı üretildi", check.ayrinti)
    assert "Kalıcı CPU yoğunluğu" in check.ayrinti and "/kayitlar/olagan.json" in check.ayrinti
    assert kabul.check_5_6(make_ctx()).durum == kabul.MANUEL


# ----------------------------------------------------------------------------- ana akış
def test_main_end_to_end_quick_run(tmp_path, monkeypatch, capsys):
    scratch = tmp_path / "gecici"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    # Alt süreçler sahte: test hızlı ve belirlenimci kalır (gerçekleri CI'daki Pardus'ta çalışır)
    monkeypatch.setattr(kabul, "run_command",
                        lambda cmd, timeout, cwd=None, env=None: kabul.CommandResult(0, ""))
    monkeypatch.setattr(kabul, "_sleep", lambda seconds: None)
    if kabul.is_linux():
        monkeypatch.setattr(kabul, "check_2_4", lambda _ctx: kabul.Check(
            "2.4", kabul.TITLES["2.4"], kabul.ATLANDI, "testte atlandı"))
    out = tmp_path / "rapor.md"

    code = kabul.main(["--hizli", "--cikti", str(out)])

    assert code in (0, 1)
    text = out.read_text(encoding="utf-8")
    assert text.startswith("# Pardus Kabul ve Doğrulama Sonuçları\n")
    rows = report_rows(text)
    assert set(kabul.TITLES) == set(rows)
    for no in ("4.1", "5.5", "5.8"):
        assert "⏭ ATLANDI" in rows[no] and "--hizli" in rows[no]
    assert "⏭ ATLANDI" in rows["4.1b"] and "--uzun" in rows["4.2"]
    for no in ("1.4b", "3.3b", "4.3", "5.3b", "5.6", "5.7", "6"):
        assert "✋ MANUEL" in rows[no]
    for no in ("5.1", "5.2", "5.3", "5.4"):
        assert "✅ GEÇTİ" in rows[no]
    if not sys.platform.startswith("linux"):
        for no in LINUX_ONLY:
            assert "⏭ ATLANDI" in rows[no], rows[no]
    assert any("❌ KALDI" in row for row in rows.values()) == (code == 1)
    assert list(scratch.iterdir()) == []  # geçici dizinler silindi
    assert capsys.readouterr().out == ""  # rapor yalnızca --cikti dosyasına yazıldı


def test_exit_code_reflects_kaldi(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(kabul, "environment_rows", lambda: [("Çekirdek", "test")])
    passing = ("9.1", lambda _ctx: kabul.Check("9.1", "geçen", kabul.GECTI))
    failing = ("9.2", lambda _ctx: kabul.Check("9.2", "kalan", kabul.KALDI, "bozuk"))
    out = tmp_path / "rapor.md"
    monkeypatch.setattr(kabul, "plan", lambda: [passing])
    assert kabul.main(["--cikti", str(out)]) == 0
    monkeypatch.setattr(kabul, "plan", lambda: [passing, failing])
    assert kabul.main(["--cikti", str(out)]) == 1
    text = out.read_text(encoding="utf-8")
    assert "## Diğer" in text and "| 9.2 | kalan | ❌ KALDI | bozuk |" in text
    capsys.readouterr()
    assert kabul.main([]) == 1  # --cikti yoksa rapor standart çıktıya yazılır
    assert capsys.readouterr().out.startswith("# Pardus Kabul ve Doğrulama Sonuçları")


def test_ctrl_c_prints_partial_report_and_exits_130(tmp_path, monkeypatch, capsys):
    def interrupted(context):
        context.partial = kabul.Check("4.2", kabul.TITLES["4.2"], kabul.ATLANDI,
                                      "Ctrl+C ile 3. dakikadan sonra kesildi")
        raise KeyboardInterrupt

    monkeypatch.setattr(kabul, "environment_rows", lambda: [])
    monkeypatch.setattr(kabul, "plan", lambda: [("1.3", kabul.check_1_3), ("4.2", interrupted),
                                                ("5.1", kabul.check_5_1)])
    out = tmp_path / "rapor.md"
    assert kabul.main(["--cikti", str(out)]) == 130
    text = capsys.readouterr().out
    assert "Ctrl+C ile yarıda kesildi" in text
    rows = report_rows(text)
    assert "1.3" in rows and "kesildi" in rows["4.2"] and "5.1" not in rows
    assert not out.exists()  # kısmi rapor --cikti dosyasının yerine yazılmaz


def test_argument_validation(tmp_path):
    for argv in (["--cikti", str(tmp_path / "yok" / "rapor.md")], ["--cikti", str(tmp_path)],
                 ["--kayit-klasoru", str(tmp_path)], ["--kalibrasyon-suresi", "0"]):
        with pytest.raises(SystemExit) as exc:
            kabul.main(argv)
        assert exc.value.code == 2, argv
