-- Compact indexes keep diagnostics and discovery off large JSON/body pages.
-- Existing observations and archived datasets remain intact.
CREATE INDEX idx_priced_capture_date ON market_price_points(capture_id,observed_date DESC)
    WHERE minimum_copper IS NOT NULL OR median_copper IS NOT NULL;
CREATE INDEX idx_world_discovery ON world_entity_facts(dataset_id,entity_type,name COLLATE NOCASE,entity_id);
CREATE INDEX idx_item_observation_names ON item_observations(name COLLATE NOCASE,item_id,source_id);
