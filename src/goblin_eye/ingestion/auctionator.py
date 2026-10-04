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
from .lua_literals import LuaLiteralReader


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
    # SavedVariables contain arbitrary CBOR bytes, not a UTF-8 text document.
    # Latin-1 preserves those bytes while the literal reader handles Lua escapes.
    reader = LuaLiteralReader(section.decode('latin-1'))
    reader.expect('AUCTIONATOR_PRICE_DATABASE')
    reader.expect('=')
    root = reader.read()
    reader.skip()
    if reader.position != len(reader.text) or not isinstance(root, dict):
        raise ValueError('Invalid Auctionator price database literal')
    if type(root.get('__dbversion')) is not int or root['__dbversion'] != 8:
        raise ValueError("Only inspected Auctionator database version 8 is supported")
    scan_match = re.search(rb'\["TimeOfLastBrowseScan"\]\s*=\s*(\d+)', data[:section_start])
    scan_timestamp = int(scan_match.group(1)) if scan_match else None
    markets: dict[str, dict[str, Any]] = {}
    for raw_key, encoded in root.items():
        if not isinstance(raw_key, str):
            raise ValueError('Invalid Auctionator market key')
        key = raw_key.encode('latin-1').decode('utf-8')
        if key == "__dbversion":
            continue
        if isinstance(encoded, str):
            encoded = encoded.encode('latin-1')
            decoder = CborDecoder(encoded)
            decoded = _text_keys(decoder.decode())
            if decoder.position != len(encoded):
                raise ValueError(f"Auctionator market {key} contains trailing serialized data")
        else:
            decoded = encoded
        if not isinstance(decoded, dict):
            raise ValueError(f"Auctionator market {key} did not decode to a map")
        if decoded.get("version") != 2:
            raise ValueError("Only inspected Auctionator market schema 2 is supported")
        markets[key] = decoded
    if not markets:
        raise ValueError("Auctionator file contains no serialized market databases")
    return AuctionatorCapture(scan_timestamp, root['__dbversion'], markets)


def select_auctionator_markets(markets, profile):
    """Match inspected legacy, normalized-realm and regional ruleset keys.

    Modern keys supply no faction or region. Never derive a ruleset from a
    realm label, and never join different saved buckets into one price series.
    """
    selected, regional, skipped = {}, {}, []
    known_realm = profile['realm'] != 'unknown'
    normalized = lambda value: ''.join(value.split()).casefold()
    rulesets = {'PvP': 'pvp', 'PvE': 'normal', 'RP': 'rp', 'HC': 'hardcore'}
    for key in markets:
        legacy = re.fullmatch(r'(.+) (Horde|Alliance|Neutral)', key)
        if legacy and matches_profile(profile, realm=legacy.group(1), faction=legacy.group(2)):
            selected[key] = (legacy.group(1), legacy.group(2), 'Legacy realm/faction key')
        elif key in rulesets:
            if known_realm and profile['ruleset'] == rulesets[key]:
                regional[key] = (profile['realm'], 'unknown', 'Regional ruleset key matched to explicitly configured local_ruleset; source faction and region are unknown')
            else:
                skipped.append(key)
        elif known_realm and normalized(key) == normalized(profile['realm']):
            selected[key] = (profile['realm'], 'unknown', 'Normalized realm key matched to selected realm; source faction, ruleset and region are unknown')
        else:
            skipped.append(key)
    # Auctionator switches to a regional bucket when regional unique names
    # are enabled. An explicitly matching bucket supersedes old realm storage.
    if regional:
        skipped.extend(selected)
        selected = regional
    if len(selected) > 1:
        raise ValueError('Auctionator contains multiple matching realms/factions and no per-market scan timestamp. Set local_realm and local_faction in config.json, or let a new AHledger scan identify this installation first. Existing evidence was retained.')
    if not selected:
        raise ValueError('No Auctionator market matches this installation. Set local_realm (or import an AHledger scan first); for regional PvP/PvE/RP keys also set local_ruleset explicitly. Saved keys: ' + ', '.join(markets))
    return selected, skipped


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
        notes="Inspected Auctionator 339/340 database version 8, serialized and literal market tables. Modern realm/ruleset keys do not identify faction or region. The addon stores aggregated prices, not raw listings.",
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
            identities, skipped_keys = select_auctionator_markets(capture.markets, market_profile(connection))
            skipped = len(skipped_keys)
            for raw_market, identity in identities.items():
                market_data = capture.markets[raw_market]
                market_id = local_market(connection,source_id,scan_at,
                    realm=identity[0], faction=identity[1])
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
                    doc_id,period=self.economic_period,limitations=[identity[2], ('Changed current prices after reset; unchanged old entries, daily ranges and quantities excluded. Per-item capture time unknown.' if reset_policy else 'Day-level addon summaries; per-item capture time unknown. Quantity is a daily observed high. Not independent individual scan rows.')])
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
                (f'Auctionator database version {capture.database_version}; aggregate price history. Latest file: {market_count} selected market(s). Skipped keys: {", ".join(skipped_keys) or "none"}. Regional PvP/PvE/RP keys require an explicitly selected local_ruleset; no faction or region is inferred.', source_id))
        notes = ((f'Skipped unmatched saved keys: {", ".join(skipped_keys)}.',) if skipped else ())
        return ImportResult(self.capability.key, "local-auctionator", record_count, market_count, notes)


class AuctionatorWatcher:
    def __init__(self, database: Database, paths: Callable[[], list[Path]], interval_seconds: int = 3):
        self.database = database
        self.paths = paths
        self.interval_seconds = max(1, interval_seconds)
        self.adapter = AuctionatorSavedVariablesAdapter()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._seen: dict[Path, tuple] = {}
        self._failed: dict[Path, tuple[tuple, float]] = {}

    def scan_once(self) -> list[ImportResult]:
        imported: list[ImportResult] = []
        with self.database.transaction() as connection:
            profile_signature = tuple(market_profile(connection).values())
        for path in self.paths():
            signature = None
            try:
                stat = path.stat()
                signature = (stat.st_mtime_ns, stat.st_size, profile_signature)
                if self._seen.get(path) == signature:
                    continue
                failed = self._failed.get(path)
                if failed and failed[0] == signature and time.monotonic() < failed[1]:
                    continue
                imported.append(self.adapter.import_file(self.database, path))
                self._seen[path] = signature
                self._failed.pop(path, None)
            except Exception as exc:
                if signature is not None:
                    self._failed[path] = (signature, time.monotonic() + max(60, self.interval_seconds))
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
