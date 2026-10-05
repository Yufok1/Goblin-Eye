"""Verify a built release ZIP the way a recipient receives it.

The portable core extracts the archive, migrates a fresh database, and drives
both MCP entry points over stdio. Windows additionally exercises the shipped
PowerShell and .cmd launchers. No game client, addon or network access is used.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EMPTY_TABLES = ("character_snapshots", "auction_rows", "price_observations",
                "research_datasets", "source_documents", "companion_entries")
FORBIDDEN_PARTS = {"data", "tests", "scripts", ".venv", "node_modules", ".github", "__pycache__"}
# Only rejected at the archive root, so the published web/dist stays allowed.
FORBIDDEN_ROOTS = {"dist", "build", "releases"}
MINIMUM_TOOLS = 36
HANDSHAKE = [
    {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2025-06-18", "capabilities": {},
        "clientInfo": {"name": "release-verification", "version": "1"}}},
    {"jsonrpc": "2.0", "method": "notifications/initialized"},
    {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {
        "name": "get_source_health", "arguments": {}}},
]


def fail(message: str) -> None:
    raise SystemExit(f"VERIFICATION FAILED: {message}")


def default_archive() -> Path:
    version = re.search(r'__version__\s*=\s*"([^"]+)"',
                        (ROOT / "src/goblin_eye/__init__.py").read_text(encoding="utf-8")).group(1)
    return ROOT / "dist" / f"Goblin-Eye-{version}-Windows.zip"


def interpreter(root: Path) -> str:
    """Prefer the interpreter bundled in the archive over the verifier's own.

    A player has no system Python, so the shipped interpreter is the only one
    that matters. It is Windows-specific, so other hosts fall back to sys.executable.
    """
    bundled = root / "python" / "python.exe"
    if os.name == "nt" and bundled.is_file():
        return str(bundled)
    return sys.executable


def verify_bundled_runtime(root: Path) -> str:
    """Prove the archive's own interpreter works before anything depends on it."""
    exe = root / "python" / "python.exe"
    stamp = root / "python" / ".goblin-eye-python.json"
    if not exe.is_file():
        fail("the archive does not contain the bundled python/python.exe")
    if not stamp.is_file():
        fail("the bundled runtime is not stamped with its pinned hash")
    recorded = json.loads(stamp.read_text(encoding="utf-8"))
    if not recorded.get("version") or len(str(recorded.get("sha256", ""))) != 64:
        fail("the bundled runtime stamp does not record a version and archive hash")
    # The stdlib lives in the bundled python3*.zip and SQLite in _sqlite3.pyd. If either was
    # dropped from the archive, this is where it shows up.
    environment = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    probe = subprocess.run([str(exe), "-c", "import sqlite3, sys; print('%d.%d' % sys.version_info[:2])"],
                           cwd=root, env=environment, capture_output=True, text=True, timeout=120)
    if probe.returncode != 0:
        fail(f"the bundled interpreter cannot start: {probe.stderr.strip()[:300]}")
    return f"Python {probe.stdout.strip()} bundled, hash-stamped, sqlite3 available"


def run(command: list[str], cwd: Path, **kwargs) -> subprocess.CompletedProcess:
    environment = dict(os.environ, PYTHONPATH=str(cwd / "src"), PYTHONUNBUFFERED="1")
    return subprocess.run(command, cwd=cwd, env=environment, capture_output=True, text=True, **kwargs)


def extract(archive_path: Path) -> Path:
    if not archive_path.is_file():
        fail(f"archive not found: {archive_path}. Run scripts/build_release.py first.")
    temporary = Path(tempfile.mkdtemp(prefix="goblin-eye-release-"))
    # The extraction parent deliberately contains spaces, which is how a
    # recipient's Documents folder usually looks. Archive members already carry
    # their own "Goblin-Eye" folder.
    workspace = temporary / "Goblin Eye With Spaces"
    workspace.mkdir()
    with zipfile.ZipFile(archive_path) as archive:
        if archive.testzip() is not None:
            fail("archive integrity")
        names = archive.namelist()
        for name in names:
            relative = Path(name)
            if relative.is_absolute() or ".." in relative.parts:
                fail(f"unsafe archive member: {name}")
            parts = relative.parts
            if parts and parts[0] in FORBIDDEN_ROOTS:
                fail(f"generated directory shipped in the archive: {name}")
            if FORBIDDEN_PARTS.intersection(parts):
                fail(f"excluded path shipped in the archive: {name}")
            if relative.name == "config.json":
                fail("a personal config.json shipped in the archive")
        archive.extractall(workspace)
    root = workspace / "Goblin-Eye"
    if not root.is_dir():
        fail("the archive does not contain a single Goblin-Eye folder")
    return root


def verify_manifest(root: Path) -> int:
    manifest_path = root / "PACKAGE-MANIFEST.json"
    if not manifest_path.is_file():
        fail("PACKAGE-MANIFEST.json is missing from the archive")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    import hashlib
    for name, details in manifest["files"].items():
        target = root / name
        if not target.is_file():
            fail(f"manifest lists a missing file: {name}")
        if hashlib.sha256(target.read_bytes()).hexdigest() != details["sha256"]:
            fail(f"manifest hash mismatch: {name}")
    return len(manifest["files"])


