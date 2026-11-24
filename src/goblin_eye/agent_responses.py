"""Small agent-facing projections. Stored facts and HTTP detail remain unchanged."""
from __future__ import annotations

import json
from copy import deepcopy
from decimal import Decimal, ROUND_HALF_UP


MAX_RESPONSE_BYTES = 32000
SOURCE_FIELDS = ('source_key', 'source_name', 'source_url', 'source_version', 'retrieved_at',
                 'game_build', 'content_phase', 'confidence', 'evidence_kind',
                 'dataset_sha256', 'limitations', 'trust_rank')


def size(value):
    return len(json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf-8'))


def compact_records(records):
    sources, lookup, result = {}, {}, []

    def reference(evidence):
        key = json.dumps(evidence, sort_keys=True)
        if key not in lookup:
            ref = 'e' + str(len(lookup) + 1)
            lookup[key] = ref
            sources[ref] = evidence
        return lookup[key]

    for original in records:
        row = deepcopy(original)
        evidence = {key: row.pop(key) for key in SOURCE_FIELDS if key in row}
        if evidence:
            row['evidence_ref'] = reference(evidence)
            # Keep the most useful labels beside the fact, including historical status.
            for key in ('source_key', 'retrieved_at', 'evidence_kind'):
                if key in evidence: row[key] = evidence[key]
        for key in ('attributes', 'entity_attributes'):
            if isinstance(row.get(key), dict):
                row[key].pop('packed_fields', None)
                for coordinates in ('spawns_by_area','waypoints_by_area'):
                    if coordinates in row[key]:
                        data=row[key].pop(coordinates)
                        row[key][coordinates+'_summary']={str(area):len(points) for area,points in data.items()}
                        row[key]['coordinate_details_omitted']=True
        for key in ('zone_label_evidence', 'rank_label_evidence'):
            if key in row: row[key.replace('_evidence', '_evidence_ref')] = reference(row.pop(key))
        quality = row.get('quality_evidence')
        if quality:
            row['quality_evidence'] = {'quality': quality['quality'],
                'evidence_ref': reference({k:v for k,v in quality.items() if k != 'quality'})}
        result.append(row)
    return result, sources

def prune_evidence(result):
    refs=set()
    def visit(value):
        if isinstance(value,dict):
            for key,child in value.items():
                if key.endswith('evidence_ref') and isinstance(child,str): refs.add(child)
                else: visit(child)
        elif isinstance(value,list):
            for child in value: visit(child)
    visit(result.get('records',[]))
    result['evidence']={k:v for k,v in result.get('evidence',{}).items() if k in refs}


def discovery_page(page, detail='compact'):
    result = deepcopy(page)
    if detail == 'compact':
        result['records'], result['evidence'] = compact_records(result['records'])
        result['detail_help'] = ('Shared provenance is in evidence, indexed by evidence_ref. '
            'Use get_world_entity(entity_type,entity_id) for NPC details or '
            'get_acquisition_evidence(fact_id=id) for an exact acquisition assertion. '
            'Coordinate arrays are summarized; get_world_entity gives focused coordinate samples and cached source documents retain complete records. '
            'For item variants use get_item_variants(item_id,item_link); for quests use get_character_quests(snapshot_id). '
            'detail=full retains raw fields, with the same response byte budget.')
        prune_evidence(result)
    result['response_format'] = detail
    result['requested_limit'] = result.get('limit')
    result['returned_count'] = len(result['records'])
    result['next_offset'] = None
    result['response_limited'] = False
    result['pagination_note'] = 'Read next_offset when present; returned_count may be smaller than requested_limit. A partial page cannot establish absence.'
    while size(result) > MAX_RESPONSE_BYTES - 1500 and result['records']:
        result['records'].pop()
        result['response_limited'] = True
        if detail=='compact': prune_evidence(result)
    if not result['records'] and page['records']:
        raise ValueError('One record exceeds the agent response budget. Use compact detail or a focused entity/item query.')
    count = len(result['records'])
    result['returned_count'] = count
    result['truncated'] = result.get('offset', 0) + count < result['total']
    if result['truncated']: result['next_offset'] = result.get('offset', 0) + count
    return result


def money_label(value):
    amount = Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    sign = '-' if amount < 0 else ''
    amount = abs(amount)
    gold = int(amount // 10000)
    silver = int((amount % 10000) // 100)
    copper = format(amount % 100, 'f').rstrip('0').rstrip('.') if amount % 1 else str(int(amount % 100))
    return f'{sign}{gold}g {silver}s {copper}c'


def with_money(value):
    if isinstance(value, list): return [with_money(v) for v in value]
    if not isinstance(value, dict): return value
    result = {k:with_money(v) for k,v in value.items()}
    money = {k:money_label(v) for k,v in value.items() if
        (k.endswith('_copper') or k in ('provider_median_7d','provider_median_30d','provider_low_30d','provider_high_30d'))
        and type(v) in (int, float)}
    if money: result['money_display'] = money
    return result


def prepare_response(name, value, detail='compact'):
    if name == 'get_item_research' and detail != 'full': value = item_summary(value)
    if name == 'get_character_snapshot' and isinstance(value, dict):
        value = deepcopy(value)
        # The same raw character was repeated at both roots. Keep the readable
        # character and shared payload metadata; HTTP detail retains the original.
        if isinstance(value.get('source_payload'), dict) and 'character' in value:
            value['source_payload'].pop('character', None)
            if isinstance(value['character'], dict):
                value['character'].pop('gear', None)  # Links and empty slots are in items/equipment_slots.
        # Inventory rows already occur in items. Share the identical instance
        # limitation once, so nineteen stat-bearing slots fit the tool budget.
        if any(item.get('location') != 'equipped' for item in value.get('items', [])):
            value.pop('inventory', None)
        instance_notes = set()
        for item in value.get('items', []):
            if item.get('instance_stats_note'):
                instance_notes.add(item.pop('instance_stats_note'))
        if instance_notes:
            value['equipment_interpretation'] = sorted(instance_notes)
        if detail=='compact':
            counts={}
            for item in value.get('items',[]):
                if item['location']!='equipped': counts[item['location']]=counts.get(item['location'],0)+1
            value['inventory_summary']={'record_counts_by_location':counts,
                'follow_up':'get_character_inventory(snapshot_id,limit=20,offset=next_offset)'}
            value['items']=[i for i in value.get('items',[]) if i['location']=='equipped']
            character=value.get('character',{})
            for field in ('bags','bank','mail','layout','recipes','crafts','duraSlots'):
                character.pop(field,None)
            character.pop('goblinEyeGear',None)
            character.pop('goblinEyeCharacter',None)
            character.pop('goblinEyeQuests',None)
            character.pop('goblinEyeQuestLog',None)
            character.pop('goblinEyeLocation',None)
            value.get('source_payload',{}).pop('recipeInfo',None)
            value['instance_evidence']={}
            for item in value['items']:
                for props in item.get('item_properties',{}).values():
                    for field in ('stats_raw','flags','catalog_build','name','new_in_forever','changed_from_classic','stats_scope'):
                        props.pop(field,None)
                instance=item.get('instance_stats')
                if instance:
                    ref='instance-'+str(instance['id'])
                    value['instance_evidence'][ref]={k:instance[k] for k in
                        ('source_key','captured_at','imported_at','game_build','raw_reference','stats_scope','effect_coverage','interpretation')}
                    item['instance_stats']={k:instance[k] for k in ('id','stats')}
                    item['instance_stats']['evidence_ref']=ref
                    item['instance_stats']['tooltip_available']=bool(instance['tooltip'])
                enchant=item.get('enchant_evidence')
                if enchant:
                    # Numeric assertions are retained; lengthy alternative recipe
                    # names remain in the focused enchant evidence tool.
                    enchant['application_count']=len(enchant['applications'])
                    enchant['applications_truncated']=len(enchant['applications'])>10
                    enchant['applications']=[{k:v for k,v in app.items() if k not in ('name','stats_raw','retrieved_at')}
                        for app in enchant['applications'][:10]]
                    enchant['follow_up']='get_enchant_evidence(enchant_id)'
            value['response_format']='compact_equipment'
            value['equipped_total']=len(value['items'])
            value['equipment_next_offset']=None
            value['equipment_follow_up']='get_character_equipment(snapshot_id,limit=10,offset=equipment_next_offset) for omitted equipment; get_item_variants for raw stats and full tooltip.'
            while size(value)>MAX_RESPONSE_BYTES-2000 and value['items']:
                value['items'].pop()
                refs={i.get('instance_stats',{}).get('evidence_ref') for i in value['items']}
                value['instance_evidence']={k:v for k,v in value['instance_evidence'].items() if k in refs}
                value['equipment_next_offset']=len(value['items'])
    if name=='get_world_entity' and isinstance(value,dict) and detail=='compact':
        value=deepcopy(value)
        for fact in value.get('assertions',[]):
            attrs=fact.get('attributes',{})
            attrs.pop('packed_fields',None)
            for key in ('spawns_by_area','waypoints_by_area'):
                if key in attrs:
                    raw=attrs.pop(key)
                    attrs[key+'_sample']={k:v[:2] if key=='spawns_by_area' else [p[:2] for p in v[:1]] for k,v in list(raw.items())[:10]}
                    attrs[key+'_group_counts']={k:len(v) for k,v in raw.items()}
                    attrs['coordinate_details_omitted']=True
        value['detail_help']='Coordinate samples are incomplete. Read the cached source document for full arrays; samples cannot establish spawn density.'
    value = with_money(value)
    if name in ('search_world_entities','search_acquisition_sources','get_item_acquisition','get_research_datasets','search_evidence','get_item_variants','get_character_quests','get_character_active_quests','get_character_inventory','get_character_equipment'):
        value = discovery_page(value, detail)
    if name=='get_item_research' and detail=='full' and size(value)>MAX_RESPONSE_BYTES-1500:
        value=item_summary(value)
        value.update(requested_detail='full',response_limited=True,
            detail_help='Full item aggregation exceeds the tool budget. This is a summary, not missing evidence; use the focused follow_up tools or /api/items/{item_id}.')
    if isinstance(value, dict):
        value['currency_units'] = 'Raw money values are copper. 1g = 10000c; 1s = 100c. money_display is computed, rounded to 0.01c for fractional unit prices. Asking prices do not establish sale value.'
    if size(value) > MAX_RESPONSE_BYTES:
        raise ValueError('Response exceeds the 32 KB agent budget. Reduce limit (start with 5), narrow filters, or use compact detail. For item research use the default summary and its focused follow_up tools. No evidence has been deleted.')
    return value


def item_summary(value):
    if value is None: return None
    keys = ('item_id','name','quality','item_class','item_subclass','item_level','required_level',
            'vendor_sell_copper','source_key','retrieved_at','game_build','confidence',
            'evidence_kind','raw_reference','identity_selection_policy','listing_markets','item_properties')
    result = {k:value[k] for k in keys if k in value}
    result=deepcopy(result)
    properties=result.get('item_properties',{})
    observed=properties.get('observed_variants')
    if observed:
        observed['records']=[{k:v for k,v in r.items() if k not in ('tooltip','stats_raw')} for r in observed['records']]
        observed['returned_count']=len(observed['records'])
        observed['next_offset']=len(observed['records']) if observed['total']>len(observed['records']) else None
        observed['follow_up']='get_item_variants(item_id,limit=10,offset=next_offset), optionally item_link for an exact variant'
    result['response_format'] = 'summary'
    acquisition = value.get('acquisition', {})
    result['acquisition'] = {k:acquisition[k] for k in ('total','coverage','complete_loot_table','interpretation') if k in acquisition}
    result['recipes'] = {}
    for relation, rows in value.get('recipe_relationships', {}).items():
        result['recipes'][relation] = {'total':len(rows), 'shown':min(5,len(rows)),
            'truncated':len(rows)>5, 'records':[{k:r.get(k) for k in
                ('id','spell_id','name','profession','output_item_id','output_quantity','source_key','game_build')} for r in rows[:5]]}
    identities = value.get('identity_observations', [])
    result['identity_observations'] = {'total':len(identities), 'records':[
        {k:r.get(k) for k in ('item_id','name','quality','source_key','retrieved_at','game_build','confidence')}
        for r in identities[:5]], 'truncated':len(identities)>5}
    result['follow_up'] = {
        'local_listings':'get_market_depth(item_id); a missing summary price is not evidence of no listings.',
        'local_timeline':'get_scan_history(item_id)',
        'public_prices':'get_price_history(item_id, market_key=explicit forever.* key, source_key=ahledger)',
        'acquisition':'get_item_acquisition(item_id, filters, limit=10, offset=next_offset)',
        'recipes':'get_recipe_evidence(fact_id=id) for listed recipes; full item detail is also available at /api/items/{item_id}.',
        'identity_conflicts':'get_fact_assertions(entity_type=item_identity, entity_key=item ID as string)',
    }
    return result
