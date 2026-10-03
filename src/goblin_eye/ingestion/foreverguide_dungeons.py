"""Import explicitly labeled Forever dungeon loot and verified quest rewards."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

from goblin_eye.repository import Database
from .base import AdapterCapability, ImportResult
from .bounded import read_file
from .foreverguide_professions import _assigned_table, _sequence
from .professiondb import positive_id


SOURCE_KEY = "foreverguide-dungeons"
SOURCE_URL = "https://www.curseforge.com/wow/addons/forever-guide"
LIMITATIONS = (
    "Forever dungeon loot comes from the package's foreverchanges.pro assertions; new-item rows do not provide drop probability or output quantity.",
    "Only bosses with a real NPC ID can form item-to-NPC edges; name-only Forever bosses remain retained in the cached source and coverage counts.",
    "Quest rewards are imported as Forever evidence only when the source reward table explicitly sets fv=true; eligibility and current phase availability remain unverified.",
    "Classic Wowhead probabilities in the same loot file are not copied into these Forever override assertions.",
    "Name-only n: quest placeholders have no game quest ID; they remain in cached source documents and coverage counts, without fabricated quest links.",
)


def parse_foreverguide_dungeons(root: Path) -> dict:
    root = root.resolve()
    names = ("ForeverGuide.toc", "DungeonLoot.lua", "DungeonData.lua", "Dungeons.lua", "ItemSearch.lua")
    files = {name: read_file(root / name, 12_000_000) for name in names}
    toc = files["ForeverGuide.toc"].decode("utf-8-sig")
    version = re.search(r"^## Version:\s*(.+)$", toc, re.MULTILINE)
    if not version or not re.search(r"^## Interface:\s*16001\s*$", toc, re.MULTILINE):
        raise ValueError("Unreviewed Forever Guide dungeon interface")
    loot_text = files["DungeonLoot.lua"].decode("utf-8-sig")
    data_text = files["DungeonData.lua"].decode("utf-8-sig")
    if "foreverchanges.pro boss loot" not in loot_text[:200] or "QuestieDB (Forever) + foreverchanges.pro" not in data_text[:200]:
        raise ValueError("Forever Guide dungeon provenance changed")
    if "rw and rw.fv" not in files["Dungeons.lua"].decode("utf-8-sig") or "fv = q.rw.fv" not in files["ItemSearch.lua"].decode("utf-8-sig"):
        raise ValueError("Forever Guide reward-label consumer semantics changed")

    item_names = {}
    entities = {}
    edges = []
    name_only_bosses = 0
    new_loot_rows = 0
    for dungeon_key, bosses in _assigned_table(loot_text, "LOOT").items():
        for boss in _sequence(bosses, f"LOOT[{dungeon_key}]"):
            if not isinstance(boss, dict) or not isinstance(boss.get("n"), str):
                raise ValueError("Invalid dungeon boss row")
            new_items = [item for item in _sequence(boss.get("items"), "boss items")
                         if isinstance(item, dict) and item.get("new") is True]
            if not new_items: continue
            boss_id = boss.get("id")
            if boss_id is None:
                name_only_bosses += 1
            else:
                positive_id(boss_id, "boss NPC ID")
                entities[("npc", boss_id)] = (boss["n"], {"dungeon_key": dungeon_key, "level": boss.get("lv"),
                    "rare": bool(boss.get("rare")), "forever_new_loot": True},
                    f"DungeonLoot.lua#ns.LOOT[{dungeon_key}]/{boss_id}")
            for item in new_items:
                item_id = positive_id(item.get("id"), "Forever loot item ID")
                if not isinstance(item.get("n"), str): raise ValueError("Forever loot item lacks a name")
                item_names[item_id] = item["n"]
                new_loot_rows += 1
                if boss_id is not None:
                    edges.append((item_id, "forever_drop", "npc", boss_id, None, 0, 0, "forever_community",
                        f"DungeonLoot.lua#ns.LOOT[{dungeon_key}]/{boss_id}/{item_id};new=true;quantity=unknown"))

    verified_quests = 0
    verified_reward_rows = 0
    name_only_quests = 0
    for quest_id, quest in _assigned_table(data_text, "DQ").items():
        if not isinstance(quest, dict) or not isinstance(quest.get("n"), str):
            raise ValueError("Invalid dungeon quest row")
        if isinstance(quest_id, str) and re.fullmatch(r"n:[^:]+:[AH]:.+", quest_id):
            name_only_quests += 1
            continue
        positive_id(quest_id, "dungeon quest ID")
        rewards = quest.get("rw")
        if not isinstance(rewards, dict) or rewards.get("fv") is not True:
            continue
        verified_quests += 1
        attributes = {key: quest.get(key) for key in ("lv", "rl", "fa", "z", "new", "inside", "pre", "ps") if key in quest}
        attributes["forever_reward_verified"] = True
        entities[("quest", quest_id)] = (quest["n"], attributes, f"DungeonData.lua#ns.DQ[{quest_id}]")
        for field, choice in (("c", True), ("i", False)):
            rows = rewards.get(field)
            if rows is None: continue
            for pair in _sequence(rows, f"DQ[{quest_id}].rw.{field}"):
                values = _sequence(pair, "quest reward pair")
                if len(values) != 2: raise ValueError("Invalid quest reward pair")
                item_id = positive_id(values[0], "quest reward item ID")
                quantity = positive_id(values[1], "quest reward quantity")
                verified_reward_rows += 1
                edges.append((item_id, "quest_reward", "quest", quest_id, None, 1, int(choice), "forever_community",
                    f"DungeonData.lua#ns.DQ[{quest_id}].rw.{field}/{item_id};quantity={quantity};fv=true"))

    for item_id, name in item_names.items():
        entities[("item", item_id)] = (name, {"forever_new_dungeon_loot": True}, f"DungeonLoot.lua#item/{item_id}")
    hashes = {name: hashlib.sha256(body).hexdigest() for name, body in files.items()}
    fingerprint = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    entity_rows = tuple((kind, entity_id, name, json.dumps(attributes, ensure_ascii=False), raw)
                        for (kind, entity_id), (name, attributes, raw) in entities.items())
    return {"root": root, "files": files, "hashes": hashes, "fingerprint": fingerprint,
            "version": version.group(1).strip(), "entities": entity_rows, "edges": tuple(edges),
            "counts": {"new_loot_rows": new_loot_rows, "name_only_bosses": name_only_bosses,
                       "verified_quests": verified_quests, "verified_reward_rows": verified_reward_rows,
                       "name_only_quests": name_only_quests}}


class ForeverGuideDungeonAdapter:
    capability = AdapterCapability(
        key="foreverguide_dungeon_overrides_v1", display_name="Forever Guide dungeon overrides", status="ready",
        input_types=("installed DungeonLoot.lua and DungeonData.lua",),
        supplies=("Forever-labeled dungeon loot", "fv-verified quest rewards", "reward quantities in raw references"),
        needs=("installed ForeverGuide package",), documentation_url=SOURCE_URL,
        notes="New loot has unknown drop probability and quantity; current obtainability remains a provider assertion.")

    def import_file(self, database: Database, path: Path) -> ImportResult:
        data = parse_foreverguide_dungeons(path)
        now = datetime.now(timezone.utc).isoformat()
        with database.transaction() as connection:
            connection.execute("""INSERT INTO sources(source_key,name,source_type,url,trust_rank,notes,last_success_at)
                VALUES (?, 'Forever Guide dungeon overrides', 'bundled_acquisition_database', ?, 4, ?, ?)
                ON CONFLICT(source_key) DO UPDATE SET last_success_at=excluded.last_success_at,last_error=NULL""",
                (SOURCE_KEY, SOURCE_URL, "Forever-labeled provider assertions retained separately from Classic baselines.", now))
            source_id = connection.execute("SELECT id FROM sources WHERE source_key=?", (SOURCE_KEY,)).fetchone()[0]
            existing = connection.execute("""SELECT id,active FROM research_datasets
                WHERE source_id=? AND dataset_key='dungeon-overrides' AND sha256=?""", (source_id, data["fingerprint"])).fetchone()
            if existing and existing["active"]:
                return ImportResult(self.capability.key, SOURCE_KEY, 0, 0, ("Dataset already imported; unchanged.",))
            connection.execute("UPDATE research_datasets SET active=0 WHERE source_id=? AND dataset_key='dungeon-overrides'", (source_id,))
            if existing:
                connection.execute("UPDATE research_datasets SET active=1 WHERE id=?", (existing["id"],))
                return ImportResult(self.capability.key, SOURCE_KEY, 0, 0, ("Previously imported revision reactivated.",))
            manifest = {name: {"path": str(data["root"] / name), "sha256": data["hashes"][name], "bytes": len(body)}
                        for name, body in data["files"].items()}
            manifest["coverage"] = data["counts"]
            cursor = connection.execute("""INSERT INTO research_datasets(source_id,dataset_key,sha256,source_version,game_build,
                content_phase,retrieved_at,confidence,evidence_kind,manifest_json,limitations_json)
                VALUES (?,'dungeon-overrides',?,?,NULL,'Forever',?,0.7,'extracted',?,?)""",
                (source_id, data["fingerprint"], data["version"], now, json.dumps(manifest), json.dumps(LIMITATIONS)))
            dataset_id = cursor.lastrowid
            connection.executemany("""INSERT INTO world_entity_facts(dataset_id,entity_type,entity_id,name,attributes_json,raw_reference)
                VALUES (?,?,?,?,?,?)""", ((dataset_id, *row) for row in data["entities"]))
            connection.executemany("""INSERT INTO acquisition_facts(dataset_id,item_id,method,entity_type,entity_id,probability,
                quest_condition,choice_reward,evidence_basis,raw_reference) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                ((dataset_id, *row) for row in data["edges"]))
            for name, body in data["files"].items():
                connection.execute("""INSERT OR IGNORE INTO source_documents(source_id,url,retrieved_at,content_type,sha256,body)
                    VALUES (?,?,?,'text/plain; charset=utf-8',?,?)""",
                    (source_id, (data["root"] / name).as_uri(), now, data["hashes"][name], body))
            count = len(data["entities"]) + len(data["edges"])
            connection.execute("""INSERT INTO imports(adapter_key,source_id,started_at,completed_at,status,file_name,record_count)
                VALUES (?,?,?,?,'complete',?,?)""", (self.capability.key, source_id, now, now, str(data["root"]), count))
        warnings = LIMITATIONS + (f"{data['counts']['name_only_bosses']} boss rows lack NPC IDs and are retained only in cached source coverage.",)
        return ImportResult(self.capability.key, SOURCE_KEY, count, 0, warnings)
