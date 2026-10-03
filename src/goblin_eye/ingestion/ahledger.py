from __future__ import annotations

from .bounded import read_file, read_stream, resilient_run

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import threading
from typing import Any
from urllib.parse import urlencode
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from goblin_eye.repository import Database
from goblin_eye.history import parse_price_table, public_capture
from goblin_eye.assertions import retain, identity_facts

from .auctionator import SCAN_DAY_ZERO
from .base import AdapterCapability, ImportResult


BASE_URL = "https://api.ahledger.com"


@dataclass(frozen=True)
class Download:
    url: str
    body: bytes
    content_type: str | None
    cache_control: str | None


def _download(path: str) -> Download:
    url = f"{BASE_URL}{path}"
    request = Request(url, headers={"User-Agent": "Goblin-Eye/0.1 (+local research; attribution: https://ahledger.com)"})
    with urlopen(request, timeout=30) as response:
        return Download(url, read_stream(response), response.headers.get("Content-Type"), response.headers.get("Cache-Control"))


def _optional_int(value: str) -> int | None:
    return int(value) if value else None


class AHLedgerPublicApiAdapter:
    economic_period = "unknown"
    capability = AdapterCapability(
        key="ahledger_public_api_v1",
        display_name="AHledger public API",
        status="ready",
        input_types=("documented public API v1",),
        supplies=("Forever market identities", "market price tables", "item identities", "historical reference fields"),
        needs=(),
        documentation_url="https://ahledger.com/developers",
        notes="No key required at the public rate. Cached locally with AHledger attribution.",
    )

    def sync(self, database: Database) -> ImportResult:
        retrieved = datetime.now(timezone.utc).isoformat()
        downloads: list[Download] = []
        markets_download = _download("/v1/markets")
        downloads.append(markets_download)
        market_payload = json.loads(markets_download.body)
        markets = [market for market in market_payload.get("markets", []) if market.get("game") == "forever"]

        if not markets:
            raise ValueError("AHledger supplied no Forever markets; retaining previous evidence")

        price_tables: list[tuple[dict[str, Any], Download, int, list[list[str]]]] = []
        item_ids: set[int] = set()
        for market in markets:
            download = _download(f"/v1/pricetable/{market['id']}")
            downloads.append(download)
            _, observed, rows = parse_price_table(download.body, market['id'])
            observed_timestamp = int(datetime.fromisoformat(observed).timestamp())
            item_ids.update(int(row[0]) for row in rows)
            price_tables.append((market, download, observed_timestamp, rows))

        with database.transaction() as connection:
            item_ids.update(row[0] for row in connection.execute(
                """SELECT DISTINCT po.item_id FROM price_observations po
                JOIN sources s ON s.id=po.source_id
                WHERE s.source_key='local-auctionator' AND po.item_id IS NOT NULL"""
            ))

        item_records: list[tuple[dict[str, Any], str]] = []
        # This endpoint is used for item identity only, not a preferred player market.
        tooltip_market = sorted(m["id"] for m in markets)[0]
        ordered_ids = sorted(item_ids)
        for offset in range(0, len(ordered_ids), 100):
            batch = ordered_ids[offset:offset + 100]
            path = f"/v1/tooltip/{tooltip_market}?{urlencode({'items': ','.join(map(str, batch))})}"
            download = _download(path)
            downloads.append(download)
            payload = json.loads(download.body)
            item_records.extend((item, download.url) for item in payload.get("items", []))
        resolved_ids = {int(item["id"]) for item, _ in item_records}
        for item_id in sorted(item_ids - resolved_ids):
            try:
                download = _download(f"/v1/items/{item_id}?game=forever")
            except HTTPError as exc:
                if exc.code == 404:
                    continue
                raise
            downloads.append(download)
            item = json.loads(download.body)
            if item.get("id"):
                item_records.append((item, download.url))

        with database.transaction() as connection:
            connection.execute(
                """INSERT INTO sources(source_key, name, source_type, url, trust_rank, enabled, notes,
                last_success_at, last_error) VALUES ('ahledger', 'AHledger Forever community prices', 'community_api',
                'https://ahledger.com/', 4, 1, ?, ?, NULL)
                ON CONFLICT(source_key) DO UPDATE SET name=excluded.name,enabled=1,notes=excluded.notes,
                last_success_at=excluded.last_success_at, last_error=NULL""",
                ("Documented public API v1; attribution required", retrieved),
            )
            source_id = connection.execute("SELECT id FROM sources WHERE source_key='ahledger'").fetchone()["id"]
            for download in downloads:
                digest = hashlib.sha256(download.body).hexdigest()
                connection.execute(
                    """INSERT OR IGNORE INTO source_documents(source_id, url, retrieved_at, content_type,
                    cache_control, sha256, body) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (source_id, download.url, retrieved, download.content_type, download.cache_control, digest, download.body),
                )

            record_count = 0
            for market, download, observed_timestamp, rows in price_tables:
                observed = datetime.fromtimestamp(observed_timestamp, timezone.utc)
                scan_day = (observed.date() - SCAN_DAY_ZERO.date()).days
                connection.execute(
                    """INSERT INTO markets(market_key, name, region, ruleset, faction, is_verified,
                    source_id, retrieved_at, game_build, content_phase, confidence, evidence_kind)
                    VALUES (?, ?, ?, ?, ?, 0, ?, ?, NULL, 'Forever beta', 0.85, 'observed')
                    ON CONFLICT(market_key) DO UPDATE SET name=excluded.name, region=excluded.region,
                    ruleset=excluded.ruleset, faction=excluded.faction, source_id=excluded.source_id,
                    retrieved_at=excluded.retrieved_at, confidence=excluded.confidence""",
                    (market["id"], "WoW Forever · " + market["label"] + " (community)", market["region"], market["ruleset"], market["faction"], source_id, retrieved),
                )
                market_id = connection.execute("SELECT id FROM markets WHERE market_key=?", (market["id"],)).fetchone()["id"]
                doc = connection.execute("SELECT id FROM source_documents WHERE source_id=? AND url=? AND sha256=?",
                    (source_id,download.url,hashlib.sha256(download.body).hexdigest())).fetchone()[0]
                public_capture(connection,source_id,market_id,doc,download.body,retrieved,period=self.economic_period)
                for row in rows:
                    item_id, median, minimum, quantity, median7, median30, low30, high30 = (
                        int(row[0]), _optional_int(row[1]), _optional_int(row[2]), _optional_int(row[3]),
                        _optional_int(row[4]), _optional_int(row[5]), _optional_int(row[6]), _optional_int(row[7])
                    )
                    connection.execute(
                        """INSERT INTO price_observations(source_id, market_id, item_key, item_id,
                        scan_day, observed_date, imported_at, source_modified_at,
                        current_min_unit_copper, daily_min_unit_copper, daily_max_low_unit_copper,
                        available_quantity, confidence, evidence_kind, raw_reference, median_unit_copper,
                        median_7d_copper, median_30d_copper, low_30d_copper, high_30d_copper)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, 0.85, 'observed', ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(source_id, market_id, item_key, scan_day) DO UPDATE SET
                        imported_at=excluded.imported_at, source_modified_at=excluded.source_modified_at,
                        current_min_unit_copper=excluded.current_min_unit_copper,
                        available_quantity=excluded.available_quantity, median_unit_copper=excluded.median_unit_copper,
                        median_7d_copper=excluded.median_7d_copper, median_30d_copper=excluded.median_30d_copper,
                        low_30d_copper=excluded.low_30d_copper, high_30d_copper=excluded.high_30d_copper""",
                        (source_id, market_id, str(item_id), item_id, scan_day, observed.date().isoformat(),
                         retrieved, observed.isoformat(), minimum, quantity, download.url, median,
                         median7, median30, low30, high30),
                    )
                    record_count += 1

            for item, reference in item_records:
                previous = connection.execute('SELECT * FROM item_observations WHERE source_id=? AND item_id=?',(source_id,item['id'])).fetchone()
                if previous:
                    old = dict(previous)
                    retained = {**identity_facts(old), 'raw_reference': old['raw_reference']}
                    retain(connection,'item_identity',str(item['id']),source_id,old['retrieved_at'],old['confidence'],retained,old['game_build'])
                retain(connection,'item_identity',str(item['id']),source_id,retrieved,.85,
                       {**identity_facts({'source_record':item}), 'raw_reference':reference})
                connection.execute(
                    """INSERT INTO item_observations(source_id, item_id, name, quality, item_class,
                    item_subclass, item_level, required_level, vendor_sell_copper, icon_url,
                    retrieved_at, content_phase, confidence, evidence_kind, raw_reference)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Forever beta', 0.85, 'extracted', ?)
                    ON CONFLICT(source_id, item_id) DO UPDATE SET name=excluded.name,
                    quality=excluded.quality, item_class=excluded.item_class,
                    item_subclass=COALESCE(excluded.item_subclass, item_observations.item_subclass),
                    item_level=excluded.item_level,
                    required_level=COALESCE(excluded.required_level, item_observations.required_level),
                    vendor_sell_copper=COALESCE(excluded.vendor_sell_copper, item_observations.vendor_sell_copper),
                    icon_url=excluded.icon_url, retrieved_at=excluded.retrieved_at,
                    confidence=excluded.confidence, raw_reference=excluded.raw_reference""",
                    (source_id, item["id"], item["name"], item.get("quality"), item.get("itemClass"),
                     item.get("itemSubclass"), item.get("level"), item.get("requiredLevel"),
                     item.get("vendorSell"), item.get("icon"), retrieved, reference),
                )

            connection.execute(
                """INSERT INTO imports(adapter_key, source_id, started_at, completed_at, status,
                file_name, record_count) VALUES (?, ?, ?, ?, 'complete', NULL, ?)""",
                (self.capability.key, source_id, retrieved, datetime.now(timezone.utc).isoformat(), record_count + len(item_records)),
            )
        return ImportResult(self.capability.key, "ahledger", record_count + len(item_records), len(price_tables))


class AHLedgerWatcher:
    def __init__(self, database: Database, refresh_minutes: int = 30):
        self.database = database
        self.refresh_seconds = max(60, refresh_minutes * 60)
        self.adapter = AHLedgerPublicApiAdapter()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="ahledger-watcher", daemon=True)
        self._thread.start()

    @resilient_run
    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.adapter.sync(self.database)
            except Exception as exc:
                now = datetime.now(timezone.utc).isoformat()
                with self.database.transaction() as connection:
                    connection.execute(
                        """INSERT INTO sources(source_key, name, source_type, url, trust_rank, enabled,
                        notes, last_success_at, last_error) VALUES ('ahledger', 'AHledger Forever community prices', 'community_api',
                        'https://ahledger.com/', 4, 1, 'Documented public API v1', NULL, ?)
                        ON CONFLICT(source_key) DO UPDATE SET last_error=excluded.last_error""", (f"{now}: {exc}",)
                    )
            if self._stop.wait(self.refresh_seconds):
                break

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
