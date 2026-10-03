-- Preserve existing assertion IDs while allowing bundled references whose
-- upstream applicability is unspecified (e.g. container-item associations).
CREATE TABLE acquisition_facts_new (
    id INTEGER PRIMARY KEY,
    dataset_id INTEGER NOT NULL REFERENCES research_datasets(id),
    item_id INTEGER NOT NULL CHECK(item_id > 0),
    method TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id INTEGER NOT NULL CHECK(entity_id > 0),
    probability REAL CHECK(probability BETWEEN 0 AND 1),
    quest_condition INTEGER NOT NULL CHECK(quest_condition IN (0,1)),
    choice_reward INTEGER NOT NULL CHECK(choice_reward IN (0,1)),
    evidence_basis TEXT NOT NULL CHECK(evidence_basis IN ('classic_baseline','forever_community','bundled_reference')),
    raw_reference TEXT NOT NULL,
    UNIQUE(dataset_id, item_id, method, entity_id)
);
INSERT INTO acquisition_facts_new SELECT * FROM acquisition_facts;
DROP TABLE acquisition_facts;
ALTER TABLE acquisition_facts_new RENAME TO acquisition_facts;
CREATE INDEX idx_acquisition_item ON acquisition_facts(item_id, dataset_id);
CREATE INDEX idx_acquisition_entity ON acquisition_facts(entity_type, entity_id, dataset_id);
CREATE INDEX idx_acquisition_dataset ON acquisition_facts(dataset_id);
