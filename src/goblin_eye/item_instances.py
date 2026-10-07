"""Observed full-link stat tables, never a guessed universal suffix catalog."""
import hashlib
import json
import math
import re
from datetime import datetime, timezone
from goblin_eye.validation import integer

# Names used by the installed Alts Forever/Forever Guide/ProfessionDB code.
STAT_KEYS = {
    'ITEM_MOD_STRENGTH_SHORT':'strength', 'ITEM_MOD_AGILITY_SHORT':'agility',
    'ITEM_MOD_STAMINA_SHORT':'stamina', 'ITEM_MOD_INTELLECT_SHORT':'intellect',
    'ITEM_MOD_SPIRIT_SHORT':'spirit', 'ITEM_MOD_SPELL_POWER_SHORT':'spell_power',
    'ITEM_MOD_SPELL_DAMAGE_DONE_SHORT':'spell_damage', 'ITEM_MOD_SPELL_HEALING_DONE_SHORT':'healing_power',
    'ITEM_MOD_ATTACK_POWER_SHORT':'attack_power', 'ITEM_MOD_RANGED_ATTACK_POWER_SHORT':'ranged_attack_power',
    'ITEM_MOD_MANA_REGENERATION_SHORT':'mana_per_5_seconds', 'ITEM_MOD_POWER_REGEN0_SHORT':'mana_per_5_seconds',
    'ITEM_MOD_HIT_SPELL_RATING_SHORT':'spell_hit_rating', 'ITEM_MOD_CRIT_SPELL_RATING_SHORT':'spell_crit_rating',
    'ITEM_MOD_HIT_RATING_SHORT':'hit_rating', 'ITEM_MOD_CRIT_RATING_SHORT':'crit_rating',
    'ITEM_MOD_DEFENSE_SKILL_RATING_SHORT':'defense_rating', 'ITEM_MOD_DODGE_RATING_SHORT':'dodge_rating',
    'ITEM_MOD_PARRY_RATING_SHORT':'parry_rating', 'ITEM_MOD_BLOCK_RATING_SHORT':'block_rating',
    'ITEM_MOD_BLOCK_VALUE_SHORT':'block_value', 'RESISTANCE0_NAME':'armor',
    'ITEM_MOD_DAMAGE_PER_SECOND_SHORT':'weapon_dps',
}

def item_string(link):
    if not isinstance(link, str) or len(link) > 2048:
        raise ValueError('Expected a bounded full item link or item string')
    match = re.search(r'\|H(item:[1-9]\d*:[^|\r\n]*)\|h', link)
    value = match[1] if match else link
    if not re.fullmatch(r'item:[1-9]\d*:[0-9A-Za-z:+-]*', value):
        raise ValueError('Invalid item string')
    return value

def normalize_stats(raw):
    # Preserve aliases separately in raw data; don't sum potentially duplicate API keys.
    result, conflicts = {}, set()
    for key, value in raw.items():
        if key in STAT_KEYS:
            name = STAT_KEYS[key]
            if name in conflicts: continue
            if name not in result: result[name] = value
            elif result[name] != value:
                result.pop(name, None); conflicts.add(name)
    return result

