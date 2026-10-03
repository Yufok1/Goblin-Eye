PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE sources (
    id INTEGER PRIMARY KEY,
    source_key TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    source_type TEXT NOT NULL,
    url TEXT,
    trust_rank INTEGER NOT NULL CHECK (trust_rank BETWEEN 1 AND 6),
    enabled INTEGER NOT NULL DEFAULT 1,
    notes TEXT,
    last_success_at TEXT,
    last_error TEXT
);

CREATE TABLE markets (
    id INTEGER PRIMARY KEY,
    market_key TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    region TEXT NOT NULL,
    ruleset TEXT NOT NULL,
    faction TEXT NOT NULL,
    is_verified INTEGER NOT NULL DEFAULT 0,
    source_id INTEGER NOT NULL REFERENCES sources(id),
    retrieved_at TEXT NOT NULL,
    game_build TEXT,
    content_phase TEXT,
    confidence REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    evidence_kind TEXT NOT NULL
);

CREATE TABLE items (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    quality TEXT NOT NULL,
    item_class TEXT NOT NULL,
    subclass TEXT,
    stack_size INTEGER NOT NULL CHECK (stack_size > 0),
    vendor_buy_copper INTEGER,
    vendor_sell_copper INTEGER,
    required_level INTEGER,
    source_id INTEGER NOT NULL REFERENCES sources(id),
    retrieved_at TEXT NOT NULL,
    game_build TEXT,
    content_phase TEXT,
    confidence REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    evidence_kind TEXT NOT NULL,
    raw_reference TEXT
);

CREATE TABLE snapshots (
    id INTEGER PRIMARY KEY,
    external_id TEXT NOT NULL UNIQUE,
    market_id INTEGER NOT NULL REFERENCES markets(id),
    captured_at TEXT NOT NULL,
    source_id INTEGER NOT NULL REFERENCES sources(id),
    game_build TEXT,
    is_complete INTEGER NOT NULL,
    confidence REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    evidence_kind TEXT NOT NULL,
    raw_reference TEXT,
    imported_at TEXT NOT NULL
);

CREATE INDEX idx_snapshots_market_time ON snapshots(market_id, captured_at DESC);

