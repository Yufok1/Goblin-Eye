from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import ipaddress
import mimetypes
import socket
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from goblin_eye.config import Settings
from goblin_eye.ingestion import AHLedgerWatcher, AuctionatorWatcher, discover_auctionator_files
from goblin_eye.ingestion.professiondb import ProfessionDBWatcher
from goblin_eye.ingestion.foreverguide import ForeverGuideWatcher
from goblin_eye.ingestion.ahledger_local import LocalAHLedgerWatcher
from goblin_eye.ingestion.alts_forever import AltsForeverWatcher
from goblin_eye.ingestion.static_watcher import QuestieDbWatcher, MapzerothWatcher
from goblin_eye.ingestion.official import BlizzardResearchWatcher
from goblin_eye.repository import Database
from goblin_eye.services import PROJECT_ROOT, ResearchService


class LocalHTTPServer(ThreadingHTTPServer):
    # Windows SO_REUSEADDR can allow stale and new servers to share the port.
    allow_reuse_address = False

    def server_bind(self) -> None:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


class RequestHandler(BaseHTTPRequestHandler):
    database: Database
    settings: Settings
    static_roots: tuple[Path, ...]

    def log_message(self, format: str, *args) -> None:
        print(f"[goblin-eye] {self.address_string()} {format % args}")

    def _json(self, value, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        try:
            if len(self.path) > 8192:
                raise ValueError("Request path is too long")
            self._get()
        except (ValueError, TypeError, KeyError) as exc:
            self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def do_POST(self) -> None:
        try:
            length = int(self.headers.get('Content-Length','0'))
            if not 0 < length <= 16_384:
                raise ValueError('JSON body must be between 1 and 16384 bytes')
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise ValueError('Incomplete JSON body')
            if not ipaddress.ip_address(self.client_address[0]).is_loopback:
                self._json({'error':'Companion writes require a local connection'}, HTTPStatus.FORBIDDEN)
                return
            origin = self.headers.get('Origin')
            host = self.headers.get('Host')
            if origin and origin != f'http://{host}':
                self._json({'error':'Cross-origin companion writes are not allowed'}, HTTPStatus.FORBIDDEN)
                return
            if self.headers.get('Content-Type', '').split(';',1)[0].strip().lower() != 'application/json':
                raise ValueError('Content-Type must be application/json')
            body = json.loads(raw)
            if not isinstance(body, dict):
                raise ValueError('JSON body must be an object')
            path = urlparse(self.path).path
            from goblin_eye.mcp_server import McpServer
            service = ResearchService(self.database, self.settings)
            server = McpServer(service, companion_writes=True, companion_author='player')
            if path == '/api/companion/entries':
                value = server._call('add_companion_entry', body, agent_view=False)
                self._json(value, HTTPStatus.CREATED)
                return
            if path.startswith('/api/companion/entries/') and path.endswith('/status'):
                parts = path.split('/')
                if len(parts) != 6 or not parts[4].isdigit():
                    raise ValueError('Invalid companion entry path')
                value = server._call('set_companion_status', {**body,'entry_id':int(parts[4])}, agent_view=False)
                self._json(value)
                return
            self._json({'error':'not found'}, HTTPStatus.NOT_FOUND)
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            self._json({'error':str(exc)}, HTTPStatus.BAD_REQUEST)

    def _get(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        service = ResearchService(self.database, self.settings)
        query = parse_qs(parsed.query)
        def arg(key, default=None): return query.get(key,[default])[0]
        if path == '/api/companion/context':
            self._json(service.companion_context());return
        if path == '/api/companion/entries':
            self._json(service.companion.list(arg('kind'),arg('status'),int(arg('limit','30')),int(arg('offset','0'))));return
        if path.startswith('/api/companion/entries/'):
            entry_id = int(path.rsplit('/',1)[-1])
            value = service.companion.get(entry_id)
            self._json(value or {'error':'not found'}, HTTPStatus.OK if value else HTTPStatus.NOT_FOUND)
            return
        if path in ('/api/world-search', '/api/acquisition-search', '/api/scan-summary', '/api/history-coverage'):
            # Use the same schema, bounds and defaults as the agent interface.
            from goblin_eye.mcp_server import McpServer, TOOLS
            name = {'/api/world-search':'search_world_entities', '/api/acquisition-search':'search_acquisition_sources',
                '/api/scan-summary':'get_scan_summary', '/api/history-coverage':'get_history_coverage'}[path]
            properties = next(t['inputSchema']['properties'] for t in TOOLS if t['name']==name)
            arguments = {k: int(v[0]) if properties.get(k,{}).get('type')=='integer' else v[0]
                for k,v in query.items()}
            self._json(McpServer(service)._call(name, arguments, agent_view=False));return
        if path == '/api/scans':
            self._json(service.history.scans(arg('market_key','wow-forever'),int(arg('limit','50')),int(arg('offset','0'))));return
        if path == '/api/price-history':
            self._json(service.history.points(int(arg('item_id','0')),arg('market_key','wow-forever'),int(arg('limit','100')),
                int(arg('offset','0')),arg('start'),arg('end'),arg('item_key'),arg('period'),arg('source_key')));return
        if path == '/api/scan-history':
            self._json(service.history.local_series(int(arg('item_id','0')),arg('market_key','wow-forever'),arg('start'),arg('end'),int(arg('limit','100')),arg('period')));return
        if path == '/api/price-reference':
            self._json(service.history.reference(int(arg('item_id','0')),arg('market_key','wow-forever'),arg('start'),arg('end'),
                arg('source_key'),arg('period'),arg('item_key'),int(arg('minimum_samples','3'))));return
        if path == '/api/compare-scans':
            self._json(service.history.compare(int(arg('item_id','0')),arg('market_key','wow-forever'),int(arg('before_id','0')),int(arg('after_id','0'))));return
        if path == '/api/assertions':
            from goblin_eye.assertions import get_assertions
            self._json(get_assertions(self.database,arg('entity_type'),arg('entity_key'),int(arg('limit','50')),int(arg('offset','0'))));return
        if path == "/api/characters":
            self._json(service.characters.list())
            return
        if path.startswith("/api/characters/"):
            try:
                value = service.characters.get(int(path.rsplit("/", 1)[-1]))
            except ValueError as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            self._json(value or {"error": "not found"}, HTTPStatus.OK if value else HTTPStatus.NOT_FOUND)
            return
        if path == "/api/health":
            self._json({"status": "ok", **service.summary()})
            return
        if path == "/api/market-observations":
            query = parse_qs(parsed.query)
            item_id = int(query["item_id"][0]) if query.get("item_id") else None
            market_key = query.get("market_key", [None])[0]
            limit = int(query.get("limit", ["250"])[0])
            self._json(service.market_observations(item_id, market_key, limit))
            return
        if path == "/api/evidence":
            query = parse_qs(parsed.query)
            self._json(service.search_evidence(query.get("q", [""])[0], int(query.get("limit", ["50"])[0])))
            return
        if path == "/api/items":
            query = parse_qs(parsed.query)
            try:
                value = service.graph.search_items(query.get("q", [""])[0],
                    int(query.get("limit", ["50"])[0]), int(query.get("offset", ["0"])[0]))
            except ValueError as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            self._json(value)
            return
        if path == "/api/research-datasets":
            self._json(service.graph.datasets())
            return
        if path == "/api/acquisition":
            from goblin_eye.mcp_server import McpServer, TOOLS
            properties = next(t['inputSchema']['properties'] for t in TOOLS if t['name']=='get_item_acquisition')
            arguments = {k: int(v[0]) if properties.get(k,{}).get('type')=='integer' else v[0]
                for k,v in query.items()}
            self._json(McpServer(service)._call('get_item_acquisition', arguments, agent_view=False))
            return
        if path == "/api/market-depth":
            query = parse_qs(parsed.query)
            try:
                value = service.graph.market_depth(int(query.get("item_id",["0"])[0]),query.get("market_key",["wow-forever"])[0],
                    int(query.get("limit",["50"])[0]),int(query.get("offset",["0"])[0]),
                    int(query["snapshot_id"][0]) if query.get("snapshot_id") else None)
            except ValueError as exc:
                self._json({"error":str(exc)},HTTPStatus.BAD_REQUEST)
                return
            self._json(value)
            return
        if path.startswith("/api/world/"):
            try:
                _, _, _, entity_type, entity_id = path.split("/")
                query = parse_qs(parsed.query)
                value = service.graph.world_entity(entity_type,int(entity_id),
                    int(query.get("limit",["50"])[0]),int(query.get("offset",["0"])[0]))
            except ValueError as exc:
                self._json({"error":str(exc)},HTTPStatus.BAD_REQUEST)
                return
            self._json(value)
            return
        if path.startswith("/api/recipes/"):
            try:
                fact_id = int(path.rsplit("/", 1)[-1])
            except ValueError:
                self._json({"error": "invalid recipe fact id"}, HTTPStatus.BAD_REQUEST)
                return
            value = service.graph.recipe(fact_id)
            self._json(value or {"error": "not found"}, HTTPStatus.OK if value else HTTPStatus.NOT_FOUND)
            return
        if path.startswith("/api/items/"):
            try:
                item_id = int(path.rsplit("/", 1)[-1])
            except ValueError:
                self._json({"error": "invalid item id"}, HTTPStatus.BAD_REQUEST)
                return
            value = service.item(item_id)
            self._json(value or {"error": "not found"}, HTTPStatus.OK if value else HTTPStatus.NOT_FOUND)
            return
        if path == "/api/farming":
            self._json(service.farming())
            return
        if path == "/api/sources":
            self._json(service.sources())
            return
        if path == "/api/documents":
            query = parse_qs(parsed.query)
            self._json(service.documents(query.get("source_key", [None])[0], int(query.get("limit", ["100"])[0])))
            return
        if path.startswith("/api/documents/"):
            try:
                document_id = int(path.rsplit("/", 1)[-1])
            except ValueError:
                self._json({"error": "invalid document id"}, HTTPStatus.BAD_REQUEST)
                return
            value = service.document(document_id,int(arg("offset","0")),int(arg("limit","100000")))
            self._json(value or {"error": "not found"}, HTTPStatus.OK if value else HTTPStatus.NOT_FOUND)
            return
        if path == "/api/next-data":
            self._json(service.next_data())
            return
        if path.startswith("/api/"):
            self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            return
        self._static(path)

    def _static(self, request_path: str) -> None:
        relative = "index.html" if request_path in ("", "/") else request_path.lstrip("/")
        if ".." in Path(relative).parts:
            self.send_error(HTTPStatus.BAD_REQUEST)
            return
        candidate = None
        for root in self.static_roots:
            path = (root / relative).resolve()
            if not path.is_relative_to(root.resolve()):
                self.send_error(HTTPStatus.BAD_REQUEST, 'Static path must stay inside the web directory')
                return
            if path.is_file():
                candidate = path
                break
        if not candidate:
            candidate = self.static_roots[-1] / "index.html"
        if not candidate.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "Build the web UI with `npm install` and `npm run build`.")
            return
        body = candidate.read_bytes()
        content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def serve(database: Database, settings: Settings) -> None:
    RequestHandler.database = database
    RequestHandler.settings = settings
    RequestHandler.static_roots = (PROJECT_ROOT / "web" / "dist", PROJECT_ROOT / "web" / "public")
    server = LocalHTTPServer((settings.host, settings.port), RequestHandler)
    from goblin_eye.ingestion.bounded import WATCHERS
    WATCHERS.clear()
    watcher = None
    ahledger_watcher = None
    professiondb_watcher = None
    foreverguide_watcher = None
    local_ahledger_watcher = None
    alts_watcher = None
    static_watchers = []
    for enabled, watcher_type, paths in (
        (settings.auto_import_questiedb, QuestieDbWatcher, settings.questiedb_paths),
        (settings.auto_import_mapzeroth, MapzerothWatcher, settings.mapzeroth_paths),
    ):
        if enabled:
            static_watcher = watcher_type(database, paths)
            static_watcher.start()
            static_watchers.append(static_watcher)
    if settings.auto_sync_official:
        official_watcher = BlizzardResearchWatcher(database, settings.external_refresh_minutes)
        official_watcher.start()
        static_watchers.append(official_watcher)
    if settings.auto_import_alts_forever:
        alts_watcher = AltsForeverWatcher(database, settings.alts_forever_paths, settings.watch_interval_seconds)
        alts_watcher.start()
    if settings.auto_import_ahledger_scans:
        local_ahledger_watcher = LocalAHLedgerWatcher(database,settings.ahledger_scan_paths,settings.watch_interval_seconds)
        local_ahledger_watcher.economic_period = settings.economic_period
        local_ahledger_watcher.start()
    if settings.auto_import_foreverguide:
        foreverguide_watcher = ForeverGuideWatcher(database, settings.foreverguide_paths)
        foreverguide_watcher.start()
    if settings.auto_import_professiondb:
        professiondb_watcher = ProfessionDBWatcher(database, settings.professiondb_paths)
        professiondb_watcher.start()
    if settings.auto_discover_auctionator:
        watcher = AuctionatorWatcher(
            database,
            lambda: discover_auctionator_files(settings.auctionator_paths),
            settings.watch_interval_seconds,
        )
        watcher.adapter.economic_period = settings.economic_period
        watcher.start()
    if settings.auto_sync_ahledger:
        ahledger_watcher = AHLedgerWatcher(database, settings.external_refresh_minutes)
        ahledger_watcher.adapter.economic_period = settings.economic_period
        ahledger_watcher.start()
    print(f"{settings.display_name} running at http://{settings.host}:{settings.port}")
    print("Every in-game action remains manual. Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        for static_watcher in static_watchers:
            static_watcher.stop()
        if watcher:
            watcher.stop()
        if ahledger_watcher:
            ahledger_watcher.stop()
        if professiondb_watcher:
            professiondb_watcher.stop()
        if foreverguide_watcher:
            foreverguide_watcher.stop()
        if local_ahledger_watcher:
            local_ahledger_watcher.stop()
        if alts_watcher:
            alts_watcher.stop()
        server.server_close()
