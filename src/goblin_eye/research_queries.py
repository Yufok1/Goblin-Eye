"""Bounded discovery queries over sourced world facts and personal auction scans."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from goblin_eye.validation import integer, text
from goblin_eye.world_labels import ZONE_NAMES, ZONE_PROVENANCE, RANK_NAMES, RANK_PROVENANCE


METHODS = ('drop', 'forever_drop', 'skinning', 'pickpocket', 'vendor', 'recipe_vendor', 'object_loot', 'quest_reward',
           'questie_drop', 'questie_object_loot', 'container_loot')
QUALITIES = ('POOR', 'COMMON', 'UNCOMMON', 'RARE', 'EPIC', 'LEGENDARY', 'ARTIFACT', 'HEIRLOOM')
PROVENANCE = """d.source_version,d.retrieved_at,d.game_build,d.content_phase,d.confidence,
    d.evidence_kind,d.sha256 dataset_sha256,d.limitations_json,
    s.source_key,s.name source_name,s.url source_url,s.trust_rank"""
WORLD_JOIN = """ FROM world_entity_facts w JOIN research_datasets d ON d.id=w.dataset_id
    JOIN sources s ON s.id=d.source_id """


def quality_sql(item_column):
    # The caller supplies only a static SQL identifier, never user input.
    return f"""(SELECT json_object('quality',io.quality,'source_key',qs.source_key,
        'retrieved_at',io.retrieved_at,'game_build',io.game_build,'confidence',io.confidence)
        FROM item_observations io JOIN sources qs ON qs.id=io.source_id
        WHERE io.item_id={item_column} AND io.quality IS NOT NULL
        ORDER BY qs.trust_rank,io.retrieved_at DESC,io.confidence DESC,io.id DESC LIMIT 1)"""


def expand(row):
    value = dict(row)
    for field, target in (('attributes_json', 'attributes'), ('limitations_json', 'limitations'),
                          ('quality_json', 'quality_evidence')):
        if field in value:
            raw = value.pop(field)
            value[target] = json.loads(raw) if raw else None
    if value.get('attributes'):
        value['zone_name'] = ZONE_NAMES.get(value['attributes'].get('ui_map_id'))
        if value['zone_name']: value['zone_label_evidence'] = ZONE_PROVENANCE
        value['rank_name'] = RANK_NAMES.get(value['attributes'].get('rank'))
        if value['rank_name']: value['rank_label_evidence'] = RANK_PROVENANCE
    return value


def world_filters(query='', entity_type=None, min_level=None, max_level=None, ui_map_id=None, rank=None, zone=None,
                  area_id=None):
    text(query, 'query', empty=True)
    where, args = ['d.active=1'], []
    if entity_type is not None:
        if entity_type not in ('npc', 'object', 'quest', 'item'):
            raise ValueError('entity_type must be npc, object, quest or item')
        where.append('w.entity_type=?'); args.append(entity_type)
    if query.strip():
        maps = [k for k,v in ZONE_NAMES.items() if len(query.strip()) >= 3 and query.strip().casefold() in v.casefold()]
        zone_clause = " OR json_extract(w.attributes_json,'$.ui_map_id') IN (" + ','.join('?' for _ in maps) + ')' if maps else ''
        where.append('(instr(lower(w.name),lower(?))>0 OR CAST(w.entity_id AS TEXT)=?' + zone_clause + ')')
        args.extend([query.strip(), query.strip()])
        args.extend(maps)
    if zone is not None:
        text(zone, 'zone')
        maps = [k for k,v in ZONE_NAMES.items() if zone.strip().casefold() in v.casefold()]
        if not maps: raise ValueError('Zone name is not in the reviewed label catalog. Use a sourced ui_map_id; this does not mean world records are missing.')
        where.append("json_extract(w.attributes_json,'$.ui_map_id') IN (" + ','.join('?' for _ in maps) + ')')
        args.extend(maps)
    for name, value, op in (('min_level', min_level, '>='), ('max_level', max_level, '<='),
                            ('ui_map_id', ui_map_id, '='), ('rank', rank, '=')):
        if value is not None:
            integer(value, name, 0 if name == 'rank' else 1)
            where.append(f"json_extract(w.attributes_json,'$.{name}'){op}?"); args.append(value)
    if area_id is not None:
        integer(area_id, 'area_id', 1)
        where.append("(json_extract(w.attributes_json,'$.area_id')=? OR EXISTS(SELECT 1 FROM json_each(w.attributes_json,'$.spawn_area_ids') WHERE value=?))")
        args.extend((area_id, area_id))
    if min_level is not None and max_level is not None and min_level > max_level:
        raise ValueError('min_level must not exceed max_level')
    return where, args


class ResearchQueries:
    def __init__(self, database):
        self.database = database

    def world(self, query='', entity_type='npc', min_level=None, max_level=None,
              ui_map_id=None, rank=None, method=None, limit=25, offset=0, zone=None, area_id=None):
        integer(limit, 'limit', 1, 100); integer(offset, 'offset')
        where, args = world_filters(query, entity_type, min_level, max_level, ui_map_id, rank, zone, area_id)
        if method is not None:
            if method not in METHODS: raise ValueError(f'method must be one of {METHODS}')
            where.append('''EXISTS(SELECT 1 FROM acquisition_facts a
                JOIN research_datasets ad ON ad.id=a.dataset_id WHERE ad.active=1
                AND a.entity_type=w.entity_type AND a.entity_id=w.entity_id AND a.method=?)''')
            args.append(method)
        base = WORLD_JOIN + ' WHERE ' + ' AND '.join(where)
        with self.database.transaction() as c:
            total = c.execute('SELECT count(*)' + base, args).fetchone()[0]
            rows = c.execute('SELECT w.*,' + PROVENANCE + base +
                ' ORDER BY w.name COLLATE NOCASE,w.entity_id,d.id LIMIT ? OFFSET ?', (*args, limit, offset)).fetchall()
        return dict(records=[expand(r) for r in rows], total=total, limit=limit, offset=offset,
            truncated=offset + len(rows) < total,
            interpretation='Active source assertions, not confirmed live spawns. Level filters require the entire stored NPC level range to fit. Rank and map IDs retain source codes. Missing metadata is excluded by explicit filters. An empty search is not proof a zone or mob is absent from the game.')

    def acquisition(self, item_id=None, query='', method=None, min_level=None, max_level=None,
                    ui_map_id=None, rank=None, item_quality=None, limit=50, offset=0, zone=None,
                    entity_id=None, entity_type=None, area_id=None):
        integer(limit, 'limit', 1, 500); integer(offset, 'offset')
        where, args = world_filters(query, None, min_level, max_level, ui_map_id, rank, zone, area_id)
        if entity_id is not None:
            integer(entity_id, 'entity_id', 1); where.append('a.entity_id=?'); args.append(entity_id)
        if entity_type is not None:
            if entity_type not in ('npc','object','quest','item'): raise ValueError('entity_type must be npc, object, quest or item')
            where.append('a.entity_type=?'); args.append(entity_type)
        if item_id is not None:
            integer(item_id, 'item_id', 1); where.append('a.item_id=?'); args.append(item_id)
        if method is not None:
            if method not in METHODS: raise ValueError(f'method must be one of {METHODS}')
            where.append('a.method=?'); args.append(method)
        quality = quality_sql('a.item_id')
        if item_quality is not None:
            if item_quality not in QUALITIES: raise ValueError(f'item_quality must be one of {QUALITIES}')
            where.append(f"json_extract({quality},'$.quality')=?"); args.append(item_quality)
        base = ''' FROM acquisition_facts a JOIN research_datasets d ON d.id=a.dataset_id
            JOIN sources s ON s.id=d.source_id LEFT JOIN world_entity_facts w
            ON w.dataset_id=a.dataset_id AND w.entity_type=a.entity_type AND w.entity_id=a.entity_id
            WHERE ''' + ' AND '.join(where)
        with self.database.transaction() as c:
            total = c.execute('SELECT count(*)' + base, args).fetchone()[0]
            rows = c.execute(f'''SELECT a.*,w.name entity_name,w.attributes_json,{PROVENANCE},
                {quality} quality_json,(SELECT name FROM selected_item_names WHERE item_id=a.item_id) item_name'''
                + base + ' ORDER BY a.evidence_basis DESC,a.method,a.entity_id,a.item_id,a.id LIMIT ? OFFSET ?',
                (*args, limit, offset)).fetchall()
            coverage = [dict(r) for r in c.execute('''SELECT c.item_id,c.method,c.omitted_count,s.source_key,d.id dataset_id
                FROM acquisition_coverage c JOIN research_datasets d ON d.id=c.dataset_id
                JOIN sources s ON s.id=d.source_id WHERE d.active=1 AND c.item_id=? ORDER BY c.method''', (item_id,))] if item_id else []
        records = [expand(r) for r in rows]
        for r in records:
            r['entity_attributes'] = r.pop('attributes') or {}
            r['evidence_kind'] = 'historical' if r['evidence_basis'] == 'classic_baseline' else 'extracted'
            r['access_requirement'] = {'skinning': 'Skinning; required skill is unknown',
                'pickpocket': 'Rogue pickpocket ability', 'quest_reward': 'Quest eligibility and prerequisites',
                'object_loot': 'Object access or gathering requirements are unknown'}.get(r['method'])
            if r['method'] in ('questie_drop', 'questie_object_loot', 'container_loot'):
                r['access_requirement'] = 'Eligibility, access requirements and quantities are unknown'
        return dict(item_id=item_id, records=records, total=total, limit=limit, offset=offset,
            truncated=offset + len(rows) < total, coverage=coverage, complete_loot_table=False,
            quality_filter_scope='Quality filters use selected item_observations only. Items without a quality observation are excluded. Zero matches does not establish that no such loot exists; the acquisition index is also incomplete.',
            coverage_scope='Omitted counts are unfiltered source coverage for the requested item; cross-item coverage is not summarized.',
            interpretation='Filters apply before pagination. These are acquisition associations, not farm rankings. Unknown quality is not RARE. Check character requirements and inspect source rank before recommending combat. Historical probability, unknown quantity and asking price cannot establish measured gold/hour.')

    def travel_nodes(self, query='', ui_map_id=None, evidence_basis=None, limit=50, offset=0):
        text(query, 'query', empty=True); integer(limit, 'limit', 1, 200); integer(offset, 'offset')
        where, args = ['d.active=1'], []
        if query.strip():
            where.append('(instr(lower(coalesce(n.name,n.node_key)),lower(?))>0 OR instr(lower(coalesce(n.container_key,\'\')),lower(?))>0)')
            args.extend((query.strip(), query.strip()))
        if ui_map_id is not None:
            integer(ui_map_id, 'ui_map_id', 1); where.append('n.ui_map_id=?'); args.append(ui_map_id)
        if evidence_basis is not None:
            text(evidence_basis, 'evidence_basis'); where.append('n.evidence_basis=?'); args.append(evidence_basis)
        base = ''' FROM travel_nodes n JOIN research_datasets d ON d.id=n.dataset_id
            JOIN sources s ON s.id=d.source_id WHERE ''' + ' AND '.join(where)
        with self.database.transaction() as c:
            total = c.execute('SELECT count(*)' + base, args).fetchone()[0]
            rows = c.execute('SELECT n.*,' + PROVENANCE + base +
                ' ORDER BY coalesce(n.name,n.node_key),n.node_key LIMIT ? OFFSET ?', (*args, limit, offset)).fetchall()
        records = []
        for row in rows:
            value = dict(row); value['attributes'] = json.loads(value.pop('attributes_json')); value['limitations'] = json.loads(value.pop('limitations_json'))
            records.append(value)
        return dict(records=records,total=total,limit=limit,offset=offset,truncated=offset+len(records)<total,
            interpretation='Static route-planning nodes. Evidence basis identifies captured, estimated, unverified, or rough-map coordinates; none is a live player position.')

    def travel_edges(self, query='', method=None, faction=None, evidence_basis=None, limit=100, offset=0):
        text(query, 'query', empty=True); integer(limit, 'limit', 1, 500); integer(offset, 'offset')
        where, args = ['d.active=1'], []
        if query.strip():
            where.append('(instr(lower(e.from_node_key),lower(?))>0 OR instr(lower(e.to_node_key),lower(?))>0)')
            args.extend((query.strip(), query.strip()))
        if method is not None:
            text(method, 'method'); where.append('e.method=?'); args.append(method)
        if faction is not None:
            if faction not in ('Horde','Alliance'): raise ValueError('faction must be Horde or Alliance')
            where.append("(json_extract(e.requirements_json,'$.faction') IS NULL OR json_extract(e.requirements_json,'$.faction')=?)"); args.append(faction)
        if evidence_basis is not None:
            text(evidence_basis, 'evidence_basis'); where.append('e.evidence_basis=?'); args.append(evidence_basis)
        base = ''' FROM travel_edges e JOIN research_datasets d ON d.id=e.dataset_id
            JOIN sources s ON s.id=d.source_id
            LEFT JOIN travel_nodes fn ON fn.dataset_id=e.dataset_id AND fn.node_key=e.from_node_key
            LEFT JOIN travel_nodes tn ON tn.dataset_id=e.dataset_id AND tn.node_key=e.to_node_key
            WHERE ''' + ' AND '.join(where)
        with self.database.transaction() as c:
            total = c.execute('SELECT count(*)' + base, args).fetchone()[0]
            rows = c.execute('''SELECT e.*,fn.name from_name,tn.name to_name,''' + PROVENANCE + base + '''
                ORDER BY e.method,e.from_node_key,e.to_node_key LIMIT ? OFFSET ?''', (*args, limit, offset)).fetchall()
        records = []
        for row in rows:
            value = dict(row); value['requirements'] = json.loads(value.pop('requirements_json'))
            value['attributes'] = json.loads(value.pop('attributes_json')); value['limitations'] = json.loads(value.pop('limitations_json'))
            records.append(value)
        return dict(records=records,total=total,limit=limit,offset=offset,truncated=offset+len(records)<total,
            interpretation='Authored directed route edges. cost_seconds is a planner input and may be measured, derived, estimated, placeholder, or absent as identified by evidence_basis and source comments. It is not a promised trip time.')

    def acquisition_evidence(self, fact_id):
        integer(fact_id, 'fact_id', 1)
        with self.database.transaction() as c:
            row = c.execute(f'''SELECT a.*,w.name entity_name,w.attributes_json,{PROVENANCE},d.active,
                {quality_sql('a.item_id')} quality_json
                FROM acquisition_facts a JOIN research_datasets d ON d.id=a.dataset_id
                JOIN sources s ON s.id=d.source_id LEFT JOIN world_entity_facts w
                ON w.dataset_id=a.dataset_id AND w.entity_type=a.entity_type AND w.entity_id=a.entity_id
                WHERE a.id=?''', (fact_id,)).fetchone()
        if row is None: return None
        result = expand(row)
        result['evidence_kind'] = 'historical' if result['evidence_basis']=='classic_baseline' else 'extracted'
        result['interpretation'] = 'Exact retained acquisition assertion. Active flag distinguishes archived revisions. Quality is a separately sourced current observation, not part of the historical drop claim.'
        return result

    def scan_provenance(self, snapshot_id):
        integer(snapshot_id, 'snapshot_id', 1)
        with self.database.transaction() as c:
            row = c.execute('''SELECT sn.id,sn.captured_at,sn.raw_reference,s.source_key,
                sd.id document_id,sd.sha256,sd.body FROM snapshots sn JOIN sources s ON s.id=sn.source_id
                LEFT JOIN source_documents sd ON sd.source_id=sn.source_id AND sd.url=sn.raw_reference
                WHERE sn.id=? ORDER BY sd.id DESC LIMIT 1''', (snapshot_id,)).fetchone()
        if row is None: return None
        result = dict(row); body = result.pop('body')
        result['source_header'] = None
        if body is not None and result['source_key']=='local-ahledger':
            raw = json.loads(bytes(body))
            result['source_header'] = {k:raw.get(k) for k in ('realm','region','faction','addon','build','ts','full','count')}
        result['interpretation'] = 'Original cached scan header, not a public-market mapping. Literal unknown region remains unknown. full is an addon claim, not verified completeness. Read document_id for the retained source body.'
        return result

    def scan_summary(self, market_key='wow-forever', snapshot_id=None, sort_by='listed_units', limit=25, offset=0):
        text(market_key, 'market_key'); integer(limit, 'limit', 1, 100); integer(offset, 'offset')
        if snapshot_id is not None: integer(snapshot_id, 'snapshot_id', 1)
        if sort_by not in ('listed_units', 'listing_count', 'listed_buyout_copper', 'min_unit_buyout_copper'):
            raise ValueError('sort_by must be listed_units, listing_count, listed_buyout_copper or min_unit_buyout_copper')
        with self.database.transaction() as c:
            scan = c.execute('''SELECT sn.*,m.market_key,s.source_key FROM snapshots sn
                JOIN markets m ON m.id=sn.market_id JOIN sources s ON s.id=sn.source_id
                WHERE m.market_key=? AND s.source_key='local-ahledger' AND (? IS NULL OR sn.id=?)
                ORDER BY sn.captured_at DESC,sn.id DESC LIMIT 1''', (market_key, snapshot_id, snapshot_id)).fetchone()
            if scan is None:
                return dict(snapshot=None, records=[], total=0, data_available=False, market_key=market_key,
                    interpretation='No local AHledger listing scan matches. Public markets supply price history instead.')
            totals = dict(c.execute('''SELECT count(*) listing_count,count(DISTINCT item_id) item_count,
                coalesce(sum(quantity),0) listed_units,coalesce(sum(buyout_copper=0),0) bid_only_listings
                FROM auction_rows WHERE snapshot_id=?''', (scan['id'],)).fetchone())
            rows = c.execute(f'''WITH grouped AS (SELECT item_id,count(*) listing_count,sum(quantity) listed_units,
                sum(CASE WHEN buyout_copper>0 THEN quantity ELSE 0 END) buyout_units,
                sum(buyout_copper=0) bid_only_listings,sum(buyout_copper) listed_buyout_copper,
                min(CASE WHEN buyout_copper>0 THEN 1.0*buyout_copper/quantity END) min_unit_buyout_copper
                FROM auction_rows WHERE snapshot_id=? GROUP BY item_id)
                SELECT g.*,(SELECT name FROM selected_item_names WHERE item_id=g.item_id) item_name,
                {quality_sql('g.item_id')} quality_json FROM grouped g
                ORDER BY {sort_by} DESC,g.item_id LIMIT ? OFFSET ?''', (scan['id'], limit, offset)).fetchall()
        return dict(snapshot=dict(scan), totals=totals, records=[expand(r) for r in rows],
            total=totals['item_count'], limit=limit, offset=offset, sort_by=sort_by, data_available=True,
            queried_at=datetime.now(timezone.utc).isoformat(),
            limitations=['Sorted asking supply, not profitable opportunities or sales. Listed buyout value sums whole-stack asks, not unit prices or realizable revenue.',
                'Bid-only rows have no buyout. Item rarity is sourced separately; unknown remains unknown.',
                'source_complete_claim is the addon claim; is_complete is independent verification. These need not agree.'])
