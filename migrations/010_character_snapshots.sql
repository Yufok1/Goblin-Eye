CREATE TABLE character_snapshots (
    id INTEGER PRIMARY KEY,
    character_key TEXT NOT NULL,
    name TEXT NOT NULL,
    realm TEXT NOT NULL,
    race TEXT NOT NULL,
    class_token TEXT NOT NULL,
    level INTEGER NOT NULL,
    source_key TEXT NOT NULL,
    source_version TEXT NOT NULL,
    game_build TEXT NOT NULL,
    imported_at TEXT NOT NULL,
    captured_at TEXT,
    evidence_kind TEXT NOT NULL,
    confidence REAL NOT NULL,
    confidence_basis TEXT NOT NULL,
    raw_reference TEXT NOT NULL,
    sha256 TEXT NOT NULL UNIQUE,
    payload_json TEXT NOT NULL,
    limitations_json TEXT NOT NULL
);
CREATE INDEX character_snapshot_identity ON character_snapshots(character_key, id DESC);
CREATE TABLE character_item_observations (
    snapshot_id INTEGER NOT NULL REFERENCES character_snapshots(id),
    location TEXT NOT NULL CHECK(location IN ('equipped','bag_gear')),
    ordinal INTEGER NOT NULL,
    item_id INTEGER NOT NULL,
    enchant_id INTEGER NOT NULL,
    random_suffix INTEGER NOT NULL,
    slot_id INTEGER,
    PRIMARY KEY(snapshot_id, location, ordinal)
);
CREATE INDEX character_item_lookup ON character_item_observations(item_id);
