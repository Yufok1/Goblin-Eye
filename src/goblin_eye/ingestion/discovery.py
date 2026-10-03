"""Find installed Forever addon data without requiring another addon to exist."""
from pathlib import Path
from typing import Iterable

WOW_ROOTS = tuple(Path(value) for value in (
    r"C:\Program Files (x86)\World of Warcraft", r"C:\Program Files\World of Warcraft",
    r"C:\Games\World of Warcraft", r"D:\World of Warcraft", r"D:\Games\World of Warcraft",
))


def discover_addon_paths(addon: str, marker: str, configured: Iterable[str] = ()) -> list[Path]:
    candidates = {Path(value) for value in configured}
    candidates.update(root / "_classic_beta_" / "Interface" / "AddOns" / addon for root in WOW_ROOTS)
    return sorted({path.resolve() for path in candidates if (path / marker).is_file()}, key=str)


def discover_saved_files(name: str, configured: Iterable[str] = ()) -> list[Path]:
    candidates = {Path(value) for value in configured}
    for root in WOW_ROOTS:
        if root.is_dir():
            candidates.update(root.glob(f"_classic_beta_/WTF/Account/*/SavedVariables/{name}"))
    return sorted({path.resolve() for path in candidates if path.is_file()}, key=str)
