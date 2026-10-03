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
            if isinstance(row.get(key), dict): row[key].pop('packed_fields', None)
        for key in ('zone_label_evidence', 'rank_label_evidence'):
            if key in row: row[key.replace('_evidence', '_evidence_ref')] = reference(row.pop(key))
        quality = row.get('quality_evidence')
        if quality:
            row['quality_evidence'] = {'quality': quality['quality'],
                'evidence_ref': reference({k:v for k,v in quality.items() if k != 'quality'})}
        result.append(row)
    return result, sources


def discovery_page(page, detail='compact'):
    result = deepcopy(page)
    if detail == 'compact':
        result['records'], result['evidence'] = compact_records(result['records'])
        result['detail_help'] = ('Shared provenance is in evidence, indexed by evidence_ref. '
            'Use get_world_entity(entity_type,entity_id) for NPC details or '
            'get_acquisition_evidence(fact_id=id) for an exact acquisition assertion. '
            'detail=full retains raw fields, with the same response byte budget.')
    result['response_format'] = detail
    result['requested_limit'] = result.get('limit')
    result['returned_count'] = len(result['records'])
    result['next_offset'] = None
    result['response_limited'] = False
    result['pagination_note'] = 'Read next_offset when present; returned_count may be smaller than requested_limit. A partial page cannot establish absence.'
    while size(result) > MAX_RESPONSE_BYTES - 1500 and result['records']:
        result['records'].pop()
        result['response_limited'] = True
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
    value = with_money(value)
    if name in ('search_world_entities','search_acquisition_sources','get_item_acquisition'):
        value = discovery_page(value, detail)
    if isinstance(value, dict):
        value['currency_units'] = 'Raw money values are copper. 1g = 10000c; 1s = 100c. money_display is computed, rounded to 0.01c for fractional unit prices. Asking prices do not establish sale value.'
    if size(value) > MAX_RESPONSE_BYTES:
        raise ValueError('Response exceeds the 32 KB agent budget. Reduce limit (start with 5), narrow filters, or use compact detail. For item research use the default summary and its focused follow_up tools. No evidence has been deleted.')
    return value


def item_summary(value):
    if value is None: return None
    keys = ('item_id','name','quality','item_class','item_subclass','item_level','required_level',
            'vendor_sell_copper','source_key','retrieved_at','game_build','confidence',
            'evidence_kind','raw_reference','identity_selection_policy','listing_markets')
    result = {k:value[k] for k in keys if k in value}
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
