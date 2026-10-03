"""Inspected AHledger DB v2 scan section only; no settings, bags, or telemetry import."""
from __future__ import annotations

from .bounded import read_file, read_stream, resilient_run

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import threading
from goblin_eye.auction_policy import policy, local_market

from goblin_eye.repository import Database
from .auctionator import discover_auctionator_files
from .base import AdapterCapability, ImportResult
from .lua_literals import LuaLiteralReader

SOURCE_KEY = "local-ahledger"
LIMITATIONS = (
    "Zero buyout means no buyout, not a free item. The bid field is retained as supplied by the addon.",
    "The source claims a full scan but does not retain its skipped-row count; completeness is unverified.",
    "Gear suffixes, variants, sellers and persistent auction IDs are absent; identical rows remain separate listings.",
    "Time-left values are source category codes, not exact expiration times. Listings do not establish completed sales.",
)


def parse_scan_file(path: Path) -> list[dict]:
    if path.stat().st_size > 50_000_000:
        raise ValueError("Saved scan exceeds supported file size")
    text = read_file(path, 50_000_000).decode("utf-8-sig")
    if not re.match(r"\s*AHledgerDB\s*=\s*\{", text):
        raise ValueError("Missing AHledgerDB root")
    versions = re.findall(r'^\["version"\]\s*=\s*(\d+),?\s*$', text, re.MULTILINE)
    if versions != ["2"]:
        raise ValueError("Only inspected AHledger database version 2 is supported")
    matches = list(re.finditer(r'^\["scans"\]\s*=\s*', text, re.MULTILINE))
    if len(matches) != 1:
        raise ValueError("Expected a single AHledger scans section")
    reader = LuaLiteralReader(text, matches[0].end())
    section = reader.read()
    if not isinstance(section, dict) or set(section) != set(range(1, len(section) + 1)):
        raise ValueError("Expected sequential saved scans")
    scans = []
    for raw in section.values():
        required = {"realm", "faction", "region", "ts", "build", "addon", "full", "count", "data"}
        if not isinstance(raw, dict) or set(raw) != required:
            raise ValueError("Unreviewed scan schema")
        if type(raw["ts"]) is not int or raw["ts"] <= 0 or type(raw["count"]) is not int or raw["count"] <= 0:
            raise ValueError("Invalid scan timestamp or count")
        if type(raw["full"]) is not bool:
            raise ValueError("Invalid completeness claim")
        if any(not isinstance(raw[key], str) or not raw[key] for key in ("realm", "faction", "region", "build", "addon", "data")):
            raise ValueError("Missing scan identity")
        if raw["faction"] not in ("Alliance", "Horde", "unknown"):
            raise ValueError("Unexpected faction value")
        rows = []
        for token in raw["data"].split(";"):
            if not re.fullmatch(r"\d+:\d+:\d+:\d+:[0-4]", token):
                raise ValueError("Unsupported packed auction row")
            row = tuple(int(value) for value in token.split(":"))
            if row[0] <= 0 or row[1] <= 0 or any(value > 2**63 - 1 for value in row):
                raise ValueError("Invalid item, quantity or integer overflow")
            rows.append(row)
        if len(rows) != raw["count"]:
            raise ValueError("Auction row count does not match saved scan count")
        scans.append({"source": raw, "rows": rows})
    return scans


