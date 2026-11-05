"""Find installed Forever addon data without requiring another addon to exist."""
from pathlib import Path
from typing import Iterable

WOW_ROOTS = tuple(Path(value) for value in (
    r"C:\Program Files (x86)\World of Warcraft", r"C:\Program Files\World of Warcraft",
    r"C:\Games\World of Warcraft", r"D:\World of Warcraft", r"D:\Games\World of Warcraft",
))


def discover_clients() -> list[Path]:
    """Prefer live per install root; never fill missing live sources from beta."""
    clients = []
    for root in WOW_ROOTS:
        live = root / "_forever_"
        beta = root / "_classic_beta_"
        if live.is_dir():
            clients.append(live)
        elif beta.is_dir():
            clients.append(beta)
    return clients


def discover_addon_paths(addon: str, marker: str, configured: Iterable[str] = ()) -> list[Path]:
    candidates = {Path(value) for value in configured}
    if not candidates:
        candidates.update(client / "Interface" / "AddOns" / addon for client in discover_clients())
    return sorted({path.resolve() for path in candidates if (path / marker).is_file()}, key=str)


def discover_saved_files(name: str, configured: Iterable[str] = ()) -> list[Path]:
    candidates = {Path(value) for value in configured}
    if not candidates:
        for client in discover_clients():
            candidates.update(client.glob(f"WTF/Account/*/SavedVariables/{name}"))
    return sorted({path.resolve() for path in candidates if path.is_file()}, key=str)
