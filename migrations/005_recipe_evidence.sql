-- Source assertions retain revisions and do not require invented item records.
CREATE TABLE research_datasets (
    id INTEGER PRIMARY KEY,
    source_id INTEGER NOT NULL REFERENCES sources(id),
    dataset_key TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    source_version TEXT,
    game_build TEXT,
    content_phase TEXT,
    retrieved_at TEXT NOT NULL,
    confidence REAL NOT NULL CHECK(confidence BETWEEN 0 AND 1),
    evidence_kind TEXT NOT NULL,
    manifest_json TEXT NOT NULL,
    limitations_json TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0, 1)),
    UNIQUE(source_id, dataset_key, sha256)
);
CREATE UNIQUE INDEX idx_active_research_dataset ON research_datasets(source_id, dataset_key) WHERE active=1;

CREATE TABLE recipe_facts (
    id INTEGER PRIMARY KEY,
    dataset_id INTEGER NOT NULL REFERENCES research_datasets(id),
    spell_id INTEGER NOT NULL CHECK(spell_id > 0),
    name TEXT,
    profession_id INTEGER NOT NULL CHECK(profession_id > 0),
    profession TEXT NOT NULL,
    output_item_id INTEGER CHECK(output_item_id > 0),
    output_quantity REAL CHECK(output_quantity > 0),
    skill_required INTEGER CHECK(skill_required >= 0),
    attributes_json TEXT NOT NULL,
    raw_reference TEXT NOT NULL,
    UNIQUE(dataset_id, profession_id, spell_id)
);
CREATE INDEX idx_recipe_facts_output ON recipe_facts(output_item_id);

CREATE TABLE reagent_facts (
    recipe_fact_id INTEGER NOT NULL REFERENCES recipe_facts(id),
    item_id INTEGER NOT NULL CHECK(item_id > 0),
    quantity REAL NOT NULL CHECK(quantity > 0),
    PRIMARY KEY(recipe_fact_id, item_id)
);
CREATE INDEX idx_reagent_facts_item ON reagent_facts(item_id);

CREATE TABLE recipe_teaching_items (
    recipe_fact_id INTEGER NOT NULL REFERENCES recipe_facts(id),
    item_id INTEGER NOT NULL CHECK(item_id > 0),
    raw_reference TEXT NOT NULL,
    PRIMARY KEY(recipe_fact_id, item_id)
);
CREATE INDEX idx_recipe_teaching_item ON recipe_teaching_items(item_id);
