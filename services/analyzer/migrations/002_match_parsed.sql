-- Persist ParsedDemo metadata and JSON payload on matches.
ALTER TABLE matches ADD COLUMN patch_version TEXT;
ALTER TABLE matches ADD COLUMN tick_rate REAL;
ALTER TABLE matches ADD COLUMN roster_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE matches ADD COLUMN round_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE matches ADD COLUMN kill_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE matches ADD COLUMN damage_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE matches ADD COLUMN parsed_json TEXT;
ALTER TABLE matches ADD COLUMN parsed_at TEXT;
ALTER TABLE matches ADD COLUMN error_code TEXT;
ALTER TABLE matches ADD COLUMN error_message TEXT;

CREATE INDEX IF NOT EXISTS idx_matches_demo_id ON matches(demo_id);
CREATE INDEX IF NOT EXISTS idx_matches_parse_status ON matches(parse_status);
