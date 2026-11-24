"""Provider-neutral access to local character observations.

Character importers must be based on an inspected saved file and keep source
provenance. This module only reads records already stored in Goblin Eye.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from goblin_eye.repository import Database

SLOT_NAMES = dict(enumerate(('Head','Neck','Shoulder','Shirt','Chest','Waist','Legs','Feet','Wrist','Hands',
    'Finger 1','Finger 2','Trinket 1','Trinket 2','Back','Main Hand','Off Hand','Ranged','Tabard'), 1))


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

    def get(self, snapshot_id: int, talent_limit=20, talent_offset=0) -> dict[str, Any] | None:
        from goblin_eye.validation import integer
        integer(talent_limit,'talent_limit',1,100); integer(talent_offset,'talent_offset')
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
            from goblin_eye.item_properties import ItemProperties
            from goblin_eye.item_instances import ItemInstances, item_string
            properties, evidence = ItemProperties(self.database).get_many([i['item_id'] for i in result['items']])
            result['item_property_evidence'] = evidence
            for field in ("realm", "race", "game_build"):
                if result[field] == "unknown":
                    result[field] = None
            for item in result["items"]:
                item.update(quantity=1, enchant_id=None, random_suffix=None,
                            item_link=char.get("gear", {}).get(str(item["slot_id"])))
                link = item['item_link'] or ''
                name = re.search(r'\|h\[(.*?)\]\|h', link)
                quality = re.search(r'\|cnIQ(\d+):', link)
                # Preserve the full modern link. Bonus IDs are not Classic random-suffix IDs.
                item.update(slot_name=SLOT_NAMES.get(item['slot_id']),
                    equipped_name=name[1] if name else None,
                    equipped_quality_id=int(quality[1]) if quality else None,
                    item_properties=properties.get(item['item_id'],{}),
                    instance_stats_status='unresolved_bonus_and_enchant',
                    instance_stats_note='Static base stats exclude unverified bonus IDs, suffixes and enchants; do not assert an exact equipped total.')
                if item.get('item_link'):
                    key=item_string(item['item_link'])
                    enchant=key.split(':')[2]
                    item['enchant_id']=int(enchant) if enchant else 0
                    if item['enchant_id']:
                        item['enchant_evidence']=ItemProperties(self.database).enchant(item['enchant_id'])
                    observed=ItemInstances(self.database).page(item['item_id'],item_link=item['item_link'],
                        namespace=result['source_payload']['namespace'],known_at=result['imported_at'],limit=10)['records']
                    # Never silently choose between observations from different builds.
                    selected=ItemInstances(self.database).page(item['item_id'],item_link=item['item_link'],
                        namespace=result['source_payload']['namespace'],game_build=result['game_build'],known_at=result['imported_at'],limit=1)['records'] if result.get('game_build') else observed
                    if len({v['game_build'] for v in selected})==1 and selected:
                        item['instance_stats']=selected[0]
                        item['observed_item_metadata']=selected[0].get('metadata',{})
                        if not item.get('equipped_name') and item['observed_item_metadata'].get('name'):
                            item['equipped_name']=item['observed_item_metadata']['name']
                        item['instance_stats_status']='api_reported'
                        item['instance_stats_note']='Numeric rows observed for this full item link; tooltip/effect coverage and enchant API semantics must be checked separately.'
                    elif observed:
                        item['instance_stats_status']='different_observed_build' if result.get('game_build') else 'conflicting_observed_builds'
                conflicts=[]
                for field in ('quality','required_level','item_level'):
                    assertions={view:p[field] for view,p in item['item_properties'].items() if p.get(field) is not None}
                    if len(set(assertions.values()))>1:
                        conflicts.append({'field':field,'assertions':assertions})
                if conflicts: item['source_conflicts']=conflicts
                for conflict in conflicts:
                    field={'quality':'quality_id','item_level':'item_level','required_level':'required_level'}[conflict['field']]
                    observed_value=item.get('observed_item_metadata',{}).get(field)
                    if observed_value is not None:
                        conflict['equipped_comparison_uses']={'value':observed_value,'field':field,'basis':'current-build client observation for exact link'}
                stat_fields=set().union(*(p.get('stats',{}) for p in item['item_properties'].values()))
                for field in sorted(stat_fields):
                    assertions={view:p['stats'][field] for view,p in item['item_properties'].items() if field in p.get('stats',{})}
                    if len(set(assertions.values()))>1:
                        item.setdefault('source_conflicts',[]).append({'field':'stats.'+field,'assertions':assertions})
            result["items"].extend({**dict(item), "ordinal": None, "slot_id": None,
                "enchant_id": None, "random_suffix": None} for item in inventory)
            result["inventory"] = [dict(item) for item in inventory]
            result["character"] = char
            by_slot = {i['slot_id']:i for i in result['items'] if i['location']=='equipped'}
            gear = char.get('gear') or {}
            result['equipment_slots'] = [{"slot_id":slot,"slot_name":name,
                "status":"equipped" if slot in by_slot else "recorded_empty" if str(slot) in gear and gear[str(slot)] is None else "not_recorded",
                "item_id":by_slot[slot]['item_id'] if slot in by_slot else None} for slot,name in SLOT_NAMES.items()]
            capture=char.get('goblinEyeGear')
            if capture:
                for slot in result['equipment_slots']:
                    saved=capture['slots'].get(str(slot['slot_id']))
                    if saved is False and slot['slot_id'] not in by_slot:
                        slot['status']='recorded_empty'
                    slot['captured_at']=datetime.fromtimestamp(capture['capturedAt'],timezone.utc).isoformat()
            from goblin_eye.character_capture import sheet, COMPARISON_POLICY
            result['character_stats']=sheet(char,result['raw_reference'],talent_limit,talent_offset)
            from goblin_eye.quest_capture import location, active_quests
            result['saved_location']=location(char,result)
            log=active_quests(char,result,limit=1)
            result['active_quest_log']={k:v for k,v in log.items() if k not in ('records','offset','limit','next_offset')}
            result['active_quest_log']['follow_up']='get_character_active_quests(snapshot_id,limit=20,offset=next_offset)'
            result['stat_comparison_policy']=COMPARISON_POLICY
            result["money_copper"] = char.get("money")
            result["money_display"] = {"money_copper": money_label(char["money"])} if char.get("money") is not None else {}
            result["coverage"] = {field: {"status": "recorded" if field in char else "not_recorded",
                "captured_at": (datetime.fromtimestamp(char["bankAt"], timezone.utc).isoformat()
                    if field == "bank" and char.get("bankAt") else None),
                "timestamp_basis": "addon bankAt Unix seconds" if field == "bank" and char.get("bankAt") else "no category-specific timestamp"}
                for field in ("bags", "gear", "bank", "mail", "recipes", "profs", "reps")}
            result["coverage"]["mail"]["completeness"] = "unknown"
            result["coverage"]["mail"]["status"] = "recorded_empty_completeness_unknown" if char.get("mail") == {} else result["coverage"]["mail"]["status"]
            quests=self.quests(snapshot_id,limit=1)
            result['quest_completion']={k:quests.get(k) for k in
                ('status','total','captured_at','file_saved_at','imported_at','source_key','freshness','raw_reference','interpretation')}
            gaps=[]
            for item in result['items']:
                if item['location']!='equipped': continue
                issues=[]
                if item['instance_stats_status']!='api_reported': issues.append('exact_full_link_stats_not_captured')
                if not item.get('instance_stats',{}).get('tooltip'): issues.append('tooltip_effects_not_captured')
                if item.get('enchant_id') and item['enchant_evidence']['status']=='not_recorded': issues.append('enchant_not_in_catalog')
                if item.get('enchant_evidence',{}).get('numeric_conflict'): issues.append('enchant_numeric_conflict')
                if item.get('source_conflicts'): issues.append('static_catalog_conflict')
                if issues: gaps.append({'slot_id':item['slot_id'],'slot_name':item['slot_name'],'item_id':item['item_id'],'issues':issues})
            blockers=[g for g in gaps if 'exact_full_link_stats_not_captured' in g['issues']]
            blocking_reasons=[]
            if blockers: blocking_reasons.append('equipped_full_link_capture_missing')
            if result['character_stats']['status']=='not_recorded': blocking_reasons.append('character_sheet_capture_missing')
            result['research_preflight']={'equipment_gaps':gaps,
                'audit_readiness':'blocked' if blocking_reasons else 'ready_for_source_qualified_comparison',
                'blocking_reasons':blocking_reasons,
                'blocking_slots':[g['slot_name'] for g in blockers],
                'unrecorded_slots':[s['slot_name'] for s in result['equipment_slots'] if s['status']=='not_recorded'],
                'quest_completion_status':quests['status'],'quest_freshness':quests.get('freshness'),
                'effective_character_totals':result['character_stats']['status'],
                'talents_status':result['character_stats'].get('talents',{}).get('status','not_recorded'),
                'instructions':'If audit_readiness is blocked, diagnose capture/source health and report the blocking slots before broad upgrade research; do not launch another full conditional gear audit unless the user explicitly wants it. Current-build exact-link observations take precedence for equipped totals; static conflicts remain visible. Never subtract spell_damage from spell_power or Shadow resistance from Shadow damage. For crafted targets read get_recipe_evidence and learning_plan, page teaching-item acquisition, and verify crafter/skill/material availability. No manual tooltip hover or rescan is needed. Unknown fields stay unknown.'}
        from goblin_eye.auction_policy import context
        result["auction_context"] = context(self.database)
        result["market_key"] = result["auction_context"]["market_key"]
        result["market_context_source"] = "User-selected local auction workspace; not a field in the character source"
        result["follow_up"] = "Use item_id with item research and acquisition tools. Treat saved character data as observations from the named source, with its recorded freshness."
        result['evidence_time_policy'] = 'Equipment observations and Questie fallback are limited to evidence imported by this snapshot. Their own capture times remain explicit. Static item catalogs are current research enrichment, not historical character observations.'
        return result

    def quests(self,snapshot_id,limit=20,offset=0):
        from goblin_eye.validation import integer
        integer(snapshot_id,'snapshot_id',1); integer(limit,'limit',1,100); integer(offset,'offset')
        with self.database.transaction() as c:
            snapshot=c.execute('SELECT name,payload_json,source_key,captured_at,imported_at,raw_reference FROM character_snapshots WHERE id=?',(snapshot_id,)).fetchone()
            if not snapshot: raise ValueError('Character snapshot not found')
            payload=json.loads(snapshot['payload_json'])
            namespace=payload.get('namespace')
            row=c.execute('''SELECT * FROM character_quest_snapshots WHERE namespace=? AND character_name=? AND imported_at<=?
                ORDER BY file_saved_at DESC,id DESC LIMIT 1''',(namespace,snapshot['name'],snapshot['imported_at'])).fetchone()
            later_cache = None if row else c.execute('''SELECT imported_at FROM character_quest_snapshots
                WHERE namespace=? AND character_name=? AND imported_at>?
                ORDER BY imported_at LIMIT 1''',(namespace,snapshot['name'],snapshot['imported_at'])).fetchone()
        capture=payload.get('character',{}).get('goblinEyeQuests')
        if capture:
            observed=datetime.fromtimestamp(capture['capturedAt'],timezone.utc).isoformat()
            if not row or observed>=row['file_saved_at']:
                ids=sorted(int(k) for k,v in capture['completed'].items() if v)
                age=max(0,(datetime.now(timezone.utc)-datetime.fromisoformat(observed)).total_seconds())
                return dict(status='recorded',records=[{'quest_id':v,'completed':True} for v in ids[offset:offset+limit]],
                    total=len(ids),offset=offset,limit=limit,captured_at=observed, file_saved_at=None,
                    imported_at=snapshot['imported_at'], source_key='local-alts-forever',
                    freshness={'age_seconds':int(age),'status':'stale' if age>300 else 'recent','timestamp_basis':'client completion query capture time'},
                    raw_reference=snapshot['raw_reference']+'/goblinEyeQuests',
                    interpretation='Client completed-quest list captured automatically through Alts. Absence does not establish quest eligibility; faction, level, active quest log and prerequisites still require evidence.')
        if not row:
            return dict(status='not_captured',records=[],total=0,offset=offset,limit=limit,
                exclusion_reason='imported_after_snapshot' if later_cache else 'no_matching_cache',
                snapshot_imported_at=snapshot['imported_at'],
                matching_cache_imported_at=later_cache['imported_at'] if later_cache else None,
                interpretation=('A matching Questie cache was imported after this character snapshot and is excluded by the historical cutoff. Query a newer character snapshot; historical evidence is unchanged. '
                    if later_cache else 'No Questie completion cache matches this exact account and full character name. ')
                    + 'Zero records does not mean zero completed quests.')
        ids=json.loads(row['payload_json'])['completed']
        age=max(0,(datetime.now(timezone.utc)-datetime.fromisoformat(row['file_saved_at'])).total_seconds())
        return dict(status='recorded',records=[{'quest_id':v,'completed':True} for v in ids[offset:offset+limit]],
            total=len(ids),offset=offset,limit=limit,file_saved_at=row['file_saved_at'],imported_at=row['imported_at'],
            source_key='local-questie',freshness={'age_seconds':int(age),'status':'stale' if age>300 else 'recent','timestamp_basis':'Questie save-file time, not a completion query timestamp'},
            raw_reference=row['raw_reference'],interpretation='Questie saved completion assertions. File time is not completion time; absence does not prove eligibility. Match static quest IDs and faction/prerequisites separately.')

    def active_quests(self,snapshot_id,limit=20,offset=0):
        from goblin_eye.validation import integer
        from goblin_eye.quest_capture import active_quests, location
        integer(snapshot_id,'snapshot_id',1); integer(limit,'limit',1,100); integer(offset,'offset')
        with self.database.transaction() as c:
            row=c.execute('SELECT * FROM character_snapshots WHERE id=?',(snapshot_id,)).fetchone()
        if row is None: raise ValueError('Character snapshot not found')
        char=json.loads(row['payload_json']).get('character',{})
        result=active_quests(char,row,limit,offset)
        result.update(snapshot_id=snapshot_id,character_name=row['name'],saved_location=location(char,row))
        return result

    def equipment(self,snapshot_id,limit=10,offset=0):
        from goblin_eye.validation import integer
        integer(limit,'limit',1,19); integer(offset,'offset')
        value=self.get(snapshot_id)
        if value is None: raise ValueError('Character snapshot not found')
        equipped=[i for i in value['items'] if i['location']=='equipped']
        return dict(records=equipped[offset:offset+limit],total=len(equipped),limit=limit,offset=offset,
            item_property_evidence=value.get('item_property_evidence',{}),
            interpretation='Exact saved equipment observations; API stats, static base views and enchant assertions remain separate. Missing stats are unknown, not zero.')

    def inventory(self,snapshot_id,limit=20,offset=0):
        from goblin_eye.validation import integer
        integer(snapshot_id,'snapshot_id',1); integer(limit,'limit',1,100); integer(offset,'offset')
        with self.database.transaction() as c:
            if not c.execute('SELECT 1 FROM character_snapshots WHERE id=?',(snapshot_id,)).fetchone():
                raise ValueError('Character snapshot not found')
            total=c.execute('SELECT count(*) FROM character_inventory_observations WHERE snapshot_id=?',(snapshot_id,)).fetchone()[0]
            rows=c.execute('''SELECT location,item_id,quantity FROM character_inventory_observations
                WHERE snapshot_id=? ORDER BY location,item_id LIMIT ? OFFSET ?''',(snapshot_id,limit,offset)).fetchall()
        return dict(records=[dict(r) for r in rows],total=total,limit=limit,offset=offset,
            interpretation='Saved inventory quantities; bank/mail require prior capture. Item IDs alone do not identify suffix variants.')
