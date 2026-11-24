"""Portable process-local temp/cache settings; never changes Windows settings."""
from __future__ import annotations

import json
import os
from pathlib import Path, PureWindowsPath
import sys


def validate_storage(path: str | Path, *, platform: str = sys.platform) -> None:
    if platform != "win32":
        return
    target = PureWindowsPath(path)
    drive = target.drive.lower()
    if not target.is_absolute() or drive.startswith("\\\\") or drive in {"c:", os.environ.get("SystemDrive", "C:").lower()}:
        raise ValueError("Goblin Eye writable storage must be on D: or another local non-system drive.")


def configure() -> Path:
    package = Path(__file__).resolve().parents[2]
    root = Path(os.environ.get("GOBLIN_EYE_STORAGE_ROOT", str(package / "data" / "runtime")))
    validate_storage(root)
    root = root.absolute()
    spec = json.loads((package / "runtime-storage.json").read_text(encoding="utf-8"))
    for key, relative in spec["directories"].items():
        directory = Path(os.path.abspath(root / relative))
        if not directory.is_relative_to(root):
            raise ValueError("Invalid portable storage directory")
        for ancestor in (directory, *directory.parents):
            if ancestor.is_symlink() or (hasattr(ancestor, "is_junction") and ancestor.is_junction()):
                raise ValueError(f"Storage directory must not be a link: {ancestor}")
        validate_storage(directory.resolve())
        directory.mkdir(parents=True, exist_ok=True)
        if key in {"HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "CODEX_HOME", "GROK_HOME", "CLAUDE_CONFIG_DIR", "XDG_CONFIG_HOME", "XDG_DATA_HOME"} and os.environ.get(key):
            os.environ.setdefault("GOBLIN_EYE_HOST_" + key, os.environ[key])
        os.environ[key] = str(directory)
    os.environ.update(spec["values"])
    os.environ["GOBLIN_EYE_STORAGE_ROOT"] = str(root)
    # tempfile may already have cached its directory in an importing library.
    import tempfile
    tempfile.tempdir = os.environ["TEMP"]
    return root
