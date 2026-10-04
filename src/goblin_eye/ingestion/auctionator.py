from __future__ import annotations

from .bounded import read_file, read_stream, resilient_run

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import re
import struct
import threading
import time
from typing import Any, Callable, Iterable

from goblin_eye.repository import Database
from goblin_eye.history import record_capture
from goblin_eye.auction_policy import policy, local_market, market_profile, matches_profile, digest as entry_digest
import json

from .base import AdapterCapability, ImportResult


SCAN_DAY_ZERO = datetime(2020, 1, 1, tzinfo=timezone.utc)


@dataclass(frozen=True)
class AuctionatorCapture:
    scan_timestamp: int | None
    database_version: int
    markets: dict[str, dict[str, Any]]


class CborDecoder:
    def __init__(self, data: bytes):
        self.data = data
        self.position = 0
        self.nodes = 0

    def _read(self, length: int) -> bytes:
        end = self.position + length
        if end > len(self.data):
            raise ValueError("Unexpected end of CBOR data")
        value = self.data[self.position:end]
        self.position = end
        return value

    def _length(self, additional: int) -> int:
        if additional < 24:
            return additional
        sizes = {24: 1, 25: 2, 26: 4, 27: 8}
        if additional not in sizes:
            raise ValueError(f"Unsupported CBOR length marker {additional}")
        return int.from_bytes(self._read(sizes[additional]), "big")

    def decode(self, depth: int = 0) -> Any:
        self.nodes += 1
        if depth > 40 or self.nodes > 2000000:
            raise ValueError("CBOR structure exceeds supported budget")
        initial = self._read(1)[0]
        major, additional = initial >> 5, initial & 31
        if major == 0:
            return self._length(additional)
        if major == 1:
            return -1 - self._length(additional)
        if major in (2, 3):
            raw = self._read(self._length(additional))
            return raw if major == 2 else raw.decode("utf-8")
        if major == 4:
            return [self.decode(depth + 1) for _ in range(self._length(additional))]
        if major == 5:
            result = {}
            for _ in range(self._length(additional)):
                key = self.decode(depth + 1)
                if not isinstance(key, (str, bytes, int)) or key in result:
                    raise ValueError('Unsupported or duplicate CBOR map key')
                result[key] = self.decode(depth + 1)
            return result
        if major == 7:
            if additional == 20:
                return False
            if additional == 21:
                return True
            if additional in (22, 23):
                return None
            if additional == 25:
                return struct.unpack(">e", self._read(2))[0]
            if additional == 26:
                return struct.unpack(">f", self._read(4))[0]
            if additional == 27:
                return struct.unpack(">d", self._read(8))[0]
        raise ValueError(f"Unsupported CBOR major type {major}, marker {additional}")


def _text_keys(value: Any) -> Any:
    """Convert Auctionator's CBOR byte strings into ordinary Python text."""
    if isinstance(value, bytes):
        return value.decode("utf-8")
    if isinstance(value, list):
        return [_text_keys(item) for item in value]
    if isinstance(value, dict):
        return {_text_keys(key): _text_keys(item) for key, item in value.items()}
    return value


def _lua_string(data: bytes, quote_position: int) -> tuple[bytes, int]:
    if data[quote_position] != 34:
        raise ValueError("Expected opening quote")
    output = bytearray()
    index = quote_position + 1
    escapes = {ord("n"): 10, ord("r"): 13, ord("t"): 9, ord("\\"): 92, ord('"'): 34}
    while index < len(data):
        value = data[index]
        if value == 34:
            return bytes(output), index + 1
        if value != 92:
            output.append(value)
            index += 1
            continue
        index += 1
        if index >= len(data):
            raise ValueError("Truncated Lua escape")
        if 48 <= data[index] <= 57:
            digits = data[index:index + 3]
            if len(digits) != 3 or not all(48 <= digit <= 57 for digit in digits):
                raise ValueError("Invalid decimal Lua escape")
            output.append(int(digits.decode("ascii"), 10))
            index += 3
        else:
            output.append(escapes.get(data[index], data[index]))
            index += 1
    raise ValueError("Unterminated Lua string")


