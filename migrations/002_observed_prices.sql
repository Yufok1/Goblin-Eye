CREATE TABLE price_observations (
    id INTEGER PRIMARY KEY,
    source_id INTEGER NOT NULL REFERENCES sources(id),
    market_id INTEGER NOT NULL REFERENCES markets(id),
    item_key TEXT NOT NULL,
    item_id INTEGER,
    scan_day INTEGER NOT NULL,
    observed_date TEXT NOT NULL,
    imported_at TEXT NOT NULL,
    source_modified_at TEXT NOT NULL,
    current_min_unit_copper INTEGER,
    daily_min_unit_copper INTEGER,
    daily_max_low_unit_copper INTEGER,
    available_quantity INTEGER,
    confidence REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    evidence_kind TEXT NOT NULL,
    raw_reference TEXT,
    UNIQUE(source_id, market_id, item_key, scan_day)
);

CREATE INDEX idx_price_observations_market_item_day
ON price_observations(market_id, item_id, scan_day DESC);

CREATE TABLE watched_files (
    path TEXT PRIMARY KEY,
    adapter_key TEXT NOT NULL,
    last_modified_at TEXT,
    last_hash TEXT,
    last_import_at TEXT,
    last_status TEXT NOT NULL DEFAULT 'discovered',
    last_error TEXT
);

