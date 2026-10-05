"""Import the inspected LibProfessionDB Forever literal data, without loading Lua."""
from __future__ import annotations

from .bounded import read_file, read_stream, resilient_run

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import threading

from goblin_eye.repository import Database
from .auctionator import discover_auctionator_files
from .base import AdapterCapability, ImportResult
from .lua_literals import read_library_table


SOURCE_KEY = "libprofessiondb-forever"
SOURCE_URL = "https://www.curseforge.com/wow/addons/libprofessiondb"
LIMITATIONS = (
    "Client-extracted recipe existence does not prove current obtainability or availability at the level cap.",
    "Output quantities are absent from this source and remain unknown.",
    "Required skill is the source's value; Forever trainer requirements are not independently verified.",
    "Vendor, trainer and drop acquisition locations are not imported from this recipe dataset.",
    "Required skills marked as borrowed retain their provider-reported origin, such as Vanilla; they are not independently verified Forever requirements.",
    "The provider's hidden-recipe and acquisition-location metadata files are cached as source documents, not imported as availability or location assertions.",
    "Synthetic recipe-scroll descriptors are excluded. Missing teaching items do not prove trainer acquisition.",
)


@dataclass(frozen=True)
class RecipeEvidence:
    spell_id: int
    profession_id: int
    profession: str
    name: str | None
    output_item_id: int | None
    skill_required: int | None
    reagents: dict[int, int]
    teaching_item_id: int | None
    attributes: dict
    raw_reference: str


@dataclass(frozen=True)
class ProfessionDataset:
    root: Path
    version: str
    build: str
    fingerprint: str
    files: dict[str, bytes]
    recipes: tuple[RecipeEvidence, ...]


def positive_id(value, field: str) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{field} must be a positive integer")
    return value


