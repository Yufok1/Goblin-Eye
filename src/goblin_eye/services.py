from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
from decimal import Decimal, ROUND_HALF_UP
from goblin_eye.validation import integer, rate, text

from goblin_eye.config import Settings
from goblin_eye.ingestion import (
    AHLedgerPublicApiAdapter,
    BlizzardResearchAdapter,
    AuctionatorSavedVariablesAdapter,
    CsvSnapshotAdapter,
    NormalizedJsonAdapter,
    PROVIDER_ADAPTERS,
)
from goblin_eye.repository import Database
from goblin_eye.item_graph import ItemGraph
from goblin_eye.characters import CharacterStore
from goblin_eye.companion import CompanionStore
from goblin_eye.history import MarketHistory
from goblin_eye.research_queries import ResearchQueries
from goblin_eye.auction_policy import context as auction_context
from goblin_eye.ingestion.professiondb import ProfessionDBAdapter
from goblin_eye.ingestion.foreverguide import ForeverGuideAdapter
from goblin_eye.ingestion.foreverguide_professions import ForeverGuideProfessionAdapter
from goblin_eye.ingestion.foreverguide_dungeons import ForeverGuideDungeonAdapter
from goblin_eye.ingestion.questiedb import QuestieDbAdapter
from goblin_eye.ingestion.mapzeroth import MapzerothAdapter
from goblin_eye.ingestion.ahledger_local import LocalAHLedgerAdapter
from goblin_eye.ingestion.alts_forever import AltsForeverAdapter


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def project_path(relative: str) -> Path:
    return PROJECT_ROOT / relative


def initialize_database(database: Database) -> None:
    database.migrate(project_path("migrations"))


