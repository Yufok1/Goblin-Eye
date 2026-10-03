ALTER TABLE price_observations ADD COLUMN median_unit_copper INTEGER;
ALTER TABLE price_observations ADD COLUMN auction_count INTEGER;
ALTER TABLE price_observations ADD COLUMN median_7d_copper INTEGER;
ALTER TABLE price_observations ADD COLUMN median_30d_copper INTEGER;
ALTER TABLE price_observations ADD COLUMN low_30d_copper INTEGER;
ALTER TABLE price_observations ADD COLUMN high_30d_copper INTEGER;

CREATE TABLE item_observations (
    id INTEGER PRIMARY KEY,
    source_id INTEGER NOT NULL REFERENCES sources(id),
    item_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    quality TEXT,
    item_class TEXT,
    item_subclass TEXT,
    item_level INTEGER,
    required_level INTEGER,
    vendor_sell_copper INTEGER,
    icon_url TEXT,
    retrieved_at TEXT NOT NULL,
    game_build TEXT,
    content_phase TEXT,
    confidence REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    evidence_kind TEXT NOT NULL,
    raw_reference TEXT,
    UNIQUE(source_id, item_id)
);

CREATE INDEX idx_item_observations_name ON item_observations(name);

CREATE TABLE source_documents (
    id INTEGER PRIMARY KEY,
    source_id INTEGER NOT NULL REFERENCES sources(id),
    url TEXT NOT NULL,
    retrieved_at TEXT NOT NULL,
    content_type TEXT,
    cache_control TEXT,
    sha256 TEXT NOT NULL,
    body BLOB NOT NULL,
    UNIQUE(source_id, url, sha256)
);

CREATE INDEX idx_source_documents_url_time ON source_documents(url, retrieved_at DESC);
