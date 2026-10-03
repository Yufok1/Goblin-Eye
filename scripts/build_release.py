"""Build the deterministic Windows share ZIP from an explicit file allowlist.

The archive is built only from files this repository publishes. It never walks
the working directory wholesale, never imports personal evidence, and never
writes into the source checkout. Identical inputs produce an identical ZIP.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"

ROOT_FILES = (
    ".gitattributes", ".gitignore", "AGENTS.md", "CHANGELOG.md", "CLAUDE.md",
    "CONTRIBUTING.md", "INSTALL-PYTHON.md", "LICENSE", "README.md",
    "REQUIREMENTS.md", "SECURITY.md", "THIRD_PARTY_NOTICES.md",
    "Run-Goblin-Eye.ps1", "Start-Agent.cmd", "Start-Goblin-Eye.cmd",
    "START-HERE.md", "config.example.json", "requirements.txt",
    "pyproject.toml", "package.json", "package-lock.json",
)
ROOT_TREES = ("src", "migrations", "docs", "web/src", "web/public", "web/dist")
# Matched anywhere in a relative path.
EXCLUDED_PARTS = {
    "__pycache__", "node_modules", ".venv", "venv", ".git", ".github", ".idea",
    ".vscode", ".pytest_cache", ".mypy_cache", "data", "tests", "scripts",
    "reports", "packaging", "fixtures", "characters",
}
# Matched only as a top-level directory, so web/dist stays publishable while the
# generated /dist output directory never is.
EXCLUDED_ROOTS = {"dist", "build", "releases"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".pyd", ".db", ".sqlite", ".sqlite3", ".log", ".zip"}
REQUIRED_FILES = (
    "src/goblin_eye/__main__.py",
    "src/goblin_eye/ingestion/static_watcher.py",
    "src/goblin_eye/ingestion/discovery.py",
    "src/goblin_eye/ingestion/foreverguide_dungeons.py",
    "web/dist/assets/main.js",
    "migrations/001_initial.sql",
)

# Absolute machine paths must never reach a public archive. These are structural
# patterns, not personal names, so they stay correct for any contributor.
# Documented WoW client locations such as "C:\Program Files\World of Warcraft"
# are legitimate content in discovery.py and the setup docs, so only user-scoped
# locations are rejected here.
PRIVATE_PATTERNS = (
    (re.compile(rb"\\(?:Users|Documents and Settings|OneDrive)\\[^\\/\r\n]+"), "user profile path"),
    (re.compile(rb"\\\\\\\\[A-Za-z0-9_.-]+\\\\"), "UNC network path"),
    (re.compile(rb"/(?:Users|home|root|Volumes)/[A-Za-z0-9_.-]+/"), "absolute POSIX home path"),
    (re.compile(rb"file:///[A-Za-z]:"), "local file URI"),
)
# Agent-local configuration is matched by name, because .gitignore legitimately
# mentions these paths in order to exclude them.
FORBIDDEN_NAMES = {".mcp.json", ".mcp.jsonc", ".codex", ".claude", "config.json"}
# A fixed DOS timestamp keeps the archive byte-identical across runs.
FIXED_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


def project_version() -> str:
    declared = {}
    init = re.search(r'__version__\s*=\s*"([^"]+)"', (ROOT / "src/goblin_eye/__init__.py").read_text(encoding="utf-8"))
    declared["src/goblin_eye/__init__.py"] = init.group(1) if init else None
    for name in ("pyproject.toml", "package.json", "package-lock.json"):
        body = (ROOT / name).read_text(encoding="utf-8")
        found = re.search(r'^\s*version\s*=\s*"([^"]+)"', body, re.M) if name.endswith(".toml") \
            else re.search(r'"version"\s*:\s*"([^"]+)"', body)
        declared[name] = found.group(1) if found else None
    mismatched = {name: value for name, value in declared.items() if value != declared["pyproject.toml"]}
    if None in declared.values() or mismatched:
        raise SystemExit(f"Version fields disagree; update CHANGELOG.md and every version file: {declared}")
    return declared["pyproject.toml"]


def collect() -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    for name in ROOT_FILES:
        path = ROOT / name
        if not path.is_file():
            raise SystemExit(f"Required release file missing: {name}")
        files[name] = path.read_bytes()
    for tree in ROOT_TREES:
        base = ROOT / tree
        if not base.is_dir():
            raise SystemExit(f"Required release tree missing: {tree}")
        for path in sorted(base.rglob("*")):
            relative = path.relative_to(ROOT)
            if not path.is_file() or EXCLUDED_PARTS.intersection(relative.parts):
                continue
            if path.suffix.lower() in EXCLUDED_SUFFIXES or path.name.endswith(".egg-info"):
                continue
            files[relative.as_posix()] = path.read_bytes()
    missing = [name for name in REQUIRED_FILES if name not in files]
    if missing:
        raise SystemExit(f"Required release file missing: {missing}")
    return files


def audit(files: dict[str, bytes]) -> None:
    for name, body in files.items():
        if EXCLUDED_ROOTS.intersection(Path(name).parts[:1]):
            raise SystemExit(f"Generated directory reached the archive: {name}")
        if EXCLUDED_PARTS.intersection(Path(name).parts):
            raise SystemExit(f"Excluded path reached the archive: {name}")
        if Path(name).name in FORBIDDEN_NAMES or Path(name).parts[0] in FORBIDDEN_NAMES:
            raise SystemExit(f"Local or agent-local state reached the archive: {name}")
        for pattern, description in PRIVATE_PATTERNS:
            if pattern.search(body):
                raise SystemExit(f"{description} found in {name}")
        try:
            body.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise SystemExit(f"{name} is not valid UTF-8 text: {exc}") from None
    settings = json.loads(files["config.example.json"])
    if settings["database_path"] != "data/goblin-eye.db":
        raise SystemExit("config.example.json must keep a relative database_path")
    if any(settings.get(key) for key in settings if key.endswith("_paths")):
        raise SystemExit("config.example.json must not ship configured local paths")
    for key in ("auto_import_questiedb", "auto_import_mapzeroth", "auto_import_foreverguide",
                "auto_import_professiondb", "auto_import_ahledger_scans", "auto_import_alts_forever",
                "auto_discover_auctionator", "auto_sync_ahledger", "auto_sync_official"):
        if settings.get(key) is not True:
            raise SystemExit(f"config.example.json must enable automatic import: {key}")
    for key in ("local_faction", "local_ruleset", "local_region", "local_realm"):
        if settings.get(key) != "unknown":
            raise SystemExit(f"config.example.json must not assert a player's market: {key}")


def write_member(archive: zipfile.ZipFile, name: str, body: bytes) -> None:
    info = zipfile.ZipInfo(name, date_time=FIXED_TIMESTAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    archive.writestr(info, body, compresslevel=9)


def main() -> int:
    version = project_version()
    files = collect()
    audit(files)
    manifest = {
        "application": "Goblin Eye",
        "version": version,
        "edition": "Windows source with prebuilt dashboard; neutral local market profile",
        "requires": "Python >=3.10; Node.js and an AI subscription are not required to run",
        "personal_data_included": False,
        "third_party_addons_included": False,
        "files": {name: {"bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}
                  for name, body in sorted(files.items())},
    }
    files["PACKAGE-MANIFEST.json"] = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")

    DIST.mkdir(parents=True, exist_ok=True)
    archive_path = DIST / f"Goblin-Eye-{version}-Windows.zip"
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, body in sorted(files.items()):
            write_member(archive, f"Goblin-Eye/{name}", body)

    with zipfile.ZipFile(archive_path) as archive:
        if archive.testzip() is not None:
            raise SystemExit("Archive integrity check failed")
        if len(archive.namelist()) != len(files):
            raise SystemExit("Archive member count does not match the manifest")
        for name, details in manifest["files"].items():
            actual = archive.read(f"Goblin-Eye/{name}")
            if hashlib.sha256(actual).hexdigest() != details["sha256"]:
                raise SystemExit(f"Archive content does not match the manifest: {name}")
    checksum = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    archive_path.with_suffix(".zip.sha256").write_text(f"{checksum}  {archive_path.name}\n", encoding="ascii")
    (DIST / "PACKAGE-MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"zip": str(archive_path), "version": version, "bytes": archive_path.stat().st_size,
                      "files": len(files), "sha256": checksum}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())