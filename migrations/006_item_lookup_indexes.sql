CREATE INDEX idx_item_observations_item ON item_observations(item_id);
CREATE INDEX idx_price_observations_item ON price_observations(item_id, scan_day DESC);
