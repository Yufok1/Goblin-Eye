"""Import installed static item catalogs, without executing Lua or querying WoW."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

from .base import AdapterCapability, ImportResult
from .bounded import read_file
from .lua_literals import LuaLiteralReader

SOURCE_KEY = "foreverguide-items"
SOURCE_URL = "https://www.curseforge.com/wow/addons/forever-guide"
FILES = ("ForeverGuide.toc", "ItemCatalogData.lua", "GearData.lua", "ItemStatsData.lua")
QUALITY = dict(enumerate(("POOR", "COMMON", "UNCOMMON", "RARE", "EPIC", "LEGENDARY", "ARTIFACT", "HEIRLOOM")))
LIMITATIONS = (
    "Installed static catalogs are source assertions, not current equipped-item tooltips.",
    "Catalog, gear and tooltip variants retain separate builds and upstream bases; conflicts are not merged.",
    "Base item stats exclude unverified random bonuses and enchants. Missing stats are unknown, not zero.",
    "F means bundled Wowhead Forever data; C means Classic fallback. Neither is a live client observation.",
)
GEAR_STATS = {"str":"strength", "agi":"agility", "sta":"stamina", "int":"intellect", "spi":"spirit",
    "sp":"spell_power", "hp":"healing_power", "sha":"shadow_damage", "fir":"fire_damage",
    "arc":"arcane_damage", "fro":"frost_damage", "nat":"nature_damage", "hol":"holy_damage",
    "mp5":"mana_per_5_seconds", "dps":"weapon_dps", "armor":"armor", "barmor":"bonus_armor",
    "shit":"spell_hit_rating", "scrit":"spell_crit_rating", "shaste":"spell_haste_rating"}
TOOLTIP_STATS = {"str":"strength", "agi":"agility", "sta":"stamina", "int":"intellect", "spi":"spirit",
    "splpwr":"spell_power", "spldmg":"spell_damage", "splheal":"healing_power", "shares":"shadow_resistance",
    "manargn":"mana_per_5_seconds", "healthrgn":"health_per_5_seconds", "splpen":"spell_penetration",
    "atkpwr":"attack_power", "rgdatkpwr":"ranged_attack_power", "feratkpwr":"feral_attack_power",
    "critstrkrtng":"crit_rating", "hitrtng":"hit_rating", "hastertng":"haste_rating",
    "defrtng":"defense_rating", "dodgertng":"dodge_rating", "parryrtng":"parry_rating",
    "blockrtng":"block_rating", "exprtng":"expertise_rating", "armorpenrtng":"armor_penetration_rating",
    "armorbonus":"bonus_armor", "holres":"holy_resistance", "firres":"fire_resistance",
    "natres":"nature_resistance", "frores":"frost_resistance", "arcres":"arcane_resistance"}


def stat_values(value, labels):
    raw = {}
    if value and value != "-":
        for token in value.split(","):
            match = re.fullmatch(r"([a-zA-Z][a-zA-Z0-9]*)=(-?\d+(?:\.\d+)?)", token)
            if not match:
                raise ValueError("Invalid stat value")
            value = float(match[2]) if "." in match[2] else int(match[2])
            key = match[1]
            if key in raw:
                raw[key] = raw[key] + [value] if isinstance(raw[key], list) else [raw[key],value]
            else:
                raw[key] = value
    return raw, {labels[k]: v for k, v in raw.items() if k in labels and not isinstance(v,list)}


def catalog_names(reader):
    """Read the names table and its inspected literal-only corrections in order."""
    reader.expect('ns.CAT_NAMES')
    reader.expect('=')
    names = reader.read()
    if not isinstance(names, dict) or any(type(i) is not int or i <= 0 or not isinstance(v, str)
                                          for i, v in names.items()):
        raise ValueError('Invalid item names catalog')
    reader.skip()
    while reader.position < len(reader.text):
        reader.expect('ns.CAT_NAMES')
        reader.expect('[')
        item_id = reader.read()
        reader.expect(']')
        reader.expect('=')
        value = reader.read()
        if type(item_id) is not int or item_id <= 0 or not isinstance(value, str):
            raise ValueError('Invalid item name correction')
        # Lua applies these authored corrections after the table, in file order.
        # Accept no functions, lookups, concatenation, or other assignments.
        names[item_id] = value
        reader.skip()
    return names


def packed_block(text, name):
    match = re.search(r"^ns\." + name + r"\s*=\s*\[\[", text, re.M)
    if not match:
        raise ValueError("Missing inspected catalog " + name)
    end = text.find("]]", match.end())
    if end < 0:
        raise ValueError("Unexpected content after item catalog")
    reader = LuaLiteralReader(text, end+2)
    reader.skip()
    names = catalog_names(reader) if name == 'CAT_DATA' else {}
    if reader.position != len(text):
        raise ValueError("Unexpected content after item catalog")
    return text[match.end():end].strip().splitlines(), names


def catalog_builds(text):
    header = '\n'.join(line for line in text[:800].splitlines() if line.startswith('--'))
    builds = list(dict.fromkeys(re.findall(r'\b1\.60\.1\.\d+\b', header)
                               + re.findall(r'\bbuild (\d{5,})\b', header)))
    numbers = {build.rsplit('.', 1)[-1] for build in builds}
    # A file mixing an older simulator snapshot and later dungeon changes does
    # not identify which build supplied each row. Retain both source labels.
    return (builds[0] if len(numbers) == 1 else None), builds


def parse_files(files):
    records = []
    names = {}
    for filename, table, width in (("ItemCatalogData.lua", "CAT_DATA", 8), ("GearData.lua", "GEAR_DATA", 8)):
        text = files[filename].decode("utf-8-sig")
        required = "ItemSparse/Item" if table == "CAT_DATA" else "WoWSims"
        if required not in text[:800]:
            raise ValueError("Item catalog provenance changed")
        build, source_builds = catalog_builds(text)
        seen = set()
        lines, corrections = packed_block(text, table)
        names.update(corrections)
        for line in lines:
            f = line.split()
            if not f:
                continue
            if len(f) != width:
                raise ValueError("Unsupported item catalog row width")
            nums = [int(v) for v in f[:8 if table == "CAT_DATA" else 7]]
            item_id = nums[0]
            if item_id <= 0 or item_id in seen:
                raise ValueError("Invalid or duplicate catalog item ID")
            seen.add(item_id)
            if table == "CAT_DATA":
                _, cls, sub, inv, ilvl, req, q, flags = nums
                data = dict(item_class_id=cls, item_subclass_id=sub, inventory_type_id=inv,
                    item_level=ilvl, required_level=None if req == -1 else req, quality=QUALITY[q], flags=flags,
                    evidence_basis="classic_fallback" if flags & 4 else "forever_client_tables",
                    new_in_forever=bool(flags & 1), changed_from_classic=bool(flags & 2))
                variant = "catalog"
            else:
                _, inv, sub, req, q, flags, classes = nums
                raw, normalized = stat_values(f[7], GEAR_STATS)
                data = dict(inventory_type_id=inv, item_subclass_id=sub, required_level=req, quality=QUALITY[q],
                    flags=flags, class_mask=classes, stats_raw=raw, stats=normalized,
                    evidence_basis="mixed_forever_references", stats_scope="base_item")
                variant = "gear"
            data["catalog_build"] = build
            data["source_builds"] = source_builds
            data["game_build"] = None if data['evidence_basis'] == 'classic_fallback' else data['catalog_build']
            data['name'] = names.get(item_id,'').split('\t')[0] or None
            records.append((item_id, variant, data, filename + "#" + str(item_id)))
    text = files["ItemStatsData.lua"].decode("utf-8-sig")
    if "Wowhead Forever" not in text[:800] or "Wowhead Classic" not in text[:800]:
        raise ValueError("Tooltip catalog provenance changed")
    match = re.search(r"^ns\.ITEM_STATS\s*=\s*", text, re.M)
    if not match:
        raise ValueError("Missing ITEM_STATS table")
    reader = LuaLiteralReader(text, match.end())
    rows = reader.read()
    reader.skip()
    if reader.position != len(text) or not isinstance(rows, dict):
        raise ValueError("Unexpected content after tooltip catalog")
    build = re.search(r"1\.60\.1\.\d+", text[:800])
    for item_id, packed in rows.items():
        if type(item_id) is not int or item_id <= 0 or not isinstance(packed, str):
            raise ValueError("Invalid tooltip item")
        f = packed.split("\t")
        if len(f) != 12 or f[0] not in ("F", "C"):
            raise ValueError("Unsupported tooltip row")
        q, ilvl, req = map(int, f[1:4])
        bind = int(f[4]) if f[4] else None
        inv, cls, sub, armor = map(int, f[5:9])
        raw, normalized = stat_values(f[10], TOOLTIP_STATS)
        data = dict(quality=QUALITY[q], item_level=ilvl, required_level=req, bind_type=bind,
            inventory_type_id=inv, item_class_id=cls, item_subclass_id=sub, armor=armor,
            stats_raw=raw, stats=normalized, stats_scope="base_item", effects=[],
            evidence_basis="wowhead_forever" if f[0] == "F" else "classic_fallback",
            game_build=build[0] if f[0] == "F" and build else None)
        if f[9]:
            damage = re.fullmatch(r"(\d+)-(\d+)@(\d+(?:\.\d+)?)", f[9])
            if not damage:
                raise ValueError("Unsupported weapon damage")
            low, high, speed = int(damage[1]), int(damage[2]), float(damage[3])
            if speed <= 0 or high < low:
                raise ValueError("Invalid weapon damage")
            data["weapon_damage"] = dict(min=low, max=high, speed=speed, dps=round((low+high)/2/speed, 3))
        for effect in filter(None, f[11].split("|")):
            if not re.match(r"^[EUH]:", effect):
                raise ValueError("Unsupported effect type")
            data["effects"].append({"trigger":effect[0], "text":effect[2:]})
        records.append((item_id, "tooltip", data, "ItemStatsData.lua#ITEM_STATS[" + str(item_id) + "]"))
    return records


class ForeverGuideItemAdapter:
    capability = AdapterCapability("foreverguide_static_items_v1", "Forever Guide item properties", "ready",
        FILES, ("base item stats", "equipment types", "requirements", "effects"), ("installed ForeverGuide",),
        SOURCE_URL, "Static local catalogs; no chat addon, game access, or redistribution of source data.")

    def import_file(self, database, path: Path):
        path = Path(path).resolve()
        files = {name: read_file(path / name, 10_000_000) for name in FILES}
        toc = files["ForeverGuide.toc"].decode("utf-8-sig")
        if not re.search(r"^## Interface:\s*16001\s*$", toc, re.M):
            raise ValueError("Unreviewed ForeverGuide interface")
        version = re.search(r"^## Version:\s*(.+)$", toc, re.M)
        hashes = {name: hashlib.sha256(body).hexdigest() for name, body in files.items()}
        # A parser revision must reimport unchanged source bytes. Keep source hashes
        # in the manifest; dataset identity also covers interpretation version.
        digest = hashlib.sha256(json.dumps({'files':hashes,'parser':3}, sort_keys=True).encode()).hexdigest()
        now = datetime.now(timezone.utc).isoformat()
        with database.write_transaction() as conn:
            existing = conn.execute("SELECT d.id FROM research_datasets d JOIN sources s ON s.id=d.source_id WHERE s.source_key=? AND d.sha256=? AND d.active=1", (SOURCE_KEY,digest)).fetchone()
            if existing:
                conn.execute("UPDATE sources SET last_success_at=?,last_error=NULL WHERE source_key=?", (now,SOURCE_KEY))
                return ImportResult(self.capability.key,SOURCE_KEY,0,0,("Catalog unchanged.",))
        records = parse_files(files)  # All validation before mutation.
        with database.write_transaction() as conn:
            conn.execute("""INSERT INTO sources(source_key,name,source_type,url,trust_rank,notes,last_success_at)
                VALUES (?,?, 'bundled_item_database', ?,6,?,?) ON CONFLICT(source_key) DO UPDATE SET last_success_at=excluded.last_success_at,last_error=NULL""",
                (SOURCE_KEY,self.capability.display_name,SOURCE_URL,"Installed catalogs only; upstream builds and fallback labels retained.",now))
            source_id = conn.execute("SELECT id FROM sources WHERE source_key=?", (SOURCE_KEY,)).fetchone()[0]
            conn.execute("UPDATE research_datasets SET active=0 WHERE source_id=? AND dataset_key='item_properties'", (source_id,))
            old = conn.execute("SELECT id FROM research_datasets WHERE source_id=? AND sha256=?", (source_id,digest)).fetchone()
            if old:
                conn.execute("UPDATE research_datasets SET active=1 WHERE id=?", (old[0],))
                return ImportResult(self.capability.key,SOURCE_KEY,0,0,("Previous catalog reactivated.",))
            dataset = conn.execute("""INSERT INTO research_datasets(source_id,dataset_key,sha256,source_version,retrieved_at,confidence,evidence_kind,manifest_json,limitations_json)
                VALUES (?,'item_properties',?,?,?,0.6,'reference',?,?)""",
                (source_id,digest,version[1].strip() if version else "unknown",now,
                 json.dumps({n:{"path":str(path/n),"sha256":hashes[n]} for n in FILES}),json.dumps(LIMITATIONS))).lastrowid
            conn.executemany("INSERT INTO item_property_facts(dataset_id,item_id,variant,attributes_json,raw_reference) VALUES (?,?,?,?,?)",
                ((dataset,i,v,json.dumps(a),ref) for i,v,a,ref in records))
            identity = {i:(a['name'],ref) for i,v,a,ref in records if a.get('name')}
            conn.executemany("INSERT INTO world_entity_facts(dataset_id,entity_type,entity_id,name,attributes_json,raw_reference) VALUES (?,'item',?,?,?,?)",
                ((dataset,i,name,'{}',ref) for i,(name,ref) in identity.items()))
        return ImportResult(self.capability.key,SOURCE_KEY,len(records),0,LIMITATIONS)
