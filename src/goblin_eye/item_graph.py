"""Read sourced recipe relationships without treating unknown properties as facts."""
from __future__ import annotations

import json
from typing import Any

from goblin_eye.repository import Database
from goblin_eye.validation import integer, text


RECIPE_SELECT = """SELECT r.*, d.source_version, d.game_build, d.content_phase,
    d.retrieved_at, d.confidence, d.evidence_kind, d.sha256 dataset_sha256,
    d.limitations_json, s.source_key, s.name source_name, s.url source_url
    FROM recipe_facts r JOIN research_datasets d ON d.id=r.dataset_id
    JOIN sources s ON s.id=d.source_id"""


class ItemGraph:
    def __init__(self, database: Database):
        self.database = database

    def search_items(self, query: str = "", limit: int = 50, offset: int = 0) -> dict[str, Any]:
        integer(limit,"limit",1,100);integer(offset,"offset");text(query,"query",empty=True)
        if not 1 <= limit <= 100 or offset < 0:
            raise ValueError("limit must be 1–100 and offset must be nonnegative")
        # An item may exist in a scan or recipe even before its name is known.
        cte = """WITH ids AS (
            SELECT item_id FROM item_observations UNION SELECT id FROM items
            UNION SELECT item_id FROM auction_rows
            UNION SELECT item_id FROM character_item_observations
            UNION SELECT w.entity_id FROM world_entity_facts w JOIN research_datasets d ON d.id=w.dataset_id
                WHERE d.active=1 AND w.entity_type='item'
            UNION SELECT item_id FROM price_observations WHERE item_id IS NOT NULL
            UNION SELECT output_item_id FROM recipe_facts r JOIN research_datasets d ON d.id=r.dataset_id
                WHERE d.active=1 AND output_item_id IS NOT NULL
            UNION SELECT rf.item_id FROM reagent_facts rf JOIN recipe_facts r ON r.id=rf.recipe_fact_id
                JOIN research_datasets d ON d.id=r.dataset_id WHERE d.active=1
            UNION SELECT t.item_id FROM recipe_teaching_items t JOIN recipe_facts r ON r.id=t.recipe_fact_id
                JOIN research_datasets d ON d.id=r.dataset_id WHERE d.active=1
        ), ranked_names AS (
            SELECT item_id,name,position FROM selected_item_names
        ), catalog AS (
            SELECT ids.item_id, rn.name FROM ids LEFT JOIN ranked_names rn
                ON rn.item_id=ids.item_id AND rn.position=1
        )
        """
        term = query.strip()
        # Escape LIKE metacharacters: user searches are literal text.
        like = "%" + term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        where = " WHERE (?='' OR name LIKE ? ESCAPE '\\' COLLATE NOCASE OR CAST(item_id AS TEXT)=?)"
        with self.database.transaction() as connection:
            total = connection.execute(cte + "SELECT COUNT(*) FROM catalog" + where, (term, like, term)).fetchone()[0]
            rows = connection.execute(cte + "SELECT * FROM catalog" + where +
                                      " ORDER BY name IS NULL, name COLLATE NOCASE, item_id LIMIT ? OFFSET ?",
                                      (term, like, term, limit, offset)).fetchall()
        return {"items": [dict(row) for row in rows], "total": total, "limit": limit, "offset": offset}

    def recipes(self, item_id: int, relation: str) -> list[dict[str, Any]]:
        filters = {
            "produces": "r.output_item_id=?",
            "consumes": "EXISTS(SELECT 1 FROM reagent_facts rf WHERE rf.recipe_fact_id=r.id AND rf.item_id=?)",
            "teaches": "EXISTS(SELECT 1 FROM recipe_teaching_items t WHERE t.recipe_fact_id=r.id AND t.item_id=?)",
        }
        if relation not in filters:
            raise ValueError("Unknown recipe relationship")
        with self.database.transaction() as connection:
            rows = connection.execute(RECIPE_SELECT + " WHERE d.active=1 AND " + filters[relation] +
                                      " ORDER BY r.profession, r.name, r.spell_id, s.trust_rank", (item_id,)).fetchall()
            return [self._expand(connection, row) for row in rows]

    @staticmethod
    def _expand(connection, row) -> dict[str, Any]:
        recipe = dict(row)
        recipe["attributes"] = json.loads(recipe.pop("attributes_json"))
        recipe["limitations"] = json.loads(recipe.pop("limitations_json"))
        recipe["reagents"] = [dict(value) for value in connection.execute(
            """SELECT rf.item_id, rf.quantity, (SELECT name FROM selected_item_names WHERE item_id=rf.item_id) name
            FROM reagent_facts rf WHERE rf.recipe_fact_id=? ORDER BY rf.item_id""", (row["id"],))]
        recipe["teaching_items"] = [dict(value) for value in connection.execute(
            "SELECT item_id, raw_reference FROM recipe_teaching_items WHERE recipe_fact_id=? ORDER BY item_id",
            (row["id"],))]
        return recipe

    def recipe(self, fact_id: int) -> dict[str, Any] | None:
        integer(fact_id,"fact_id",1)
        with self.database.transaction() as connection:
            row = connection.execute(RECIPE_SELECT + " WHERE r.id=?", (fact_id,)).fetchone()
            if row is None:
                return None
            result = self._expand(connection, row)
            result["active"] = bool(connection.execute("SELECT active FROM research_datasets WHERE id=?",
                                                       (row["dataset_id"],)).fetchone()[0])
            alternatives = connection.execute(RECIPE_SELECT + " WHERE d.active=1 AND r.spell_id=? AND r.id<>?",
                                             (row["spell_id"], fact_id)).fetchall()
            result["other_source_assertions"] = [self._expand(connection, value) for value in alternatives]
            return result

    def datasets(self) -> list[dict[str, Any]]:
        with self.database.transaction() as connection:
            rows = connection.execute("""SELECT d.*, s.source_key, s.name source_name,
                (SELECT COUNT(*) FROM recipe_facts r WHERE r.dataset_id=d.id) recipe_count,
                (SELECT COUNT(*) FROM acquisition_facts a WHERE a.dataset_id=d.id) acquisition_count,
                (SELECT COUNT(*) FROM world_entity_facts w WHERE w.dataset_id=d.id) world_entity_count
                FROM research_datasets d JOIN sources s ON s.id=d.source_id
                ORDER BY d.active DESC, d.retrieved_at DESC""").fetchall()
        results = []
        for row in rows:
            value = dict(row)
            value["manifest"] = json.loads(value.pop("manifest_json"))
            value["limitations"] = json.loads(value.pop("limitations_json"))
            results.append(value)
        return results

    def acquisition(self, item_id: int, limit: int = 50, offset: int = 0, **filters) -> dict[str, Any]:
        from goblin_eye.research_queries import ResearchQueries
        integer(item_id, "item_id", 1)
        return ResearchQueries(self.database).acquisition(item_id=item_id, limit=limit, offset=offset, **filters)

    def world_entity(self, entity_type: str, entity_id: int, limit: int = 50, offset: int = 0) -> dict[str, Any]:
        if entity_type not in ("npc", "object", "quest", "item") or entity_id <= 0 or not 1 <= limit <= 500 or offset < 0:
            raise ValueError("Use npc/object/quest/item, positive entity ID, limit 1–500 and nonnegative offset")
        with self.database.transaction() as connection:
            facts = connection.execute("""SELECT w.*, d.source_version,d.retrieved_at,d.game_build,d.confidence,
                d.evidence_kind,d.sha256 dataset_sha256,d.limitations_json,s.source_key,s.url source_url
                FROM world_entity_facts w JOIN research_datasets d ON d.id=w.dataset_id JOIN sources s ON s.id=d.source_id
                WHERE d.active=1 AND w.entity_type=? AND w.entity_id=? ORDER BY s.trust_rank,d.retrieved_at DESC""",
                (entity_type,entity_id)).fetchall()
            total = connection.execute("""SELECT COUNT(*) FROM acquisition_facts a JOIN research_datasets d ON d.id=a.dataset_id
                WHERE d.active=1 AND a.entity_type=? AND a.entity_id=?""", (entity_type,entity_id)).fetchone()[0]
            rows = connection.execute("""SELECT a.*, w.name item_name,d.source_version,d.retrieved_at,
                d.game_build,d.confidence,s.source_key,s.url source_url,
                CASE WHEN a.evidence_basis='classic_baseline' THEN 'historical' ELSE 'extracted' END evidence_kind
                FROM acquisition_facts a JOIN research_datasets d ON d.id=a.dataset_id JOIN sources s ON s.id=d.source_id
                LEFT JOIN world_entity_facts w ON w.dataset_id=a.dataset_id AND w.entity_type='item' AND w.entity_id=a.item_id
                WHERE d.active=1 AND a.entity_type=? AND a.entity_id=? ORDER BY a.method,a.item_id,a.id LIMIT ? OFFSET ?""",
                (entity_type,entity_id,limit,offset)).fetchall()
        from goblin_eye.research_queries import quality_sql
        items = [dict(row) for row in rows]
        with self.database.transaction() as connection:
            for item in items:
                raw = connection.execute('SELECT ' + quality_sql('?'), (item['item_id'],)).fetchone()[0]
                item['quality_evidence'] = json.loads(raw) if raw else None
        assertions = []
        for row in facts:
            value = dict(row)
            value["attributes"] = json.loads(value.pop("attributes_json"))
            value["limitations"] = json.loads(value.pop("limitations_json"))
            assertions.append(value)
        return {"entity_type":entity_type,"entity_id":entity_id,"assertions":assertions,
                "items":items,"total":total,"limit":limit,"offset":offset,
                "complete_loot_table":False,
                "interpretation":"Reverse lookup of an item-source index. Missing drops, quantities and omitted associations prevent a complete per-kill valuation."}

    def listing_markets(self, item_id: int) -> list[dict[str, Any]]:
        with self.database.transaction() as connection:
            return [dict(row) for row in connection.execute("""SELECT m.market_key,m.name,MAX(sn.captured_at) latest_scan_at
                FROM markets m JOIN snapshots sn ON sn.market_id=m.id
                WHERE EXISTS(SELECT 1 FROM auction_rows a WHERE a.snapshot_id=sn.id AND a.item_id=?)
                GROUP BY m.id ORDER BY latest_scan_at DESC""",(item_id,))]

    def market_depth(self,item_id:int,market_key:str,limit:int=50,offset:int=0,snapshot_id:int|None=None) -> dict[str,Any]:
        integer(item_id,"item_id",1);integer(limit,"limit",1,500);integer(offset,"offset");text(market_key,"market_key")
        if snapshot_id is not None: integer(snapshot_id,"snapshot_id",1)
        if item_id <= 0 or not market_key or not 1 <= limit <= 500 or offset < 0:
            raise ValueError("Positive item ID, explicit market key, limit 1–500 and nonnegative offset required")
        with self.database.transaction() as connection:
            snapshot = connection.execute("""SELECT sn.*,m.market_key,m.name market_name,m.region,m.ruleset,m.faction,
                m.is_verified,s.source_key FROM snapshots sn JOIN markets m ON m.id=sn.market_id
                JOIN sources s ON s.id=sn.source_id WHERE m.market_key=? AND s.source_key='local-ahledger' AND (? IS NULL OR sn.id=?)
                ORDER BY sn.captured_at DESC,sn.id DESC LIMIT 1""",(market_key,snapshot_id,snapshot_id)).fetchone()
            if snapshot is None:
                return {"item_id":item_id,"market_key":market_key,"snapshot":None,"data_available":False,
                        "listings":[],"total":0,"limit":limit,"offset":offset}
            params = (snapshot["id"],item_id)
            totals = dict(connection.execute("""SELECT COUNT(*) listing_count,COALESCE(SUM(quantity),0) listed_units,
                COALESCE(SUM(CASE WHEN buyout_copper>0 THEN quantity ELSE 0 END),0) buyout_units,
                COALESCE(SUM(CASE WHEN buyout_copper=0 THEN 1 ELSE 0 END),0) bid_only_listings,
                MIN(CASE WHEN buyout_copper>0 THEN 1.0*buyout_copper/quantity END) min_unit_buyout_copper
                FROM auction_rows WHERE snapshot_id=? AND item_id=?""",params).fetchone())
            rows = connection.execute("""SELECT ordinal,item_id,quantity,buyout_copper,bid_copper,time_left_code,
                CASE WHEN buyout_copper>0 THEN 1.0*buyout_copper/quantity END unit_buyout_copper
                FROM auction_rows WHERE snapshot_id=? AND item_id=?
                ORDER BY buyout_copper=0,1.0*buyout_copper/quantity,ordinal LIMIT ? OFFSET ?""",(*params,limit,offset)).fetchall()
            stacks = [dict(row) for row in connection.execute("""SELECT quantity stack_size,COUNT(*) listing_count,
                SUM(quantity) listed_units,MIN(CASE WHEN buyout_copper>0 THEN buyout_copper END) min_stack_buyout_copper
                FROM auction_rows WHERE snapshot_id=? AND item_id=? GROUP BY quantity ORDER BY quantity""",params)]
        return {"item_id":item_id,"market_key":market_key,"data_available":True,"snapshot":dict(snapshot),
                "total":totals["listing_count"],"totals":totals,"limit":limit,"offset":offset,
                "listings":[dict(row) for row in rows],"stack_distribution":stacks,
                "limitations":["Snapshot of listed supply, not sales or liquidity.",
                    "Zero buyout means bid-only; it is not a free item.",
                    "Source completeness claim is retained but not independently verified.",
                    "Gear variants and persistent auction identifiers are absent; compare base item IDs cautiously."]}
