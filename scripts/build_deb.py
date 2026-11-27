#!/usr/bin/env python3
"""PardusInsight için Pardus/Debian ikili paketi (.deb) oluşturur.

Yalnızca Python standart kütüphanesini kullanır (tarfile, lzma, gzip, hashlib).
dpkg-deb gerektirmediği için Windows'ta da çalışır. Çıktı ``dpkg-deb --build``
ile aynı yapıdadır: ``ar`` arşivi içinde sırasıyla ``debian-binary``,
``control.tar.xz`` ve ``data.tar.xz``.

Paket düzeni (Debian Python politikası, uygulamaya özel modüller):

  /usr/bin/pardusinsight                          başlatıcı
  /usr/share/pardusinsight/pardusinsight/         uygulama modülleri
  /usr/share/pardusinsight/scenarios/*.json       önceden kaydedilmiş senaryolar
  /usr/share/applications/pardusinsight.desktop   menü kaydı
  /usr/share/icons/hicolor/scalable/apps/pardusinsight.svg
  /usr/share/man/man1/pardusinsight.1.gz
  /usr/share/doc/pardusinsight/                   copyright, changelog, belgeler

Arşivdeki dosyalar root:root sahipliğinde, sabit zaman damgalı ve LF satır
sonludur; aynı kaynaktan her platformda bayt bayt aynı paket üretilir.

Kullanım:
  python3 scripts/build_deb.py                  # dist/pardusinsight_<sürüm>_all.deb
  python3 scripts/build_deb.py --cikti /tmp     # başka klasöre yaz
  python3 scripts/build_deb.py --liste          # oluşturup içeriğini listele

Kurulum (Pardus 25.1):  sudo apt install ./dist/pardusinsight_<sürüm>_all.deb
Kaldırma:               sudo apt remove pardusinsight
"""
from __future__ import annotations

import argparse
import email.utils
import gzip
import hashlib
import io
import math
import os
import re
import sys
import tarfile
from dataclasses import dataclass
from typing import Dict, Iterator, List, Optional, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGING = os.path.join(ROOT, "packaging")
PACKAGE = "pardusinsight"
PRIVATE_DIR = "usr/share/pardusinsight"  # uygulamaya özel modül dizini
DOC_DIR = "usr/share/doc/pardusinsight"
#: /usr/share/doc altına sıkıştırılarak konan kullanıcı belgeleri
USER_DOCS = ("README.md", "docs/KULLANIM.md", "docs/KURALLAR.md")

LAUNCHER = '''#!/usr/bin/python3
"""PardusInsight başlatıcısı (Pardus/Debian paketi).

Uygulama modülleri Debian Python politikasına uygun olarak özel bir dizinde
(/usr/share/pardusinsight) bulunur; bu betik o dizini modül yoluna ekler.
"""
import os
import sys

_PREFIX = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
sys.path.insert(0, os.path.join(_PREFIX, "share", "pardusinsight"))

from pardusinsight.cli import main  # noqa: E402

sys.exit(main())
'''


class BuildError(Exception):
    """Paket oluşturulamadı (eksik dosya, sürüm uyuşmazlığı vb.)."""


@dataclass(frozen=True)
class Entry:
    """Paketteki tek dosya. ``path`` başında "./" olmadan, '/' ayırıcılıdır."""

    path: str
    data: bytes
    mode: int = 0o644


# ---------------------------------------------------------------------------
# Kaynaklar
# ---------------------------------------------------------------------------


def read_lf(path: str) -> bytes:
    """Metin dosyasını okur ve CRLF satır sonlarını LF'ye çevirir.

    Windows'ta Git (core.autocrlf) çalışma kopyasını CRLF yapabilir; kabuk
    betikleri CRLF ile Linux'ta çalışmaz ve paket platforma göre değişirdi.
    """
    with open(path, "rb") as handle:
        return handle.read().replace(b"\r\n", b"\n")


def package_version(root: str = ROOT) -> str:
    text = read_lf(os.path.join(root, PACKAGE, "__init__.py")).decode("utf-8")
    match = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
    if not match:
        raise BuildError("pardusinsight/__init__.py içinde __version__ bulunamadı")
    return match.group(1)


def changelog_entry(packaging: str = PACKAGING) -> Tuple[str, int]:
    """Debian changelog'unun en üst kaydındaki sürümü ve tarihini (epoch) döndürür."""
    text = read_lf(os.path.join(packaging, "debian", "changelog")).decode("utf-8")
    head = re.match(r"^pardusinsight \(([^)]+)\) ", text)
    trailer = re.search(r"^ -- .+?<[^>]+>  (.+)$", text, re.MULTILINE)
    if not head or not trailer:
        raise BuildError("packaging/debian/changelog biçimi tanınmadı")
    parsed = email.utils.parsedate_to_datetime(trailer.group(1).strip())
    return head.group(1), int(parsed.timestamp())