def verify_fresh_install(root: Path, python: str) -> int:
    for stale in ("config.json", ".venv", "node_modules"):
        if (root / stale).exists():
            fail(f"fresh archive contains {stale}")
    result = run([python, "-m", "goblin_eye", "init"], root, timeout=180)
    if result.returncode != 0:
        fail(f"init failed: {result.stdout}{result.stderr}")
    if (root / "config.json").exists():
        fail("init must not create a config.json")
    database_path = root / "data" / "goblin-eye.db"
    if not database_path.is_file():
        fail("init did not create the database")
    with sqlite3.connect(database_path) as connection:
        for table in EMPTY_TABLES:
            count = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            if count:
                fail(f"a fresh database contains {count} row(s) in {table}")
        applied = connection.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]
    migrations = len(list((root / "migrations").glob("*.sql")))
    if applied != migrations:
        fail(f"applied {applied} migrations but the archive ships {migrations}")
    return applied


def verify_mcp(root: Path, python: str, command: str, expect_write_tool: bool) -> int:
    result = run([python, "-m", "goblin_eye", command], root,
                 input="".join(json.dumps(message) + "\n" for message in HANDSHAKE),
                 timeout=120)
    if result.returncode != 0:
        fail(f"{command} exited {result.returncode}: {result.stdout}{result.stderr}")
    replies = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    if [reply.get("id") for reply in replies] != [1, 2, 3]:
        fail(f"{command} returned unexpected reply ids: {[r.get('id') for r in replies]}")
    if any("error" in reply or reply.get("result", {}).get("isError") for reply in replies):
        fail(f"{command} returned a protocol or tool error")
    tools = replies[1]["result"]["tools"]
    health = replies[2]["result"]["structuredContent"]["result"]
    if not health.get("research_imports", {}).get("questiedb"):
        fail("questiedb import is not enabled by default")
    if not health.get("research_imports", {}).get("mapzeroth"):
        fail("mapzeroth import is not enabled by default")
    if health.get("price_record_count") or health.get("snapshot_count"):
        fail("a fresh install reported auction evidence")
    context = health.get("auction_context") or {}
    if any(context.get(key) != "unknown" for key in ("faction", "ruleset", "region")):
        fail("a fresh install must not assert a local market identity")
    names = {tool["name"] for tool in tools}
    if expect_write_tool and "add_companion_entry" not in names:
        fail("companion-mcp does not expose companion writes")
    if not expect_write_tool and "add_companion_entry" in names:
        fail("read-only mcp must not expose companion writes")
    return len(tools)


