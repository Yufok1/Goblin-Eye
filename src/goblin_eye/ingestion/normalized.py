from __future__ import annotations

import csv
import io
import hashlib
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from goblin_eye.repository import Database
from goblin_eye.assertions import retain
from goblin_eye.validation import timestamp, rate
from .bounded import read_file

from .base import AdapterCapability, ImportResult


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _required(row: dict[str, Any], key: str, context: str) -> Any:
    if key not in row or row[key] in (None, ""):
        raise ValueError(f"Missing required field '{key}' in {context}")
    return row[key]


def _source_id(connection, source_key: str) -> int:
    row = connection.execute(
        "SELECT id FROM sources WHERE source_key = ?", (source_key,)
    ).fetchone()
    if not row:
        raise ValueError(f"Unknown source_key '{source_key}'")
    return int(row["id"])


def _market_id(connection, market_key: str) -> int:
    row = connection.execute(
        "SELECT id FROM markets WHERE market_key = ?", (market_key,)
    ).fetchone()
    if not row:
        raise ValueError(f"Unknown market_key '{market_key}'")
    return int(row["id"])


def _provenance_values(connection, row: dict[str, Any]) -> tuple:
    return (
        _source_id(connection, _required(row, "source_key", "provenance")),
        timestamp(_required(row, "retrieved_at", "provenance")),
        row.get("game_build"),
        row.get("content_phase"),
        rate(_required(row, "confidence", "provenance"), "confidence"),
        _required(row, "evidence_kind", "provenance"),
        row.get("raw_reference"),
    )