def build_mtime(packaging: str = PACKAGING) -> int:
    """Yeniden üretilebilir derleme zamanı: SOURCE_DATE_EPOCH veya changelog tarihi."""
    env = os.environ.get("SOURCE_DATE_EPOCH")
    if env:
        try:
            return int(env)
        except ValueError as exc:
            raise BuildError(f"SOURCE_DATE_EPOCH geçersiz: {env!r}") from exc
    return changelog_entry(packaging)[1]


def _python_sources(root: str) -> Iterator[Tuple[str, str]]:
    top = os.path.join(root, PACKAGE)
    for dirpath, dirnames, filenames in os.walk(top):
        dirnames[:] = sorted(d for d in dirnames if d != "__pycache__")
        for name in sorted(filenames):
            if name.endswith(".py"):
                full = os.path.join(dirpath, name)
                yield os.path.relpath(full, root).replace(os.sep, "/"), full


def _gz(data: bytes) -> bytes:
    # mtime=0: zaman damgasız gzip (lintian: package-contains-timestamped-gzip)
    return gzip.compress(data, compresslevel=9, mtime=0)


def collect_entries(root: str = ROOT, packaging: str = PACKAGING) -> List[Entry]:
    """Pakete girecek tüm dosyaları hedef yollarıyla birlikte toplar."""
    entries: List[Entry] = [Entry("usr/bin/pardusinsight", LAUNCHER.encode("utf-8"), 0o755)]
    sources = list(_python_sources(root))
    if not sources:
        raise BuildError(f"{PACKAGE}/ altında Python dosyası bulunamadı")
    entries += [Entry(f"{PRIVATE_DIR}/{rel}", read_lf(full)) for rel, full in sources]

    scenario_dir = os.path.join(root, "scenarios")
    scenarios = sorted(n for n in os.listdir(scenario_dir) if n.endswith(".json")) \
        if os.path.isdir(scenario_dir) else []
    if not scenarios:
        raise BuildError("scenarios/ klasöründe senaryo dosyası bulunamadı "
                         "(python3 scripts/generate_scenarios.py)")
    entries += [Entry(f"{PRIVATE_DIR}/scenarios/{n}", read_lf(os.path.join(scenario_dir, n)))
                for n in scenarios]

    def pkg(*parts: str) -> str:
        path = os.path.join(packaging, *parts)
        if not os.path.isfile(path):
            raise BuildError(f"Paketleme dosyası eksik: {os.path.relpath(path, root)}")
        return path

    entries += [
        Entry("usr/share/applications/pardusinsight.desktop", read_lf(pkg("pardusinsight.desktop"))),
        Entry("usr/share/icons/hicolor/scalable/apps/pardusinsight.svg",
              read_lf(pkg("pardusinsight.svg"))),
        Entry("usr/share/man/man1/pardusinsight.1.gz", _gz(read_lf(pkg("pardusinsight.1")))),
        Entry(f"{DOC_DIR}/copyright", read_lf(pkg("debian", "copyright"))),
        Entry(f"{DOC_DIR}/changelog.gz", _gz(read_lf(pkg("debian", "changelog")))),
    ]
    for doc in USER_DOCS:
        path = os.path.join(root, *doc.split("/"))
        if os.path.isfile(path):
            entries.append(Entry(f"{DOC_DIR}/{os.path.basename(doc)}.gz", _gz(read_lf(path))))
    return sorted(entries, key=lambda e: e.path)


def installed_size_kib(entries: List[Entry]) -> int:
    """dpkg-gencontrol gibi: dosya başına yukarı yuvarlanmış KiB toplamı."""
    return sum(max(1, math.ceil(len(e.data) / 1024)) for e in entries)


def control_text(version: str, installed_size: int, packaging: str = PACKAGING) -> str:
    template = read_lf(os.path.join(packaging, "debian", "control.in")).decode("utf-8")
    text = template.replace("@VERSION@", version).replace("@INSTALLED_SIZE@", str(installed_size))
    if "@" in re.sub(r"<[^>]*>", "", text):
        raise BuildError("control.in içinde doldurulmamış yer tutucu kaldı")
    return text if text.endswith("\n") else text + "\n"


def md5sums_text(entries: List[Entry]) -> str:
    return "".join(f"{hashlib.md5(e.data).hexdigest()}  {e.path}\n" for e in entries)


# ---------------------------------------------------------------------------
# Arşivler
# ---------------------------------------------------------------------------


def _tarinfo(name: str, mtime: int, kind: bytes, mode: int, size: int = 0) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.type = kind
    info.mode = mode
    info.size = size
    info.mtime = mtime
    info.uid = info.gid = 0
    info.uname = info.gname = "root"
    return info


