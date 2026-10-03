CREATE TABLE world_entity_facts (
    dataset_id INTEGER NOT NULL REFERENCES research_datasets(id),
    entity_type TEXT NOT NULL CHECK(entity_type IN ('item','npc','object','quest')),
    entity_id INTEGER NOT NULL CHECK(entity_id > 0),
    name TEXT,
    attributes_json TEXT NOT NULL,
    raw_reference TEXT NOT NULL,
    PRIMARY KEY(dataset_id, entity_type, entity_id)
);
CREATE INDEX idx_world_entity_lookup ON world_entity_facts(entity_type, entity_id);

CREATE TABLE acquisition_facts (
    id INTEGER PRIMARY KEY,
    dataset_id INTEGER NOT NULL REFERENCES research_datasets(id),
    item_id INTEGER NOT NULL CHECK(item_id > 0),
    method TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id INTEGER NOT NULL CHECK(entity_id > 0),
    probability REAL CHECK(probability BETWEEN 0 AND 1),
    quest_condition INTEGER NOT NULL CHECK(quest_condition IN (0,1)),
    choice_reward INTEGER NOT NULL CHECK(choice_reward IN (0,1)),
    evidence_basis TEXT NOT NULL CHECK(evidence_basis IN ('classic_baseline','forever_community')),
    raw_reference TEXT NOT NULL,
    UNIQUE(dataset_id, item_id, method, entity_id)
);
CREATE INDEX idx_acquisition_item ON acquisition_facts(item_id, dataset_id);
CREATE INDEX idx_acquisition_entity ON acquisition_facts(entity_type, entity_id, dataset_id);

CREATE TABLE acquisition_coverage (
    dataset_id INTEGER NOT NULL REFERENCES research_datasets(id),
    item_id INTEGER NOT NULL,
    method TEXT NOT NULL,
    omitted_count INTEGER NOT NULL CHECK(omitted_count >= 0),
    PRIMARY KEY(dataset_id, item_id, method)
);