class NormalizedJsonAdapter:
    capability = AdapterCapability(
        key="normalized_json",
        display_name="Normalized research JSON",
        status="ready",
        input_types=("JSON",),
        supplies=("static research", "markets", "recipes", "vendors", "mobs", "loot", "spawns", "camps"),
        needs=(),
    )

    def import_file(self, database: Database, path: Path) -> ImportResult:
        data = json.loads(read_file(path).decode("utf-8"))
        if data.get("markets") or data.get("snapshots") or data.get("listings"):
            from goblin_eye.auction_policy import reject_external_auctions
            reject_external_auctions(database)
        source_key = _required(data, "source_key", "normalized research document")
        count = 0
        with database.transaction() as connection:
            for row in data.get("sources", []):
                connection.execute(
                    """INSERT INTO sources(source_key, name, source_type, url, trust_rank, enabled, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(source_key) DO UPDATE SET
                      name=excluded.name, source_type=excluded.source_type, url=excluded.url,
                      trust_rank=excluded.trust_rank, enabled=excluded.enabled, notes=excluded.notes""",
                    (
                        _required(row, "key", "sources"), row["name"], row["source_type"],
                        row.get("url"), row["trust_rank"], int(row.get("enabled", True)), row.get("notes"),
                    ),
                )
                count += 1

            for row in data.get("markets", []):
                p = row["provenance"]
                source_id, retrieved, build, phase, confidence, kind, _ = _provenance_values(connection, p)
                if not retain(connection,'markets',row['key'],source_id,retrieved,confidence,row,build):
                    continue
                connection.execute(
                    """INSERT INTO markets(market_key, name, region, ruleset, faction, is_verified,
                    source_id, retrieved_at, game_build, content_phase, confidence, evidence_kind)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(market_key) DO UPDATE SET name=excluded.name, region=excluded.region,
                    ruleset=excluded.ruleset, faction=excluded.faction, is_verified=excluded.is_verified,
                    source_id=excluded.source_id, retrieved_at=excluded.retrieved_at,
                    game_build=excluded.game_build, content_phase=excluded.content_phase,
                    confidence=excluded.confidence, evidence_kind=excluded.evidence_kind""",
                    (row["key"], row["name"], row["region"], row["ruleset"], row["faction"],
                     int(row.get("is_verified", False)), source_id, retrieved, build, phase, confidence, kind),
                )
                count += 1

            entity_specs = (
                ("items", """INSERT INTO items(id, name, quality, item_class, subclass, stack_size,
                  vendor_buy_copper, vendor_sell_copper, required_level, source_id, retrieved_at,
                  game_build, content_phase, confidence, evidence_kind, raw_reference)
                  VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                  ON CONFLICT(id) DO UPDATE SET name=excluded.name, quality=excluded.quality,
                  item_class=excluded.item_class, subclass=excluded.subclass, stack_size=excluded.stack_size,
                  vendor_buy_copper=excluded.vendor_buy_copper, vendor_sell_copper=excluded.vendor_sell_copper,
                  required_level=excluded.required_level, source_id=excluded.source_id,
                  retrieved_at=excluded.retrieved_at, game_build=excluded.game_build,
                  content_phase=excluded.content_phase, confidence=excluded.confidence,
                  evidence_kind=excluded.evidence_kind, raw_reference=excluded.raw_reference""",
                 lambda r, p: (r["id"], r["name"], r["quality"], r["item_class"], r.get("subclass"),
                               r.get("stack_size", 1), r.get("vendor_buy_copper"), r.get("vendor_sell_copper"),
                               r.get("required_level"), *p)),
                ("recipes", """INSERT INTO recipes(id, name, output_item_id, output_quantity, profession,
                  skill_required, kind, source_id, retrieved_at, game_build, content_phase, confidence,
                  evidence_kind, raw_reference) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                  ON CONFLICT(id) DO UPDATE SET name=excluded.name, output_item_id=excluded.output_item_id,
                  output_quantity=excluded.output_quantity, profession=excluded.profession,
                  skill_required=excluded.skill_required, kind=excluded.kind, source_id=excluded.source_id,
                  retrieved_at=excluded.retrieved_at, game_build=excluded.game_build,
                  content_phase=excluded.content_phase, confidence=excluded.confidence,
                  evidence_kind=excluded.evidence_kind, raw_reference=excluded.raw_reference""",
                 lambda r, p: (r["id"], r["name"], r["output_item_id"], _required(r, "output_quantity", "recipes (unknown output quantity cannot be assumed)"),
                               r["profession"], r.get("skill_required"), r.get("kind", "crafting"), *p)),
                ("vendors", """INSERT INTO vendors(id, name, zone, faction, x, y, source_id, retrieved_at,
                  game_build, content_phase, confidence, evidence_kind, raw_reference)
                  VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                  ON CONFLICT(id) DO UPDATE SET name=excluded.name, zone=excluded.zone,
                  faction=excluded.faction, x=excluded.x, y=excluded.y, source_id=excluded.source_id,
                  retrieved_at=excluded.retrieved_at, game_build=excluded.game_build,
                  content_phase=excluded.content_phase, confidence=excluded.confidence,
                  evidence_kind=excluded.evidence_kind, raw_reference=excluded.raw_reference""",
                 lambda r, p: (r["id"], r["name"], r["zone"], r.get("faction"), r.get("x"), r.get("y"), *p)),
                ("mobs", """INSERT INTO mobs(id, name, min_level, max_level, classification, faction_access,
                  expected_coin_copper, skinning_item_id, skinning_probability, source_id, retrieved_at,
                  game_build, content_phase, confidence, evidence_kind, raw_reference)
                  VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                  ON CONFLICT(id) DO UPDATE SET name=excluded.name, min_level=excluded.min_level,
                  max_level=excluded.max_level, classification=excluded.classification,
                  faction_access=excluded.faction_access, expected_coin_copper=excluded.expected_coin_copper,
                  skinning_item_id=excluded.skinning_item_id, skinning_probability=excluded.skinning_probability,
                  source_id=excluded.source_id, retrieved_at=excluded.retrieved_at,
                  game_build=excluded.game_build, content_phase=excluded.content_phase,
                  confidence=excluded.confidence, evidence_kind=excluded.evidence_kind,
                  raw_reference=excluded.raw_reference""",
                 lambda r, p: (r["id"], r["name"], r["min_level"], r["max_level"],
                               r.get("classification", "normal"), r.get("faction_access"),
                               r.get("expected_coin_copper", 0), r.get("skinning_item_id"),
                               r.get("skinning_probability"), *p)),
                ("spawns", """INSERT INTO spawns(id, mob_id, zone, x, y, respawn_seconds, source_id,
                  retrieved_at, game_build, content_phase, confidence, evidence_kind, raw_reference)
                  VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                  ON CONFLICT(id) DO UPDATE SET mob_id=excluded.mob_id, zone=excluded.zone,
                  x=excluded.x, y=excluded.y, respawn_seconds=excluded.respawn_seconds,
                  source_id=excluded.source_id, retrieved_at=excluded.retrieved_at,
                  game_build=excluded.game_build, content_phase=excluded.content_phase,
                  confidence=excluded.confidence, evidence_kind=excluded.evidence_kind,
                  raw_reference=excluded.raw_reference""",
                 lambda r, p: (r["id"], r["mob_id"], r["zone"], r["x"], r["y"], r.get("respawn_seconds"), *p)),
                ("camps", """INSERT INTO camps(id, name, zone, centroid_x, centroid_y, travel_notes,
                  source_id, retrieved_at, game_build, content_phase, confidence, evidence_kind, raw_reference)
                  VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                  ON CONFLICT(id) DO UPDATE SET name=excluded.name, zone=excluded.zone,
                  centroid_x=excluded.centroid_x, centroid_y=excluded.centroid_y,
                  travel_notes=excluded.travel_notes, source_id=excluded.source_id,
                  retrieved_at=excluded.retrieved_at, game_build=excluded.game_build,
                  content_phase=excluded.content_phase, confidence=excluded.confidence,
                  evidence_kind=excluded.evidence_kind, raw_reference=excluded.raw_reference""",
                 lambda r, p: (r["id"], r["name"], r["zone"], r["centroid_x"], r["centroid_y"],
                               r.get("travel_notes"), *p)),
            )
            for section, sql, values in entity_specs:
                for row in data.get(section, []):
                    p = _provenance_values(connection, row["provenance"])
                    if retain(connection,section,str(row['id']),p[0],p[1],p[4],row,p[2]):
                        connection.execute(sql, values(row, p))
                    count += 1

            for row in data.get("recipe_reagents", []):
                parent = connection.execute("SELECT * FROM recipes WHERE id=?",(row['recipe_id'],)).fetchone()
                provenance = row.get('provenance', {'source_key':source_key,'retrieved_at':_utc_now(),'confidence':parent['confidence'],'evidence_kind':parent['evidence_kind'],'game_build':parent['game_build']})
                p = _provenance_values(connection,provenance)
                key = json.dumps([row[k] for k in ['recipe_id', 'item_id']])
                if not retain(connection,'recipe_reagents',key,p[0],p[1],p[4],row,p[2]):
                    continue
                connection.execute(
                    "INSERT OR REPLACE INTO recipe_reagents(recipe_id, item_id, quantity) VALUES (?, ?, ?)",
                    (row["recipe_id"], row["item_id"], row["quantity"]),
                )
                count += 1
            for row in data.get("vendor_offers", []):
                parent = connection.execute("SELECT * FROM vendors WHERE id=?",(row['vendor_id'],)).fetchone()
                provenance = row.get('provenance', {'source_key':source_key,'retrieved_at':_utc_now(),'confidence':parent['confidence'],'evidence_kind':parent['evidence_kind'],'game_build':parent['game_build']})
                p = _provenance_values(connection,provenance)
                key = json.dumps([row[k] for k in ['vendor_id', 'item_id']])
                if not retain(connection,'vendor_offers',key,p[0],p[1],p[4],row,p[2]):
                    continue
                connection.execute(
                    """INSERT OR REPLACE INTO vendor_offers(vendor_id, item_id, price_copper, quantity,
                    limited_stock, restock_seconds) VALUES (?, ?, ?, ?, ?, ?)""",
                    (row["vendor_id"], row["item_id"], row["price_copper"], row.get("quantity", 1),
                     row.get("limited_stock"), row.get("restock_seconds")),
                )
                count += 1
            for row in data.get("loot_entries", []):
                parent = connection.execute("SELECT * FROM mobs WHERE id=?",(row['mob_id'],)).fetchone()
                provenance = row.get('provenance', {'source_key':source_key,'retrieved_at':_utc_now(),'confidence':parent['confidence'],'evidence_kind':parent['evidence_kind'],'game_build':parent['game_build']})
                p = _provenance_values(connection,provenance)
                key = json.dumps([row[k] for k in ['mob_id', 'item_id']])
                if not retain(connection,'loot_entries',key,p[0],p[1],p[4],row,p[2]):
                    continue
                connection.execute(
                    """INSERT OR REPLACE INTO loot_entries(mob_id, item_id, drop_probability,
                    min_quantity, max_quantity, source_id, retrieved_at, game_build, content_phase,
                    confidence, evidence_kind, raw_reference) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (row["mob_id"], row["item_id"], row["drop_probability"], row.get("min_quantity", 1),
                     row.get("max_quantity", 1), *p),
                )
                count += 1
            for row in data.get("camp_spawns", []):
                parent = connection.execute("SELECT * FROM camps WHERE id=?",(row['camp_id'],)).fetchone()
                provenance = row.get('provenance', {'source_key':source_key,'retrieved_at':_utc_now(),'confidence':parent['confidence'],'evidence_kind':parent['evidence_kind'],'game_build':parent['game_build']})
                p = _provenance_values(connection,provenance)
                key = json.dumps([row[k] for k in ['camp_id', 'spawn_id']])
                if not retain(connection,'camp_spawns',key,p[0],p[1],p[4],row,p[2]):
                    continue
                connection.execute(
                    "INSERT OR REPLACE INTO camp_spawns(camp_id, spawn_id) VALUES (?, ?)",
                    (row["camp_id"], row["spawn_id"]),
                )
                count += 1

            source_id = _source_id(connection, source_key)
            connection.execute(
                """INSERT INTO imports(adapter_key, source_id, started_at, completed_at, status,
                file_name, record_count) VALUES (?, ?, ?, ?, 'complete', ?, ?)""",
                (self.capability.key, source_id, _utc_now(), _utc_now(), path.name, count),
            )
        return ImportResult(self.capability.key, source_key, count, 0)


class CsvSnapshotAdapter:
    capability = AdapterCapability(
        key="snapshot_csv",
        display_name="Normalized auction snapshot CSV",
        status="ready",
        input_types=("CSV",),
        supplies=("auction snapshots", "listings"),
        needs=(),
    )
    required_columns = {
        "snapshot_external_id", "market_key", "captured_at", "source_key", "is_complete",
        "confidence", "evidence_kind", "item_id", "quantity", "stack_size", "buyout_copper",
    }

    def import_file(self, database: Database, path: Path) -> ImportResult:
        from goblin_eye.auction_policy import reject_external_auctions
        reject_external_auctions(database)
        reader = csv.DictReader(io.StringIO(read_file(path).decode('utf-8-sig')))
        missing = self.required_columns - set(reader.fieldnames or [])
        if missing: raise ValueError(f"Snapshot CSV missing columns: {sorted(missing)}")
        rows = list(reader)
        if not rows: raise ValueError("Snapshot CSV contains no listings")
        groups = {}
        metadata = ('market_key','captured_at','source_key','is_complete','confidence','evidence_kind','game_build','economic_period')
        for row in rows:
            row['captured_at'] = timestamp(row['captured_at'])
            if row['is_complete'].lower() not in ('1','0','true','false','yes','no'):
                raise ValueError('Invalid completeness claim')
            key = (row['source_key'],row['market_key'],row['snapshot_external_id'])
            group = groups.setdefault(key,[])
            if group and any(row.get(k)!=group[0].get(k) for k in metadata):
                raise ValueError('Inconsistent metadata within CSV snapshot')
            group.append(row)
        for key, group in groups.items():
            digest=hashlib.sha256(json.dumps(group,sort_keys=True).encode()).hexdigest()
            identity='csv:'+json.dumps(key,separators=(',',':'))+':'+digest
            for row in group: row['snapshot_external_id']=identity
        snapshot_keys: set[str] = set()
        with database.transaction() as connection:
            existing_ids={row[0] for row in connection.execute("SELECT external_id FROM snapshots WHERE external_id LIKE 'csv:%'")}
            for row in rows:
                if row['snapshot_external_id'] in existing_ids: continue
                external_id = row["snapshot_external_id"]
                if external_id not in snapshot_keys:
                    if connection.execute("SELECT 1 FROM snapshots WHERE external_id=?",(external_id,)).fetchone():
                        continue
                    source_id = _source_id(connection, row["source_key"])
                    market_id = _market_id(connection, row["market_key"])
                    connection.execute(
                        """INSERT INTO snapshots(external_id, market_id, captured_at, source_id,
                        game_build, is_complete, confidence, evidence_kind, raw_reference, imported_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
""",
                        (external_id, market_id, row["captured_at"], source_id, row.get("game_build") or None,
                         int(str(row["is_complete"]).lower() in ("1", "true", "yes")),
                         float(row["confidence"]), row["evidence_kind"], row.get("raw_reference") or path.name,
                         _utc_now()),
                    )
                    connection.execute("UPDATE snapshots SET economic_period=? WHERE external_id=?",(row.get('economic_period') or 'unknown',external_id))
                    snapshot_keys.add(external_id)
                    snapshot_id = connection.execute(
                        "SELECT id FROM snapshots WHERE external_id = ?", (external_id,)
                    ).fetchone()["id"]

                snapshot_id = connection.execute(
                    "SELECT id FROM snapshots WHERE external_id = ?", (external_id,)
                ).fetchone()["id"]
                connection.execute(
                    """INSERT INTO listings(snapshot_id, item_id, quantity, stack_size,
                    buyout_copper, bid_copper, time_left, seller_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (snapshot_id, int(row["item_id"]), int(row["quantity"]), int(row["stack_size"]),
                     int(row["buyout_copper"]), int(row["bid_copper"]) if row.get("bid_copper") else None,
                     row.get("time_left") or None, row.get("seller_hash") or None),
                )

            source_id = _source_id(connection, rows[0]["source_key"])
            connection.execute(
                """INSERT INTO imports(adapter_key, source_id, started_at, completed_at, status,
                file_name, record_count) VALUES (?, ?, ?, ?, 'complete', ?, ?)""",
                (self.capability.key, source_id, _utc_now(), _utc_now(), path.name, len(rows)),
            )
        return ImportResult(self.capability.key, rows[0]["source_key"], len(rows), len(snapshot_keys))