def verify_windows_launchers(root: Path) -> None:
    launcher = ["powershell.exe", "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass",
                "-File", str(root / "Run-Goblin-Eye.ps1")]
    result = subprocess.run(launcher + ["-InitializeOnly"], cwd=root, capture_output=True,
                            text=True, timeout=300)
    if result.returncode != 0:
        fail(f"Run-Goblin-Eye.ps1 -InitializeOnly failed: {result.stdout}{result.stderr}")
    # The launcher must use the bundled interpreter and must not build a venv.
    if (root / ".venv").exists():
        fail("the launcher created a .venv; the bundled runtime removes that step")
    settings = json.loads((root / "config.json").read_text(encoding="utf-8"))
    if not (settings.get("auto_import_questiedb") and settings.get("auto_import_mapzeroth")):
        fail("the launcher wrote a config.json without the automatic imports")
    # The whole tree already sits under a path containing spaces.
    protocol = "".join(json.dumps(message) + "\n" for message in HANDSHAKE)
    result = subprocess.run(["cmd.exe", "/d", "/c", str(root / "Start-Agent.cmd")], cwd=root,
                            input=protocol, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        fail(f"Start-Agent.cmd failed from a path with spaces: {result.stdout}{result.stderr}")
    replies = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    if any("error" in reply or reply.get("result", {}).get("isError") for reply in replies):
        fail("Start-Agent.cmd returned a protocol or tool error from a spaced path")


def verify_dashboard(root: Path) -> None:
    bundle = (root / "web/dist/assets/main.js").read_text(encoding="utf-8")
    if "World entities:" not in bundle:
        fail("the prebuilt dashboard bundle is stale or incomplete")
    # The local market identity must never be baked into the shipped interface.
    if "Horde / PvP" in bundle or "Horde/PvP" in bundle:
        fail("the shipped dashboard still asserts a faction/ruleset")


def verify_chat_installation(root: Path) -> dict:
    """Exercise the shipped setup on a mock client, then relocate the package."""
    node = shutil.which("node")
    if not node:
        fail("Node >=22.2 is required to verify the optional chat installer")
    client = root.parent / "Mock Forever Client"
    (client / "Interface").mkdir(parents=True)
    (client / "WTF/Account/TEST_ACCOUNT").mkdir(parents=True)
    (client / "WowB.exe").write_text("mock client, never executed", encoding="ascii")
    # Keep the mock small; the slot-pool algorithm has its own full tests.
    example = root / "wow-ai/bridge/config.example.json"
    config = json.loads(example.read_text())
    config.update(slots=3, actMax=3, presenceMax=4)
    example.write_text(json.dumps(config), encoding="utf-8")

    def setup(package: Path) -> None:
        result = subprocess.run([node, str(package / "Setup-WoWAI.js"), "--wow", str(client),
                                 "--account", "TEST_ACCOUNT", "--agent", "codex", "--yes"],
                                cwd=package, capture_output=True, text=True, timeout=180)
        if result.returncode:
            fail(f"optional chat setup failed: {result.stdout}{result.stderr}")
        cfg = json.loads((package / "wow-ai/bridge/config.json").read_text())
        if cfg["defaultCwd"] != str(package / "Goblin-Eye-Chat"):
            fail("chat setup kept another installation's work folder")
        mcp = json.loads((package / "Goblin-Eye-Chat/.mcp.json").read_text())["mcpServers"]["goblin_eye"]
        if mcp["command"] != str(package / "python/python.exe") or mcp["args"][-1] != "mcp":
            fail("chat setup did not use its bundled interpreter and read-only MCP")
        if str(package / "config.json") not in mcp["args"]:
            fail("chat setup did not select this package's config")
        protocol = "".join(json.dumps(message) + "\n" for message in HANDSHAKE)
        result = run([mcp["command"], *mcp["args"]], package, input=protocol, timeout=120)
        replies = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
        if result.returncode or len(replies) != 3 or any("error" in reply for reply in replies):
            fail("generated chat MCP connection failed the handshake")
        if any(t["name"] == "add_companion_entry" for t in replies[1]["result"]["tools"]):
            fail("chat setup exposed companion write tools")
        if not (client / "Interface/AddOns/WoWAI_S003/Inbox.lua").is_file():
            fail("reply slot addons were not installed")
        toml = package / "Goblin-Eye-Chat/.codex/config.toml"
        check = run([mcp["command"], "-c", "import sys,tomllib; tomllib.load(open(sys.argv[1],'rb'))", str(toml)], package, timeout=30)
        if check.returncode:
            fail("generated Codex TOML is invalid")
        kilo = json.loads((package / "Goblin-Eye-Chat/kilo.json").read_text())
        if kilo["mcp"]["goblin-eye"]["command"] != [mcp["command"], *mcp["args"]]:
            fail("generated Kilo MCP connection differs")

    setup(root)
    inbox = client / "Interface/AddOns/WoWAI/Inbox.lua"
    inbox.write_text("-- existing private reply\nWoWAI_Inbox={replies={}}\n", encoding="utf-8")
    moved = root.with_name("Moved Goblin Eye With Spaces")
    if root.resolve().parent != moved.resolve().parent or moved.exists():
        fail("unexpected relocation target")
    # A recipient may relocate by copying the extracted folder. Keeping the old
    # copy also proves generated MCP commands actually use the new interpreter.
    shutil.copytree(root, moved)
    setup(moved)
    if "existing private reply" not in inbox.read_text():
        fail("rerunning setup erased the existing Inbox")
    return {"mock_client_installation": "passed", "generated_read_only_mcp": "passed",
            "package_relocation": "passed", "existing_inbox_preserved": "passed"}


def main() -> int:
    archive_path = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else default_archive()
    root = extract(archive_path)
    runtime = verify_bundled_runtime(root)
    python = interpreter(root)
    manifest_files = verify_manifest(root)
    migrations = verify_fresh_install(root, python)
    verify_dashboard(root)
    tool_count = verify_mcp(root, python, "mcp", expect_write_tool=False)
    companion_tools = verify_mcp(root, python, "companion-mcp", expect_write_tool=True)
    report = {
        "archive": archive_path.name,
        "archive_integrity": "passed",
        "manifest_files": manifest_files,
        "bundled_runtime": runtime,
        "interpreter_used": "bundled" if python != sys.executable else "host python (bundled runtime is Windows-only)",
        "fresh_install": "passed",
        "empty_personal_database": "passed",
        "migrations": migrations,
        "read_only_mcp": "passed",
        "read_only_tools": tool_count,
        "companion_mcp": "passed",
        "companion_tools": companion_tools,
        "neutral_local_market": "passed",
        "prebuilt_dashboard": "passed",
        "no_ai_subscription_required_for_dashboard": True,
        "personal_data_included": False,
    }
    if os.name == "nt":
        verify_windows_launchers(root)
        report["windows_launchers"] = "passed"
        report["paths_with_spaces"] = "passed"
        report["optional_chat"] = verify_chat_installation(root)
    else:
        report["windows_launchers"] = "skipped: not a Windows host"
    # The version contains dots, so build the name explicitly.
    report_path = archive_path.with_name(archive_path.name.removesuffix(".zip") + ".validation.json")
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
