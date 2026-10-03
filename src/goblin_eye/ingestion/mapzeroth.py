"""Import Mapzeroth's authored Forever world-travel graph without executing Lua."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

from goblin_eye.repository import Database
from .base import AdapterCapability, ImportResult
from .bounded import read_file
from .lua_literals import LuaLiteralReader


SOURCE_KEY = "mapzeroth-forever"
SOURCE_URL = "https://www.curseforge.com/wow/addons/mapzeroth"
FILES = ("Mapzeroth.toc", "Data/Forever/Nodes_EasternKingdoms.lua", "Data/Forever/Nodes_Kalimdor.lua",
         "Data/Forever/Nodes_ZephrasIsle.lua", "Data/Forever/NodeNames_enUS.lua", "Data/Forever/Edges.lua",
         "Data/Forever/Flights.lua", "Data/Forever/Borders.lua", "Data/Forever/Pois.lua", "Data/Forever/Blackrock.lua")
LIMITATIONS = (
    "Mapzeroth is a route-planning dataset: authored costs are planning inputs, not guarantees of travel time.",
    "Evidence labels preserve measured, captured, estimated, placeholder, rough-map and derived assertions; callers must not pool them as equally verified.",
    "The graph does not establish current access, player discovery, PvP safety, waiting time at a particular arrival, or phase availability.",
    "Only authored world nodes and edges are imported; player-specific abilities, hearthstones, professions and movement-speed calculations remain runtime inputs.",
)


def _sequence(value: dict, label: str) -> list:
    if not isinstance(value, dict) or set(value) != set(range(1, len(value) + 1)):
        raise ValueError(f"{label} must be a contiguous literal sequence")
    return [value[index] for index in range(1, len(value) + 1)]


def _read_after(text: str, end: int):
    reader = LuaLiteralReader(text, end)
    value = reader.read()
    return value, reader.position


def _assigned_sequence(text: str, name: str) -> list:
    matches = list(re.finditer(rf"^addon\.Nodes\.{re.escape(name)}\s*=\s*", text, re.MULTILINE))
    if len(matches) != 1:
        raise ValueError(f"Expected one Mapzeroth node table {name}")
    value, _ = _read_after(text, matches[0].end())
    return _sequence(value, name)


def _comment_after(text: str, end: int) -> str:
    tail = text[end:text.find("\n", end) if text.find("\n", end) >= 0 else len(text)]
    match = re.search(r"--\s*(.*)", tail)
    return match.group(1).strip() if match else ""


def _literal_edge_tables(text: str) -> list[tuple[dict, int, str]]:
    results = []
    covered = []
    for match in re.finditer(r"ipairs\(\s*", text):
        value, end = _read_after(text, match.end())
        for row in _sequence(value, "edge block"):
            if not isinstance(row, dict): raise ValueError("Invalid edge row")
            results.append((row, match.start(), ""))
        covered.append((match.start(), end))
    for match in re.finditer(r"table\.insert\(addon\.Edges\s*,\s*(?=\{)", text):
        if any(start <= match.start() <= end for start, end in covered):
            continue
        value, end = _read_after(text, match.end())
        if not isinstance(value, dict): raise ValueError("Invalid direct edge row")
        results.append((value, match.start(), _comment_after(text, end)))
    return results


def _basis(text: str, default: str) -> str:
    value = text.casefold()
    if "placeholder" in value: return "placeholder"
    if "estimated" in value or "estimate" in value: return "estimated"
    if "measured live" in value or "live-measured" in value or "captured live" in value: return "measured_live"
    if "verify" in value or "untested" in value: return "unverified"
    return default


def _line_comment_for_id(text: str, node_id: str) -> str:
    match = re.search(rf'^.*id\s*=\s*"{re.escape(node_id)}".*$', text, re.MULTILINE)
    if not match: return ""
    found = re.search(r"--\s*(.*)$", match.group(), re.MULTILINE)
    return found.group(1).strip() if found else ""


def _line_comment_for_edge(text: str, from_node: str, to_node: str) -> str:
    match = re.search(rf'^.*from\s*=\s*"{re.escape(from_node)}".*to\s*=\s*"{re.escape(to_node)}".*$', text, re.MULTILINE)
    if not match: return ""
    found = re.search(r"--\s*(.*)$", match.group(), re.MULTILINE)
    return found.group(1).strip() if found else ""


def parse_mapzeroth(root: Path) -> dict:
    root = root.resolve()
    files = {name: read_file(root / Path(name), 10_000_000) for name in FILES}
    texts = {name: body.decode("utf-8-sig") for name, body in files.items()}
    toc = texts["Mapzeroth.toc"]
    version = re.search(r"^## Version:\s*(.+)$", toc, re.MULTILINE)
    if not version or not re.search(r"^## Interface:\s*16001\s*$", toc, re.MULTILINE):
        raise ValueError("Unreviewed Mapzeroth interface or version")
    locale_text = texts["Data/Forever/NodeNames_enUS.lua"]
    match = re.search(r'addon:RegisterLocale\("enUS",\s*', locale_text)
    if not match: raise ValueError("Missing Mapzeroth enUS node labels")
    names_raw, _ = _read_after(locale_text, match.end())
    names = {key.removeprefix("NODE_"): value for key, value in names_raw.items() if isinstance(key, str) and key.startswith("NODE_")}

    nodes = {}
    node_files = (("Data/Forever/Nodes_EasternKingdoms.lua", "EasternKingdoms", "authored_coordinate"),
                  ("Data/Forever/Nodes_Kalimdor.lua", "Kalimdor", "authored_coordinate"),
                  ("Data/Forever/Nodes_ZephrasIsle.lua", "ZephrasIsle", "authored_coordinate"),
                  ("Data/Forever/Borders.lua", "Borders", "rough_map_coordinate"),
                  ("Data/Forever/Pois.lua", "Pois", "authored_coordinate"))
    for file_name, group, default_basis in node_files:
        text = texts[file_name]
        for row in _assigned_sequence(text, group):
            if not isinstance(row, dict) or not isinstance(row.get("id"), str):
                raise ValueError("Invalid Mapzeroth node")
            node_id = row["id"]
            if node_id in nodes: raise ValueError(f"Duplicate Mapzeroth node {node_id}")
            comment = _line_comment_for_id(text, node_id)
            basis = _basis(comment, default_basis)
            nodes[node_id] = dict(node_key=node_id, name=names.get(node_id), container=row.get("container"),
                ui_map_id=row.get("mapID"), x=row.get("x"), y=row.get("y"), kind=row.get("kind"),
                evidence_basis=basis, attributes={"group": group, "source_fields": row, "source_comment": comment},
                raw_reference=f"{file_name}#node/{node_id}")

    edges = []
    edge_files = (("Data/Forever/Flights.lua", "measured_reference"),
                  ("Data/Forever/Edges.lua", "authored_route"),
                  ("Data/Forever/Borders.lua", "rough_map_route"))
    for file_name, default_basis in edge_files:
        text = texts[file_name]
        for index, (row, position, direct_comment) in enumerate(_literal_edge_tables(text), 1):
            if not isinstance(row.get("from"), str) or not isinstance(row.get("to"), str):
                raise ValueError("Mapzeroth edge is missing endpoints")
            line = text.count("\n", 0, position) + 1
            source_comment = direct_comment or _line_comment_for_edge(text, row["from"], row["to"])
            context = source_comment or text[position:max(position, text.find("\n", position))]
            method = row.get("method") or "taxi"  # the first Edges block and Flights set this in their inspected loops
            if file_name.endswith("Flights.lua"): method = "taxi"
            edges.append(dict(from_node=row["from"], to_node=row["to"], method=method, cost=row.get("cost"),
                fare=row.get("fare"), loading=row.get("loadingScreens"), one_way=bool(row.get("oneway")),
                evidence_basis=_basis(context, default_basis), requirements=row.get("requirements") or {},
                attributes={"source_fields": row, "source_comment": source_comment},
                raw_reference=f"{file_name}:{line}#edge/{index}"))

    # Blackrock.lua deliberately generates the Cartesian product of two literal lists.
    blackrock = texts["Data/Forever/Blackrock.lua"]
    def local_sequence(name):
        match = re.search(rf"^local {name}\s*=\s*", blackrock, re.MULTILINE)
        if not match: raise ValueError(f"Missing Blackrock {name}")
        value, _ = _read_after(blackrock, match.end())
        return _sequence(value, name)
    for door in local_sequence("doors"):
        for instance in local_sequence("instances"):
            edges.append(dict(from_node=door, to_node=instance, method="walk", cost=None, fare=None, loading=None,
                one_way=False, evidence_basis="approximate", requirements={},
                attributes={"generator": "door x instance", "source_comment": "instance positions are Wowhead markers; walks are approximations"},
                raw_reference=f"Data/Forever/Blackrock.lua#edge/{door}/{instance}"))
    missing = sorted({key for edge in edges for key in (edge["from_node"], edge["to_node"])} - set(nodes))
    if missing:
        raise ValueError(f"Travel edges reference missing nodes: {missing[:10]}")
    hashes = {name: hashlib.sha256(body).hexdigest() for name, body in files.items()}
    fingerprint = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    return {"root": root, "files": files, "hashes": hashes, "fingerprint": fingerprint,
            "version": version.group(1).strip(), "nodes": tuple(nodes.values()), "edges": tuple(edges)}


class MapzerothAdapter:
    capability = AdapterCapability(
        key="mapzeroth_forever_v1", display_name="Mapzeroth Forever travel graph", status="ready",
        input_types=("installed static Mapzeroth Forever Lua tables",),
        supplies=("travel nodes", "directed route edges", "taxi times and fares", "route evidence labels"),
        needs=("installed Mapzeroth package",), documentation_url=SOURCE_URL,
        notes="Imports static authored graph only; player-specific abilities and movement calculations stay runtime inputs.")

    def import_file(self, database: Database, path: Path) -> ImportResult:
        data = parse_mapzeroth(path)
        now = datetime.now(timezone.utc).isoformat()
        with database.transaction() as connection:
            connection.execute("""INSERT INTO sources(source_key,name,source_type,url,trust_rank,notes,last_success_at)
                VALUES (?, 'Mapzeroth Forever travel graph', 'bundled_travel_database', ?, 5, ?, ?)
                ON CONFLICT(source_key) DO UPDATE SET last_success_at=excluded.last_success_at,last_error=NULL""",
                (SOURCE_KEY, SOURCE_URL, "Static planning graph; evidence basis distinguishes measured and estimated data.", now))
            source_id = connection.execute("SELECT id FROM sources WHERE source_key=?", (SOURCE_KEY,)).fetchone()[0]
            existing = connection.execute("""SELECT id,active FROM research_datasets
                WHERE source_id=? AND dataset_key='travel-graph' AND sha256=?""", (source_id, data["fingerprint"])).fetchone()
            if existing and existing["active"]:
                return ImportResult(self.capability.key, SOURCE_KEY, 0, 0, ("Dataset already imported; unchanged.",))
            connection.execute("UPDATE research_datasets SET active=0 WHERE source_id=? AND dataset_key='travel-graph'", (source_id,))
            if existing:
                connection.execute("UPDATE research_datasets SET active=1 WHERE id=?", (existing["id"],))
                return ImportResult(self.capability.key, SOURCE_KEY, 0, 0, ("Previously imported revision reactivated.",))
            manifest = {name: {"path": str(data["root"] / Path(name)), "sha256": data["hashes"][name], "bytes": len(body)}
                        for name, body in data["files"].items()}
            cursor = connection.execute("""INSERT INTO research_datasets(source_id,dataset_key,sha256,source_version,game_build,
                content_phase,retrieved_at,confidence,evidence_kind,manifest_json,limitations_json)
                VALUES (?,'travel-graph',?,?,NULL,'Forever',?,0.6,'extracted',?,?)""",
                (source_id, data["fingerprint"], data["version"], now, json.dumps(manifest), json.dumps(LIMITATIONS)))
            dataset_id = cursor.lastrowid
            connection.executemany("""INSERT INTO travel_nodes(dataset_id,node_key,name,container_key,ui_map_id,x,y,kind,
                evidence_basis,attributes_json,raw_reference) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                ((dataset_id, n["node_key"], n["name"], n["container"], n["ui_map_id"], n["x"], n["y"], n["kind"],
                  n["evidence_basis"], json.dumps(n["attributes"], ensure_ascii=False), n["raw_reference"]) for n in data["nodes"]))
            connection.executemany("""INSERT INTO travel_edges(dataset_id,from_node_key,to_node_key,method,cost_seconds,fare_copper,
                loading_screens,one_way,evidence_basis,requirements_json,attributes_json,raw_reference)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                ((dataset_id, e["from_node"], e["to_node"], e["method"], e["cost"], e["fare"], e["loading"],
                  int(e["one_way"]), e["evidence_basis"], json.dumps(e["requirements"]),
                  json.dumps(e["attributes"], ensure_ascii=False), e["raw_reference"]) for e in data["edges"]))
            for name, body in data["files"].items():
                connection.execute("""INSERT OR IGNORE INTO source_documents(source_id,url,retrieved_at,content_type,sha256,body)
                    VALUES (?,?,?,'text/plain; charset=utf-8',?,?)""",
                    (source_id, (data["root"] / Path(name)).as_uri(), now, data["hashes"][name], body))
            count = len(data["nodes"]) + len(data["edges"])
            connection.execute("""INSERT INTO imports(adapter_key,source_id,started_at,completed_at,status,file_name,record_count)
                VALUES (?,?,?,?,'complete',?,?)""", (self.capability.key, source_id, now, now, str(data["root"]), count))
        return ImportResult(self.capability.key, SOURCE_KEY, count, 0, LIMITATIONS)
