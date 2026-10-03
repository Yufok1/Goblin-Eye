"""Read inspected Alts Forever 0.9.1 SavedVariables v2; never execute Lua."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import logging
from pathlib import Path
import re
import threading

from goblin_eye.repository import Database
from .base import AdapterCapability, ImportResult
from .bounded import read_file, resilient_run
from .lua_literals import LuaLiteralReader

SOURCE_KEY = "local-alts-forever"
LIMITATIONS = (
    "Saved addon observations are not live game state; import time is not capture time.",
    "Alts Forever v2 exports full character names, not realm, race or client build; those fields remain unknown.",
    "Bank contents require visiting a banker; mail requires opening the mailbox; recipes require opening profession windows.",
    "The character updated timestamp does not independently date each inventory, gear or profession observation. Bank bankAt is retained separately.",
    "Absent fields mean unknown/unscanned. Empty mail alone does not establish a complete mailbox survey.",
    "Item links and explicit equipment slots are preserved; enchant and random-suffix interpretations are not verified for this build.",
    "Talents, quest completion, combat, movement and sale completion are not supplied by this adapter.",
)


def _integer(value, label, minimum=0, maximum=2**63-1):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"Invalid {label}")
    return value


def _counts(value, label):
    if not isinstance(value, dict):
        raise ValueError(f"Expected {label} table")
    for item_id, count in value.items():
        _integer(item_id, f"{label} item ID", 1)
        _integer(count, f"{label} quantity", 1)


def parse_alts_file(path: Path) -> dict:
    text = read_file(path, 16 * 1024 * 1024).decode("utf-8-sig")
    reader = LuaLiteralReader(text)
    reader.skip()
    reader.expect("AltsForeverDB")
    reader.expect("=")
    root = reader.read()
    reader.skip()
    if reader.position != len(text):
        raise ValueError("Unexpected content after AltsForeverDB")
    if not isinstance(root, dict) or type(root.get("v")) is not int or root["v"] != 2:
        raise ValueError("Only inspected Alts Forever SavedVariables version 2 is supported")
    chars = root.get("chars")
    if not isinstance(chars, dict):
        raise ValueError("Missing characters table")
    for key, char in chars.items():
        if not isinstance(key, str) or not key.strip() or not isinstance(char, dict):
            raise ValueError("Invalid character identity")
        if char.get("name") != key or not isinstance(char.get("class"), str) or not char["class"]:
            raise ValueError("Character name/key mismatch or missing class")
        if char.get("faction") not in ("Horde", "Alliance", None):
            raise ValueError("Unreviewed faction")
        _integer(char.get("level"), "level", 1, 1000)
        for field in ("updated", "seen", "playedAt", "bankAt"):
            if char.get(field) is not None:
                _integer(char[field], field, 1, 253402300799)
        for field in ("money", "xp", "xpMax", "rested", "played", "ilvl"):
            if char.get(field) is not None:
                _integer(char[field], field)
        for field in ("bags", "bank", "mail", "equip"):
            if char.get(field) is not None:
                _counts(char[field], field)
        for field in ("profs", "profMax"):
            if char.get(field) is not None:
                if not isinstance(char[field], dict):
                    raise ValueError(f"Expected {field} table")
                for name, skill in char[field].items():
                    if not isinstance(name, str) or not name:
                        raise ValueError("Invalid profession name")
                    _integer(skill, "profession skill")
        if char.get("gear") is not None:
            if not isinstance(char["gear"], dict):
                raise ValueError("Expected gear table")
            for slot, link in char["gear"].items():
                _integer(slot, "equipment slot", 1, 100)
                if link is not None and (not isinstance(link, str) or not re.search(r"\|Hitem:[1-9]\d*:", link)):
                    raise ValueError("Invalid equipment item link")
        for field in ("layout", "recipes", "crafts", "reps", "duraSlots"):
            if char.get(field) is not None and not isinstance(char[field], dict):
                raise ValueError(f"Expected {field} table")
        for bag, slots in (char.get("layout") or {}).items():
            _integer(bag, "bag identifier", -100, 100)
            if not isinstance(slots, dict):
                raise ValueError("Expected bag slot table")
            for slot, packed in slots.items():
                _integer(slot, "bag slot", 0, 10000)
                _integer(packed, "packed bag slot")
        for profession, recipes in (char.get("recipes") or {}).items():
            if not isinstance(profession,str) or not isinstance(recipes,dict) or any(
                not isinstance(name,str) or known is not True for name,known in recipes.items()):
                raise ValueError("Invalid learned-recipe table")
    return root


def discover_alts_files(configured: tuple[str, ...] = ()) -> list[Path]:
    from .discovery import discover_saved_files
    return discover_saved_files("AltsForever.lua", configured)


class AltsForeverAdapter:
    capability = AdapterCapability(
        key="alts_forever_savedvariables_v2", display_name="Alts Forever character observations", status="ready",
        input_types=("AltsForever.lua SavedVariables v2",),
        supplies=("character progress", "equipment links and slots", "inventory quantities and layout",
                  "professions", "reputation", "recorded bank/mail/recipes"), needs=("WoW-saved Alts Forever file",),
        documentation_url="https://www.curseforge.com/wow/addons/alts-forever",
        notes="Inspected installed addon 0.9.1 and a real v2 capture. Missing coverage stays unknown; no game access.")

    def import_file(self, database: Database, path: Path) -> ImportResult:
        root = parse_alts_file(path)
        now = datetime.now(timezone.utc).isoformat()
        # Full names are unique only in the addon's account/region context. Never merge accounts by name.
        namespace = hashlib.sha256(str(path.resolve()).casefold().encode()).hexdigest()[:24]
        imported = records = 0
        with database.transaction() as connection:
            connection.execute("""INSERT INTO sources(source_key,name,source_type,url,trust_rank,notes,last_success_at)
                VALUES (?,'Alts Forever character observations','local_character_observation',?,1,?,?)
                ON CONFLICT(source_key) DO UPDATE SET last_success_at=excluded.last_success_at,last_error=NULL""",
                (SOURCE_KEY, self.capability.documentation_url, "Saved character evidence; auction workspace is configured separately.", now))
            source_id = connection.execute("SELECT id FROM sources WHERE source_key=?", (SOURCE_KEY,)).fetchone()[0]
            for name, char in root["chars"].items():
                body = json.dumps({"schema_version": 2, "character": char, "factions": root.get("factions"),
                                   "recipeInfo": root.get("recipeInfo"), "namespace": namespace},
                                  sort_keys=False, ensure_ascii=False, separators=(",", ":"))
                # Dict insertion order is stable for a WoW save; canonicalize recursively including mixed Lua keys.
                def canonical(value):
                    if isinstance(value, dict):
                        return [[type(k).__name__, k, canonical(v)] for k,v in sorted(value.items(), key=lambda p:(type(p[0]).__name__, str(p[0])))]
                    return value
                digest = hashlib.sha256(json.dumps(canonical(json.loads(body)), ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
                if connection.execute("SELECT 1 FROM character_snapshots WHERE sha256=?", (digest,)).fetchone():
                    continue
                captured = (datetime.fromtimestamp(char["updated"], timezone.utc).isoformat()
                            if char.get("updated") else None)
                reference = path.resolve().as_uri() + "#AltsForeverDB/chars/" + name
                snapshot_id = connection.execute("""INSERT INTO character_snapshots(character_key,name,realm,race,class_token,
                    level,source_key,source_version,game_build,imported_at,captured_at,evidence_kind,confidence,confidence_basis,
                    raw_reference,sha256,payload_json,limitations_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (f"alts-forever:{namespace}:{name}",name,"unknown","unknown",char["class"],char["level"],SOURCE_KEY,
                     "SavedVariables v2 (inspected addon 0.9.1)","unknown",now,captured,"observed",0.9,
                     "Direct WoW-saved addon observation; coverage and field freshness vary, not a probability.",
                     reference,digest,body,json.dumps(LIMITATIONS))).lastrowid
                for slot, link in (char.get("gear") or {}).items():
                    if link is None:
                        continue
                    item_id = int(re.search(r"\|Hitem:(\d+):", link).group(1))
                    _integer(item_id, "equipment item ID", 1)
                    connection.execute("""INSERT INTO character_item_observations
                        (snapshot_id,location,ordinal,item_id,enchant_id,random_suffix,slot_id)
                        VALUES (?,'equipped',?,?,0,0,?)""", (snapshot_id,slot,item_id,slot))
                    records += 1
                for field, location in (("bags","bag"),("bank","bank"),("mail","mail")):
                    rows = [(snapshot_id,location,item_id,quantity) for item_id,quantity in (char.get(field) or {}).items()]
                    connection.executemany("INSERT INTO character_inventory_observations VALUES (?,?,?,?)", rows)
                    records += len(rows)
                imported += 1
            if imported:
                connection.execute("""INSERT INTO imports(adapter_key,source_id,started_at,completed_at,status,file_name,record_count)
                    VALUES (?,?,?,?,'complete',?,?)""", (self.capability.key,source_id,now,now,str(path),records))
        return ImportResult(self.capability.key, SOURCE_KEY, records, imported, LIMITATIONS)


