"""Debian/Pardus paketinin (.deb) yapı ve içerik testleri.

Paket scripts/build_deb.py ile yalnızca standart kütüphane kullanılarak
oluşturulur; bu testler her platformda çalışır. Pardus'ta gerçek kurulum
(apt install, py3compile, kaldırma) CI'daki Pardus 25.1 kapsayıcısında denenir.
"""
import gzip
import hashlib
import io
import os
import re
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

from pardusinsight import __version__
from pardusinsight.cli import build_parser

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_deb  # noqa: E402


@pytest.fixture(scope="module")
def deb(tmp_path_factory):
    out = tmp_path_factory.mktemp("deb")
    result = build_deb.build_deb(str(out))
    blob = Path(result.path).read_bytes()
    members = build_deb.read_ar(blob)
    data = dict(members)

    def tar_members(name):
        with tarfile.open(fileobj=io.BytesIO(data[name]), mode="r:xz") as tar:
            return {info.name: (info, tar.extractfile(info).read() if info.isfile() else None)
                    for info in tar.getmembers()}

    return {"result": result, "blob": blob, "members": members,
            "control": tar_members("control.tar.xz"), "data": tar_members("data.tar.xz")}


def control_fields(deb):
    text = deb["control"]["./control"][1].decode("utf-8")
    fields = {}
    for line in text.splitlines():
        if line and not line.startswith(" "):
            key, _, value = line.partition(":")
            fields[key] = value.strip()
    return fields


def data_files(deb):
    return {name[2:]: content for name, (info, content) in deb["data"].items() if info.isfile()}


# ----------------------------------------------------------------------------- yapı
def test_ar_members_follow_dpkg_order(deb):
    names = [name for name, _ in deb["members"]]
    assert deb["blob"].startswith(b"!<arch>\n")
    assert names == ["debian-binary", "control.tar.xz", "data.tar.xz"]
    assert deb["members"][0][1] == b"2.0\n"


def test_control_fields_and_dependencies(deb):
    fields = control_fields(deb)
    assert fields["Package"] == "pardusinsight"
    assert fields["Version"] == __version__
    assert fields["Architecture"] == "all"
    assert int(fields["Installed-Size"]) > 0
    for dep in ("python3", "python3-psutil", "python3-pyside6.qtwidgets"):
        assert re.search(rf"(^|, ){re.escape(dep)}( |,|$)", fields["Depends"]), dep
    assert "@" not in fields["Version"] + fields["Installed-Size"]


def test_md5sums_cover_every_file(deb):
    files = data_files(deb)
    lines = deb["control"]["./md5sums"][1].decode("utf-8").splitlines()
    listed = dict(reversed(line.split("  ", 1)) for line in lines)
    assert set(listed) == set(files)
    for path, digest in listed.items():
        assert hashlib.md5(files[path]).hexdigest() == digest, path


def test_maintainer_scripts_are_executable_posix_shell(deb):
    for name in ("./postinst", "./prerm"):
        info, content = deb["control"][name]
        assert info.mode == 0o755
        assert content.startswith(b"#!/bin/sh\n") and b"\r" not in content


def test_ownership_modes_and_parent_directories(deb):
    entries = deb["data"]
    assert "." in entries or "./" in entries
    for name, (info, _content) in entries.items():
        assert (info.uid, info.gid, info.uname, info.gname) == (0, 0, "root", "root"), name
        if info.isdir():
            assert info.mode == 0o755, name
        else:
            expected = 0o755 if name == "./usr/bin/pardusinsight" else 0o644
            assert info.mode == expected, name
            parent = name.rsplit("/", 1)[0]
            assert parent == "." or parent in entries, f"{name}: üst dizin arşivde yok"