def parse_auctionator_file(path: Path, data: bytes | None = None) -> AuctionatorCapture:
    data = read_file(path) if data is None else data
    section_start = data.find(b"AUCTIONATOR_PRICE_DATABASE = {")
    section_end = data.find(b"\nAUCTIONATOR_POSTING_HISTORY", section_start)
    if section_start < 0 or section_end < 0:
        raise ValueError("Auctionator price database section not found")
    section = data[section_start:section_end]
    version_match = re.search(rb'\["__dbversion"\]\s*=\s*(\d+)', section)
    if not version_match:
        raise ValueError("Auctionator database version not found")
    if int(version_match.group(1)) != 8:
        raise ValueError("Only inspected Auctionator database version 8 is supported")
    scan_match = re.search(rb'\["TimeOfLastBrowseScan"\]\s*=\s*(\d+)', data[:section_start])
    scan_timestamp = int(scan_match.group(1)) if scan_match else None
    markets: dict[str, dict[str, Any]] = {}
    entry_pattern = re.compile(rb'\["([^"\\]+)"\]\s*=\s*"')
    for match in entry_pattern.finditer(section):
        key = match.group(1).decode("utf-8")
        if key == "__dbversion":
            continue
        encoded, _ = _lua_string(section, match.end() - 1)
        decoder = CborDecoder(encoded)
        decoded = _text_keys(decoder.decode())
        if decoder.position != len(encoded):
            raise ValueError(f"Auctionator market {key} contains trailing serialized data")
        if not isinstance(decoded, dict):
            raise ValueError(f"Auctionator market {key} did not decode to a map")
        if decoded.get("version") != 2:
            raise ValueError("Only inspected Auctionator market schema 2 is supported")
        markets[key] = decoded
    if not markets:
        raise ValueError("Auctionator file contains no serialized market databases")
    return AuctionatorCapture(scan_timestamp, int(version_match.group(1)), markets)


def discover_auctionator_files(configured: Iterable[str] = ()) -> list[Path]:
    from .discovery import discover_saved_files
    return discover_saved_files("Auctionator.lua", configured)


