"""Read installed static acquisition data. Never read ForeverGuide gameplay history."""
from __future__ import annotations

from .bounded import read_file, read_stream, resilient_run

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

from goblin_eye.repository import Database
from .base import AdapterCapability, ImportResult
from .lua_literals import LuaLiteralReader
from .professiondb import ProfessionDBWatcher, discover_professiondb_paths, positive_id


SOURCE_KEY = "foreverguide-acquisition"
SOURCE_URL = "https://www.curseforge.com/wow/addons/forever-guide"
METHODS = {"d": ("drop", "npc"), "o": ("object_loot", "object"), "pp": ("pickpocket", "npc"),
           "sk": ("skinning", "npc"), "q": ("quest_reward", "quest"), "v": ("vendor", "npc"),
           "fd": ("forever_drop", "npc"), "qd": ("questie_drop", "npc"),
           "qo": ("questie_object_loot", "object"), "ci": ("container_loot", "item")}
LIMITATIONS = (
    "World drop probabilities, vendor stock and quest rewards are Classic baselines, not verified Forever facts.",
    "Entries explicitly marked fd are Forever community drop associations with unknown probabilities.",
    "qd/qo are bundled Questie associations labeled Classic by the addon; probabilities and quest eligibility are unknown.",
    "ci links to a container item; probability, quantity and upstream build are unspecified, not verified Forever evidence.",
    "NPC and quest metadata come from the bundled package; their individual upstream builds are unspecified.",
    "Source lists may be truncated; omitted counts are retained. This is not a complete loot table.",
    "Expected drop quantities, vendor prices, current availability and respawn times are unknown.",
    "NPC coordinates are a source-provided reference point, not a complete spawn or route dataset.",
)


def parse_tables(text: str) -> dict[str, dict]:
    if "cmangos" not in text[:500] or "classic-db" not in text[:500]:
        raise ValueError("Acquisition provenance header changed; review source before import")
    matches = list(re.finditer(r"^ns\.(SI_ITEM|SI_NPC|SI_OBJ|SI_QUEST)\s*=\s*", text, re.MULTILINE))
    if [match.group(1) for match in matches] != ["SI_ITEM", "SI_NPC", "SI_OBJ", "SI_QUEST"]:
        raise ValueError("Unsupported ForeverGuide acquisition table layout")
    result = {}
    for index, match in enumerate(matches):
        reader = LuaLiteralReader(text, match.end())
        value = reader.read()
        if not isinstance(value, dict):
            raise ValueError("Expected acquisition literal table")
        reader.skip()
        expected_end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        if reader.position != expected_end:
            raise ValueError("Unexpected statements between acquisition data tables")
        for key, row in value.items():
            positive_id(key, "entity ID")
            if not isinstance(row, str):
                raise ValueError("Expected packed acquisition string")
        result[match.group(1)] = value
    return result


def unpack_sources(item_id: int, packed: str):
    fields = packed.split("\t")
    if len(fields) != 4:
        raise ValueError(f"Unexpected item record width: {item_id}")
    edges, coverage = [], []
    for group in filter(None, fields[3].split(";")):
        code, body = group.split("=", 1)
        if code not in METHODS:
            raise ValueError(f"Unsupported acquisition method: {code}")
        method, entity_type = METHODS[code]
        omitted = 0
        for token in filter(None, body.split(",")):
            if re.fullmatch(r"\+\d+", token):
                omitted += int(token[1:])
                continue
            probability, conditional, choice = None, False, False
            if code == "q":
                match = re.fullmatch(r"(\d+)(c?)", token)
                if not match:
                    raise ValueError("Invalid decimal quest reward ID")
                entity_id, choice = int(match.group(1)), bool(match.group(2))
            elif code in ("v", "fd", "qd", "qo", "ci"):
                if not re.fullmatch(r"[0-9a-z]+", token):
                    raise ValueError("Invalid base36 acquisition ID")
                entity_id = int(token, 36)
            else:
                match = re.fullmatch(r"([0-9a-z]+):(\d+(?:\.\d+)?)(q?)", token)
                if not match:
                    raise ValueError("Invalid acquisition probability")
                entity_id = int(match.group(1), 36)
                probability, conditional = float(match.group(2)) / 100, bool(match.group(3))
                if not 0 <= probability <= 1:
                    raise ValueError("Acquisition probability out of range")
            positive_id(entity_id, "acquisition entity ID")
            edges.append((item_id, method, entity_type, entity_id, probability, int(conditional), int(choice),
                          "forever_community" if code == "fd" else "bundled_reference" if code == "ci" else "classic_baseline",
                          f"ItemSearchData.lua#SI_ITEM[{item_id}]/{code}/{token}"))
        coverage.append((item_id, method, omitted))
    return fields, edges, coverage


