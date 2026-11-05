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
AREA_MAP_FILE = "support/Forever/Zones/areaIdToUiMapId.lua"
QUEST_FIELDS = ('name startedBy finishedBy requiredLevel questLevel requiredRaces requiredClasses '
    'objectivesText triggerEnd objectives sourceItemId preQuestGroup preQuestSingle childQuests '
    'inGroupWith exclusiveTo zoneOrSort requiredSkill requiredMinRep requiredMaxRep requiredSourceItems '
    'nextQuestInChain questFlags specialFlags parentQuest reputationReward breadcrumbForQuestId '
    'breadcrumbs extraObjectives requiredSpell requiredSpecialization requiredMaxLevel '
    'availableUntilCompleted availableStartingWith requiredRanks disabledByQuest').split()
LIMITATIONS = (
    "Baked QuestieDB Forever metadata is a static source assertion, not a live spawn survey.",
    "Spawn map keys are Questie area IDs and are deliberately not relabeled as UI map IDs.",
    "Coordinates and paths do not supply simultaneous population, respawn timers, kill rates, drop quantities or current phase availability.",
    "The baked artifact includes static corrections; client-time faction-specific dynamic corrections are not applied by this offline import.",
    "Quest requirements and objectives are static assertions, not the active quest log or proof of current eligibility. Positive zoneOrSort values are area IDs; negative values are quest categories.",
    "UI map associations come from the installed Forever area mapping; original area IDs and area-relative coordinates are preserved. No coordinate conversion is performed.",
)


def _metadata(text: str) -> dict[str, str]:
    result = {key: value.strip() for key,value in re.findall(r"^## ([^:\r\n]+):[^\S\r\n]*(.*)$", text, re.MULTILINE)}
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


def _json_value(value):
    if isinstance(value, bytes): return value.decode('utf-8')
    if isinstance(value, list): return [_json_value(v) for v in value]
    if isinstance(value, dict): return {str(_text(k)): _json_value(v) for k, v in value.items()}
    return value


def parse_area_maps(body):
    """Read only the inspected numeric literal table, never execute addon Lua."""
    match = re.search(r'ZoneDB\.private\.areaIdToUiMapId\s*=\s*\[\[return\s*\{(.*?)\}\s*\]\]', body.decode('utf-8-sig'), re.S)
    if not match: raise ValueError('Unreviewed QuestieDB Forever area mapping')
    table = re.sub(r'--[^\n]*', '', match.group(1))
    entries = re.findall(r'\[(\d+)\]\s*=\s*(\d+)\s*,?', table)
    if re.sub(r'\[\d+\]\s*=\s*\d+\s*,?', '', table).strip() or not entries:
        raise ValueError('Nonliteral QuestieDB area mapping')
    result = {int(k): int(v) for k, v in entries}
    if len(result) != len(entries): raise ValueError('Duplicate QuestieDB area mapping')
    return result


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
    map_body = read_file(root / AREA_MAP_FILE, 2_000_000)
    area_maps = parse_area_maps(map_body)
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
            attributes['ui_map_ids'] = sorted({area_maps[a] for a in spawns if area_maps.get(a, 0)>0})
            if area_maps.get(attributes['area_id'], 0)>0: attributes['ui_map_id'] = area_maps[attributes['area_id']]
            attributes['map_mapping_reference'] = AREA_MAP_FILE
            counts[kind] += 1
            if spawns: counts[f"{kind}_with_spawns"] += 1
            if waypoints: counts[f"{kind}_with_waypoints"] += 1
            counts["spawn_points"] += attributes["spawn_count"]
            counts["waypoint_points"] += sum(len(path) for paths in waypoints.values() for path in paths)
            records.append((kind, entity_id, _text(row.get(1)), json.dumps(attributes, ensure_ascii=False, separators=(",", ":")),
                            f"QuestieDB_Forever.toc#X-{entity}-{entity_id}"))
    quest_ids = _decode(metadata, 'X-Quest-IDS', compressed=True)
    if not isinstance(quest_ids, list) or len(quest_ids)!=len(set(quest_ids)):
        raise ValueError('Invalid QuestieDB quest ID index')
    counts['quest'] = 0
    for quest_id in quest_ids:
        positive_id(quest_id, 'Quest ID')
        row = _decode(metadata, f'X-Quest-{quest_id}-S')
        if isinstance(row, list): row = dict(enumerate(row, 1))
        if not isinstance(row, dict): raise ValueError(f'Missing QuestieDB quest scalar row: {quest_id}')
        fields = {}
        for index, name in enumerate(QUEST_FIELDS, 1):
            value = row.get(index)
            if _field_present(row, index):
                value = _decode(metadata, f'X-Quest-{quest_id}-{index}')
                if value is None: raise ValueError(f'Missing QuestieDB quest field: {quest_id}/{index}')
            if value is not None: fields[name] = _json_value(value)
        if not isinstance(fields.get('name'), str): raise ValueError('Quest name missing')
        attributes = {'quest_fields': fields, 'level': fields.get('questLevel'),
                      'required_level': fields.get('requiredLevel'), 'zone_or_sort': fields.get('zoneOrSort')}
        area = fields.get('zoneOrSort')
        if isinstance(area, int) and area>0:
            attributes['area_id'] = area
            if area_maps.get(area, 0)>0: attributes['ui_map_id'] = area_maps[area]
        attributes['map_mapping_reference'] = AREA_MAP_FILE
        records.append(('quest', quest_id, fields['name'], json.dumps(attributes, ensure_ascii=False), f'QuestieDB_Forever.toc#X-Quest-{quest_id}'))
        counts['quest'] += 1
    return {"root": root, "body": body, "map_body": map_body, "version": metadata.get("Version"), "build_commit": metadata.get("X-BUILD-COMMIT"),
            "build_time": metadata.get("X-BUILD-TIME"), "sha256": hashlib.sha256(b'questiedb-quest-schema-v2\0'+body+map_body).hexdigest(),
            "records": tuple(records), "counts": counts}