class LocalAHLedgerAdapter:
    economic_period = "unknown"
    capability = AdapterCapability(
        key="ahledger_saved_scans_v2", display_name="Local AHledger auction rows", status="ready",
        input_types=("AHledger.lua database v2 scan section",),
        supplies=("individual auction rows", "stack quantities", "buyout and bid amounts", "scan identity and timestamp"),
        needs=("real saved AHledger scan",), documentation_url="https://www.curseforge.com/wow/addons/ahledger",
        notes="Verified against local addon 0.4.6. No uploads; no inventory or settings import; scan completeness unverified.")

    def import_file(self, database: Database, path: Path) -> ImportResult:
        scans = parse_scan_file(path)
        now = datetime.now(timezone.utc).isoformat()
        count, imported = 0, 0
        with database.transaction() as connection:
            connection.execute("""INSERT INTO sources(source_key,name,source_type,url,trust_rank,notes,last_success_at)
                VALUES (?, 'Local AHledger scans', 'local_addon', ?, 1, ?, ?)
                ON CONFLICT(source_key) DO UPDATE SET last_success_at=excluded.last_success_at,last_error=NULL""",
                (SOURCE_KEY,self.capability.documentation_url,"Only saved auction scans; region unknown remains unknown; no transactions.",now))
            source_id = connection.execute("SELECT id FROM sources WHERE source_key=?",(SOURCE_KEY,)).fetchone()[0]
            for scan in scans:
                raw = scan["source"]
                captured = datetime.fromtimestamp(raw["ts"],timezone.utc).isoformat()
                body = json.dumps(raw,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode("utf-8")
                digest = hashlib.sha256(body).hexdigest()
                p = policy(connection)
                if p and datetime.fromisoformat(captured) <= datetime.fromisoformat(p['reset_at']):
                    continue
                market_id = local_market(connection,source_id,now,raw['build'], faction=raw['faction'], region=raw['region'], realm=raw['realm'])
                external_id = f"ahledger-local:{raw['ts']}:{digest}"
                if connection.execute("SELECT 1 FROM snapshots WHERE external_id=?",(external_id,)).fetchone():
                    continue
                reference = path.resolve().as_uri()+f"#scan/{raw['ts']}/{digest}"
                cursor = connection.execute("""INSERT INTO snapshots(external_id,market_id,captured_at,source_id,game_build,
                    is_complete,confidence,evidence_kind,raw_reference,imported_at,source_complete_claim)
                    VALUES (?,?,?,?,?,0,0.9,'observed',?,?,?)""",
                    (external_id,market_id,captured,source_id,raw["build"],reference,now,int(raw["full"])))
                snapshot_id = cursor.lastrowid
                connection.execute("UPDATE snapshots SET economic_period=? WHERE id=?",(self.economic_period,snapshot_id))
                connection.executemany("""INSERT INTO auction_rows(snapshot_id,ordinal,item_id,quantity,buyout_copper,bid_copper,time_left_code)
                    VALUES (?,?,?,?,?,?,?)""", ((snapshot_id,index,*row) for index,row in enumerate(scan["rows"],1)))
                connection.execute("""INSERT OR IGNORE INTO source_documents(source_id,url,retrieved_at,content_type,sha256,body)
                    VALUES (?,?,?,'application/json',?,?)""",(source_id,reference,now,digest,body))
                count += len(scan["rows"])
                imported += 1
            if imported:
                connection.execute("""INSERT INTO imports(adapter_key,source_id,started_at,completed_at,status,file_name,record_count)
                    VALUES (?,?,?,?,'complete',?,?)""",(self.capability.key,source_id,now,now,str(path),count))
        return ImportResult(self.capability.key,SOURCE_KEY,count,imported,LIMITATIONS)


def discover_local_scans(configured: tuple[str,...] = ()) -> list[Path]:
    from .discovery import discover_saved_files
    candidates = {Path(path) for path in configured}
    candidates.update(path.with_name("AHledger.lua") for path in discover_auctionator_files())
    return discover_saved_files("AHledger.lua", candidates)


class LocalAHLedgerWatcher:
    def __init__(self,database:Database,paths:tuple[str,...]=(),interval:int=3):
        self.database,self.paths,self.interval = database,paths,max(3,interval)
        self._signatures = {}
        self._stop = threading.Event()
        self._thread = None

    def scan_once(self):
        results = []
        for path in discover_local_scans(self.paths):
            try:
                stat = path.stat()
                signature = (stat.st_mtime_ns,stat.st_size)
                if self._signatures.get(str(path)) == signature:
                    continue
                adapter = LocalAHLedgerAdapter()
                adapter.economic_period = getattr(self,"economic_period","unknown")
                results.append(adapter.import_file(self.database,path))
                self._signatures[str(path)] = signature
            except Exception as exc:
                import logging
                logging.exception("Source path failed: %s", path)
                try:
                    with self.database.transaction() as connection:
                        connection.execute("""INSERT INTO sources(source_key,name,source_type,trust_rank,last_error)
                            VALUES (?,'Local AHledger scans','local_addon',1,?)
                            ON CONFLICT(source_key) DO UPDATE SET last_error=excluded.last_error""", (SOURCE_KEY,str(exc)))
                except Exception:
                    logging.exception("Could not record source error")
        return results


    @resilient_run
    def _run(self):
        while not self._stop.is_set():
            try:
                self.scan_once()
            except Exception as exc:
                with self.database.transaction() as connection:
                    connection.execute("""INSERT INTO sources(source_key,name,source_type,trust_rank,last_error)
                        VALUES (?,'Local AHledger scans','local_addon',1,?)
                        ON CONFLICT(source_key) DO UPDATE SET last_error=excluded.last_error""",(SOURCE_KEY,str(exc)))
            self._stop.wait(self.interval)

    def start(self):
        self._thread = threading.Thread(target=self._run,name="local-ahledger-watcher",daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)
