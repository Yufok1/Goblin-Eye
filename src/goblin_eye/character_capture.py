"""Validate and expose passive, timestamped Alts character-sheet observations."""
import math
from datetime import datetime, timezone

STATS = {'max_health','max_mana','strength','agility','stamina','intellect','spirit','armor',
    'healing_power','spell_hit_modifier_percent','spell_hit_rating_bonus_percent','spell_penetration',
    'mana_regen_per_second','mana_regen_casting_per_second'} | {
    school+suffix for school in ('holy','fire','nature','frost','shadow','arcane')
    for suffix in ('_damage','_crit_percent')}
REQUIRED_STATS = {'max_health','max_mana','strength','agility','stamina','intellect','spirit'}

def stamp(value):
    if type(value) is not int or not 0 < value <= 253402300799:
        raise ValueError('Invalid character observation time')
    return datetime.fromtimestamp(value, timezone.utc).isoformat()

def _id(value):
    if type(value) is not int or not 0 < value < 100000000:
        raise ValueError('Invalid character observation ID')

def _array(value, maximum):
    if not isinstance(value,dict) or len(value)>maximum or set(value)!=set(range(1,len(value)+1)):
        raise ValueError('Invalid character observation array')
    return list(value.values())

def validate_character_capture(char):
    capture = char.get('goblinEyeCharacter')
    if capture is not None:
        if not isinstance(capture,dict) or type(capture.get('version')) is not int or capture['version']!=1:
            raise ValueError('Unsupported character sheet export')
        stamp(capture.get('capturedAt'))
        for key in ('build','locale','race','realm'):
            value=capture.get(key)
            if value is not None and (not isinstance(value,str) or len(value)>200):
                raise ValueError('Invalid character identity metadata')
        stats=capture.get('stats')
        if not isinstance(stats,dict) or set(stats)-STATS:
            raise ValueError('Invalid character sheet stats')
        if any(type(v) not in (int,float) or not math.isfinite(v) or abs(v)>100000000 for v in stats.values()):
            raise ValueError('Invalid numeric character stat')
        talents=capture.get('talents')
        if not isinstance(talents,dict) or talents.get('status') not in ('recorded','partial','not_recorded'):
            raise ValueError('Invalid talent capture')
        if talents.get('configID') is not None: _id(talents['configID'])
        for node in _array(talents.get('nodes'),128):
            if not isinstance(node,dict): raise ValueError('Invalid talent row')
            for key in ('nodeID','treeID','rank'): _id(node.get(key))
            for key in ('entryID','spellID'):
                if node.get(key) is not None: _id(node[key])
            if node.get('name') is not None and (not isinstance(node['name'],str) or len(node['name'])>200):
                raise ValueError('Invalid talent name')
        buffs=capture.get('buffs')
        if not isinstance(buffs,dict) or buffs.get('status') not in ('recorded','partial','not_recorded'):
            raise ValueError('Invalid buff capture')
        for buff in _array(buffs.get('records'),40):
            if not isinstance(buff,dict): raise ValueError('Invalid buff row')
            _id(buff.get('spellID'))
            if buff.get('applications') is not None and (type(buff['applications']) is not int or not 0<=buff['applications']<=100000000):
                raise ValueError('Invalid buff stacks')
            if buff.get('name') is not None and (not isinstance(buff['name'],str) or len(buff['name'])>200):
                raise ValueError('Invalid buff name')
    quests=char.get('goblinEyeQuests')
    if quests is not None:
        if not isinstance(quests,dict) or type(quests.get('version')) is not int or quests['version']!=1:
            raise ValueError('Unsupported completed quest export')
        stamp(quests.get('capturedAt'))
        complete=quests.get('completed')
        if not isinstance(complete,dict) or len(complete)>100000:
            raise ValueError('Invalid completed quest snapshot')
        for key,value in complete.items():
            _id(key)
            if value is not True: raise ValueError('Invalid completed quest flag')

def sheet(char, reference, talent_limit=20, talent_offset=0):
    capture=char.get('goblinEyeCharacter')
    if not capture:
        return {'status':'not_recorded','reason':'No Alts character-sheet observation has been saved yet.'}
    nodes=[capture['talents']['nodes'][k] for k in sorted(capture['talents']['nodes'],key=int)]
    missing=sorted(REQUIRED_STATS-set(capture['stats']))
    return {'status':'partial' if missing else 'recorded', 'stats':capture['stats'], 'missing_fields':missing,
        'captured_at':stamp(capture['capturedAt']), 'game_build':capture.get('build'),
        'source_key':'local-alts-forever','raw_reference':reference+'/goblinEyeCharacter',
        'talents':{'status':capture['talents']['status'],'records':nodes[talent_offset:talent_offset+talent_limit],
            'total':len(nodes),'offset':talent_offset,'limit':talent_limit,
            'next_offset':talent_offset+talent_limit if talent_offset+talent_limit<len(nodes) else None},
        'buffs':{'status':capture['buffs']['status'],
            'records':[capture['buffs']['records'][k] for k in sorted(capture['buffs']['records'],key=int)]},
        'interpretation':'Out-of-combat character-sheet values at capture time, including current effects where the API includes them. Max health/mana are capacities, not combat telemetry. School damage and crit are separate; hit modifier and rating contribution are not a verified total hit chance. Never add item bonuses to these totals again. Talent spell IDs/ranks do not establish DoT coefficients.'}

COMPARISON_POLICY = {
    'delta_rule':'Subtract only the same normalized stat key at comparable scope/build. Missing keys are unknown, not zero.',
    'distinct_keys':['shadow_damage','shadow_resistance','spell_power','spell_damage','healing_power'],
    'equivalence_verified':False,
    'selection':'Current-build exact-link observations resolve equipped totals; static catalog conflicts remain separate source assertions.',
    'suffix_coverage':'Encountered full-link variants only. No installed complete modern suffix catalog; no numeric family extrapolation.',
}
