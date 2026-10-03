CREATE TABLE travel_nodes (
    dataset_id INTEGER NOT NULL REFERENCES research_datasets(id),
    node_key TEXT NOT NULL,
    name TEXT,
    container_key TEXT,
    ui_map_id INTEGER,
    x REAL,
    y REAL,
    kind TEXT,
    evidence_basis TEXT NOT NULL,
    attributes_json TEXT NOT NULL,
    raw_reference TEXT NOT NULL,
    PRIMARY KEY(dataset_id, node_key)
);
CREATE INDEX idx_travel_nodes_map ON travel_nodes(ui_map_id, dataset_id);

CREATE TABLE travel_edges (
    id INTEGER PRIMARY KEY,
    dataset_id INTEGER NOT NULL REFERENCES research_datasets(id),
    from_node_key TEXT NOT NULL,
    to_node_key TEXT NOT NULL,
    method TEXT NOT NULL,
    cost_seconds REAL,
    fare_copper INTEGER,
    loading_screens INTEGER,
    one_way INTEGER NOT NULL CHECK(one_way IN (0,1)),
    evidence_basis TEXT NOT NULL,
    requirements_json TEXT NOT NULL,
    attributes_json TEXT NOT NULL,
    raw_reference TEXT NOT NULL
);
CREATE INDEX idx_travel_edges_from ON travel_edges(from_node_key, dataset_id);
CREATE INDEX idx_travel_edges_to ON travel_edges(to_node_key, dataset_id);
CREATE INDEX idx_travel_edges_method ON travel_edges(method, dataset_id);
