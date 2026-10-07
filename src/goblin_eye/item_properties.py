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
        return dict(status="recorded" if item_id in items else "not_recorded", variants=items.get(item_id,{}),evidence=evidence,
            interpretation="Separate sourced base-item variants. Inspect build and conflicts; no suffix, enchant or live character totals are inferred.")
