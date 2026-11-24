"""Package the existing in-game UI; the complete Windows companion stays separate.

Keep WoWAI's folder, manifest, saved-variable and transport names unchanged so
the installed companion continues to work. Never package an installed AddOns
directory: its Inbox and signal files can contain private runtime state.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import zipfile
from pathlib import Path

# The embedded interpreter's isolated path does not include this script folder.
_spec = importlib.util.spec_from_file_location(
    "goblin_eye_release", Path(__file__).with_name("build_release.py"))
_release = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_release)
ROOT, DIST = _release.ROOT, _release.DIST
audit, project_version, write_member = (
    _release.audit, _release.project_version, _release.write_member)


ADDON = "wow-ai/addon/WoWAI"
# Publish only reviewed repository assets, including the source modules used to
# build WoWAI.lua. Companion setup continues to create its runtime reply slots.
ADDON_FILES = (
    "WoWAI.toc", "Codec.lua", "Inbox.lua", "WoWAI.lua", "Map.lua",
    "Research.lua", "Settings.lua", "Theme.lua", "Prompts.lua", "WoWAI.core.lua",
    "Media/GoblinEye.png", "Media/GoblinEye.tga", "Media/README.md",
)
DOCUMENTS = {
    "LICENSE": "wow-ai/LICENSE",
    "GOBLIN-EYE-LICENSE": "LICENSE",
    "UPSTREAM.md": "wow-ai/UPSTREAM.md",
    "README.md": "docs/CURSEFORGE.md",
}


def collect(root: Path = ROOT) -> dict[str, bytes]:
    source = {f"{ADDON}/{name}": (root / ADDON / name).read_bytes()
              for name in ADDON_FILES}
    source.update({name: (root / name).read_bytes() for name in DOCUMENTS.values()})
    # Reuse the Windows release's privacy/binary audit. Its configuration checks
    # inspect only the clean example; that example is not put in the addon ZIP.
    audit({**source, "config.example.json": (root / "config.example.json").read_bytes()})
    files = {f"WoWAI/{name}": source[f"{ADDON}/{name}"] for name in ADDON_FILES}
    files.update({f"WoWAI/{name}": source[path] for name, path in DOCUMENTS.items()})
    validate(files)
    return files


def validate(files: dict[str, bytes]) -> None:
    expected = {f"WoWAI/{name}" for name in (*ADDON_FILES, *DOCUMENTS)}
    if set(files) != expected:
        raise ValueError("The addon package differs from the reviewed allowlist")
    toc = files["WoWAI/WoWAI.toc"].decode("utf-8-sig")
    if "## Interface: 16001" not in toc.splitlines():
        raise ValueError("Review the target WoW interface before publishing")
    if "## SavedVariables: WoWAIDB, WoWAIMapDB" not in toc.splitlines():
        raise ValueError("Review saved-variable compatibility before publishing")
    for line in toc.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            if f"WoWAI/{line.replace(chr(92), '/')}" not in files:
                raise ValueError(f"Manifest references an unpackaged file: {line}")
    # This repository file is a template. An installed copy is never eligible.
    if files["WoWAI/Inbox.lua"].decode("utf-8").strip() != (
        "-- Runtime replies are written locally by the bridge.\n"
        "WoWAI_Inbox = { replies = {} }"
    ):
        raise ValueError("Inbox.lua must contain only the empty repository template")


def build(destination: Path, root: Path = ROOT) -> dict:
    files = collect(root)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, body in sorted(files.items()):
            write_member(archive, name, body)
    with zipfile.ZipFile(destination) as archive:
        if archive.testzip() is not None or set(archive.namelist()) != set(files):
            raise ValueError("Addon archive integrity check failed")
        for name, body in files.items():
            if archive.read(name) != body:
                raise ValueError(f"Addon archive content differs: {name}")
    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    destination.with_suffix(".zip.sha256").write_text(
        f"{digest}  {destination.name}\n", encoding="ascii")
    report = {
        "archive": destination.name,
        "sha256": digest,
        "files": len(files),
        "archive_integrity": "passed",
        "privacy_allowlist": "passed",
        "manifest_files": "passed",
        "empty_inbox": "passed",
        "addon_folder": "WoWAI",
        "interface": "16001",
        "desktop_companion_required": True,
        "reply_slots": "created locally by Setup-WoWAI.cmd",
        "personal_data_included": False,
        "curseforge_uploaded": False,
        "curseforge_approval": "not submitted",
        "live_game_test": "not performed",
    }
    destination.with_suffix(".validation.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main() -> None:
    archive = DIST / f"Goblin-Eye-{project_version()}-CurseForge.zip"
    print(json.dumps(build(archive), indent=2))


if __name__ == "__main__":
    main()
