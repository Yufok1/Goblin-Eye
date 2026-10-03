CREATE TABLE companion_entries (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL CHECK(kind IN ('goal', 'note', 'session')),
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'completed', 'archived')),
    basis TEXT NOT NULL CHECK(basis IN ('player_report', 'agent_inference', 'sourced_evidence')),
    author TEXT NOT NULL CHECK(author IN ('player', 'agent')),
    character_snapshot_id INTEGER REFERENCES character_snapshots(id) ON DELETE SET NULL,
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    occurred_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX companion_entries_by_status ON companion_entries(status, updated_at DESC, id DESC);
CREATE INDEX companion_entries_by_kind ON companion_entries(kind, updated_at DESC, id DESC);
CREATE TABLE companion_status_events (
    id INTEGER PRIMARY KEY,
    entry_id INTEGER NOT NULL REFERENCES companion_entries(id) ON DELETE CASCADE,
    old_status TEXT NOT NULL,
    new_status TEXT NOT NULL,
    author TEXT NOT NULL CHECK(author IN ('player', 'agent')),
    changed_at TEXT NOT NULL
);