def parse_professiondb(root: Path) -> ProfessionDataset:
    root = root.resolve()
    files: dict[str, bytes] = {}

    def read(relative: str) -> str:
        path = (root / relative).resolve()
        if not path.is_relative_to(root) or path.suffix.lower() not in (".lua", ".toc", ""):
            raise ValueError("Unexpected addon data path")
        body = read_file(path, 5_000_000)
        if len(body) > 5_000_000:
            raise ValueError("Addon data file exceeds supported size")
        files[relative] = body
        return body.decode("utf-8-sig")

    toc = read("ProfessionDB_Camelot.toc")
    version = re.search(r"^## Version:\s*(.+)$", toc, re.MULTILINE)
    if not version or not re.search(r"^## Interface:\s*16001\s*$", toc, re.MULTILINE):
        raise ValueError("Expected inspected Forever TOC interface 16001; review newer interfaces before importing")
    license_text = read("LICENSE")
    if not license_text.startswith("MIT License"):
        raise ValueError("Unreviewed dataset license")
    core_paths = [line.strip().replace("\\", "/") for line in toc.splitlines()
                  if line.strip().replace("\\", "/").startswith("Data/Forever/_core/")]
    if not core_paths or len(core_paths) != len(set(core_paths)):
        raise ValueError("Missing or duplicate Forever core files")
    recipe_items_path = "Data/Forever/_core/RecipeItems.lua"
    acquire_path = "Data/Forever/_core/AcquireMethods.lua"
    if recipe_items_path not in core_paths or acquire_path not in core_paths:
        raise ValueError("Required Forever metadata files are absent from the TOC")
    teaching_text = read(recipe_items_path)
    _, teaching = read_library_table(teaching_text, "LoadRecipeItems")
    _, rank_books = read_library_table(teaching_text, "LoadSkillRankBooks")
    acquire_text = read(acquire_path)
    _, acquire = read_library_table(acquire_text, "LoadAcquireMethods")
    # Deliberately never parse or invoke LoadSyntheticRecipes/GetSyntheticRecipeScroll.
    builds = set(re.findall(r"(?:client )?build (\d+\.\d+\.\d+\.\d+)", teaching_text + acquire_text))
    recipes = []
    for relative in core_paths:
        if relative in (recipe_items_path, acquire_path):
            continue
        if relative in {f"Data/Forever/_core/{name}.lua" for name in ("HiddenRecipes", "Sources", "SourceNames")}:
            # These v1.9 catalogs describe availability and emulator-sourced
            # acquisition, not profession recipe rows. Preserve their source
            # documents without converting them into unsupported Forever facts.
            read(relative)
            continue
        text = read(relative)
        if "WoW Forever" not in text[:250] or 'IsGameVersion("Forever")' not in text:
            raise ValueError(f"Missing Forever guard: {relative}")
        stamp = re.search(r"-- build (\d+\.\d+\.\d+\.\d+) - (\d+) recipes", text)
        if not stamp:
            raise ValueError(f"Missing source build/count: {relative}")
        builds.add(stamp.group(1))
        borrowed = {}
        profession_id, core = read_library_table(text, "LoadCore", True, ("LoadEnchantsCore", "LoadBorrowed"), borrowed)
        if len(core) != int(stamp.group(2)):
            raise ValueError(f"Source row count mismatch: {relative}")
        names_path = relative.replace("/_core/", "/enUS/")
        if names_path.replace("/", "\\") not in toc and names_path not in toc:
            raise ValueError(f"Locale file not declared in TOC: {names_path}")
        names_id, names = read_library_table(read(names_path), "LoadNames", True, ("LoadEnchantsNames",))
        if names_id != profession_id or set(names) != set(core):
            raise ValueError(f"Core/locale identity mismatch: {relative}")
        profession = Path(relative).stem
        if profession == "Firstaid":
            profession = "First Aid"
        for spell_id, fields in core.items():
            positive_id(spell_id, "spell ID")
            if not isinstance(fields, dict) or not isinstance(fields.get("reagents"), dict):
                raise ValueError(f"Missing reagent table: {spell_id}")
            supported = {"craftedItemId", "difficulty", "reagents", "requiredSkill", "teaches", "itemId",
                         "phase", "enchantId", "enchantSlot", "stats", "slots", "requiredSpec"}
            if set(fields) - supported:
                raise ValueError(f"Unreviewed recipe fields: {set(fields) - supported}")
            if fields.get("teaches") != spell_id:
                raise ValueError(f"Unexpected recipe spell mapping: {spell_id}")
            reagents = {positive_id(item, "reagent ID"): positive_id(quantity, "reagent quantity")
                        for item, quantity in fields["reagents"].items()}
            output = fields.get("craftedItemId")
            if output is not None:
                positive_id(output, "output item ID")
            skill = fields.get("requiredSkill")
            if skill is not None and (type(skill) is not int or skill < 0):
                raise ValueError("Invalid required skill")
            teaching_id = teaching.get(spell_id)
            if teaching_id is not None:
                positive_id(teaching_id, "teaching item ID")
            if fields.get("itemId") is not None and fields["itemId"] != teaching_id:
                raise ValueError(f"Conflicting teaching-item assertions within package: {spell_id}")
            localized = names[spell_id]
            if not isinstance(localized, dict) or not isinstance(localized.get("name"), str):
                raise ValueError(f"Missing literal recipe name: {spell_id}")
            attributes = {"source_fields": {key: value for key, value in fields.items() if key != "reagents"},
                          "localized_fields": localized, "locale": "enUS", "names_reference": f"{names_path}#{spell_id}",
                          "acquire_method": acquire.get(spell_id), "is_skill_rank": bool(rank_books.get(spell_id)),
                          "acquisition_reference": f"{acquire_path}#{spell_id}" if spell_id in acquire else None}
            if spell_id in borrowed:
                attributes["borrowed_fields"] = borrowed[spell_id]
                attributes["required_skill_basis"] = "borrowed:" + borrowed[spell_id]["requiredSkill"]
            recipes.append(RecipeEvidence(spell_id, positive_id(profession_id, "profession ID"), profession,
                localized["name"], output, skill, reagents, teaching_id, attributes, f"{relative}#{spell_id}"))
    if len(builds) != 1 or not recipes:
        raise ValueError("Mixed/missing source builds or empty recipe dataset")
    hashes = {path: hashlib.sha256(body).hexdigest() for path, body in sorted(files.items())}
    identity_hashes = {path: digest for path, digest in hashes.items() if not path.lower().endswith('.toc')}
    fingerprint = hashlib.sha256(json.dumps(identity_hashes, sort_keys=True).encode()).hexdigest()
    return ProfessionDataset(root, version.group(1).strip(), builds.pop(), fingerprint, files, tuple(recipes))


