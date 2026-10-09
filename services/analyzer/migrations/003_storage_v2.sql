-- Storage schema v2: identity graph, dual-clock events, round markers.
-- Do not store dense player-tick datasets in SQLite (reserved for Parquet/DuckDB).

ALTER TABLE matches ADD COLUMN structural_probe_version TEXT;
ALTER TABLE matches ADD COLUMN build_num TEXT;
ALTER TABLE matches ADD COLUMN server_start_tick INTEGER;
ALTER TABLE matches ADD COLUMN storage_schema_version TEXT NOT NULL DEFAULT '2';

CREATE TABLE IF NOT EXISTS player_identities (
    id TEXT PRIMARY KEY,
    steamid64 TEXT UNIQUE,
    display_name_latest TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS controller_sessions (
    id TEXT PRIMARY KEY,
    match_id TEXT NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    userid INTEGER NOT NULL,
    player_identity_id TEXT REFERENCES player_identities(id) ON DELETE SET NULL,
    connected_demo_tick INTEGER,
    disconnected_demo_tick INTEGER,
    is_bot INTEGER NOT NULL DEFAULT 0 CHECK (is_bot IN (0, 1)),
    is_hltv INTEGER NOT NULL DEFAULT 0 CHECK (is_hltv IN (0, 1))
);

CREATE INDEX IF NOT EXISTS idx_controller_sessions_match
    ON controller_sessions(match_id);
CREATE INDEX IF NOT EXISTS idx_controller_sessions_userid
    ON controller_sessions(match_id, userid);
CREATE INDEX IF NOT EXISTS idx_controller_sessions_identity
    ON controller_sessions(player_identity_id);

CREATE TABLE IF NOT EXISTS pawn_lives (
    id TEXT PRIMARY KEY,
    match_id TEXT NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    controller_session_id TEXT REFERENCES controller_sessions(id) ON DELETE SET NULL,
    pawn_handle INTEGER NOT NULL,
    spawn_demo_tick INTEGER,
    death_demo_tick INTEGER
);

CREATE INDEX IF NOT EXISTS idx_pawn_lives_match ON pawn_lives(match_id);
CREATE INDEX IF NOT EXISTS idx_pawn_lives_controller
    ON pawn_lives(controller_session_id);
CREATE INDEX IF NOT EXISTS idx_pawn_lives_handle
    ON pawn_lives(match_id, pawn_handle);

CREATE TABLE IF NOT EXISTS rounds (
    id TEXT PRIMARY KEY,
    match_id TEXT NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    round_no INTEGER NOT NULL,
    freeze_end_demo_tick INTEGER,
    end_demo_tick INTEGER,
    end_marker_type TEXT,
    winner TEXT,
    win_reason TEXT,
    UNIQUE (match_id, round_no)
);

CREATE INDEX IF NOT EXISTS idx_rounds_match ON rounds(match_id);

CREATE TABLE IF NOT EXISTS round_markers (
    id TEXT PRIMARY KEY,
    match_id TEXT NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    marker_type TEXT NOT NULL,
    demo_tick INTEGER NOT NULL,
    server_tick INTEGER,
    sequence_index INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_round_markers_match ON round_markers(match_id);
CREATE INDEX IF NOT EXISTS idx_round_markers_type
    ON round_markers(match_id, marker_type);

CREATE TABLE IF NOT EXISTS kill_events (
    event_id TEXT PRIMARY KEY,
    match_id TEXT NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    round_id TEXT REFERENCES rounds(id) ON DELETE SET NULL,
    demo_tick INTEGER NOT NULL,
    server_tick INTEGER,
    victim_userid INTEGER,
    victim_pawn_handle INTEGER,
    attacker_userid INTEGER,
    attacker_pawn_handle INTEGER,
    assister_userid INTEGER,
    assister_pawn_handle INTEGER,
    weapon TEXT,
    headshot INTEGER NOT NULL DEFAULT 0 CHECK (headshot IN (0, 1)),
    penetrated INTEGER NOT NULL DEFAULT 0 CHECK (penetrated IN (0, 1)),
    source_event_id TEXT NOT NULL,
    source_parser TEXT
);

CREATE INDEX IF NOT EXISTS idx_kill_events_match ON kill_events(match_id);
CREATE INDEX IF NOT EXISTS idx_kill_events_round ON kill_events(round_id);
CREATE INDEX IF NOT EXISTS idx_kill_events_demo_tick
    ON kill_events(match_id, demo_tick);

CREATE TABLE IF NOT EXISTS damage_events (
    event_id TEXT PRIMARY KEY,
    match_id TEXT NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    round_id TEXT REFERENCES rounds(id) ON DELETE SET NULL,
    demo_tick INTEGER NOT NULL,
    server_tick INTEGER,
    victim_userid INTEGER,
    victim_pawn_handle INTEGER,
    attacker_userid INTEGER,
    attacker_pawn_handle INTEGER,
    hp_damage INTEGER NOT NULL,
    armor_damage INTEGER NOT NULL DEFAULT 0,
    weapon TEXT,
    source_event_id TEXT NOT NULL,
    source_parser TEXT
);

CREATE INDEX IF NOT EXISTS idx_damage_events_match ON damage_events(match_id);
CREATE INDEX IF NOT EXISTS idx_damage_events_round ON damage_events(round_id);

CREATE TABLE IF NOT EXISTS grenade_events (
    event_id TEXT PRIMARY KEY,
    match_id TEXT NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    round_id TEXT REFERENCES rounds(id) ON DELETE SET NULL,
    demo_tick INTEGER NOT NULL,
    server_tick INTEGER,
    grenade_type TEXT NOT NULL,
    thrower_userid INTEGER,
    x REAL,
    y REAL,
    z REAL,
    source_event_id TEXT NOT NULL,
    source_parser TEXT
);

CREATE INDEX IF NOT EXISTS idx_grenade_events_match ON grenade_events(match_id);
CREATE INDEX IF NOT EXISTS idx_grenade_events_round ON grenade_events(round_id);