def world_entity(kind: str, entity_id: int, packed: str) -> tuple:
    fields = packed.split("\t")
    name = fields[0] if kind == "item" else fields[1] if len(fields) > 1 else None
    attributes: dict = {"packed_fields": fields}
    if kind == "npc":
        if len(fields) != 11:
            raise ValueError(f"Unexpected NPC record width: {entity_id}")
        for key, index in (("min_level", 2), ("max_level", 3), ("rank", 4), ("ui_map_id", 5), ("spawn_count", 9)):
            attributes[key] = int(fields[index]) if fields[index] else None
        attributes["ui_map_id"] = attributes["ui_map_id"] or None
        for key, index in (("x", 6), ("y", 7)):
            attributes[key] = float(fields[index]) if fields[index] else None
            if attributes[key] is not None and not 0 <= attributes[key] <= 100:
                raise ValueError("Invalid map coordinate")
        attributes.update(dungeon_key=fields[8] or None, friendly_to=fields[10] or None)
    elif kind == "quest":
        padded = fields + [""] * (8 - len(fields))
        if len(padded) != 8:
            raise ValueError("Unexpected quest record width")
        for key, index in (("level", 2), ("giver_npc_id", 4), ("start_item_id", 6), ("start_object_id", 7)):
            attributes[key] = int(padded[index]) if padded[index] else None
        attributes["faction"] = padded[3] or None
        prereq = padded[5].split("|")
        attributes["prerequisites_all"] = [int(value) for value in prereq[0].split(",") if value]
        attributes["prerequisites_any"] = [int(value) for value in prereq[1].split(",") if value] if len(prereq) == 2 else []
    table = {"item": "SI_ITEM", "npc": "SI_NPC", "object": "SI_OBJ", "quest": "SI_QUEST"}[kind]
    return kind, entity_id, name or None, json.dumps(attributes, ensure_ascii=False), f"ItemSearchData.lua#{table}[{entity_id}]"


class ForeverGuideAdapter:
    capability = AdapterCapability(
        key="foreverguide_static_acquisition_v1", display_name="Forever Guide acquisition research",
        status="ready", input_types=("installed static ItemSearchData.lua",),
        supplies=("item acquisition relationships", "NPC reference locations", "quest prerequisites", "baseline drop probabilities"),
        needs=("installed ForeverGuide package",), documentation_url=SOURCE_URL,
        notes="Local personal research; bundled files remain local. Gameplay SavedVariables are never read. Classic baselines stay labeled.")

    def import_file(self, database: Database, path: Path) -> ImportResult:
        path = path.resolve()
        files = {name: read_file(path / name, 10_000_000) for name in ("ForeverGuide.toc", "README.txt", "ItemSearchData.lua", "ItemSearch.lua")}
        toc = files["ForeverGuide.toc"].decode("utf-8-sig")
        if not re.search(r"^## Interface:\s*16001\s*$", toc, re.MULTILINE):
            raise ValueError("Unreviewed Forever Guide interface")
        version = re.search(r"^## Version:\s*(.+)$", toc, re.MULTILINE)
        if not version:
            raise ValueError("Missing addon version")
        hashes = {name: hashlib.sha256(body).hexdigest() for name, body in files.items()}
        identity_hashes = {name: hashes[name] for name in ("ItemSearchData.lua", "ItemSearch.lua")}
        digest = hashlib.sha256(json.dumps(identity_hashes, sort_keys=True).encode()).hexdigest()
        # Check content fingerprints before parsing a multi-megabyte static catalog.
        with database.transaction() as connection:
            row = connection.execute("""SELECT d.id FROM research_datasets d JOIN sources s ON s.id=d.source_id
                WHERE s.source_key=? AND d.dataset_key='acquisition' AND d.sha256=? AND d.active=1""", (SOURCE_KEY, digest)).fetchone()
        if row:
            with database.transaction() as connection:
                connection.execute("UPDATE sources SET last_success_at=?,last_error=NULL WHERE source_key=?",
                                   (datetime.now(timezone.utc).isoformat(),SOURCE_KEY))
            return ImportResult(self.capability.key, SOURCE_KEY, 0, 0, ("Dataset already imported; unchanged.",))
        tables = parse_tables(files["ItemSearchData.lua"].decode("utf-8-sig"))
        entities, edges, coverage = [], [], []
        for key, kind in (("SI_ITEM", "item"), ("SI_NPC", "npc"), ("SI_OBJ", "object"), ("SI_QUEST", "quest")):
            for entity_id, packed in tables[key].items():
                entities.append(world_entity(kind, entity_id, packed))
                if kind == "item":
                    _, item_edges, item_coverage = unpack_sources(entity_id, packed)
                    edges.extend(item_edges)
                    coverage.extend(item_coverage)
        now = datetime.now(timezone.utc).isoformat()
        manifest = {name: {"sha256": hashes[name], "path": str(path / name), "bytes": len(body)} for name, body in files.items()}
        with database.transaction() as connection:
            connection.execute("""INSERT INTO sources(source_key,name,source_type,url,trust_rank,notes,last_success_at)
                VALUES (?, 'Forever Guide acquisition research', 'bundled_world_database', ?, 5, ?, ?)
                ON CONFLICT(source_key) DO UPDATE SET last_success_at=excluded.last_success_at,last_error=NULL""",
                (SOURCE_KEY, SOURCE_URL, "All rights reserved; installed static data for local personal research only. Classic baselines labeled per relationship.", now))
            source_id = connection.execute("SELECT id FROM sources WHERE source_key=?", (SOURCE_KEY,)).fetchone()[0]
            connection.execute("UPDATE research_datasets SET active=0 WHERE source_id=? AND dataset_key='acquisition'", (source_id,))
            existing = connection.execute("SELECT id FROM research_datasets WHERE source_id=? AND dataset_key='acquisition' AND sha256=?", (source_id, digest)).fetchone()
            if existing:
                connection.execute("UPDATE research_datasets SET active=1 WHERE id=?", (existing[0],))
                return ImportResult(self.capability.key, SOURCE_KEY, 0, 0, ("Previously imported revision reactivated.",))
            cursor = connection.execute("""INSERT INTO research_datasets(source_id,dataset_key,sha256,source_version,
                retrieved_at,confidence,evidence_kind,manifest_json,limitations_json)
                VALUES (?, 'acquisition', ?, ?, ?, 0.5, 'historical', ?, ?)""",
                (source_id,digest,version.group(1).strip(),now,json.dumps(manifest),json.dumps(LIMITATIONS)))
            dataset_id = cursor.lastrowid
            connection.executemany("""INSERT INTO world_entity_facts(dataset_id,entity_type,entity_id,name,attributes_json,raw_reference)
                VALUES (?,?,?,?,?,?)""", ((dataset_id,*row) for row in entities))
            connection.executemany("""INSERT INTO acquisition_facts(dataset_id,item_id,method,entity_type,entity_id,probability,
                quest_condition,choice_reward,evidence_basis,raw_reference) VALUES (?,?,?,?,?,?,?,?,?,?)""", ((dataset_id,*row) for row in edges))
            connection.executemany("INSERT INTO acquisition_coverage(dataset_id,item_id,method,omitted_count) VALUES (?,?,?,?)",
                                   ((dataset_id,*row) for row in coverage))
            for name, body in files.items():
                connection.execute("""INSERT OR IGNORE INTO source_documents(source_id,url,retrieved_at,content_type,sha256,body)
                    VALUES (?,?,?,'text/plain; charset=utf-8',?,?)""", (source_id,(path / name).as_uri(),now,hashes[name],body))
            connection.execute("""INSERT INTO imports(adapter_key,source_id,started_at,completed_at,status,file_name,record_count)
                VALUES (?,?,?,?,'complete',?,?)""", (self.capability.key,source_id,now,now,str(path),len(edges)))
        return ImportResult(self.capability.key,SOURCE_KEY,len(edges),0,LIMITATIONS)


