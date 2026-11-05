"""Read static item properties for existing character and item tools."""
from __future__ import annotations
import json


class ItemProperties:
    def __init__(self, database):
        self.database = database

    def get_many(self, ids):
        ids = sorted(set(ids))
        if not ids:
            return {}, {}
        with self.database.transaction() as conn:
            rows = conn.execute("""SELECT p.*,d.source_version,d.retrieved_at,d.sha256,d.limitations_json,s.source_key,s.url
                FROM item_property_facts p JOIN research_datasets d ON d.id=p.dataset_id JOIN sources s ON s.id=d.source_id
                WHERE d.active=1 AND p.item_id IN (""" + ','.join('?' for _ in ids) + ") ORDER BY p.item_id,d.retrieved_at DESC,p.variant",ids).fetchall()
        evidence, items = {}, {}
        for row in rows:
            ref = 'item-dataset-' + str(row['dataset_id'])
            evidence[ref] = {k:row[k] for k in ('source_key','source_version','retrieved_at')}
            evidence[ref].update(source_url=row['url'],dataset_sha256=row['sha256'],limitations=json.loads(row['limitations_json']))
            attributes = json.loads(row['attributes_json'])
            attributes.update(evidence_ref=ref,raw_reference=row['raw_reference'])
            items.setdefault(row['item_id'],{}).setdefault(row['variant'],attributes)
        return items, evidence

    def get(self, item_id):
        items, evidence = self.get_many([item_id])
        from .item_instances import ItemInstances
        observed = ItemInstances(self.database).page(item_id,limit=3)
        from .character_capture import COMPARISON_POLICY
        variants=items.get(item_id,{})
        conflicts=[]
        keys=set().union(*(v.get('stats',{}) for v in variants.values()))
        for key in sorted(keys):
            values={name:v['stats'][key] for name,v in variants.items() if key in v.get('stats',{})}
            if len(set(values.values()))>1: conflicts.append({'stat':key,'assertions':values})
        return dict(status="recorded" if item_id in items or observed['total'] else "not_recorded",
            variants=items.get(item_id,{}),evidence=evidence,observed_variants=observed,
            stat_conflicts=conflicts,comparison_policy=COMPARISON_POLICY,
            interpretation="Separate sourced base-item variants. Inspect build and conflicts; no suffix, enchant or live character totals are inferred.")

    def enchant(self,enchant_id):
        from .item_instances import normalize_stats
        from .validation import integer
        integer(enchant_id,'enchant_id',1)
        with self.database.transaction() as c:
            rows=c.execute('''SELECT e.*,d.game_build,d.source_version,d.retrieved_at,s.source_key
                FROM enchant_facts e JOIN research_datasets d ON d.id=e.dataset_id JOIN sources s ON s.id=d.source_id
                WHERE d.active=1 AND e.enchant_id=? ORDER BY d.retrieved_at DESC''',(enchant_id,)).fetchall()
        assertions=[]
        for row in rows:
            data=json.loads(row['attributes_json'])
            for app in data['applications']:
                assertions.append({**app,'stats':normalize_stats(app['stats_raw']),
                    'source_key':row['source_key'],'game_build':row['game_build'],
                    'source_version':row['source_version'],'retrieved_at':row['retrieved_at']})
        stats={json.dumps(v['stats_raw'],sort_keys=True) for v in assertions if v['stats_raw']}
        return {'enchant_id':enchant_id,'status':'recorded' if assertions else 'not_recorded',
            'numeric_conflict':len(stats)>1,'applications':assertions,
            'interpretation':'Permanent enchant source assertions; application recipes may differ by slot. Do not double-count against full-link API stats.'}
