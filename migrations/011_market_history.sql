CREATE TABLE market_captures (
 id INTEGER PRIMARY KEY,
 source_id INTEGER NOT NULL REFERENCES sources(id),
 market_id INTEGER NOT NULL REFERENCES markets(id),
 document_id INTEGER REFERENCES source_documents(id),
 identity TEXT NOT NULL,
 observed_at TEXT,
 retrieved_at TEXT NOT NULL,
 granularity TEXT NOT NULL CHECK(granularity IN ('scan','source_table','daily_capture','legacy_daily')),
 game_build TEXT,
 economic_period TEXT NOT NULL DEFAULT 'unknown',
 recovered INTEGER NOT NULL DEFAULT 0,
 limitations_json TEXT NOT NULL,
 UNIQUE(source_id,market_id,identity)
);
CREATE TABLE market_price_points (
 capture_id INTEGER NOT NULL REFERENCES market_captures(id),
 item_key TEXT NOT NULL,
 item_id INTEGER,
 observed_date TEXT NOT NULL,
 minimum_copper INTEGER,
 median_copper INTEGER,
 available_quantity INTEGER,
 payload_json TEXT NOT NULL,
 PRIMARY KEY(capture_id,item_key,observed_date)
);
CREATE INDEX idx_history_item_capture ON market_price_points(item_id,capture_id);
CREATE INDEX idx_capture_market_time ON market_captures(market_id,observed_at,id);
CREATE TABLE evidence_assertions (
 id INTEGER PRIMARY KEY,
 entity_type TEXT NOT NULL,
 entity_key TEXT NOT NULL,
 source_id INTEGER NOT NULL REFERENCES sources(id),
 retrieved_at TEXT NOT NULL,
 game_build TEXT,
 confidence REAL NOT NULL,
 payload_json TEXT NOT NULL,
 sha256 TEXT NOT NULL,
 selected INTEGER NOT NULL DEFAULT 0,
 UNIQUE(entity_type,entity_key,source_id,sha256)
);
CREATE INDEX idx_assertion_entity ON evidence_assertions(entity_type,entity_key);
CREATE TABLE assertion_conflicts (
 id INTEGER PRIMARY KEY,
 left_id INTEGER NOT NULL REFERENCES evidence_assertions(id),
 right_id INTEGER NOT NULL REFERENCES evidence_assertions(id),
 fields_json TEXT NOT NULL,
 UNIQUE(left_id,right_id)
);
