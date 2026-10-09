CREATE TABLE IF NOT EXISTS demos (
    id TEXT PRIMARY KEY,
    sha256 TEXT NOT NULL UNIQUE,
    original_path TEXT NOT NULL,
    size_bytes INTEGER NOT NULL CHECK (size_bytes > 0),
    imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS matches (
    id TEXT PRIMARY KEY,
    demo_id TEXT NOT NULL REFERENCES demos(id) ON DELETE CASCADE,
    map_name TEXT,
    parser_name TEXT,
    parser_version TEXT,
    normalization_schema_version TEXT NOT NULL DEFAULT '1',
    parse_status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS incidents (
    id TEXT PRIMARY KEY,
    match_id TEXT NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    player_id TEXT,
    round_number INTEGER,
    incident_type TEXT NOT NULL,
    start_tick INTEGER,
    anchor_tick INTEGER NOT NULL,
    end_tick INTEGER,
    severity INTEGER CHECK (severity BETWEEN 1 AND 5),
    confidence REAL CHECK (confidence BETWEEN 0 AND 1),
    rule_version TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    job_type TEXT NOT NULL,
    entity_id TEXT,
    status TEXT NOT NULL,
    progress REAL NOT NULL DEFAULT 0 CHECK (progress BETWEEN 0 AND 1),
    attempt INTEGER NOT NULL DEFAULT 0,
    error_code TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