class ResearchService:
    def __init__(self, database: Database, settings: Settings):
        self.database = database
        self.settings = settings
        self.graph = ItemGraph(database)
        self.characters = CharacterStore(database)
        self.companion = CompanionStore(database)
        self.history = MarketHistory(database)
        self.research = ResearchQueries(database)

    def companion_context(self) -> dict[str, Any]:
        """One bounded starting point for a fresh agent conversation."""
        value = self.companion.context()
        characters = self.characters.list()
        value['auction_context'] = characters['auction_context']
        value['character_snapshots'] = characters['characters'][:20]
        value['character_snapshots_truncated'] = len(characters['characters']) > 20
        value['character_refresh_instructions'] = characters['refresh_instructions']
        value['research_next_steps'] = [
            'For prices and source freshness, call get_economic_summary before drawing conclusions.',
            'For personalized gear or adventures, select a character snapshot and call get_character_snapshot.',
            'For a specific item or destination, follow its IDs through item and acquisition research tools.',
        ]
        return value

    def search_evidence(self, query: str, limit: int = 25) -> list[dict[str, Any]]:
        integer(limit, "limit", 1, 100)
        text(query, "query", empty=True)
        term = f"%{query.strip()}%"
        if not query.strip():
            return []
        results: list[dict[str, Any]] = []
        specs = (
            ("item", "items", "id", "name"),
            ("recipe", "recipes", "id", "name"),
            ("vendor", "vendors", "id", "name"),
            ("mob", "mobs", "id", "name"),
            ("camp", "camps", "id", "name"),
        )
        with self.database.transaction() as connection:
            for entity_type, table, id_column, name_column in specs:
                rows = connection.execute(
                    f"""SELECT e.{id_column} entity_id, e.{name_column} name,
                    e.retrieved_at, e.game_build, e.content_phase, e.confidence,
                    e.evidence_kind, e.raw_reference, s.source_key, s.name source_name,
                    s.url source_url, s.trust_rank
                    FROM {table} e JOIN sources s ON s.id=e.source_id
                    WHERE e.{name_column} LIKE ? COLLATE NOCASE LIMIT ?""",
                    (term, limit),
                ).fetchall()
                results.extend({"entity_type": entity_type, **dict(row)} for row in rows)
            item_rows = connection.execute(
                """SELECT io.item_id entity_id, io.name, io.retrieved_at, io.game_build,
                io.content_phase, io.confidence, io.evidence_kind, io.raw_reference,
                s.source_key, s.name source_name, s.url source_url, s.trust_rank
                FROM item_observations io JOIN sources s ON s.id=io.source_id
                WHERE io.name LIKE ? COLLATE NOCASE LIMIT ?""", (term, limit)
            ).fetchall()
            results.extend({"entity_type": "item", **dict(row)} for row in item_rows)
            recipe_rows = connection.execute(
                """SELECT r.id entity_id, r.spell_id, r.name, d.retrieved_at, d.game_build,
                d.content_phase, d.confidence, d.evidence_kind, r.raw_reference,
                s.source_key, s.name source_name, s.url source_url, s.trust_rank
                FROM recipe_facts r JOIN research_datasets d ON d.id=r.dataset_id
                JOIN sources s ON s.id=d.source_id WHERE d.active=1 AND r.name LIKE ? COLLATE NOCASE LIMIT ?""",
                (term, limit)).fetchall()
            results.extend({"entity_type": "recipe_fact", **dict(row)} for row in recipe_rows)
        results.extend(self.research.world(query=query, entity_type=None, limit=limit)['records'])
        results.sort(key=lambda row: ((row.get("name") or "").casefold() != query.strip().casefold(),
            row["trust_rank"], -float(row["confidence"]), row.get("name") or ""))
        return results[:limit]

    def market_observations(self, item_id: int | None = None, market_key: str | None = None,
                            limit: int = 100) -> list[dict[str, Any]]:
        integer(limit, "limit", 1, 1000)
        market_key = self.settings.market_key if market_key is None else market_key
        if item_id is not None: integer(item_id, "item_id", 1)
        if market_key is not None: text(market_key, "market_key")
        parameters: list[Any] = []
        auction_item_filter = ""
        legacy_item_filter = ""
        market_filter = ""
        if market_key:
            market_filter = " AND m.market_key=?"
            parameters.append(market_key)
        if item_id is not None:
            auction_item_filter = " AND a.item_id=?"
            legacy_item_filter = " AND l.item_id=?"
            parameters.append(item_id)
        parameters.append(limit)
        with self.database.transaction() as connection:
            auction_rows = connection.execute(
                f"""SELECT sn.external_id snapshot_id, sn.id snapshot_record_id,
                sn.captured_at, sn.game_build, sn.confidence, sn.evidence_kind,
                sn.raw_reference, so.source_key, m.market_key,
                a.ordinal, a.item_id, names.name item_name, a.quantity,
                a.quantity stack_size, a.buyout_copper,
                CASE WHEN a.buyout_copper>0 THEN ROUND(1.0*a.buyout_copper/a.quantity, 2)
                END unit_buyout_copper, a.bid_copper, a.time_left_code
                FROM auction_rows a JOIN snapshots sn ON sn.id=a.snapshot_id
                JOIN markets m ON m.id=sn.market_id JOIN sources so ON so.id=sn.source_id
                LEFT JOIN selected_item_names names ON names.item_id=a.item_id
                WHERE 1=1{market_filter}{auction_item_filter}
                ORDER BY so.trust_rank, sn.captured_at DESC, sn.id DESC, a.ordinal LIMIT ?""",
                parameters,
            ).fetchall()
            legacy_rows = connection.execute(
                f"""SELECT sn.external_id snapshot_id, sn.captured_at, sn.game_build,
                sn.confidence, sn.evidence_kind, so.source_key, m.market_key,
                l.item_id, i.name item_name, l.quantity, l.stack_size,
                l.buyout_copper, CASE WHEN l.buyout_copper>0
                THEN ROUND(1.0*l.buyout_copper/l.quantity, 2) END unit_buyout_copper,
                l.bid_copper, l.time_left
                FROM listings l JOIN snapshots sn ON sn.id=l.snapshot_id
                JOIN markets m ON m.id=sn.market_id JOIN sources so ON so.id=sn.source_id
                JOIN items i ON i.id=l.item_id
                WHERE 1=1{market_filter}{legacy_item_filter}
                ORDER BY so.trust_rank, sn.captured_at DESC, l.item_id, unit_buyout_copper LIMIT ?""",
                parameters,
            ).fetchall()
            price_parameters: list[Any] = []
            price_market_filter = ""
            price_item_filter = ""
            if market_key:
                price_market_filter = " AND m.market_key=?"
                price_parameters.append(market_key)
            if item_id is not None:
                price_item_filter = " AND po.item_id=?"
                price_parameters.append(item_id)
            price_parameters.append(limit)
            price_rows = connection.execute(
                f"""SELECT po.observed_date, po.source_modified_at, po.item_key, po.item_id,
                (SELECT name FROM selected_item_names WHERE item_id=po.item_id) item_name,
                po.current_min_unit_copper, po.daily_min_unit_copper,
                po.daily_max_low_unit_copper, po.available_quantity, po.median_unit_copper,
                po.auction_count, po.median_7d_copper, po.median_30d_copper,
                po.low_30d_copper, po.high_30d_copper, po.confidence,
                po.evidence_kind, so.source_key, m.market_key
                FROM price_observations po JOIN markets m ON m.id=po.market_id
                JOIN sources so ON so.id=po.source_id
                WHERE 1=1{price_market_filter}{price_item_filter}
                ORDER BY so.trust_rank, po.scan_day DESC, po.item_key LIMIT ?""",
                price_parameters,
            ).fetchall()
        listings = ([{"observation_type": "listing", **dict(row)} for row in auction_rows]
                    + [{"observation_type": "listing", **dict(row)} for row in legacy_rows])
        listings.sort(key=lambda row: (row["captured_at"], row["snapshot_id"]), reverse=True)
        prices = [{"observation_type": "aggregated_price", **dict(row)} for row in price_rows]
        if not listings:
            return prices[:limit]
        if not prices:
            return listings[:limit]
        listing_count = min(len(listings), (limit + 1) // 2)
        price_count = min(len(prices), limit - listing_count)
        listing_count = min(len(listings), limit - price_count)
        return listings[:listing_count] + prices[:price_count]

    def calculate_trade(self, quantity: int, entry_unit_copper: int, exit_unit_copper: int,
                        auction_cut_rate: float | None = None, deposit_copper: int | None = None,
                        additional_cost_copper: int = 0, deposit_loss_rate: float = 1.0) -> dict[str, Any]:
        integer(quantity, "quantity", 1, 1000000000)
        for name, value in (("entry_unit_copper", entry_unit_copper), ("exit_unit_copper", exit_unit_copper),
                            ("additional_cost_copper", additional_cost_copper)):
            integer(value, name)
        cut = self.settings.auction_cut_rate if auction_cut_rate is None else auction_cut_rate
        deposit = self.settings.default_deposit_copper if deposit_copper is None else deposit_copper
        integer(deposit, "deposit_copper")
        rate(cut, "auction_cut_rate")
        rate(deposit_loss_rate, "deposit_loss_rate")
        rounded = lambda value: int(value.quantize(Decimal('1'), rounding=ROUND_HALF_UP))
        gross_cost = quantity * entry_unit_copper + additional_cost_copper
        gross_revenue = quantity * exit_unit_copper
        fee = rounded(Decimal(gross_revenue) * Decimal(str(cut)))
        loss = rounded(Decimal(deposit) * Decimal(str(deposit_loss_rate)))
        profit = gross_revenue - fee - loss - gross_cost
        return {"formula": "net_profit = gross_revenue - auction_fee - expected_deposit_loss - gross_cost",
                "inputs": {"quantity": quantity, "entry_unit_copper": entry_unit_copper,
                    "exit_unit_copper": exit_unit_copper, "auction_cut_rate": cut, "deposit_copper": deposit,
                    "deposit_loss_rate": deposit_loss_rate, "additional_cost_copper": additional_cost_copper},
                "gross_cost_copper": gross_cost, "gross_revenue_copper": gross_revenue,
                "auction_fee_copper": fee, "expected_deposit_loss_copper": loss,
                "expected_deposit_refund_copper": deposit - loss, "capital_required_copper": gross_cost + deposit,
                "net_profit_copper": profit, "roi": round(profit / gross_cost, 6) if gross_cost else None,
                "interpretation": "Scenario arithmetic, not liquidity or realized value. Deposit is a total outlay; loss rate defaults to 1 (all lost) for compatibility. Supply an explicit scenario rate. Fees and refund rules are unverified assumptions. Copper rounds half up."}

    def item(self, item_id: int) -> dict[str, Any] | None:
        integer(item_id, "item_id", 1)
        with self.database.transaction() as connection:
            selected = connection.execute('SELECT * FROM selected_item_names WHERE item_id=?',(item_id,)).fetchone()
            item = None
            observed_item = None
            if selected:
                if selected['record_kind'] in ('items','item_observations'):
                    table = selected['record_kind']
                    item = connection.execute(f'SELECT i.*,s.source_key FROM {table} i JOIN sources s ON s.id=i.source_id WHERE i.id=?', (selected['record_id'],)).fetchone()
                else:
                    item = connection.execute("""SELECT w.entity_id item_id,w.name,w.raw_reference,
                        d.retrieved_at,d.game_build,d.confidence,d.evidence_kind,s.source_key
                        FROM world_entity_facts w JOIN research_datasets d ON d.id=w.dataset_id
                        JOIN sources s ON s.id=d.source_id WHERE w.dataset_id=? AND w.entity_type='item' AND w.entity_id=?""",
                        (selected['dataset_id'],item_id)).fetchone()
            if not item and not self.graph.search_items(str(item_id),1)['items']:
                return None
            listings = connection.execute(
                """SELECT m.market_key, sn.source_id, sn.captured_at, sn.external_id, l.quantity, l.stack_size, l.buyout_copper,
                ROUND(1.0*l.buyout_copper/l.quantity, 2) unit_price_copper
                FROM listings l JOIN snapshots sn ON sn.id=l.snapshot_id
                JOIN markets m ON m.id=sn.market_id
                WHERE l.item_id=? ORDER BY sn.captured_at DESC, unit_price_copper LIMIT 500""",
                (item_id,),
            ).fetchall()
            recipes_using = connection.execute(
                """SELECT r.id, r.name, r.profession, rr.quantity FROM recipe_reagents rr
                JOIN recipes r ON r.id=rr.recipe_id WHERE rr.item_id=?""", (item_id,)
            ).fetchall()
            recipes_making = connection.execute(
                "SELECT id, name, profession, kind, output_quantity FROM recipes WHERE output_item_id=?",
                (item_id,),
            ).fetchall()
            loot = connection.execute(
                """SELECT m.id mob_id, m.name mob_name, le.drop_probability,
                le.min_quantity, le.max_quantity FROM loot_entries le
                JOIN mobs m ON m.id=le.mob_id WHERE le.item_id=?""", (item_id,)
            ).fetchall()
            prices = connection.execute(
                """SELECT po.observed_date, po.source_modified_at, po.item_key,
                po.current_min_unit_copper, po.daily_min_unit_copper,
                po.daily_max_low_unit_copper, po.available_quantity, po.median_unit_copper,
                po.median_7d_copper, po.median_30d_copper, po.low_30d_copper,
                po.high_30d_copper, po.confidence, po.evidence_kind, po.imported_at retrieved_at, po.raw_reference,
                m.market_key, s.source_key FROM price_observations po
                JOIN markets m ON m.id=po.market_id JOIN sources s ON s.id=po.source_id
                WHERE po.item_id=? ORDER BY s.trust_rank, po.scan_day DESC,po.id DESC LIMIT 500""", (item_id,)
            ).fetchall()
            result = dict(item or observed_item) if (item or observed_item) else {"item_id": item_id, "name": None}
            result["item_id"] = item_id
            result['identity_selection_policy'] = 'Source trust rank, newest retrieval, confidence, deterministic tie. Build applicability must be checked; world relationship names remain source-specific.'
            result['price_observation_limit'] = 500
            result['price_observations_truncated'] = connection.execute('SELECT count(*) FROM price_observations WHERE item_id=?',(item_id,)).fetchone()[0] > 500
            from goblin_eye.assertions import get_assertions
            result['generic_assertions'] = get_assertions(self.database,'items',str(item_id))
            result['identity_history'] = get_assertions(self.database,'item_identity',str(item_id))
            result.update(
                listing_markets=self.graph.listing_markets(item_id),
                acquisition=self.graph.acquisition(item_id),
                listings=[dict(row) for row in listings],
                recipes_using=[dict(row) for row in recipes_using],
                recipes_making=[dict(row) for row in recipes_making],
                loot_sources=[dict(row) for row in loot],
                price_observations=[dict(row) for row in prices],
                recipe_relationships={
                    "produces": self.graph.recipes(item_id, "produces"),
                    "consumes": self.graph.recipes(item_id, "consumes"),
                    "teaches": self.graph.recipes(item_id, "teaches"),
                },
                identity_observations=[dict(row) for row in connection.execute(
                    """SELECT io.*, s.source_key FROM item_observations io JOIN sources s ON s.id=io.source_id
                    WHERE io.item_id=? ORDER BY s.trust_rank, io.retrieved_at DESC""", (item_id,))],
            )
            return result

    def documents(self, source_key: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        integer(limit, "limit", 1, 500)
        if source_key is not None: text(source_key, "source_key")
        clause = "WHERE s.source_key=?" if source_key else ""
        parameters: list[Any] = [source_key] if source_key else []
        parameters.append(limit)
        with self.database.transaction() as connection:
            rows = connection.execute(
                f"""SELECT sd.id, s.source_key, sd.url, sd.retrieved_at, sd.content_type,
                sd.cache_control, sd.sha256, LENGTH(sd.body) byte_count
                FROM source_documents sd JOIN sources s ON s.id=sd.source_id {clause}
                ORDER BY sd.retrieved_at DESC, sd.id DESC LIMIT ?""", parameters
            ).fetchall()
        return [dict(row) for row in rows]

    def document(self, document_id: int, offset: int = 0, limit: int = 100000) -> dict[str, Any] | None:
        integer(document_id, "document_id", 1)
        integer(offset,"offset");integer(limit,"limit",1,200000)
        with self.database.transaction() as connection:
            row = connection.execute(
                """SELECT sd.id, s.source_key, sd.url, sd.retrieved_at, sd.content_type,
                sd.cache_control, sd.sha256, LENGTH(sd.body) total_bytes, substr(sd.body,?,?) body FROM source_documents sd
                JOIN sources s ON s.id=sd.source_id WHERE sd.id=?""", (offset+1,limit,document_id)
            ).fetchone()
        if not row:
            return None
        value = dict(row)
        body = value.pop("body")
        value["text"] = bytes(body).decode("utf-8", errors="replace")
        value.update(offset=offset,limit=limit,truncated=offset+len(body)<value["total_bytes"],chunk_unit="bytes; boundary UTF-8 characters may be replaced")
        value['returned_bytes'] = len(body)
        value['next_offset'] = offset + len(body) if value['truncated'] else None
        return value

    def search_documents(self, query: str, limit: int = 25, source_key: str | None = None) -> list[dict[str, Any]]:
        integer(limit, "limit", 1, 100)
        text(query, "query", empty=True)
        if source_key is not None: text(source_key, "source_key")
        needle = query.strip().casefold()
        if not needle:
            return []
        matches = []
        with self.database.transaction() as connection:
            cursor = connection.execute("""SELECT sd.id, s.source_key, sd.url, sd.retrieved_at, sd.content_type,
                sd.sha256, sd.body FROM source_documents sd JOIN sources s ON s.id=sd.source_id
                WHERE (? IS NULL OR s.source_key=?)
                ORDER BY s.trust_rank, sd.retrieved_at DESC, sd.id DESC""", (source_key, source_key))
            for row in cursor:
                body = bytes(row["body"]).decode("utf-8", errors="replace")
                position = body.casefold().find(needle)
                if position < 0:
                    continue
                value = {key: row[key] for key in row.keys() if key != "body"}
                value["excerpt"] = body[max(0, position - 240):position + len(needle) + 240]
                matches.append(value)
                if len(matches) >= limit:
                    break
        return matches

    def farming(self) -> list[dict[str, Any]]:
        with self.database.transaction() as connection:
            rows = connection.execute(
                """SELECT c.id, c.name, c.zone, c.centroid_x, c.centroid_y, c.travel_notes,
                c.retrieved_at, c.game_build, c.content_phase, c.confidence, c.evidence_kind,
                c.raw_reference, s.source_key, s.url source_url, COUNT(cs.spawn_id) spawn_count
                FROM camps c JOIN sources s ON s.id=c.source_id
                LEFT JOIN camp_spawns cs ON cs.camp_id=c.id GROUP BY c.id
                ORDER BY c.confidence DESC, c.name"""
            ).fetchall()
        return [dict(row) for row in rows]

    def sources(self) -> dict[str, Any]:
        with self.database.transaction() as connection:
            watched_files = [dict(row) for row in connection.execute(
                'SELECT * FROM watched_files ORDER BY path')]
            sources = [dict(row) for row in connection.execute(
                """SELECT s.*,
                (SELECT COUNT(*) FROM snapshots sn WHERE sn.source_id=s.id) snapshot_count,
                (SELECT COUNT(*) FROM price_observations po WHERE po.source_id=s.id) price_record_count,
                (SELECT COUNT(*) FROM item_observations io WHERE io.source_id=s.id) item_record_count,
                (SELECT COUNT(*) FROM source_documents sd WHERE sd.source_id=s.id) cached_document_count,
                (SELECT COUNT(*) FROM recipe_facts rf JOIN research_datasets rd ON rd.id=rf.dataset_id
                 WHERE rd.source_id=s.id AND rd.active=1) recipe_record_count,
                (SELECT COUNT(*) FROM acquisition_facts af JOIN research_datasets rd ON rd.id=af.dataset_id
                 WHERE rd.source_id=s.id AND rd.active=1) acquisition_record_count,
                (SELECT COUNT(*) FROM world_entity_facts wf JOIN research_datasets rd ON rd.id=wf.dataset_id
                 WHERE rd.source_id=s.id AND rd.active=1) world_entity_record_count,
                (SELECT COUNT(*) FROM travel_nodes tn JOIN research_datasets rd ON rd.id=tn.dataset_id
                 WHERE rd.source_id=s.id AND rd.active=1) travel_node_count,
                (SELECT COUNT(*) FROM travel_edges te JOIN research_datasets rd ON rd.id=te.dataset_id
                 WHERE rd.source_id=s.id AND rd.active=1) travel_edge_count,
                (SELECT COUNT(*) FROM auction_rows a JOIN snapshots sn ON sn.id=a.snapshot_id
                 WHERE sn.source_id=s.id) auction_row_count,
                NULLIF(MAX(
                    COALESCE((SELECT MAX(sn.captured_at) FROM snapshots sn WHERE sn.source_id=s.id), ''),
                    COALESCE((SELECT MAX(CASE WHEN s.source_key='local-auctionator' THEN po.observed_date||'T00:00:00+00:00' ELSE po.source_modified_at END) FROM price_observations po WHERE po.source_id=s.id), '')
                ), '') newest_snapshot
                FROM sources s ORDER BY s.trust_rank, s.name"""
            )]
            snapshots = connection.execute(
                """SELECT MAX(newest) newest, SUM(count) count FROM (
                SELECT MAX(captured_at) newest, COUNT(*) count FROM snapshots
                UNION ALL
                SELECT MAX(CASE WHEN s.source_key='local-auctionator' THEN po.observed_date||'T00:00:00+00:00' ELSE po.source_modified_at END) newest, COUNT(*) count FROM price_observations po JOIN sources s ON s.id=po.source_id)"""
            ).fetchone()
            markets = [dict(row) for row in connection.execute(
                """SELECT m.market_key,m.name,m.region,m.ruleset,m.faction,m.is_verified,
                (SELECT MAX(captured_at) FROM snapshots WHERE market_id=m.id) latest_listing_scan,
                (SELECT MAX(observed_at) FROM market_captures WHERE market_id=m.id) latest_precise_price_capture,
                (SELECT MAX(observed_date) FROM price_observations WHERE market_id=m.id) latest_aggregate_date,
                (SELECT MAX(retrieved_at) FROM market_captures WHERE market_id=m.id) latest_capture_import
                FROM markets m ORDER BY m.name"""
            )]
        from goblin_eye.ingestion.bounded import WATCHERS
        from goblin_eye.ingestion.discovery import discover_addon_paths
        unconnected_addons = []
        for addon, marker, supplies in (
            ("GatherLite", "GatherLite.toc", "Herb and ore location references; no Goblin Eye importer yet."),
            ("AtlasLootContinued_Data", "AtlasLootContinued_Data_Camelot.toc",
             "AtlasLoot Continued item-source catalogs; no Goblin Eye importer yet."),
        ):
            if discover_addon_paths(addon, marker):
                unconnected_addons.append({"addon": addon, "status": "no_importer", "notes": supplies})
        newest = snapshots["newest"] if snapshots else None
        age_hours = None
        if newest:
            captured = datetime.fromisoformat(newest.replace("Z", "+00:00"))
            age_hours = (datetime.now(timezone.utc) - captured).total_seconds() / 3600
        return {
            "queried_at": datetime.now(timezone.utc).isoformat(),
            "market_key": self.settings.market_key,
            "auction_context": auction_context(self.database),
            "newest_snapshot": newest,
            "snapshot_count": sum(s["snapshot_count"] for s in sources),
            "price_record_count": sum(s["price_record_count"] for s in sources),
            "freshness_scope": "Newest WoW Forever auction evidence; local scans and public references have separate source timestamps.",
            "age_hours": round(age_hours, 2) if age_hours is not None else None,
            "is_stale": age_hours is None or age_hours > self.settings.stale_after_hours,
            "markets": markets,
            "workers_in_this_process": [{"worker": type(w).__name__,"alive": bool(w._thread and w._thread.is_alive()),
                "stopping": w._stop.is_set()} for w in list(WATCHERS)],
            "worker_scope": "Only this process; an MCP process cannot assert the separate dashboard worker is alive.",
            "auction_imports": {
                "public_ahledger": self.settings.auto_sync_ahledger,
                "local_auctionator": self.settings.auto_discover_auctionator,
                "local_ahledger": self.settings.auto_import_ahledger_scans,
            },
            "sources": sources,
            "watched_files": watched_files,
            "file_import_error_count": sum(row['last_status'] == 'error' for row in watched_files),
            "character_imports": {"alts_forever": self.settings.auto_import_alts_forever},
            "research_imports": {
                "professiondb": self.settings.auto_import_professiondb,
                "foreverguide": self.settings.auto_import_foreverguide,
                "questiedb": self.settings.auto_import_questiedb,
                "mapzeroth": self.settings.auto_import_mapzeroth,
                "official_blizzard": self.settings.auto_sync_official,
            },
            "unconnected_installed_data_addons": unconnected_addons,
            "adapters": [AuctionatorSavedVariablesAdapter.capability.to_dict(), AHLedgerPublicApiAdapter.capability.to_dict(),
                         BlizzardResearchAdapter.capability.to_dict(), ProfessionDBAdapter.capability.to_dict(),
                         ForeverGuideAdapter.capability.to_dict(), ForeverGuideProfessionAdapter.capability.to_dict(),
                         ForeverGuideDungeonAdapter.capability.to_dict(),
                         QuestieDbAdapter.capability.to_dict(), MapzerothAdapter.capability.to_dict(),
                         LocalAHLedgerAdapter.capability.to_dict(), AltsForeverAdapter.capability.to_dict()]
            + [NormalizedJsonAdapter.capability.to_dict()]
            + [adapter.capability.to_dict() for adapter in PROVIDER_ADAPTERS],
        }

    def next_data(self) -> dict[str, Any]:
        with self.database.transaction() as connection:
            unresolved_local_items = connection.execute(
                """SELECT COUNT(DISTINCT po.item_id) FROM price_observations po
                JOIN sources s ON s.id=po.source_id WHERE s.source_key='local-auctionator'
                AND po.item_id IS NOT NULL AND NOT EXISTS
                (SELECT 1 FROM item_observations io WHERE io.item_id=po.item_id)"""
            ).fetchone()[0]
            local_depth_count = connection.execute("SELECT COUNT(*) FROM auction_rows").fetchone()[0]
            local_price_count = connection.execute("""SELECT COUNT(*) FROM price_observations p
                JOIN sources s ON s.id=p.source_id WHERE s.source_key='local-auctionator'""").fetchone()[0]
            forever_recipe_counts = connection.execute("""SELECT COUNT(*) recipes,
                SUM(CASE WHEN r.output_quantity IS NOT NULL THEN 1 ELSE 0 END) quantified,
                SUM(CASE WHEN r.output_quantity>1 THEN 1 ELSE 0 END) multi_output
                FROM recipe_facts r JOIN research_datasets d ON d.id=r.dataset_id
                JOIN sources s ON s.id=d.source_id
                WHERE d.active=1 AND s.source_key='foreverguide-professions'""").fetchone()
            corroborated_recipes = connection.execute("""SELECT COUNT(*) FROM (
                SELECT r.spell_id FROM recipe_facts r JOIN research_datasets d ON d.id=r.dataset_id
                JOIN sources s ON s.id=d.source_id WHERE d.active=1
                AND s.source_key IN ('libprofessiondb-forever','foreverguide-professions')
                GROUP BY r.spell_id HAVING COUNT(DISTINCT s.source_key)=2)""").fetchone()[0]
            spawn_counts = connection.execute("""SELECT
                COUNT(*) entities,
                SUM(CASE WHEN json_extract(w.attributes_json,'$.spawn_count')>0 THEN 1 ELSE 0 END) with_spawns,
                SUM(COALESCE(json_extract(w.attributes_json,'$.spawn_count'),0)) spawn_points
                FROM world_entity_facts w JOIN research_datasets d ON d.id=w.dataset_id
                JOIN sources s ON s.id=d.source_id WHERE d.active=1 AND s.source_key='questiedb-forever'""").fetchone()
            travel_counts = connection.execute("""SELECT
                (SELECT COUNT(*) FROM travel_nodes n JOIN research_datasets d ON d.id=n.dataset_id
                 JOIN sources s ON s.id=d.source_id WHERE d.active=1 AND s.source_key='mapzeroth-forever') nodes,
                (SELECT COUNT(*) FROM travel_edges e JOIN research_datasets d ON d.id=e.dataset_id
                 JOIN sources s ON s.id=d.source_id WHERE d.active=1 AND s.source_key='mapzeroth-forever') edges""").fetchone()
            override_counts = connection.execute("""SELECT
                SUM(CASE WHEN a.method='forever_drop' THEN 1 ELSE 0 END) forever_drops,
                SUM(CASE WHEN a.method='quest_reward' THEN 1 ELSE 0 END) verified_rewards
                FROM acquisition_facts a JOIN research_datasets d ON d.id=a.dataset_id
                JOIN sources s ON s.id=d.source_id WHERE d.active=1 AND s.source_key='foreverguide-dungeons'""").fetchone()
        return {
            "headline": "Connect locally observed Forever evidence",
            "items": [
                {
                    "priority": 1,
                    "title": "Forever item identity data",
                    "needed": (f"Resolve the {unresolved_local_items} local Auctionator item IDs still absent from the synced AHledger catalog."
                               if unresolved_local_items else
                               "Add missing static Forever item properties when research requires them. AHledger Forever public prices are available as community references."),
                    "unlocks": ["Named market records", "Item search", "Market-to-world joins"],
                },
                {
                    "priority": 2,
                    "title": "Your WoW Forever scans",
                    "needed": "Local market identity comes from explicit configuration and source fields; missing identity remains unknown. Local scans and public references are distinguished by source. After a reset, do a fresh auction scan and let WoW save SavedVariables. Import is automatic; no public market mapping is needed.",
                    "unlocks": ["Fresh auction evidence", "Scan history"],
                },
                {
                    "priority": 3,
                    "title": "Expand the item graph",
                    "needed": (f"Forever Guide supplies {forever_recipe_counts['recipes'] or 0:,} independent recipe assertions; "
                               f"{forever_recipe_counts['quantified'] or 0:,} have source-backed output quantities "
                               f"({forever_recipe_counts['multi_output'] or 0:,} explicitly produce more than one), and "
                               f"{corroborated_recipes:,} spell IDs overlap LibProfessionDB. "
                               f"Forever dungeon labels add {override_counts['forever_drops'] or 0:,} ID-addressable new boss-loot links "
                               f"and {override_counts['verified_rewards'] or 0:,} fv-verified quest-reward links. "
                               f"QuestieDB contributes {spawn_counts['entities'] or 0:,} NPC/object assertions, "
                               f"{spawn_counts['with_spawns'] or 0:,} with {spawn_counts['spawn_points'] or 0:,} coordinate points. "
                               f"Mapzeroth contributes {travel_counts['nodes'] or 0:,} travel nodes and {travel_counts['edges'] or 0:,} authored edges. "
                               "Current server obtainability, respawn timing, live simultaneous populations and unlabeled travel assumptions remain unverified."),
                    "unlocks": ["Forever overrides", "Recipe verification", "Farming research"],
                },
                {
                    "priority": 4,
                    "title": "Listing-depth coverage" if local_depth_count else "Raw listing-depth source",
                    "needed": (f"{local_depth_count:,} local AHledger auction rows are indexed. Completeness and gear variants still need verification; sale outcomes are unavailable."
                               if local_depth_count else "A real saved AHledger scan supplies individual auction rows and stack sizes."),
                    "unlocks": ["Stack distributions", "Listing-level depth", "Bulk structure"],
                },
                {
                    "priority": 5,
                    "title": "Economic rules",
                    "needed": "Locally verified auction cut, deposit rules, durations, and mail timing.",
                    "unlocks": ["Accurate fees", "Deposit risk", "Net profit thresholds"],
                },
                {
                    "priority": 6,
                    "title": "Optional player context",
                    "needed": "Class, level, professions, capital, preferred activities, risk, and holding period when an agent investigation needs them.",
                    "unlocks": ["Feasibility checks", "Relevant evidence filters", "Scenario arithmetic"],
                },
            ],
            "auctionator_price_history_connected": local_price_count > 0,
        }

    def summary(self) -> dict[str, Any]:
        source_health = self.sources()
        with self.database.transaction() as connection:
            counts = {
                table: connection.execute(f"SELECT COUNT(*) count FROM {table}").fetchone()["count"]
                for table in ("items", "item_observations", "recipes", "vendors", "mobs", "camps",
                              "snapshots", "listings", "price_observations", "source_documents",
                              "research_datasets", "recipe_facts", "reagent_facts", "world_entity_facts", "acquisition_facts",
                              "travel_nodes", "travel_edges", "auction_rows")
            }
            stored_counts = dict(counts)
            # Archived world revisions remain inspectable but do not double the active graph's coverage.
            for table in ("recipe_facts", "world_entity_facts", "acquisition_facts", "travel_nodes", "travel_edges"):
                counts[table] = connection.execute(f"SELECT COUNT(*) FROM {table} f JOIN research_datasets d ON d.id=f.dataset_id WHERE d.active=1").fetchone()[0]
            counts["research_datasets"] = connection.execute("SELECT COUNT(*) FROM research_datasets WHERE active=1").fetchone()[0]
            counts["reagent_facts"] = connection.execute("""SELECT COUNT(*) FROM reagent_facts f
                JOIN recipe_facts r ON r.id=f.recipe_fact_id JOIN research_datasets d ON d.id=r.dataset_id WHERE d.active=1""").fetchone()[0]
        return {
            "product": self.settings.display_name,
            "queried_at": datetime.now(timezone.utc).isoformat(),
            "market_key": self.settings.market_key,
            "auction_context": auction_context(self.database),
            "source_count": len(source_health["sources"]),
            "observed_markets": source_health["markets"],
            "record_counts": counts,
            "stored_record_counts": stored_counts,
            "freshness": {
                "newest_snapshot": source_health["newest_snapshot"],
                "is_stale": source_health["is_stale"],
            },
            "safety": "Observational and advisory only; every in-game action remains manual.",
        }


def json_text(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False)
