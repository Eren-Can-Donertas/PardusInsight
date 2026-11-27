#!/usr/bin/env python3
"""Aşama 2 teslim ZIP'ini oluşturur ve içeriğini yeniden açarak denetler.

Yapı (BIL461-Proje-Asama2.pdf, bölüm 3):

    PardusInsight.zip
    ├── source_code/        Git'te izlenen kaynak dosyalar (uygulama, testler, senaryolar, belgeler)
    ├── README.md           bağlantıları source_code/ yapısına göre düzenlenmiş README
    ├── technical_report.pdf
    └── VIDEO_LINK.txt

Yalnızca `git ls-files` ile izlenen dosyalar alınır; .venv, __pycache__, .pytest_cache,
kişisel dosyalar ve kurs PDF'leri böylece dışarıda kalır. Geliştirici kalite belgeleri
(TEST_REPORT.md vb.) görev tanımı gereği ZIP'e eklenmez.

Kullanım:
    python3 scripts/build_submission.py                  # dist/PardusInsight.zip
    python3 scripts/build_submission.py --verify-only dist/PardusInsight.zip
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess  # yalnızca bu geliştirici betiğinde: `git ls-files` (uygulama kodunda yok)
import sys
import tempfile
import time
import zipfile
from typing import Iterable, List, Set

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT_FILES = ("README.md", "technical_report.pdf", "VIDEO_LINK.txt")
#: Geliştirici çalışma klasöründe kalan, teslim ZIP'ine girmeyen belgeler
DEVELOPER_DOCS = {"TEST_REPORT.md", "REQUIREMENTS_MATRIX.md", "PARDUS_VALIDATION.md",
                  "VIDEO_PLAN.md", "ORAL_EXAM_PREP.md", "FINAL_CHECKLIST.md"}
#: source_code/ altına konmayan dosya ve klasörler (kök düzeyde ayrıca yer alanlar dahil)
SOURCE_EXCLUDES = DEVELOPER_DOCS | {"technical_report.pdf", "VIDEO_LINK.txt"}
SOURCE_EXCLUDE_DIRS = ("report/",)  # teknik rapor kaynakları; PDF kökte yer alır
FORBIDDEN_PARTS = (".git/", ".venv/", "venv/", "__pycache__/", ".pytest_cache/", ".mypy_cache/",
                   ".ruff_cache/", "dist/", ".egg-info/")
FORBIDDEN_SUFFIXES = (".pyc", ".pyo", ".log", ".tmp", ".env", ".pem", ".key")
MAX_FILE_BYTES = 2 * 1024 * 1024  # tek dosya için üst sınır: büyük veri dosyası girmesin


def tracked_files() -> List[str]:
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, check=True,
                         capture_output=True).stdout.decode("utf-8")
    return sorted(f for f in out.split("\0") if f)


def source_files(files: Iterable[str]) -> List[str]:
    return [f for f in files
            if f not in SOURCE_EXCLUDES and not f.startswith(SOURCE_EXCLUDE_DIRS)
            and os.path.isfile(os.path.join(ROOT, f))]


_LINK = re.compile(r"\[([^\]]+)\]\(([^)#\s]+)(#[^)\s]*)?\)")


def rewrite_readme(text: str, included: Set[str]) -> str:
    """Kökteki README'nin göreli bağlantılarını source_code/ altına yönlendirir.

    ZIP'te bulunmayan geliştirici belgelerine verilen bağlantılar düz metne çevrilir.
    """
    def repl(match: "re.Match[str]") -> str:
        label, target, anchor = match.group(1), match.group(2), match.group(3) or ""
        if re.match(r"^[a-z]+://", target) or target.startswith("mailto:"):
            return match.group(0)
        clean = target.lstrip("./")
        if clean in ROOT_FILES:
            return match.group(0)
        if clean in included or any(f.startswith(clean.rstrip("/") + "/") for f in included):
            return f"[{label}](source_code/{clean}{anchor})"
        return f"{label} (yalnızca Git deposunda)"

    return _LINK.sub(repl, text)


def build(output: str) -> str:
    files = tracked_files()
    missing = [f for f in ROOT_FILES if f not in files]
    if missing:
        raise SystemExit(f"Git'te izlenmeyen zorunlu dosya(lar): {', '.join(missing)}")
    included = source_files(files)
    os.makedirs(os.path.dirname(os.path.abspath(output)), exist_ok=True)
    tmp = output + ".tmp"
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for rel in included:
            zf.write(os.path.join(ROOT, rel), f"source_code/{rel}")
        with open(os.path.join(ROOT, "README.md"), "r", encoding="utf-8") as handle:
            readme = zipfile.ZipInfo("README.md", date_time=time.localtime()[:6])
            readme.external_attr = 0o644 << 16  # writestr varsayılanı 0600 olurdu
            readme.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(readme, rewrite_readme(handle.read(), set(included)))
        zf.write(os.path.join(ROOT, "technical_report.pdf"), "technical_report.pdf")
        zf.write(os.path.join(ROOT, "VIDEO_LINK.txt"), "VIDEO_LINK.txt")
    os.replace(tmp, output)
    return output


def verify(path: str) -> List[str]:
    """ZIP'i geçici klasöre açar ve yapıyı denetler; bulunan sorunları döndürür."""
    problems: List[str] = []
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        bad = zf.testzip()
        if bad:
            problems.append(f"bozuk arşiv üyesi: {bad}")
        with tempfile.TemporaryDirectory(prefix="pi-verify-") as tmpdir:
            zf.extractall(tmpdir)
            for required in ROOT_FILES + ("source_code/pardusinsight/__init__.py",
                                          "source_code/requirements.txt",
                                          "source_code/pyproject.toml", "source_code/tests"):
                if not os.path.exists(os.path.join(tmpdir, required)):
                    problems.append(f"eksik: {required}")
            top = {n.split("/", 1)[0] for n in names}
            if top != {"source_code", *ROOT_FILES}:
                problems.append(f"beklenmeyen kök öğeler: {sorted(top)}")
            for name in names:
                if any(part in name for part in FORBIDDEN_PARTS) or name.endswith(
                        FORBIDDEN_SUFFIXES):
                    problems.append(f"teslime girmemesi gereken dosya: {name}")
                if os.path.basename(name) in DEVELOPER_DOCS:
                    problems.append(f"geliştirici belgesi ZIP'e girmiş: {name}")
                if zf.getinfo(name).file_size > MAX_FILE_BYTES:
                    problems.append(f"çok büyük dosya: {name}")
                if name.lower().endswith(".pdf") and name != "technical_report.pdf":
                    problems.append(f"beklenmeyen PDF: {name}")
            with open(os.path.join(tmpdir, "README.md"), "r", encoding="utf-8") as handle:
                for match in _LINK.finditer(handle.read()):
                    target = match.group(2)
                    if re.match(r"^[a-z]+://", target):
                        continue
                    if not os.path.exists(os.path.join(tmpdir, target)):
                        problems.append(f"README'de kırık bağlantı: {target}")
            with open(os.path.join(tmpdir, "VIDEO_LINK.txt"), "r", encoding="utf-8") as handle:
                first = handle.readline().strip()
            if not (first == "VIDEO_LINK_PENDING" or first.startswith("https://")):
                problems.append(f"VIDEO_LINK.txt ilk satırı geçersiz: {first!r}")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", default=os.path.join(ROOT, "dist", "PardusInsight.zip"))
    parser.add_argument("--verify-only", metavar="ZIP")
    args = parser.parse_args()
    path = args.verify_only or build(args.output)
    problems = verify(path)
    with zipfile.ZipFile(path) as zf:
        infos = zf.infolist()
        with zf.open("VIDEO_LINK.txt") as handle:
            pending = handle.readline().decode("utf-8").strip() == "VIDEO_LINK_PENDING"
    size = os.path.getsize(path)
    print(f"Arşiv: {path}")
    print(f"Dosya sayısı: {len(infos)} · sıkıştırılmış boyut: {size / 1024:.1f} KiB · "
          f"açılmış boyut: {sum(i.file_size for i in infos) / 1024:.1f} KiB")
    if problems:
        print("DENETİM BAŞARISIZ:")
        for problem in problems:
            print("  -", problem)
        return 1
    print("Denetim: yapı, yasaklı dosyalar, README bağlantıları ve VIDEO_LINK.txt uygun.")
    if pending:
        print("DURUM: ÖN TESLİM — video bağlantısı bekleniyor (VIDEO_LINK_PENDING). "
              "Video eklenmeden nihai teslim tamamlanmış sayılmaz.")
    else:
        print("DURUM: video bağlantısı mevcut.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
