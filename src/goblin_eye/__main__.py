from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path

from goblin_eye.api import serve
from goblin_eye.config import Settings
from goblin_eye.ingestion import (
    AHLedgerPublicApiAdapter,
    BlizzardResearchAdapter,
    AuctionatorSavedVariablesAdapter,
    AuctionatorWatcher,
    CsvSnapshotAdapter,
    NormalizedJsonAdapter,
    discover_auctionator_files,
)
from goblin_eye.mcp_server import McpServer
from goblin_eye.ingestion.professiondb import ProfessionDBAdapter
from goblin_eye.ingestion.foreverguide import ForeverGuideAdapter
from goblin_eye.ingestion.foreverguide_professions import ForeverGuideProfessionAdapter
from goblin_eye.ingestion.foreverguide_dungeons import ForeverGuideDungeonAdapter
from goblin_eye.ingestion.questiedb import QuestieDbAdapter
from goblin_eye.ingestion.mapzeroth import MapzerothAdapter
from goblin_eye.ingestion.ahledger_local import LocalAHLedgerAdapter
from goblin_eye.ingestion.alts_forever import AltsForeverAdapter
from goblin_eye.repository import Database
from goblin_eye.history import recover_history
from goblin_eye.services import ResearchService, initialize_database, json_text, project_path


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="goblin-eye", description="Local-first WoW Forever economic research")
    root.add_argument("--config", type=Path, default=Path("config.json"))
    root.add_argument("--database", type=Path, help="Override the configured SQLite path")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("recover-history", help="Replay cached supported price tables and preserve legacy daily state")
    commands.add_parser("reset-auctions", help="Erase auction evidence and ignore old saved scans; retain static research and characters")
    commands.add_parser("reset-personal-data", help="With dashboard stopped: erase all character exports and auction evidence, pause auction imports in config, create no backup")
    commands.add_parser("init", help="Create an empty, migrated local database")
    commands.add_parser("characters", help="List latest imported character snapshots")
    commands.add_parser("companion", help="Read bounded player goals and recent notes as JSON")
    companion_add = commands.add_parser("companion-add", help="Save a personal goal, note or session report")
    companion_add.add_argument("kind", choices=("goal", "note", "session"))
    companion_add.add_argument("title")
    companion_add.add_argument("body")
    companion_add.add_argument("--basis", choices=("player_report", "agent_inference", "sourced_evidence"), default="player_report")
    companion_add.add_argument("--evidence-ref", action="append", default=[])
    companion_add.add_argument("--character-snapshot-id", type=int)
    companion_add.add_argument("--occurred-at")
    companion_status = commands.add_parser("companion-status", help="Mark a companion entry active, completed or archived")
    companion_status.add_argument("entry_id", type=int)
    companion_status.add_argument("status", choices=("active", "completed", "archived"))
    commands.add_parser("serve", help="Run the local dashboard and API")
    observations = commands.add_parser("observations", help="Print sourced market observations as JSON")
    observations.add_argument("--item-id", type=int)
    observations.add_argument("--market-key")
    observations.add_argument("--limit", type=int, default=100)
    commands.add_parser("sources", help="Print source health and adapter readiness")
    commands.add_parser("next-data", help="Print the next real data needed")
    research = commands.add_parser("research", help="Invoke a read-only research tool without an agent")
    research.add_argument("tool")
    research.add_argument("--arguments-file", type=Path, help="JSON object containing tool arguments")
    commands.add_parser("mcp", help="Run the read-only MCP server over stdio")
    commands.add_parser("companion-mcp", help="Run MCP with bounded companion note and goal writes")
    commands.add_parser("watch", help="Watch discovered Auctionator files and import changes")
    commands.add_parser("sync-ahledger", help="Sync documented public AHledger Forever datasets")
    commands.add_parser("sync-official", help="Cache official Blizzard Forever research pages")
    import_auctionator = commands.add_parser("import-auctionator", help="Import a real Auctionator SavedVariables file")
    import_auctionator.add_argument("path", type=Path)
    import_professiondb = commands.add_parser("import-professiondb", help="Import inspected static Forever recipe data from an installed ProfessionDB directory")
    import_professiondb.add_argument("path", type=Path)
    import_foreverguide = commands.add_parser("import-foreverguide", help="Import installed static acquisition data; preserve Classic baseline labels")
    import_foreverguide.add_argument("path", type=Path)
    import_questiedb = commands.add_parser("import-questiedb", help="Import complete baked Forever NPC/object spawn coordinates")
    import_questiedb.add_argument("path", type=Path)
    import_mapzeroth = commands.add_parser("import-mapzeroth", help="Import labeled Forever world travel nodes and routes")
    import_mapzeroth.add_argument("path", type=Path)
    import_ahledger_scan = commands.add_parser("import-ahledger-scan", help="Import real AHledger v2 saved auction rows")
    import_ahledger_scan.add_argument("path", type=Path)
    import_alts = commands.add_parser("import-alts-forever", help="Import inspected Alts Forever character and inventory observations")
    import_alts.add_argument("path", type=Path)
    import_json = commands.add_parser("import-json", help="Import normalized research JSON")
    import_json.add_argument("path", type=Path)
    import_csv = commands.add_parser("import-csv", help="Import normalized auction snapshot CSV")
    import_csv.add_argument("path", type=Path)
    return root


