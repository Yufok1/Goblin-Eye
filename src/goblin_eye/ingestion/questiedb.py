"""Import complete baked QuestieDB Forever NPC/object spawn metadata."""
from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import zlib

from goblin_eye.repository import Database
from .base import AdapterCapability, ImportResult
from .bounded import read_file
from .cbor_literals import loads as cbor_loads
from .professiondb import positive_id


SOURCE_KEY = "questiedb-forever"
SOURCE_URL = "https://github.com/Questie/QuestieDB"
LIMITATIONS = (
    "Baked QuestieDB Forever metadata is a static source assertion, not a live spawn survey.",
    "Spawn map keys are Questie area IDs and are deliberately not relabeled as UI map IDs.",
    "Coordinates and paths do not supply simultaneous population, respawn timers, kill rates, drop quantities or current phase availability.",
    "The baked artifact includes static corrections; client-time faction-specific dynamic corrections are not applied by this offline import.",
)


def _metadata(text: str) -> dict[str, str]:
    result = dict(re.findall(r"^## ([^:]+):\s*(.*)$", text, re.MULTILINE))
    if len(result) < 100:
        raise ValueError("QuestieDB baked metadata is missing")
    return result


def _stored(metadata: dict[str, str], key: str) -> str | None:
    value = metadata.get(key)
    if value is None:
        return None
    match = re.fullmatch(r"~(\d+)~", value)
    if not match:
        return value
    count = int(match.group(1))
    parts = [metadata.get(f"{key}-{index}") for index in range(1, count + 1)]
    if any(part is None for part in parts):
        raise ValueError(f"Truncated QuestieDB metadata chunks for {key}")
    return "".join(parts)  # type: ignore[arg-type]


def _decode(metadata: dict[str, str], key: str, *, compressed: bool = False):
    stored = _stored(metadata, key)
    if stored is None:
        return None
    try:
        body = base64.b64decode(stored, validate=True)
    except ValueError as error:
        raise ValueError(f"Invalid QuestieDB base64 for {key}") from error
    if compressed:
        body = zlib.decompress(body)
    return cbor_loads(body)


def _text(value):
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return value


def _field_present(row: dict, index: int) -> bool:
    mask = row.get(b"p", row.get("p", 0))
    return isinstance(mask, int) and bool(mask & (1 << (index - 1)))


def _validate_points(value, *, paths: bool = False) -> dict[int, list]:
    if value is None:
        return {}
    if isinstance(value, list):
        value = {index: points for index, points in enumerate(value, 1) if points is not None}
    if not isinstance(value, dict):
        raise ValueError("QuestieDB coordinate field is not grouped by area")
    result = {}
    for raw_area, groups in value.items():
        area = positive_id(raw_area, "Questie area ID")
        if not isinstance(groups, list):
            raise ValueError("QuestieDB coordinate group is not a list")
        paths_to_check = groups if paths else [groups]
        for path in paths_to_check:
            if not isinstance(path, list):
                raise ValueError("QuestieDB coordinate path is not a list")
            for point in path:
                if not isinstance(point, list) or len(point) not in (2, 3):
                    raise ValueError("Unexpected QuestieDB coordinate")
                if any(type(number) not in (int, float) for number in point):
                    raise ValueError("Non-numeric QuestieDB coordinate")
        result[area] = groups
    return result


def parse_questiedb(root: Path) -> dict:
    root = root.resolve()
    toc_path = root / "QuestieDB_Forever.toc"
    body = read_file(toc_path, 80_000_000)
    text = body.decode("utf-8-sig")
    metadata = _metadata(text)
    if metadata.get("Interface") != "16001" or metadata.get("X-Flavor") != "Forever" or metadata.get("X-Mode") != "baked":
        raise ValueError("Unreviewed QuestieDB flavor, interface or storage mode")
    schema = {"Npc": {"count": 15, "spawns": 7, "waypoints": 8},
              "Object": {"count": 7, "spawns": 4, "waypoints": 7}}
    records = []
    counts = {"npc": 0, "object": 0, "npc_with_spawns": 0, "object_with_spawns": 0,
              "npc_with_waypoints": 0, "object_with_waypoints": 0, "spawn_points": 0, "waypoint_points": 0}
    for entity, info in schema.items():
        ids = _decode(metadata, f"X-{entity}-IDS", compressed=True)
        if not isinstance(ids, list) or len(ids) != len(set(ids)):
            raise ValueError(f"Invalid QuestieDB {entity} ID index")
        for entity_id in ids:
            positive_id(entity_id, f"{entity} ID")
            row = _decode(metadata, f"X-{entity}-{entity_id}-S")
            if isinstance(row, list):
                row = {index: value for index, value in enumerate(row, 1) if value is not None}
            if not isinstance(row, dict):
                raise ValueError(f"Missing QuestieDB scalar row for {entity} {entity_id}")
            spawn_index, waypoint_index = info["spawns"], info["waypoints"]
            spawns = _validate_points(_decode(metadata, f"X-{entity}-{entity_id}-{spawn_index}")
                                      if _field_present(row, spawn_index) else None)
            waypoints = _validate_points(_decode(metadata, f"X-{entity}-{entity_id}-{waypoint_index}")
                                         if _field_present(row, waypoint_index) else None, paths=True)
            kind = entity.lower()
            attributes = {
                "area_id": row.get(9 if entity == "Npc" else 5),
                "spawn_area_ids": sorted(spawns), "spawns_by_area": spawns,
                "waypoint_area_ids": sorted(waypoints), "waypoints_by_area": waypoints,
                "spawn_count": sum(len(points) for points in spawns.values()),
                "waypoint_path_count": sum(len(paths) for paths in waypoints.values()),
                "coordinate_system": "Questie area-relative percent",
                "source_fields": {str(index): _text(row[index]) for index in range(1, info["count"] + 1)
                                  if index in row and index not in (spawn_index, waypoint_index)},
            }
            if entity == "Npc":
                attributes.update(min_level=row.get(4), max_level=row.get(5), rank=row.get(6),
                                  faction_id=row.get(12), friendly_to=_text(row.get(13)), sub_name=_text(row.get(14)),
                                  npc_flags=row.get(15))
            else:
                attributes.update(faction_id=row.get(6))
            counts[kind] += 1
            if spawns: counts[f"{kind}_with_spawns"] += 1
            if waypoints: counts[f"{kind}_with_waypoints"] += 1
            counts["spawn_points"] += attributes["spawn_count"]
            counts["waypoint_points"] += sum(len(path) for paths in waypoints.values() for path in paths)
            records.append((kind, entity_id, _text(row.get(1)), json.dumps(attributes, ensure_ascii=False, separators=(",", ":")),
                            f"QuestieDB_Forever.toc#X-{entity}-{entity_id}"))
    return {"root": root, "body": body, "version": metadata.get("Version"), "build_commit": metadata.get("X-BUILD-COMMIT"),
            "build_time": metadata.get("X-BUILD-TIME"), "sha256": hashlib.sha256(body).hexdigest(),
            "records": tuple(records), "counts": counts}