class AltsForeverWatcher:
    def __init__(self, database: Database, paths: tuple[str, ...] = (), interval: int = 3):
        self.database, self.paths, self.interval = database, paths, max(3, interval)
        self._signatures = {}
        self._stop = threading.Event()
        self._thread = None

    def scan_once(self):
        results = []
        for path in discover_alts_files(self.paths):
            try:
                stat = path.stat()
                signature = (stat.st_mtime_ns, stat.st_size)
                if self._signatures.get(str(path)) == signature:
                    continue
                results.append(AltsForeverAdapter().import_file(self.database, path))
                self._signatures[str(path)] = signature
            except Exception as exc:
                logging.exception("Alts Forever saved-file import failed: %s", path)
                with self.database.transaction() as connection:
                    connection.execute("""INSERT INTO sources(source_key,name,source_type,trust_rank,last_error)
                        VALUES (?,'Alts Forever character observations','local_character_observation',1,?)
                        ON CONFLICT(source_key) DO UPDATE SET last_error=excluded.last_error""", (SOURCE_KEY,str(exc)))
        return results

    @resilient_run
    def _run(self):
        while not self._stop.is_set():
            self.scan_once()
            self._stop.wait(self.interval)

    def start(self):
        self._thread = threading.Thread(target=self._run, name="alts-forever-watcher", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)
