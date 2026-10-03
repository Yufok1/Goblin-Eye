"""Retain competing generic assertions; legacy tables are selected projections."""
import hashlib
import json
from goblin_eye.validation import rate, timestamp, text

SELECTION_POLICY = 'Lowest source trust rank, newest retrieval, highest confidence, then assertion ID. Build alternatives remain inspectable; this is not proof of current-build applicability.'
NON_CONFLICT_FIELDS = ('provenance','raw_reference','source_record')

IDENTITY_FIELDS = ('item_id', 'name', 'quality', 'item_class', 'item_subclass',
                   'item_level', 'required_level', 'vendor_sell_copper', 'icon_url')


def identity_facts(payload):
    """Compare identity facts, including legacy wrapped AHledger assertions."""
    if 'source_record' in payload:
        raw = payload['source_record']
        aliases = dict(item_id='id', item_class='itemClass', item_subclass='itemSubclass',
                       item_level='level', required_level='requiredLevel',
                       vendor_sell_copper='vendorSell', icon_url='icon')
        return {key: raw.get(aliases.get(key, key)) for key in IDENTITY_FIELDS}
    return {key: payload.get(key) for key in IDENTITY_FIELDS}

def retain(c, entity_type, entity_key, source_id, retrieved_at, confidence, payload, game_build=None):
    timestamp(retrieved_at);rate(confidence,'confidence');text(entity_type,'entity_type');text(str(entity_key),'entity_key')
    encoded=json.dumps(payload,sort_keys=True,separators=(',',':'),allow_nan=False)
    identity = json.dumps({'facts': identity_facts(payload), 'game_build': game_build}, sort_keys=True, allow_nan=False) if entity_type == 'item_identity' else encoded
    digest=hashlib.sha256(identity.encode()).hexdigest()
    existing=c.execute('SELECT id FROM evidence_assertions WHERE entity_type=? AND entity_key=? AND source_id=? AND sha256=?',
                       (entity_type,str(entity_key),source_id,digest)).fetchone()
    if existing:
        return bool(c.execute('SELECT selected FROM evidence_assertions WHERE id=?',(existing[0],)).fetchone()[0])
    new=c.execute('''INSERT INTO evidence_assertions(entity_type,entity_key,source_id,retrieved_at,game_build,confidence,payload_json,sha256)
                    VALUES(?,?,?,?,?,?,?,?)''',(entity_type,str(entity_key),source_id,retrieved_at,game_build,confidence,encoded,digest)).lastrowid
    candidates=c.execute('''SELECT a.*,s.trust_rank FROM evidence_assertions a JOIN sources s ON s.id=a.source_id
        WHERE entity_type=? AND entity_key=? ORDER BY s.trust_rank,a.retrieved_at DESC,a.confidence DESC,a.id DESC''',
        (entity_type,str(entity_key))).fetchall()
    chosen=candidates[0]
    c.execute('UPDATE evidence_assertions SET selected=(id=?) WHERE entity_type=? AND entity_key=?',(chosen['id'],entity_type,str(entity_key)))
    for other in candidates:
        if other['id']==new: continue
        old=json.loads(other['payload_json'])
        incoming = payload
        if entity_type == 'item_identity':
            old, incoming = identity_facts(old), identity_facts(payload)
        fields={k:{'previous':old.get(k),'incoming':incoming.get(k)} for k in old.keys()|incoming.keys()
                if k not in NON_CONFLICT_FIELDS and old.get(k)!=incoming.get(k)
                and (entity_type != 'item_identity' or (old.get(k) is not None and incoming.get(k) is not None))}
        if not fields: continue
        c.execute('INSERT OR IGNORE INTO assertion_conflicts(left_id,right_id,fields_json) VALUES(?,?,?)',
                  (other['id'],new,json.dumps(fields,sort_keys=True)))
        for field,values in fields.items():
            incoming_preferred=chosen['id']==new
            c.execute('''INSERT INTO fact_conflicts(entity_type,entity_key,field_name,preferred_source_id,
                conflicting_source_id,preferred_value,conflicting_value,detected_at,resolution) VALUES(?,?,?,?,?,?,?,?,?)''',
                (entity_type,str(entity_key),field,source_id if incoming_preferred else other['source_id'],
                 other['source_id'] if incoming_preferred else source_id,
                 json.dumps(values['incoming'] if incoming_preferred else values['previous']),
                 json.dumps(values['previous'] if incoming_preferred else values['incoming']),retrieved_at,
                 'Retained alternatives; consult evidence_assertions for current selection.'))
    return chosen['id']==new

def get_assertions(database,entity_type,entity_key,limit=50,offset=0):
    from goblin_eye.validation import integer
    text(entity_type,'entity_type');text(str(entity_key),'entity_key');integer(limit,'limit',1,200);integer(offset,'offset')
    with database.transaction() as c:
        total=c.execute('SELECT count(*) FROM evidence_assertions WHERE entity_type=? AND entity_key=?',(entity_type,str(entity_key))).fetchone()[0]
        rows=c.execute('''SELECT a.*,s.source_key,s.trust_rank FROM evidence_assertions a JOIN sources s ON s.id=a.source_id
            WHERE entity_type=? AND entity_key=? ORDER BY selected DESC,retrieved_at DESC,id DESC LIMIT ? OFFSET ?''',
            (entity_type,str(entity_key),limit,offset)).fetchall()
        records=[]
        for row in rows:
            r=dict(row);r['payload']=json.loads(r.pop('payload_json'));records.append(r)
    return dict(records=records,total=total,limit=limit,offset=offset,selection_policy=SELECTION_POLICY)