class QuestieDbAdapter:
    capability = AdapterCapability(
        key="questiedb_forever_v1", display_name="QuestieDB Forever spawn graph", status="ready",
        input_types=("installed baked QuestieDB_Forever.toc",),
        supplies=("complete baked NPC/object index", "spawn coordinates", "movement paths", "levels and ranks"),
        needs=("installed QuestieDB Forever package",), documentation_url=SOURCE_URL,
        notes="Area IDs stay distinct from UI map IDs; no respawn time or live population is inferred.")

    def import_file(self, database: Database, path: Path) -> ImportResult:
        data = parse_questiedb(path)
        now = datetime.now(timezone.utc).isoformat()
        with database.transaction() as connection:
            connection.execute("""INSERT INTO sources(source_key,name,source_type,url,trust_rank,notes,last_success_at)
                VALUES (?, 'QuestieDB Forever spawn graph', 'bundled_world_database', ?, 5, ?, ?)
                ON CONFLICT(source_key) DO UPDATE SET last_success_at=excluded.last_success_at,last_error=NULL""",
                (SOURCE_KEY, SOURCE_URL, "Installed static baked metadata; source assertions are not live observations.", now))
            source_id = connection.execute("SELECT id FROM sources WHERE source_key=?", (SOURCE_KEY,)).fetchone()[0]
            existing = connection.execute("""SELECT id,active FROM research_datasets
                WHERE source_id=? AND dataset_key='world-spawns' AND sha256=?""", (source_id, data["sha256"])).fetchone()
            if existing and existing["active"]:
                return ImportResult(self.capability.key, SOURCE_KEY, 0, 0, ("Dataset already imported; unchanged.",))
            connection.execute("UPDATE research_datasets SET active=0 WHERE source_id=? AND dataset_key='world-spawns'", (source_id,))
            if existing:
                connection.execute("UPDATE research_datasets SET active=1 WHERE id=?", (existing["id"],))
                return ImportResult(self.capability.key, SOURCE_KEY, 0, 0, ("Previously imported revision reactivated.",))
            manifest = {"QuestieDB_Forever.toc": {"path": str(data["root"] / "QuestieDB_Forever.toc"),
                "sha256": data["sha256"], "bytes": len(data["body"]), "counts": data["counts"],
                "build_commit": data["build_commit"], "build_time": data["build_time"]}}
            cursor = connection.execute("""INSERT INTO research_datasets(source_id,dataset_key,sha256,source_version,game_build,
                content_phase,retrieved_at,confidence,evidence_kind,manifest_json,limitations_json)
                VALUES (?,'world-spawns',?,?,?,'Forever',?,0.65,'extracted',?,?)""",
                (source_id, data["sha256"], data["version"], data["build_commit"], now,
                 json.dumps(manifest), json.dumps(LIMITATIONS)))
            dataset_id = cursor.lastrowid
            connection.executemany("""INSERT INTO world_entity_facts(dataset_id,entity_type,entity_id,name,attributes_json,raw_reference)
                VALUES (?,?,?,?,?,?)""", ((dataset_id, *row) for row in data["records"]))
            connection.execute("""INSERT OR IGNORE INTO source_documents(source_id,url,retrieved_at,content_type,sha256,body)
                VALUES (?,?,?,'text/plain; charset=utf-8',?,?)""",
                (source_id, (data["root"] / "QuestieDB_Forever.toc").as_uri(), now, data["sha256"], data["body"]))
            connection.execute("""INSERT INTO imports(adapter_key,source_id,started_at,completed_at,status,file_name,record_count)
                VALUES (?,?,?,?,'complete',?,?)""", (self.capability.key, source_id, now, now, str(data["root"]), len(data["records"])))
        return ImportResult(self.capability.key, SOURCE_KEY, len(data["records"]), 0, LIMITATIONS)