def test_application_layout(deb):
    files = data_files(deb)
    sources = sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / "pardusinsight").rglob("*.py")
                     if "__pycache__" not in p.parts)
    for rel in sources:
        assert f"usr/share/pardusinsight/{rel}" in files, rel
    for scenario in (ROOT / "scenarios").glob("*.json"):
        assert f"usr/share/pardusinsight/scenarios/{scenario.name}" in files
    for required in ("usr/bin/pardusinsight", "usr/share/applications/pardusinsight.desktop",
                     "usr/share/icons/hicolor/scalable/apps/pardusinsight.svg",
                     "usr/share/man/man1/pardusinsight.1.gz",
                     "usr/share/doc/pardusinsight/copyright",
                     "usr/share/doc/pardusinsight/changelog.gz"):
        assert required in files, required
    assert not any("__pycache__" in p or p.endswith(".pyc") for p in files)


def test_text_files_use_lf_line_endings(deb):
    for path, content in data_files(deb).items():
        if not path.endswith(".gz"):
            assert b"\r\n" not in content, path


def test_gzip_members_have_no_timestamp(deb):
    for path, content in data_files(deb).items():
        if path.endswith(".gz"):
            assert content[4:8] == b"\x00\x00\x00\x00", path  # gzip MTIME alanı
            gzip.decompress(content)


def test_desktop_entry_launches_installed_command(deb):
    desktop = data_files(deb)["usr/share/applications/pardusinsight.desktop"].decode("utf-8")
    assert desktop.startswith("[Desktop Entry]\n")
    assert "\nExec=pardusinsight\n" in desktop and "\nIcon=pardusinsight\n" in desktop
    assert "\nCategories=System;Monitor;\n" in desktop


def test_build_is_reproducible(deb, tmp_path):
    again = build_deb.build_deb(str(tmp_path))
    assert Path(again.path).read_bytes() == deb["blob"]


def test_changelog_version_matches_package_version():
    version, _epoch = build_deb.changelog_entry()
    assert version == __version__ == build_deb.package_version()


def test_version_mismatch_is_reported(tmp_path):
    fake = tmp_path / "packaging"
    (fake / "debian").mkdir(parents=True)
    for name in ("control.in", "copyright", "postinst", "prerm"):
        (fake / "debian" / name).write_bytes((ROOT / "packaging" / "debian" / name).read_bytes())
    (fake / "debian" / "changelog").write_text(
        "pardusinsight (9.9.9) unstable; urgency=medium\n\n  * deneme\n\n"
        " -- A B <a@b.c>  Wed, 25 Nov 2026 14:00:00 +0300\n", encoding="utf-8")
    with pytest.raises(build_deb.BuildError, match="Sürüm uyuşmuyor"):
        build_deb.build_deb(str(tmp_path / "out"), packaging=str(fake))


# ----------------------------------------------------------------------------- davranış
def test_extracted_launcher_runs_cli(deb, tmp_path):
    with tarfile.open(fileobj=io.BytesIO(dict(deb["members"])["data.tar.xz"]), mode="r:xz") as tar:
        kwargs = {"filter": "data"} if hasattr(tarfile, "data_filter") else {}
        tar.extractall(tmp_path, **kwargs)
    launcher = tmp_path / "usr" / "bin" / "pardusinsight"
    env = dict(os.environ, PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")
    env.pop("PYTHONPATH", None)
    version = subprocess.run([sys.executable, str(launcher), "--version"], capture_output=True,
                             text=True, encoding="utf-8", env=env, cwd=str(tmp_path), timeout=60)
    assert version.returncode == 0 and __version__ in version.stdout
    replay = subprocess.run(
        [sys.executable, str(launcher), "--headless", "--replay",
         str(tmp_path / "usr/share/pardusinsight/scenarios/cpu.json")],
        capture_output=True, text=True, encoding="utf-8", env=env, cwd=str(tmp_path), timeout=120)
    assert replay.returncode == 0, replay.stderr
    assert "Kalıcı CPU yoğunluğu" in replay.stdout


def test_man_page_documents_every_cli_option():
    page = (ROOT / "packaging" / "pardusinsight.1").read_text(encoding="utf-8")
    for action in build_parser()._actions:
        for option in action.option_strings:
            assert option.replace("-", r"\-") in page, f"kılavuzda eksik seçenek: {option}"