def main() -> None:
    args = parser().parse_args()
    settings = Settings.load(args.config)
    if args.database:
        settings = replace(settings, database_path=str(args.database))
    read_only = args.command in {"characters", "companion", "observations", "sources", "next-data", "mcp", "research"}
    database = Database(settings.database_path, read_only=read_only)
    if args.command == "init":
        initialize_database(database)
    else:
        database.require_ready(project_path("migrations"))
    service = ResearchService(database, settings)
    if not read_only:
        from goblin_eye.auction_policy import configure_market
        configure_market(database, settings)
    def configured(adapter):
        adapter.economic_period = settings.economic_period
        return adapter

    if args.command == "init":
        print(f"Initialized/migrated database at {database.path}. No invented data was added.")
    elif args.command == "reset-personal-data":
        import json
        import socket
        from goblin_eye.auction_policy import reset_personal_data
        try:
            with socket.create_connection((settings.host, settings.port), timeout=1):
                raise ValueError('Stop the dashboard before resetting personal data; auction workers must not be running.')
        except OSError:
            pass
        # Pause before deletion so a later server restart cannot repopulate data.
        values = json.loads(args.config.read_text(encoding='utf-8')) if args.config.exists() else {}
        values.update(auto_sync_ahledger=False, auto_discover_auctionator=False, auto_import_ahledger_scans=False, auto_import_alts_forever=False)
        args.config.write_text(json.dumps(values, indent=2) + '\n', encoding='utf-8')
        print(json_text(reset_personal_data(database, settings.auctionator_paths)))
    elif args.command == "reset-auctions":
        from goblin_eye.auction_policy import reset_auctions
        print(json_text(reset_auctions(database,settings.auctionator_paths)))
    elif args.command == "recover-history":
        print(json_text(recover_history(database)))
    elif args.command == "serve":
        serve(database, settings)
    elif args.command == "characters":
        print(json_text(service.characters.list()))
    elif args.command == "companion":
        print(json_text(service.companion_context()))
    elif args.command == "companion-add":
        print(json_text(service.companion.add(args.kind,args.title,args.body,args.basis,
            'player',args.character_snapshot_id,args.evidence_ref,args.occurred_at)))
    elif args.command == "companion-status":
        print(json_text(service.companion.set_status(args.entry_id,args.status,'player')))
    elif args.command == "observations":
        print(json_text(service.market_observations(args.item_id, args.market_key, args.limit)))
    elif args.command == "sources":
        print(json_text(service.sources()))
    elif args.command == "next-data":
        print(json_text(service.next_data()))
    elif args.command == "research":
        import json
        from goblin_eye.ingestion.bounded import read_file
        arguments = json.loads(read_file(args.arguments_file,1024*1024)) if args.arguments_file else {}
        print(json_text(McpServer(service)._call(args.tool,arguments)))
    elif args.command == "mcp":
        McpServer(service).run()
    elif args.command == "companion-mcp":
        McpServer(service, companion_writes=True).run()
    elif args.command == "watch":
        watcher = AuctionatorWatcher(
            database,
            lambda: discover_auctionator_files(settings.auctionator_paths),
            settings.watch_interval_seconds,
        )
        watcher.adapter.economic_period = settings.economic_period
        results = watcher.scan_once()
        print(f"Watching {len(discover_auctionator_files(settings.auctionator_paths))} Auctionator file(s); imported {sum(result.records for result in results)} record(s).")
        try:
            watcher.start()
            while True:
                import time
                time.sleep(1)
        except KeyboardInterrupt:
            watcher.stop()
    elif args.command == "import-auctionator":
        print(configured(AuctionatorSavedVariablesAdapter()).import_file(database, args.path))
    elif args.command == "import-professiondb":
        print(ProfessionDBAdapter().import_file(database, args.path))
    elif args.command == "import-foreverguide":
        print(ForeverGuideAdapter().import_file(database, args.path))
        print(ForeverGuideProfessionAdapter().import_file(database, args.path))
        print(ForeverGuideDungeonAdapter().import_file(database, args.path))
    elif args.command == "import-questiedb":
        print(QuestieDbAdapter().import_file(database, args.path))
    elif args.command == "import-mapzeroth":
        print(MapzerothAdapter().import_file(database, args.path))
    elif args.command == "import-ahledger-scan":
        print(configured(LocalAHLedgerAdapter()).import_file(database,args.path))
    elif args.command == "import-alts-forever":
        print(AltsForeverAdapter().import_file(database,args.path))
    elif args.command == "sync-ahledger":
        print(configured(AHLedgerPublicApiAdapter()).sync(database))
    elif args.command == "sync-official":
        print(BlizzardResearchAdapter().sync(database))
    elif args.command == "import-json":
        print(NormalizedJsonAdapter().import_file(database, args.path))
    elif args.command == "import-csv":
        print(CsvSnapshotAdapter().import_file(database, args.path))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError) as exc:
        raise SystemExit(str(exc))
