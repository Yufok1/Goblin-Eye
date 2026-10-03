CREATE VIEW selected_item_names AS
WITH candidates AS (
 SELECT i.id item_id,i.name,s.source_key,s.trust_rank,i.retrieved_at,i.confidence,i.game_build,
        'items' record_kind,i.id record_id,NULL dataset_id
 FROM items i JOIN sources s ON s.id=i.source_id
 UNION ALL
 SELECT i.item_id,i.name,s.source_key,s.trust_rank,i.retrieved_at,i.confidence,i.game_build,
        'item_observations',i.id,NULL
 FROM item_observations i JOIN sources s ON s.id=i.source_id
 UNION ALL
 SELECT w.entity_id,w.name,s.source_key,s.trust_rank,d.retrieved_at,d.confidence,d.game_build,
        'world_entity_facts',w.entity_id,d.id
 FROM world_entity_facts w JOIN research_datasets d ON d.id=w.dataset_id JOIN sources s ON s.id=d.source_id
 WHERE d.active=1 AND w.entity_type='item'
), ranked AS (
 SELECT *,ROW_NUMBER() OVER(PARTITION BY item_id ORDER BY trust_rank,retrieved_at DESC,confidence DESC,source_key,record_kind,record_id) position
 FROM candidates
)
SELECT * FROM ranked WHERE position=1;
