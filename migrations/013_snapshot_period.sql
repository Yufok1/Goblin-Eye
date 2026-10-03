ALTER TABLE snapshots ADD COLUMN economic_period TEXT NOT NULL DEFAULT 'unknown';
CREATE INDEX idx_snapshots_market_period_time ON snapshots(market_id,economic_period,captured_at);
