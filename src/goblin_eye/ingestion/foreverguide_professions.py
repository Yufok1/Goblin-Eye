"""Import Forever Guide's inspected profession literals as a second recipe assertion source."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

from goblin_eye.repository import Database
from .base import AdapterCapability, ImportResult
from .bounded import read_file
from .lua_literals import LuaLiteralReader
from .professiondb import positive_id


SOURCE_KEY = "foreverguide-professions"
SOURCE_URL = "https://www.curseforge.com/wow/addons/forever-guide"
LIMITATIONS = (
    "Recipe rows are a Forever Guide assertion derived from the Forever client and wowforevertalents.com; they independently corroborate but do not replace LibProfessionDB.",
    "Output quantity is the addon's q field, defaulting to one exactly as its inspected display and valuation code do; recipes without an output item retain unknown quantity.",
    "Trainer and recipe-source labels do not prove that a recipe is currently obtainable from the live server at the player's level or phase.",
    "Recipe vendors and their stock limits are Classic baselines; vendor positions are Questie Forever references, not live observations.",
    "Merchant's Favor locations are not imported because the package labels some of them approximate beta reports.",
)


@dataclass(frozen=True)
class ForeverGuideProfessionDataset:
    root: Path
    version: str
    build: str
    fingerprint: str
    files: dict[str, bytes]
    recipes: tuple[dict, ...]
    items: tuple[tuple, ...]
    npcs: tuple[tuple, ...]
    vendor_edges: tuple[tuple, ...]
    unkeyed_recipe_count: int


def _assigned_table(text: str, name: str) -> dict:
    matches = list(re.finditer(rf"^ns\.{re.escape(name)}\s*=\s*", text, re.MULTILINE))
    if len(matches) != 1:
        raise ValueError(f"Expected one literal ns.{name} table")
    reader = LuaLiteralReader(text, matches[0].end())
    value = reader.read()
    if not isinstance(value, dict):
        raise ValueError(f"ns.{name} must be a literal table")
    return value


def _sequence(value: dict, field: str) -> list:
    if not isinstance(value, dict) or set(value) != set(range(1, len(value) + 1)):
        raise ValueError(f"{field} must be a contiguous literal sequence")
    return [value[index] for index in range(1, len(value) + 1)]


def _profession_name(key: str) -> str:
    return {"first-aid": "First Aid"}.get(key, key.title())


def parse_foreverguide_professions(root: Path) -> ForeverGuideProfessionDataset:
    root = root.resolve()
    names = ("ForeverGuide.toc", "README.txt", "ProfessionData.lua", "Professions.lua", "Auction.lua")
    files = {name: read_file(root / name, 10_000_000) for name in names}
    toc = files["ForeverGuide.toc"].decode("utf-8-sig")
    if not re.search(r"^## Interface:\s*16001\s*$", toc, re.MULTILINE):
        raise ValueError("Unreviewed Forever Guide interface")
    version = re.search(r"^## Version:\s*(.+)$", toc, re.MULTILINE)
    if not version:
        raise ValueError("Missing Forever Guide version")
    text = files["ProfessionData.lua"].decode("utf-8-sig")
    consumer = files["Professions.lua"].decode("utf-8-sig")
    auction_consumer = files["Auction.lua"].decode("utf-8-sig")
    build = re.search(r"Recipes: WoW Forever client build ([0-9.]+)", text[:500])
    if not build or "r.q or 1" not in auction_consumer or "if r.tr then" not in consumer or "elseif r.src then" not in consumer:
        raise ValueError("Forever Guide profession provenance or consumer semantics changed")

    prof_rows = _sequence(_assigned_table(text, "PROFS"), "PROFS")
    prof_ids: dict[str, int] = {}
    for row in prof_rows:
        if not isinstance(row, dict) or set(row) != {"key", "spell", "cat", "secs"}:
            raise ValueError("Unexpected profession descriptor")
        key = row["key"]
        if not isinstance(key, str) or key in prof_ids:
            raise ValueError("Invalid profession key")
        prof_ids[key] = positive_id(row["spell"], "profession spell ID")

    prec = _assigned_table(text, "PREC")
    if set(prec) != set(prof_ids):
        raise ValueError("Profession recipe groups do not match descriptors")
    allowed = {"s", "i", "l", "y", "g", "x", "sec", "tr", "src", "sq", "mf", "bop", "sod", "r", "st", "n", "note", "q"}
    recipes: list[dict] = []
    unkeyed_recipe_count = 0
    for key, group in prec.items():
        for row in _sequence(group, f"PREC[{key}]"):
            if not isinstance(row, dict) or set(row) - allowed or not isinstance(row.get("n"), str):
                raise ValueError(f"Unexpected Forever Guide recipe fields in {key}")
            if row.get("s") is None:
                # The source currently contains one output-only row without a
                # spell ID.  Retain it in the cached document and item index;
                # recipe_facts deliberately requires a real game spell ID.
                unkeyed_recipe_count += 1
                continue
            spell_id = positive_id(row.get("s"), "recipe spell ID")
            output = row.get("i")
            if output is not None:
                positive_id(output, "recipe output item ID")
            quantity = row.get("q", 1) if output is not None else None
            if quantity is not None:
                positive_id(quantity, "recipe output quantity")
            skill = row.get("l")
            if skill is not None and (type(skill) is not int or skill < 0):
                raise ValueError("Invalid recipe skill")
            flat = _sequence(row.get("r"), "recipe reagents")
            if len(flat) % 2:
                raise ValueError("Recipe reagents must contain item/count pairs")
            reagents: dict[int, int] = {}
            for index in range(0, len(flat), 2):
                item = positive_id(flat[index], "reagent item ID")
                count = positive_id(flat[index + 1], "reagent quantity")
                if item in reagents:
                    raise ValueError("Duplicate recipe reagent")
                reagents[item] = count
            source_item = row.get("src")
            if source_item is not None:
                positive_id(source_item, "recipe teaching item ID")
            if row.get("tr") not in (None, 1) or row.get("st") not in ("n", "c", "s"):
                raise ValueError("Unsupported recipe source/status marker")
            attributes = {name: value for name, value in row.items() if name not in {"s", "i", "l", "r", "n", "q"}}
            attributes.update({
                "source_fields": dict(row),
                "status": {"n": "new_in_forever", "c": "changed_in_forever", "s": "same_as_classic"}[row["st"]],
                "obtainability_basis": ("trainer_source_claim" if row.get("tr") else
                                        "classic_vendor_or_drop_baseline" if source_item else "unknown"),
                "source_reference": f"ProfessionData.lua#ns.PREC[{key}]/{spell_id}",
            })
            recipes.append(dict(spell_id=spell_id, profession_id=prof_ids[key], profession=_profession_name(key),
                name=row["n"], output_item_id=output, output_quantity=quantity, skill_required=skill,
                reagents=reagents, teaching_item_id=source_item, attributes=attributes,
                raw_reference=f"ProfessionData.lua#ns.PREC[{key}]/{spell_id}"))

    items = []
    for item_id, packed in _assigned_table(text, "PNAME").items():
        positive_id(item_id, "profession item ID")
        if not isinstance(packed, str):
            raise ValueError("Invalid profession item name")
        localized = packed.split("\t", 1)
        items.append(("item", item_id, localized[0] or None,
            json.dumps({"localized_name_ruRU": localized[1] if len(localized) > 1 and localized[1] else None}, ensure_ascii=False),
            f"ProfessionData.lua#ns.PNAME[{item_id}]"))

    npc_attributes: dict[int, dict] = {}
    npc_names: dict[int, str] = {}
    for key, group in _assigned_table(text, "PTRAIN").items():
        if key not in prof_ids:
            raise ValueError("Unknown trainer profession")
        for row in _sequence(group, f"PTRAIN[{key}]"):
            npc_id = positive_id(row.get("id"), "trainer NPC ID")
            npc_names[npc_id] = row.get("n") or npc_names.get(npc_id)
            value = npc_attributes.setdefault(npc_id, {"roles": [], "locations": []})
            value["roles"].append({"type": "profession_trainer", "profession": _profession_name(key), "rank": row.get("rk")})
            value["locations"].append({"ui_map_id": row.get("m"), "x": row.get("x"), "y": row.get("y"), "friendly_to": row.get("fr")})

    vendors = _assigned_table(text, "PVNPC")
    for npc_id, row in vendors.items():
        positive_id(npc_id, "vendor NPC ID")
        if not isinstance(row, dict):
            raise ValueError("Invalid vendor NPC")
        npc_names[npc_id] = row.get("n") or npc_names.get(npc_id)
        value = npc_attributes.setdefault(npc_id, {"roles": [], "locations": []})
        value["roles"].append({"type": "recipe_vendor", "basis": "classic_baseline"})
        value["locations"].append({"ui_map_id": row.get("m"), "x": row.get("x"), "y": row.get("y"), "friendly_to": row.get("fr")})

    vendor_edges = []
    for item_id, group in _assigned_table(text, "PVEND").items():
        positive_id(item_id, "vendor recipe item ID")
        for pair in _sequence(group, f"PVEND[{item_id}]"):
            values = _sequence(pair, "vendor pair")
            if len(values) != 2 or values[1] not in (0, 1):
                raise ValueError("Invalid recipe vendor row")
            npc_id = positive_id(values[0], "recipe vendor NPC ID")
            if npc_id not in vendors:
                raise ValueError("Recipe vendor metadata missing")
            vendor_edges.append((item_id, "recipe_vendor", "npc", npc_id, None, 0, 0, "classic_baseline",
                                 f"ProfessionData.lua#ns.PVEND[{item_id}]/{npc_id};limited={values[1]}"))

    npcs = tuple(("npc", npc_id, npc_names.get(npc_id), json.dumps(attributes, ensure_ascii=False),
                  f"ProfessionData.lua#profession-npc/{npc_id}") for npc_id, attributes in npc_attributes.items())
    hashes = {name: hashlib.sha256(body).hexdigest() for name, body in sorted(files.items())}
    fingerprint = hashlib.sha256(json.dumps({name: hashes[name] for name in ("ProfessionData.lua", "Professions.lua", "Auction.lua")},
                                           sort_keys=True).encode()).hexdigest()
    return ForeverGuideProfessionDataset(root, version.group(1).strip(), build.group(1), fingerprint, files,
                                          tuple(recipes), tuple(items), npcs, tuple(vendor_edges), unkeyed_recipe_count)


class ForeverGuideProfessionAdapter:
    capability = AdapterCapability(
        key="foreverguide_professions_v1", display_name="Forever Guide profession verification",
        status="ready", input_types=("installed static ProfessionData.lua",),
        supplies=("Forever recipe assertions", "output quantities", "recipe source labels", "trainer and vendor reference locations"),
        needs=("installed ForeverGuide package",), documentation_url=SOURCE_URL,
        notes="Reads inspected literals only; server obtainability remains unverified and Classic vendors stay labeled.")

    def import_file(self, database: Database, path: Path) -> ImportResult:
        dataset = parse_foreverguide_professions(path)
        now = datetime.now(timezone.utc).isoformat()
        manifest = {name: {"sha256": hashlib.sha256(body).hexdigest(), "path": str(dataset.root / name), "bytes": len(body)}
                    for name, body in dataset.files.items()}
        with database.transaction() as connection:
            connection.execute("""INSERT INTO sources(source_key,name,source_type,url,trust_rank,notes,last_success_at)
                VALUES (?, 'Forever Guide profession verification', 'bundled_profession_database', ?, 4, ?, ?)
                ON CONFLICT(source_key) DO UPDATE SET last_success_at=excluded.last_success_at,last_error=NULL""",
                (SOURCE_KEY, SOURCE_URL, "Installed static source for local personal research; provider assertions remain labeled.", now))
            source_id = connection.execute("SELECT id FROM sources WHERE source_key=?", (SOURCE_KEY,)).fetchone()[0]
            existing = connection.execute("""SELECT id,active FROM research_datasets
                WHERE source_id=? AND dataset_key='recipes-enUS' AND sha256=?""", (source_id, dataset.fingerprint)).fetchone()
            if existing and existing["active"]:
                return ImportResult(self.capability.key, SOURCE_KEY, 0, 0, ("Dataset already imported; unchanged.",))
            connection.execute("UPDATE research_datasets SET active=0 WHERE source_id=? AND dataset_key='recipes-enUS'", (source_id,))
            if existing:
                connection.execute("UPDATE research_datasets SET active=1 WHERE id=?", (existing["id"],))
                return ImportResult(self.capability.key, SOURCE_KEY, 0, 0, ("Previously imported revision reactivated.",))
            limitations = LIMITATIONS + ((f"{dataset.unkeyed_recipe_count} source recipe row(s) lack a spell ID and remain only in the cached source document and item index.",)
                                         if dataset.unkeyed_recipe_count else ())
            cursor = connection.execute("""INSERT INTO research_datasets(source_id,dataset_key,sha256,source_version,game_build,
                content_phase,retrieved_at,confidence,evidence_kind,manifest_json,limitations_json)
                VALUES (?, 'recipes-enUS', ?, ?, ?, 'Forever beta', ?, 0.7, 'extracted', ?, ?)""",
                (source_id, dataset.fingerprint, dataset.version, dataset.build, now, json.dumps(manifest), json.dumps(limitations)))
            dataset_id = cursor.lastrowid
            connection.executemany("""INSERT INTO world_entity_facts(dataset_id,entity_type,entity_id,name,attributes_json,raw_reference)
                VALUES (?,?,?,?,?,?)""", ((dataset_id, *row) for row in (*dataset.items, *dataset.npcs)))
            for recipe in dataset.recipes:
                cursor = connection.execute("""INSERT INTO recipe_facts(dataset_id,spell_id,name,profession_id,profession,
                    output_item_id,output_quantity,skill_required,attributes_json,raw_reference)
                    VALUES (?,?,?,?,?,?,?,?,?,?)""", (dataset_id, recipe["spell_id"], recipe["name"], recipe["profession_id"],
                    recipe["profession"], recipe["output_item_id"], recipe["output_quantity"], recipe["skill_required"],
                    json.dumps(recipe["attributes"], ensure_ascii=False), recipe["raw_reference"]))
                fact_id = cursor.lastrowid
                connection.executemany("INSERT INTO reagent_facts(recipe_fact_id,item_id,quantity) VALUES (?,?,?)",
                    ((fact_id, item, quantity) for item, quantity in recipe["reagents"].items()))
                if recipe["teaching_item_id"] is not None:
                    connection.execute("INSERT INTO recipe_teaching_items(recipe_fact_id,item_id,raw_reference) VALUES (?,?,?)",
                        (fact_id, recipe["teaching_item_id"], recipe["raw_reference"]))
            connection.executemany("""INSERT INTO acquisition_facts(dataset_id,item_id,method,entity_type,entity_id,probability,
                quest_condition,choice_reward,evidence_basis,raw_reference) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                ((dataset_id, *row) for row in dataset.vendor_edges))
            for name, body in dataset.files.items():
                connection.execute("""INSERT OR IGNORE INTO source_documents(source_id,url,retrieved_at,content_type,sha256,body)
                    VALUES (?,?,?,'text/plain; charset=utf-8',?,?)""",
                    (source_id, (dataset.root / name).as_uri(), now, hashlib.sha256(body).hexdigest(), body))
            total = len(dataset.recipes) + len(dataset.vendor_edges)
            connection.execute("""INSERT INTO imports(adapter_key,source_id,started_at,completed_at,status,file_name,record_count)
                VALUES (?,?,?,?,'complete',?,?)""", (self.capability.key, source_id, now, now, str(dataset.root), total))
        return ImportResult(self.capability.key, SOURCE_KEY, total, 0, limitations)