def validate_export(root):
    export = root.get('goblinEye')
    if export is None: return []
    if not isinstance(export,dict) or type(export.get('version')) is not int or export['version'] != 1 or not isinstance(export.get('items'),dict):
        raise ValueError('Unsupported Goblin Eye Alts export')
    if len(export['items']) > 1000: raise ValueError('Too many exported item variants')
    rows = []
    for key, record in export['items'].items():
        if not isinstance(record,dict) or item_string(key) != key or item_string(record.get('link')) != key:
            raise ValueError('Variant key/link mismatch')
        item_id = int(key.split(':')[1])
        if type(record.get('itemId')) is not int or record['itemId'] != item_id: raise ValueError('Variant item ID mismatch')
        integer(record.get('capturedAt'),'item capture time',1,253402300799)
        stats = record.get('stats')
        if not isinstance(stats,dict) or len(stats)>100: raise ValueError('Invalid item stat table')
        for name, amount in stats.items():
            if (not isinstance(name,str) or not re.fullmatch(r'[A-Z][A-Z0-9_]{0,99}',name)
                or type(amount) not in (int,float) or not math.isfinite(amount) or abs(amount)>100000000):
                raise ValueError('Invalid numeric item stat')
        lines = record.get('tooltip',{})
        if not isinstance(lines,dict) or set(lines)!=set(range(1,len(lines)+1)) or len(lines)>40:
            raise ValueError('Invalid item tooltip lines')
        if any(not isinstance(v,str) or len(v)>400 for v in lines.values()): raise ValueError('Invalid tooltip text')
        if sum(len(v.encode('utf-8')) for v in lines.values())>8000: raise ValueError('Item tooltip exceeds export budget')
        build, locale = record.get('build'), record.get('locale')
        if not isinstance(build,str) or len(build)>100 or not isinstance(locale,str) or len(locale)>20:
            raise ValueError('Missing item build/locale')
        rows.append((key,record))
    return rows

def import_instances(connection, namespace, rows, now, reference):
    count = 0
    for key, record in rows:
        body = json.dumps(record, sort_keys=True, ensure_ascii=False)
        digest = hashlib.sha256(body.encode()).hexdigest()
        captured = datetime.fromtimestamp(record['capturedAt'],timezone.utc).isoformat()
        count += connection.execute('''INSERT OR IGNORE INTO item_instance_facts
            (namespace,item_id,item_string,captured_at,imported_at,game_build,sha256,attributes_json,raw_reference)
            VALUES (?,?,?,?,?,?,?,?,?)''', (namespace,record['itemId'],key,captured,now,record['build'],digest,body,
            reference+'#AltsForeverDB/goblinEye/items/'+key)).rowcount
    return count

class ItemInstances:
    def __init__(self,database): self.database=database

    def page(self,item_id,limit=10,offset=0,item_link=None,namespace=None):
        integer(item_id,'item_id',1); integer(limit,'limit',1,100); integer(offset,'offset')
        where,args=['item_id=?'],[item_id]
        if item_link is not None:
            key=item_string(item_link)
            if int(key.split(':')[1]) != item_id: raise ValueError('item_link does not match item_id')
            where.append('item_string=?'); args.append(key)
        if namespace is not None: where.append('namespace=?'); args.append(namespace)
        clause=' AND '.join(where)
        base=''' FROM (SELECT *,ROW_NUMBER() OVER(PARTITION BY namespace,item_string,game_build
            ORDER BY captured_at DESC,id DESC) latest FROM item_instance_facts WHERE '''+clause+''') WHERE latest=1'''
        with self.database.transaction() as c:
            total=c.execute('SELECT count(*)'+base,args).fetchone()[0]
            rows=c.execute('SELECT *'+base+' ORDER BY captured_at DESC,id DESC LIMIT ? OFFSET ?',(*args,limit,offset)).fetchall()
        records=[]
        for row in rows:
            raw=json.loads(row['attributes_json'])
            records.append({'id':row['id'],'item_id':row['item_id'],'item_string':row['item_string'],
                'item_link':raw['link'],'stats_raw':raw['stats'],'stats':normalize_stats(raw['stats']),
                'tooltip':[raw['tooltip'][k] for k in sorted(raw.get('tooltip',{}),key=int)],'locale':raw['locale'],
                'captured_at':row['captured_at'],'imported_at':row['imported_at'],'game_build':row['game_build'],
                'source_key':'local-alts-forever','raw_reference':row['raw_reference'],
                'stats_scope':'client API reported for this exact full link',
                'effect_coverage':'tooltip_recorded' if raw.get('tooltip') else 'not_captured',
                'interpretation':'API stat rows do not establish complete proc/effect coverage. Enchant evidence is separate; do not add it again without verifying API semantics.'})
        return dict(records=records,total=total,limit=limit,offset=offset,
            coverage='observed_variants_only',interpretation='Unseen suffixes remain unknown. Never extrapolate a captured bonus to other items or builds.')