class ForeverGuideWatcher(ProfessionDBWatcher):
    @resilient_run
    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.scan_once()
            except Exception as exc:
                with self.database.transaction() as connection:
                    connection.execute("""INSERT INTO sources(source_key,name,source_type,url,trust_rank,last_error)
                        VALUES (?, 'Forever Guide acquisition research', 'bundled_world_database', ?, 5, ?)
                        ON CONFLICT(source_key) DO UPDATE SET last_error=excluded.last_error""", (SOURCE_KEY,SOURCE_URL,str(exc)))
            self._stop.wait(self.interval)

    def scan_once(self) -> list[ImportResult]:
        from .foreverguide_professions import ForeverGuideProfessionAdapter, SOURCE_KEY as PROFESSION_SOURCE_KEY
        from .foreverguide_dungeons import ForeverGuideDungeonAdapter, SOURCE_KEY as DUNGEON_SOURCE_KEY
        from .discovery import discover_addon_paths
        from .static_watcher import record_error
        results = []
        candidates = {Path(value) for value in self.paths}
        candidates.update(path.parent / "ForeverGuide" for path in discover_professiondb_paths())
        imports = (
            (ForeverGuideAdapter(), SOURCE_KEY, "bundled_world_database", 5,
             ("ForeverGuide.toc", "README.txt", "ItemSearchData.lua", "ItemSearch.lua")),
            (ForeverGuideProfessionAdapter(), PROFESSION_SOURCE_KEY, "bundled_profession_database", 4,
             ("ForeverGuide.toc", "README.txt", "ProfessionData.lua", "Professions.lua", "Auction.lua")),
            (ForeverGuideDungeonAdapter(), DUNGEON_SOURCE_KEY, "bundled_acquisition_database", 4,
             ("ForeverGuide.toc", "DungeonLoot.lua", "DungeonData.lua", "Dungeons.lua", "ItemSearch.lua")),
        )
        for path in discover_addon_paths("ForeverGuide", "ForeverGuide.toc", candidates):
            for adapter, source_key, source_type, rank, names in imports:
                key = (str(path), source_key)
                try:
                    watched = [path / name for name in names]
                    signature = tuple((str(file), file.stat().st_mtime_ns, file.stat().st_size) for file in watched)
                    if self._signatures.get(key) == signature:
                        continue
                    results.append(adapter.import_file(self.database, path))
                    after = tuple((str(file), file.stat().st_mtime_ns, file.stat().st_size) for file in watched)
                    if after == signature:
                        self._signatures[key] = signature
                except Exception as exc:
                    record_error(self.database, source_key, adapter.capability.display_name,
                                 source_type, SOURCE_URL, rank, exc)
        return results
