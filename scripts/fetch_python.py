"""Install or verify the vendored Python runtime in python/.

The archive is verified against a pinned SHA-256 before anything is written, so
python/ can only ever contain the exact upstream build named in
scripts/python_runtime.json. Run with --check to verify without network access.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PIN_PATH = Path(__file__).with_name("python_runtime.json")
# The embeddable build ignores PYTHONPATH; use the ABI of the pinned runtime.
PYTHON_ABI = ''.join(json.loads(PIN_PATH.read_text(encoding='utf-8'))['version'].split('.')[:2])
PTH_NAME = f"python{PYTHON_ABI}._pth"
PTH_BODY = f"python{PYTHON_ABI}.zip\n.\n..\\src\nimport site\n"
STAMP = ".goblin-eye-python.json"


def tree_digest(target: Path) -> str:
    """Hash every installed runtime file, excluding the derived stamp.

    This catches a file that is missing or corrupted after installation, which a
    single archive hash cannot: a git ignore rule or a partial copy can drop one
    extension module and leave the rest of the tree intact.
    """
    entries = []
    for path in sorted(target.rglob("*")):
        if path.is_file() and path.name != STAMP:
            entries.append(f"{path.relative_to(target).as_posix()}:{hashlib.sha256(path.read_bytes()).hexdigest()}")
    return hashlib.sha256("\n".join(entries).encode()).hexdigest()


def load_pin() -> dict:
    return json.loads(PIN_PATH.read_text(encoding="utf-8"))


def runtime_dir(pin: dict) -> Path:
    return ROOT / pin["directory"]


def stamp_path(pin: dict) -> Path:
    return runtime_dir(pin) / STAMP


def verify(pin: dict) -> list[str]:
    """Return a list of problems with the installed runtime."""
    problems: list[str] = []
    target = runtime_dir(pin)
    if not target.is_dir():
        return [f"{pin['directory']}/ is missing"]
    for name in pin["required_files"]:
        if not (target / name).is_file():
            problems.append(f"missing {name}")
    pth = target / PTH_NAME
    if not pth.is_file():
        problems.append(f"missing {PTH_NAME}")
    elif pth.read_text(encoding="utf-8").replace("\r\n", "\n") != PTH_BODY:
        problems.append(f"{PTH_NAME} was not rewritten for this project")
    if not stamp_path(pin).is_file():
        problems.append(f"missing {STAMP}")
    elif json.loads(stamp_path(pin).read_text(encoding="utf-8")).get("sha256") != pin["sha256"]:
        problems.append("installed runtime does not match the pinned archive hash")
    else:
        installed = tree_digest(target)
        if installed != pin["tree_sha256"]:
            problems.append(f"runtime tree hash mismatch: expected {pin['tree_sha256']}, found {installed}")
    if not problems:
        exe = target / "python.exe"
        probe = subprocess.run([str(exe), "-c", "import sqlite3, sys; print(sys.version_info[:2])"],
                               capture_output=True, text=True, timeout=60)
        if probe.returncode != 0:
            problems.append(f"bundled interpreter cannot import sqlite3: {probe.stderr.strip()[:200]}")
    return problems


def download(pin: dict, destination: Path) -> None:
    request = urllib.request.Request(pin["url"], headers={"User-Agent": "goblin-eye-build"})
    with urllib.request.urlopen(request, timeout=300) as response, destination.open("wb") as handle:
        shutil.copyfileobj(response, handle)


def install(pin: dict) -> None:
    target = runtime_dir(pin)
    with tempfile.TemporaryDirectory(prefix="goblin-eye-python-") as work:
        archive = Path(work) / "python-embed.zip"
        if not archive.exists():
            download(pin, archive)
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        if digest != pin["sha256"]:
            raise SystemExit(f"archive hash mismatch\n  expected {pin['sha256']}\n  actual   {digest}")
        if archive.stat().st_size != pin["archive_bytes"]:
            raise SystemExit("archive size does not match the pin")
        with zipfile.ZipFile(archive) as source:
            for member in source.namelist():
                resolved = Path(member)
                if resolved.is_absolute() or ".." in resolved.parts:
                    raise SystemExit(f"unsafe archive member: {member}")
            if target.exists():
                shutil.rmtree(target)
            target.mkdir(parents=True)
            source.extractall(target)
    (target / PTH_NAME).write_text(PTH_BODY, encoding="utf-8", newline="\n")
    (target / STAMP).write_text(json.dumps(
        {"version": pin["version"], "sha256": pin["sha256"], "url": pin["url"], "license": pin["license"]},
        indent=2) + "\n", encoding="utf-8")
    missing = [name for name in pin["required_files"] if not (target / name).is_file()]
    if missing:
        raise SystemExit(f"upstream archive is missing expected files: {missing}")
    installed = tree_digest(target)
    if installed != pin["tree_sha256"]:
        raise SystemExit(f"extracted tree does not match the pin\n  expected {pin['tree_sha256']}\n  actual   {installed}\n"
                         f"Update scripts/python_runtime.json tree_sha256 when changing the pinned Python build.")
    probe = subprocess.run([str(target / "python.exe"), "-c", "import sqlite3; print(sqlite3.sqlite_version)"],
                           capture_output=True, text=True, timeout=60)
    if probe.returncode != 0:
        raise SystemExit(f"bundled interpreter cannot import sqlite3: {probe.stderr.strip()[:300]}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Install or verify the vendored Python runtime")
    parser.add_argument("--check", action="store_true", help="verify the installed runtime without downloading")
    arguments = parser.parse_args()
    pin = load_pin()
    if arguments.check:
        problems = verify(pin)
        if problems:
            for problem in problems:
                print(f"FAIL {problem}")
            return 1
        print(f"OK python {pin['version']} matches the pinned hash and imports sqlite3")
        return 0
    install(pin)
    problems = verify(pin)
    if problems:
        for problem in problems:
            print(f"FAIL {problem}")
        return 1
    print(json.dumps({"installed": pin["directory"], "version": pin["version"], "sha256": pin["sha256"],
                      "files": sum(1 for p in runtime_dir(pin).rglob('*') if p.is_file())}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