CREATE TABLE listings (
    id INTEGER PRIMARY KEY,
    snapshot_id INTEGER NOT NULL REFERENCES snapshots(id) ON DELETE CASCADE,
    item_id INTEGER NOT NULL REFERENCES items(id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    stack_size INTEGER NOT NULL CHECK (stack_size > 0),
    buyout_copper INTEGER NOT NULL CHECK (buyout_copper >= 0),
    bid_copper INTEGER,
    time_left TEXT,
    seller_hash TEXT
);

CREATE INDEX idx_listings_snapshot_item ON listings(snapshot_id, item_id);

CREATE TABLE recipes (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    output_item_id INTEGER NOT NULL REFERENCES items(id),
    output_quantity INTEGER NOT NULL CHECK (output_quantity > 0),
    profession TEXT NOT NULL,
    skill_required INTEGER,
    kind TEXT NOT NULL,
    source_id INTEGER NOT NULL REFERENCES sources(id),
    retrieved_at TEXT NOT NULL,
    game_build TEXT,
    content_phase TEXT,
    confidence REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    evidence_kind TEXT NOT NULL,
    raw_reference TEXT
);

CREATE TABLE recipe_reagents (
    recipe_id INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
    item_id INTEGER NOT NULL REFERENCES items(id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (recipe_id, item_id)
);

CREATE TABLE vendors (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    zone TEXT NOT NULL,
    faction TEXT,
    x REAL,
    y REAL,
    source_id INTEGER NOT NULL REFERENCES sources(id),
    retrieved_at TEXT NOT NULL,
    game_build TEXT,
    content_phase TEXT,
    confidence REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    evidence_kind TEXT NOT NULL,
    raw_reference TEXT
);

CREATE TABLE vendor_offers (
    vendor_id INTEGER NOT NULL REFERENCES vendors(id) ON DELETE CASCADE,
    item_id INTEGER NOT NULL REFERENCES items(id),
    price_copper INTEGER NOT NULL CHECK (price_copper >= 0),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    limited_stock INTEGER,
    restock_seconds INTEGER,
    PRIMARY KEY (vendor_id, item_id)
);

CREATE TABLE mobs (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    min_level INTEGER NOT NULL,
    max_level INTEGER NOT NULL,
    classification TEXT NOT NULL,
    faction_access TEXT,
    expected_coin_copper REAL NOT NULL DEFAULT 0,
    skinning_item_id INTEGER REFERENCES items(id),
    skinning_probability REAL,
    source_id INTEGER NOT NULL REFERENCES sources(id),
    retrieved_at TEXT NOT NULL,
    game_build TEXT,
    content_phase TEXT,
    confidence REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    evidence_kind TEXT NOT NULL,
    raw_reference TEXT
);

CREATE TABLE loot_entries (
    mob_id INTEGER NOT NULL REFERENCES mobs(id) ON DELETE CASCADE,
    item_id INTEGER NOT NULL REFERENCES items(id),
    drop_probability REAL NOT NULL CHECK (drop_probability BETWEEN 0 AND 1),
    min_quantity INTEGER NOT NULL CHECK (min_quantity > 0),
    max_quantity INTEGER NOT NULL CHECK (max_quantity >= min_quantity),
    source_id INTEGER NOT NULL REFERENCES sources(id),
    retrieved_at TEXT NOT NULL,
    game_build TEXT,
    content_phase TEXT,
    confidence REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    evidence_kind TEXT NOT NULL,
    raw_reference TEXT,
    PRIMARY KEY (mob_id, item_id, source_id)
);

CREATE TABLE spawns (
    id INTEGER PRIMARY KEY,
    mob_id INTEGER NOT NULL REFERENCES mobs(id) ON DELETE CASCADE,
    zone TEXT NOT NULL,
    x REAL NOT NULL,
    y REAL NOT NULL,
    respawn_seconds INTEGER,
    source_id INTEGER NOT NULL REFERENCES sources(id),
    retrieved_at TEXT NOT NULL,
    game_build TEXT,
    content_phase TEXT,
    confidence REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    evidence_kind TEXT NOT NULL,
    raw_reference TEXT
);

CREATE TABLE camps (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    zone TEXT NOT NULL,
    centroid_x REAL NOT NULL,
    centroid_y REAL NOT NULL,
    travel_notes TEXT,
    source_id INTEGER NOT NULL REFERENCES sources(id),
    retrieved_at TEXT NOT NULL,
    game_build TEXT,
    content_phase TEXT,
    confidence REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    evidence_kind TEXT NOT NULL,
    raw_reference TEXT
);

CREATE TABLE camp_spawns (
    camp_id INTEGER NOT NULL REFERENCES camps(id) ON DELETE CASCADE,
    spawn_id INTEGER NOT NULL REFERENCES spawns(id) ON DELETE CASCADE,
    PRIMARY KEY (camp_id, spawn_id)
);

CREATE TABLE imports (
    id INTEGER PRIMARY KEY,
    adapter_key TEXT NOT NULL,
    source_id INTEGER REFERENCES sources(id),
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL,
    file_name TEXT,
    record_count INTEGER NOT NULL DEFAULT 0,
    error TEXT
);

CREATE TABLE fact_conflicts (
    id INTEGER PRIMARY KEY,
    entity_type TEXT NOT NULL,
    entity_key TEXT NOT NULL,
    field_name TEXT NOT NULL,
    preferred_source_id INTEGER REFERENCES sources(id),
    conflicting_source_id INTEGER REFERENCES sources(id),
    preferred_value TEXT,
    conflicting_value TEXT,
    detected_at TEXT NOT NULL,
    resolution TEXT
);