class AuctionatorSavedVariablesAdapter:
    economic_period = "unknown"
    capability = AdapterCapability(
        key="auctionator_savedvariables_v339",
        display_name="Auctionator SavedVariables",
        status="ready_price_history",
        input_types=("Auctionator.lua SavedVariables",),
        supplies=("observed minimum unit prices", "daily low range", "observed available quantity"),
        needs=("separate raw-listing source for individual auctions and stack sizes",),
        documentation_url="https://www.curseforge.com/wow/addons/auctionator",
        notes="Verified against Auctionator 339 database version 8. The addon stores aggregated prices, not raw listings.",
    )

    def import_file(self, database: Database, path: Path) -> ImportResult:
        body = read_file(path)
        capture = parse_auctionator_file(path, body)
        modified = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
        imported = datetime.now(timezone.utc).isoformat()
        digest = hashlib.sha256(body).hexdigest()
        scan_at = datetime.fromtimestamp(capture.scan_timestamp, timezone.utc).isoformat() if capture.scan_timestamp else modified
        record_count, market_count, skipped = 0, 0, 0
        with database.transaction() as connection:
            reset_policy = policy(connection)
            if reset_policy and (not capture.scan_timestamp or datetime.fromisoformat(scan_at) <= datetime.fromisoformat(reset_policy['reset_at'])):
                return ImportResult(self.capability.key, 'local-auctionator', 0, 0, ('Waiting for a new scan after the auction reset.',))
            connection.execute(
                """INSERT INTO sources(source_key, name, source_type, url, trust_rank, enabled, notes,
                last_success_at, last_error) VALUES ('local-auctionator', 'Local Auctionator scan',
                'local_auction_observation', NULL, 1, 1, ?, ?, NULL)
                ON CONFLICT(source_key) DO UPDATE SET notes=excluded.notes,
                last_success_at=excluded.last_success_at, last_error=NULL""",
                (f"Auctionator database version {capture.database_version}; aggregated price history", imported),
            )
            source_id = connection.execute(
                "SELECT id FROM sources WHERE source_key='local-auctionator'"
            ).fetchone()["id"]
            identities = {}
            for raw_market in capture.markets:
                # Inspected LegacyAH key: GetRealmName() + space + UnitFactionGroup().
                identity = re.fullmatch(r"(.+) (Horde|Alliance|Neutral)", raw_market)
                if not identity:
                    raise ValueError('Unrecognized Auctionator realm/faction key; retaining existing evidence')
                if matches_profile(market_profile(connection), realm=identity.group(1), faction=identity.group(2)):
                    identities[raw_market] = identity
                else:
                    skipped += 1
            if len(identities) > 1:
                raise ValueError('Auctionator contains multiple matching realms/factions and no per-market scan timestamp. Set local_realm and local_faction in config.json, or let a new AHledger scan identify this installation first. Existing evidence was retained.')
            for raw_market, identity in identities.items():
                market_data = capture.markets[raw_market]
                market_id = local_market(connection,source_id,scan_at,
                    realm=identity.group(1), faction=identity.group(2))
                market_count += 1
                if reset_policy:
                    baseline = {r['item_key']:r['digest'] for r in connection.execute(
                        'SELECT item_key,digest FROM auction_reset_baselines WHERE path=? AND raw_market=?',
                        (str(path.resolve()),raw_market))}
                    scan_day = (datetime.fromisoformat(scan_at).date()-SCAN_DAY_ZERO.date()).days
                    market_data = {k:v for k,v in market_data.items() if isinstance(v,dict)
                        and baseline.get(str(k)) != entry_digest(v) and v.get('m') is not None
                        and max((int(d) for field in ('h','l','a') for d in (v.get(field) or {})),default=-1) == scan_day}
                    if not market_data:
                        continue
                    connection.executemany('INSERT OR REPLACE INTO auction_reset_baselines VALUES (?,?,?,?)',
                        ((str(path.resolve()),raw_market,str(k),entry_digest(v)) for k,v in market_data.items()))
                    # Retain newly changed current values, not pre-reset daily extrema or quantities.
                    market_data = {k:{'m':v['m']} for k,v in market_data.items()}
                    archived = dict(raw_market=raw_market,scan_timestamp=capture.scan_timestamp,
                        projection='Changed current prices since reset; daily history and quantities excluded',items=market_data)
                else:
                    archived = market_data
                price_body = json.dumps(archived,sort_keys=True,separators=(',', ':'),allow_nan=False).encode()
                price_hash = hashlib.sha256(price_body).hexdigest()
                reference = "auctionator-price:" + raw_market
                connection.execute("""INSERT OR IGNORE INTO source_documents(source_id,url,retrieved_at,content_type,sha256,body)
                    VALUES (?,?,?,'application/json',?,?)""",(source_id,reference,imported,price_hash,price_body))
                doc_id = connection.execute("SELECT id FROM source_documents WHERE source_id=? AND url=? AND sha256=?",
                    (source_id,reference,price_hash)).fetchone()[0]
                history_points = []
                for item_key, item_data in market_data.items():
                    if item_key == "version" or not isinstance(item_data, dict):
                        continue
                    raw_key = str(item_key)
                    item_match = re.search(r"(?:^|:)(\d+)(?::|$)", raw_key)
                    item_id = int(item_match.group(1)) if item_match else None
                    current_min = item_data.get("m")
                    highs = item_data.get("h") if isinstance(item_data.get("h"), dict) else {}
                    lows = item_data.get("l") if isinstance(item_data.get("l"), dict) else {}
                    available = item_data.get("a") if isinstance(item_data.get("a"), dict) else {}
                    days = ({(datetime.fromisoformat(scan_at).date()-SCAN_DAY_ZERO.date()).days}
                            if reset_policy else set(highs) | set(lows) | set(available))
                    latest_day = max((int(value) for value in days), default=None)
                    for day_value in days:
                        day = int(day_value)
                        high = highs.get(day_value)
                        low = lows.get(day_value, high)
                        observed_date = (SCAN_DAY_ZERO + timedelta(days=day)).date().isoformat()
                        connection.execute(
                            """INSERT INTO price_observations(source_id, market_id, item_key, item_id,
                            scan_day, observed_date, imported_at, source_modified_at,
                            current_min_unit_copper, daily_min_unit_copper, daily_max_low_unit_copper,
                            available_quantity, confidence, evidence_kind, raw_reference)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0.95, 'observed', ?)
                            ON CONFLICT(source_id, market_id, item_key, scan_day) DO UPDATE SET
                            imported_at=excluded.imported_at, source_modified_at=excluded.source_modified_at,
                            current_min_unit_copper=excluded.current_min_unit_copper,
                            daily_min_unit_copper=excluded.daily_min_unit_copper,
                            daily_max_low_unit_copper=excluded.daily_max_low_unit_copper,
                            available_quantity=excluded.available_quantity""",
                            (source_id, market_id, raw_key, item_id, day, observed_date, imported, modified,
                             current_min if day == latest_day else None, low, high,
                             available.get(day_value), str(path)),
                        )
                        history_points.append(dict(item_key=raw_key,item_id=item_id,observed_date=observed_date,
                            minimum_copper=current_min if day == latest_day else None,
                            available_quantity=available.get(day_value),daily_low_copper=low,daily_high_low_copper=high))
                        record_count += 1
                record_capture(connection,source_id,market_id,price_hash,None,imported,'daily_capture',history_points,
                    doc_id,period=self.economic_period,limitations=[('Changed current prices after reset; unchanged old entries, daily ranges and quantities excluded. Per-item capture time unknown.' if reset_policy else 'Day-level addon summaries; per-item capture time unknown. Quantity is a daily observed high. Not independent individual scan rows.')])
            connection.execute(
                """INSERT INTO watched_files(path, adapter_key, last_modified_at, last_hash,
                last_import_at, last_status, last_error) VALUES (?, ?, ?, ?, ?, 'complete', NULL)
                ON CONFLICT(path) DO UPDATE SET last_modified_at=excluded.last_modified_at,
                last_hash=excluded.last_hash, last_import_at=excluded.last_import_at,
                last_status='complete', last_error=NULL""",
                (str(path), self.capability.key, modified, digest, imported),
            )
            connection.execute(
                """INSERT INTO imports(adapter_key, source_id, started_at, completed_at, status,
                file_name, record_count) VALUES (?, ?, ?, ?, 'complete', ?, ?)""",
                (self.capability.key, source_id, imported, imported, path.name, record_count),
            )
            connection.execute('UPDATE sources SET notes=? WHERE id=?',
                (f'Auctionator database version {capture.database_version}; aggregate price history. Latest file: {market_count} selected market(s), {skipped} other-market market(s) skipped.', source_id))
        notes = ((f'Skipped {skipped} market(s) belonging to other realms/factions; use a separate installation for them.',) if skipped else ())
        return ImportResult(self.capability.key, "local-auctionator", record_count, market_count, notes)


class AuctionatorWatcher:
    def __init__(self, database: Database, paths: Callable[[], list[Path]], interval_seconds: int = 3):
        self.database = database
        self.paths = paths
        self.interval_seconds = max(1, interval_seconds)
        self.adapter = AuctionatorSavedVariablesAdapter()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._seen: dict[Path, tuple[int, int]] = {}

    def scan_once(self) -> list[ImportResult]:
        imported: list[ImportResult] = []
        for path in self.paths():
            try:
                stat = path.stat()
                signature = (stat.st_mtime_ns, stat.st_size)
                if self._seen.get(path) == signature:
                    continue
                imported.append(self.adapter.import_file(self.database, path))
                self._seen[path] = signature
            except Exception as exc:
                with self.database.transaction() as connection:
                    connection.execute(
                        """INSERT INTO watched_files(path, adapter_key, last_status, last_error)
                        VALUES (?, ?, 'error', ?) ON CONFLICT(path) DO UPDATE SET
                        last_status='error', last_error=excluded.last_error""",
                        (str(path), self.adapter.capability.key, str(exc)),
                    )
        return imported

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="auctionator-watcher", daemon=True)
        self._thread.start()

    @resilient_run
    def _run(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            self.scan_once()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=self.interval_seconds + 1)