class ProfessionDBAdapter:
    capability = AdapterCapability(
        key="libprofessiondb_forever_literals_v1", display_name="LibProfessionDB Forever",
        status="ready", input_types=("installed ProfessionDB Forever literal data",),
        supplies=("recipe dependencies", "reagents", "output item IDs", "teaching item IDs", "profession requirements"),
        needs=("installed Forever data tree",), documentation_url=SOURCE_URL,
        notes="Reads static files only. Output counts and acquisition locations remain unknown; synthetic scrolls excluded.",
    )

    def import_file(self, database: Database, path: Path) -> ImportResult:
        dataset = parse_professiondb(path)  # All parsing/validation happens before any mutation.
        now = datetime.now(timezone.utc).isoformat()
        manifest = {name: {"sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body),
                           "path": str(dataset.root / name)} for name, body in sorted(dataset.files.items())}
        with database.transaction() as connection:
            connection.execute("""INSERT INTO sources(source_key, name, source_type, url, trust_rank, notes, last_success_at)
                VALUES (?, 'LibProfessionDB Forever', 'client_extracted_addon', ?, 3, ?, ?)
                ON CONFLICT(source_key) DO UPDATE SET last_success_at=excluded.last_success_at, last_error=NULL""",
                (SOURCE_KEY, SOURCE_URL, "MIT; literal Forever data only; source confidence is a policy assessment, not a probability.", now))
            source_id = connection.execute("SELECT id FROM sources WHERE source_key=?", (SOURCE_KEY,)).fetchone()[0]
            existing = connection.execute("SELECT id, active FROM research_datasets WHERE source_id=? AND dataset_key='recipes-enUS' AND sha256=?",
                                          (source_id, dataset.fingerprint)).fetchone()
            if existing and existing["active"]:
                return ImportResult(self.capability.key, SOURCE_KEY, 0, 0, ("Dataset already imported; unchanged.",))
            connection.execute("UPDATE research_datasets SET active=0 WHERE source_id=? AND dataset_key='recipes-enUS'", (source_id,))
            if existing:
                connection.execute("UPDATE research_datasets SET active=1 WHERE id=?", (existing["id"],))
                return ImportResult(self.capability.key, SOURCE_KEY, 0, 0, ("Previously imported revision reactivated.",))
            cursor = connection.execute("""INSERT INTO research_datasets(source_id, dataset_key, sha256, source_version,
                game_build, content_phase, retrieved_at, confidence, evidence_kind, manifest_json, limitations_json)
                VALUES (?, 'recipes-enUS', ?, ?, ?, 'Forever beta', ?, 0.8, 'extracted', ?, ?)""",
                (source_id, dataset.fingerprint, dataset.version, dataset.build, now,
                 json.dumps(manifest), json.dumps(LIMITATIONS)))
            dataset_id = cursor.lastrowid
            for relative, body in dataset.files.items():
                connection.execute("""INSERT OR IGNORE INTO source_documents(source_id, url, retrieved_at, content_type, sha256, body)
                    VALUES (?, ?, ?, 'text/plain; charset=utf-8', ?, ?)""",
                    (source_id, (dataset.root / relative).as_uri(), now, hashlib.sha256(body).hexdigest(), body))
            for recipe in dataset.recipes:
                cursor = connection.execute("""INSERT INTO recipe_facts(dataset_id, spell_id, name, profession_id, profession,
                    output_item_id, output_quantity, skill_required, attributes_json, raw_reference)
                    VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?, ?)""",
                    (dataset_id, recipe.spell_id, recipe.name, recipe.profession_id, recipe.profession, recipe.output_item_id,
                     recipe.skill_required, json.dumps(recipe.attributes), recipe.raw_reference))
                fact_id = cursor.lastrowid
                connection.executemany("INSERT INTO reagent_facts(recipe_fact_id, item_id, quantity) VALUES (?, ?, ?)",
                                       ((fact_id, item, quantity) for item, quantity in recipe.reagents.items()))
                if recipe.teaching_item_id is not None:
                    connection.execute("INSERT INTO recipe_teaching_items(recipe_fact_id, item_id, raw_reference) VALUES (?, ?, ?)",
                        (fact_id, recipe.teaching_item_id, f"Data/Forever/_core/RecipeItems.lua#{recipe.spell_id}"))
            connection.execute("""INSERT INTO imports(adapter_key, source_id, started_at, completed_at, status, file_name, record_count)
                VALUES (?, ?, ?, ?, 'complete', ?, ?)""",
                (self.capability.key, source_id, now, now, str(dataset.root), len(dataset.recipes)))
        return ImportResult(self.capability.key, SOURCE_KEY, len(dataset.recipes), 0, LIMITATIONS)


