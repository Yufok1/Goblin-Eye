from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

from goblin_eye.repository import Database


class AdapterNotReadyError(RuntimeError):
    """Raised when an adapter lacks a verified schema or required configuration."""


@dataclass(frozen=True)
class AdapterCapability:
    key: str
    display_name: str
    status: str
    input_types: tuple[str, ...]
    supplies: tuple[str, ...]
    needs: tuple[str, ...]
    documentation_url: str | None = None
    notes: str | None = None

    def to_dict(self) -> dict:
        result = asdict(self)
        result["input_types"] = list(self.input_types)
        result["supplies"] = list(self.supplies)
        result["needs"] = list(self.needs)
        return result


@dataclass(frozen=True)
class ImportResult:
    adapter_key: str
    source_key: str
    records: int
    snapshots: int
    warnings: tuple[str, ...] = ()


class ImportAdapter(Protocol):
    capability: AdapterCapability

    def import_file(self, database: Database, path: Path) -> ImportResult: ...