class QuestieDbAdapter:
    capability = AdapterCapability(
        key="questiedb_forever_v1", display_name="QuestieDB Forever spawn graph", status="ready",
        input_types=("installed baked QuestieDB_Forever.toc",),
        supplies=("baked NPC/object/quest index", "quest requirements and objectives", "spawn coordinates", "movement paths", "levels and ranks"),
        needs=("installed QuestieDB Forever package",), documentation_url=SOURCE_URL,
        notes="Area IDs stay distinct from UI map IDs; no respawn time or live population is inferred.")

    def import_file(self, database: Database, path: Path) -> ImportResult:
        data = parse_questiedb(path)
        now = datetime.now(timezone.utc).isoformat()
        with database.write_transaction() as connection:
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
                "sha256": hashlib.sha256(data["body"]).hexdigest(), "bytes": len(data["body"]), "counts": data["counts"],
                "build_commit": data["build_commit"], "build_time": data["build_time"]},
                AREA_MAP_FILE: {"sha256": hashlib.sha256(data['map_body']).hexdigest(), "bytes": len(data['map_body'])},
                "parser_revision": 2}
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
                (source_id, (data["root"] / "QuestieDB_Forever.toc").as_uri(), now, hashlib.sha256(data['body']).hexdigest(), data["body"]))
            connection.execute("""INSERT OR IGNORE INTO source_documents(source_id,url,retrieved_at,content_type,sha256,body)
                VALUES (?,?,?,'text/plain; charset=utf-8',?,?)""",
                (source_id, (data['root']/AREA_MAP_FILE).as_uri(), now, hashlib.sha256(data['map_body']).hexdigest(), data['map_body']))
            connection.execute("""INSERT INTO imports(adapter_key,source_id,started_at,completed_at,status,file_name,record_count)
                VALUES (?,?,?,?,'complete',?,?)""", (self.capability.key, source_id, now, now, str(data["root"]), len(data["records"])))
        return ImportResult(self.capability.key, SOURCE_KEY, len(data["records"]), 0, LIMITATIONS)
