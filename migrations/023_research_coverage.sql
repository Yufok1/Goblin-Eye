CREATE TABLE item_instance_facts (
 id INTEGER PRIMARY KEY,
 namespace TEXT NOT NULL,
 item_id INTEGER NOT NULL CHECK(item_id > 0),
 item_string TEXT NOT NULL,
 captured_at TEXT NOT NULL,
 imported_at TEXT NOT NULL,
 game_build TEXT NOT NULL,
 sha256 TEXT NOT NULL,
 attributes_json TEXT NOT NULL,
 raw_reference TEXT NOT NULL,
 UNIQUE(namespace,item_string,sha256)
);
CREATE INDEX idx_item_instances ON item_instance_facts(item_id,namespace,item_string,captured_at);
CREATE TABLE enchant_facts (
 dataset_id INTEGER NOT NULL REFERENCES research_datasets(id),
 enchant_id INTEGER NOT NULL CHECK(enchant_id > 0),
 attributes_json TEXT NOT NULL,
 raw_reference TEXT NOT NULL,
 PRIMARY KEY(dataset_id,enchant_id)
);
CREATE TABLE character_quest_snapshots (
 id INTEGER PRIMARY KEY,
 namespace TEXT NOT NULL,
 character_name TEXT NOT NULL,
 imported_at TEXT NOT NULL,
 file_saved_at TEXT NOT NULL,
 sha256 TEXT NOT NULL,
 payload_json TEXT NOT NULL,
 raw_reference TEXT NOT NULL,
 UNIQUE(namespace,character_name,sha256)
);
CREATE TABLE dungeon_labels (
 dataset_id INTEGER NOT NULL REFERENCES research_datasets(id),
 dungeon_key TEXT NOT NULL,
 name TEXT NOT NULL,
 slug TEXT NOT NULL,
 attributes_json TEXT NOT NULL,
 raw_reference TEXT NOT NULL,
 PRIMARY KEY(dataset_id,dungeon_key)
);
CREATE TABLE dungeon_memberships (
 dataset_id INTEGER NOT NULL REFERENCES research_datasets(id),
 dungeon_key TEXT NOT NULL,
 entity_type TEXT NOT NULL,
 entity_id INTEGER NOT NULL CHECK(entity_id > 0),
 raw_reference TEXT NOT NULL,
 PRIMARY KEY(dataset_id,dungeon_key,entity_type,entity_id)
);