def discover_professiondb_paths(configured: tuple[str, ...] = ()) -> list[Path]:
    from .discovery import discover_addon_paths
    candidates = {Path(path) for path in configured}
    for saved in discover_auctionator_files():
        for parent in saved.parents:
            if parent.name == "WTF":
                candidates.add(parent.parent / "Interface" / "AddOns" / "ProfessionDB")
    return discover_addon_paths("ProfessionDB", "ProfessionDB_Camelot.toc", candidates)


class ProfessionDBWatcher:
    def __init__(self, database: Database, paths: tuple[str, ...] = (), interval: int = 60):
        self.database, self.paths, self.interval = database, paths, max(10, interval)
        self._stop = threading.Event()
        self._signatures: dict[str, tuple] = {}
        self._thread: threading.Thread | None = None

    def scan_once(self) -> list[ImportResult]:
        results = []
        for path in discover_professiondb_paths(self.paths):
            try:
                watched = [path / "ProfessionDB_Camelot.toc", path / "LICENSE", *sorted((path / "Data" / "Forever").rglob("*.lua"))]
                signature = tuple((str(file), file.stat().st_mtime_ns, file.stat().st_size) for file in watched)
                if self._signatures.get(str(path)) == signature:
                    continue
                results.append(ProfessionDBAdapter().import_file(self.database, path))
                self._signatures[str(path)] = signature
            except Exception as exc:
                import logging
                logging.exception("Source path failed: %s", path)
                try:
                    with self.database.transaction() as connection:
                        connection.execute("""INSERT INTO sources(source_key,name,source_type,url,trust_rank,last_error)
                            VALUES (?, 'LibProfessionDB Forever', 'client_extracted_addon', ?, 3, ?)
                            ON CONFLICT(source_key) DO UPDATE SET last_error=excluded.last_error""", (SOURCE_KEY,SOURCE_URL,str(exc)))
                except Exception:
                    logging.exception("Could not record source error")
        return results


    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="professiondb-watcher", daemon=True)
        self._thread.start()

    @resilient_run
    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.scan_once()
            except Exception as exc:
                with self.database.transaction() as connection:
                    connection.execute("""INSERT INTO sources(source_key, name, source_type, url, trust_rank, last_error)
                        VALUES (?, 'LibProfessionDB Forever', 'client_extracted_addon', ?, 3, ?)
                        ON CONFLICT(source_key) DO UPDATE SET last_error=excluded.last_error""", (SOURCE_KEY, SOURCE_URL, str(exc)))
            self._stop.wait(self.interval)

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)
