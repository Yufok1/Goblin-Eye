from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import json
from goblin_eye.validation import integer, rate, text


@dataclass(frozen=True)
class Settings:
    display_name: str = "Goblin Eye"
    host: str = "127.0.0.1"
    port: int = 8765
    database_path: str = "data/goblin-eye.db"
    market_key: str = "wow-forever"
    local_faction: str = "unknown"
    local_ruleset: str = "unknown"
    local_region: str = "unknown"
    local_realm: str = "unknown"
    game_build: str | None = None
    economic_period: str = 'unknown'
    auction_cut_rate: float = 0.05
    default_deposit_copper: int = 0
    stale_after_hours: int = 24
    auto_discover_auctionator: bool = True
    auctionator_paths: tuple[str, ...] = ()
    watch_interval_seconds: int = 3
    auto_sync_ahledger: bool = True
    external_refresh_minutes: int = 30
    auto_import_professiondb: bool = True
    professiondb_paths: tuple[str, ...] = ()
    auto_import_foreverguide: bool = True
    foreverguide_paths: tuple[str, ...] = ()
    auto_import_ahledger_scans: bool = True
    ahledger_scan_paths: tuple[str, ...] = ()
    auto_import_alts_forever: bool = True
    alts_forever_paths: tuple[str, ...] = ()
    auto_import_questiedb: bool = True
    questiedb_paths: tuple[str, ...] = ()
    auto_import_mapzeroth: bool = True
    mapzeroth_paths: tuple[str, ...] = ()
    auto_sync_official: bool = True

    @classmethod
    def load(cls, path: Path | None = None) -> "Settings":
        config_path = path or Path("config.json")
        if not config_path.exists():
            return cls()
        values = json.loads(config_path.read_text(encoding="utf-8"))
        if not isinstance(values, dict):
            raise ValueError("Configuration must be an object")
        unknown = values.keys() - cls.__dataclass_fields__.keys()
        if unknown:
            raise ValueError(f"Unknown configuration keys: {sorted(unknown)}")
        selected = dict(values)
        for key in cls.__dataclass_fields__:
            if not key.endswith("_paths"):
                continue
            if key in selected:
                if not isinstance(selected[key], list) or not all(isinstance(p, str) and p.strip() for p in selected[key]):
                    raise ValueError(f"{key} must be an array of path strings")
                selected[key] = tuple(str((config_path.parent / p).resolve()) for p in selected[key])
        if "database_path" in selected:
            text(selected["database_path"], "database_path", 4096)
            selected["database_path"] = str((config_path.parent / selected["database_path"]).resolve())
        return cls(**selected)

    def __post_init__(self):
        for key, choices in (
            ("local_faction", {"unknown", "horde", "alliance", "neutral"}),
            ("local_ruleset", {"unknown", "normal", "pvp", "rp"}),
            ("local_region", {"unknown", "us", "eu", "kr", "tw", "cn"}),
        ):
            if getattr(self, key) not in choices:
                raise ValueError(f"{key} must be one of {sorted(choices)}")
        text(self.local_realm, "local_realm", 256)
        integer(self.port, "port", 1, 65535)
        integer(self.default_deposit_copper, "default_deposit_copper")
        rate(self.auction_cut_rate, "auction_cut_rate")
        for key in ("stale_after_hours", "watch_interval_seconds", "external_refresh_minutes"):
            integer(getattr(self, key), key, 1, 1000000)
        for key in ("display_name", "host", "database_path", "market_key", "economic_period"):
            text(getattr(self, key), key, 4096)
        if self.game_build is not None:
            text(self.game_build, "game_build")
        for key in self.__dataclass_fields__:
            value = getattr(self, key)
            if key.startswith("auto_") and type(value) is not bool:
                raise ValueError(f"{key} must be boolean")
            if key.endswith("_paths") and (not isinstance(value, tuple) or not all(isinstance(p, str) and p.strip() for p in value)):
                raise ValueError(f"{key} must be a tuple of path strings")

    def write_example(self, path: Path) -> None:
        path.write_text(json.dumps(asdict(self), indent=2) + "\n", encoding="utf-8")