def tar_xz(entries: List[Entry], mtime: int) -> bytes:
    """"./yol" biçimli, dizinleri dosyalardan önce içeren tar.xz üretir."""
    dirs = set()
    for entry in entries:
        parts = entry.path.split("/")[:-1]
        for i in range(1, len(parts) + 1):
            dirs.add("/".join(parts[:i]))
    items: List[Tuple[str, Optional[Entry]]] = [(d, None) for d in dirs]
    items += [(e.path, e) for e in entries]
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:xz", format=tarfile.GNU_FORMAT) as tar:
        tar.addfile(_tarinfo(".", mtime, tarfile.DIRTYPE, 0o755))
        for path, entry in sorted(items, key=lambda item: item[0]):
            if entry is None:
                tar.addfile(_tarinfo("./" + path, mtime, tarfile.DIRTYPE, 0o755))
            else:
                info = _tarinfo("./" + path, mtime, tarfile.REGTYPE, entry.mode, len(entry.data))
                tar.addfile(info, io.BytesIO(entry.data))
    return buf.getvalue()


def ar_archive(members: List[Tuple[str, bytes]], mtime: int) -> bytes:
    """dpkg'nin beklediği BSD/GNU ortak ``ar`` biçimi (üye adları 16 karakter)."""
    out = [b"!<arch>\n"]
    for name, data in members:
        header = f"{name:<16}{mtime:<12}{0:<6}{0:<6}{'100644':<8}{len(data):<10}`\n"
        encoded = header.encode("ascii")
        if len(encoded) != 60:
            raise BuildError(f"ar başlığı 60 bayt değil: {name}")
        out.append(encoded)
        out.append(data)
        if len(data) % 2:
            out.append(b"\n")
    return b"".join(out)


def read_ar(blob: bytes) -> List[Tuple[str, bytes]]:
    """ar arşivini (yalnızca bu betiğin ürettiği basit biçim) üyelerine ayırır."""
    if not blob.startswith(b"!<arch>\n"):
        raise BuildError("ar imzası yok")
    pos, members = 8, []
    while pos < len(blob):
        header = blob[pos:pos + 60].decode("ascii")
        if header[58:60] != "`\n":
            raise BuildError("bozuk ar başlığı")
        name, size = header[:16].strip().rstrip("/"), int(header[48:58])
        pos += 60
        members.append((name, blob[pos:pos + size]))
        pos += size + (size % 2)
    return members


# ---------------------------------------------------------------------------
# Paket
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BuildResult:
    path: str
    version: str
    entries: Tuple[Entry, ...]
    size: int


def build_deb(out_dir: str, root: str = ROOT, packaging: str = PACKAGING) -> BuildResult:
    version = package_version(root)
    log_version, _ = changelog_entry(packaging)
    if log_version != version:
        raise BuildError(f"Sürüm uyuşmuyor: pardusinsight/__init__.py {version}, "
                         f"packaging/debian/changelog {log_version}. Changelog'a yeni kayıt "
                         "ekleyin.")
    mtime = build_mtime(packaging)
    entries = collect_entries(root, packaging)
    control = control_text(version, installed_size_kib(entries), packaging)
    control_entries = [
        Entry("control", control.encode("utf-8")),
        Entry("md5sums", md5sums_text(entries).encode("utf-8")),
        Entry("postinst", read_lf(os.path.join(packaging, "debian", "postinst")), 0o755),
        Entry("prerm", read_lf(os.path.join(packaging, "debian", "prerm")), 0o755),
    ]
    deb = ar_archive([("debian-binary", b"2.0\n"),
                      ("control.tar.xz", tar_xz(control_entries, mtime)),
                      ("data.tar.xz", tar_xz(entries, mtime))], mtime)
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{PACKAGE}_{version}_all.deb")
    tmp = path + ".tmp"
    with open(tmp, "wb") as handle:
        handle.write(deb)
    os.replace(tmp, path)
    return BuildResult(path, version, tuple(entries), len(deb))


def describe(path: str) -> str:
    """Oluşturulan paketin control alanlarını ve dosya listesini metin olarak verir."""
    members = dict(read_ar(open(path, "rb").read()))
    lines = []
    with tarfile.open(fileobj=io.BytesIO(members["control.tar.xz"]), mode="r:xz") as tar:
        member = tar.extractfile("./control")
        lines.append(member.read().decode("utf-8") if member else "")
    with tarfile.open(fileobj=io.BytesIO(members["data.tar.xz"]), mode="r:xz") as tar:
        for info in tar.getmembers():
            kind = "d" if info.isdir() else "-"
            lines.append(f"{kind}{oct(info.mode)[2:]:>5} {info.uname}/{info.gname} "
                         f"{info.size:>9} {info.name}")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cikti", default=os.path.join(ROOT, "dist"),
                        help="paketin yazılacağı klasör (varsayılan: dist/)")
    parser.add_argument("--liste", action="store_true",
                        help="oluşturulan paketin control alanlarını ve içeriğini yazdır")
    args = parser.parse_args(argv)
    try:
        result = build_deb(args.cikti)
    except (BuildError, OSError) as exc:
        print(f"Paket oluşturulamadı: {exc}", file=sys.stderr)
        return 1
    print(f"Oluşturuldu: {result.path} (sürüm {result.version}, {len(result.entries)} dosya, "
          f"{result.size / 1024:.1f} KiB)")
    if args.liste:
        print(describe(result.path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
