"""Provider-neutral access to local character observations.

Character importers must be based on an inspected saved file and keep source
provenance. This module only reads records already stored in Goblin Eye.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from goblin_eye.repository import Database


class CharacterStore:
    def __init__(self, database: Database):
        self.database = database

    def list(self) -> dict[str, Any]:
        with self.database.transaction() as connection:
            rows = connection.execute("""SELECT id snapshot_id,name,NULLIF(realm,'unknown') realm,
                NULLIF(race,'unknown') race,class_token,level,
                imported_at,captured_at,NULLIF(game_build,'unknown') game_build,source_key,confidence FROM character_snapshots
                WHERE id IN (SELECT id FROM (SELECT id,ROW_NUMBER() OVER
                    (PARTITION BY character_key ORDER BY captured_at DESC,id DESC) latest FROM character_snapshots) WHERE latest=1)
                ORDER BY id DESC""").fetchall()
        from goblin_eye.auction_policy import context
        return {
            "auction_context": context(self.database),
            "characters": [dict(row) for row in rows],
            "identity_warning": "Character identity and capture freshness depend on the inspected source; do not merge names or realms without evidence.",
            "refresh_instructions": "Alts Forever imports automatically while the dashboard runs, after WoW saves on /reload or logout. Visit bank/mail and open profession windows before saving to record those categories. Missing categories remain unknown.",
        }

    def get(self, snapshot_id: int) -> dict[str, Any] | None:
        if type(snapshot_id) is not int or snapshot_id < 1:
            raise ValueError("snapshot_id must be a positive integer")
        with self.database.transaction() as connection:
            row = connection.execute("SELECT * FROM character_snapshots WHERE id=?", (snapshot_id,)).fetchone()
            if row is None:
                return None
            items = connection.execute("""SELECT location,ordinal,item_id,enchant_id,random_suffix,slot_id
                FROM character_item_observations WHERE snapshot_id=? ORDER BY location,ordinal""", (snapshot_id,)).fetchall()
            inventory = connection.execute("""SELECT location,item_id,quantity FROM character_inventory_observations
                WHERE snapshot_id=? ORDER BY location,item_id""", (snapshot_id,)).fetchall()
        result = dict(row)
        result["source_payload"] = json.loads(result.pop("payload_json"))
        result["limitations"] = json.loads(result.pop("limitations_json"))
        result["items"] = [dict(item) for item in items]
        if result["source_key"] == "local-alts-forever":
            from goblin_eye.agent_responses import money_label
            char = result["source_payload"]["character"]
            for field in ("realm", "race", "game_build"):
                if result[field] == "unknown":
                    result[field] = None
            for item in result["items"]:
                item.update(quantity=1, enchant_id=None, random_suffix=None,
                            item_link=char.get("gear", {}).get(str(item["slot_id"])))
            result["items"].extend({**dict(item), "ordinal": None, "slot_id": None,
                "enchant_id": None, "random_suffix": None} for item in inventory)
            result["inventory"] = [dict(item) for item in inventory]
            result["character"] = char
            result["money_copper"] = char.get("money")
            result["money_display"] = {"money_copper": money_label(char["money"])} if char.get("money") is not None else {}
            result["coverage"] = {field: {"status": "recorded" if field in char else "not_recorded",
                "captured_at": (datetime.fromtimestamp(char["bankAt"], timezone.utc).isoformat()
                    if field == "bank" and char.get("bankAt") else None),
                "timestamp_basis": "addon bankAt Unix seconds" if field == "bank" and char.get("bankAt") else "no category-specific timestamp"}
                for field in ("bags", "gear", "bank", "mail", "recipes", "profs", "reps")}
            result["coverage"]["mail"]["completeness"] = "unknown"
            result["coverage"]["mail"]["status"] = "recorded_empty_completeness_unknown" if char.get("mail") == {} else result["coverage"]["mail"]["status"]
        from goblin_eye.auction_policy import context
        result["auction_context"] = context(self.database)
        result["market_key"] = result["auction_context"]["market_key"]
        result["market_context_source"] = "User-selected local auction workspace; not a field in the character source"
        result["follow_up"] = "Use item_id with item research and acquisition tools. Treat saved character data as observations from the named source, with its recorded freshness."
        return result
