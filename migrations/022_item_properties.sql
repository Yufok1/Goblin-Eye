CREATE TABLE item_property_facts (
 dataset_id INTEGER NOT NULL REFERENCES research_datasets(id),
 item_id INTEGER NOT NULL CHECK(item_id > 0),
 variant TEXT NOT NULL CHECK(variant IN ('catalog','gear','tooltip')),
 attributes_json TEXT NOT NULL,
 raw_reference TEXT NOT NULL,
 PRIMARY KEY(dataset_id,item_id,variant)
);
CREATE INDEX idx_item_properties ON item_property_facts(item_id,dataset_id);
