CREATE TABLE IF NOT EXISTS live_fixtures (
    match_id_hash TEXT PRIMARY KEY,
    home_team TEXT NOT NULL,
    away_team TEXT NOT NULL,
    league TEXT NOT NULL,
    score TEXT DEFAULT '',
    minute TEXT DEFAULT '',
    status TEXT DEFAULT 'live',
    kickoff_utc TIMESTAMPTZ,
    fixture_date DATE,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS live_snapshots (
    id BIGSERIAL PRIMARY KEY,
    match_id_hash TEXT NOT NULL,
    snapshot_at TIMESTAMPTZ NOT NULL,
    market TEXT NOT NULL,
    selection TEXT NOT NULL,
    odds REAL,
    share REAL,
    volume REAL,
    ou_line TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_live_snapshots_hash ON live_snapshots(match_id_hash);
CREATE INDEX IF NOT EXISTS idx_live_snapshots_at ON live_snapshots(snapshot_at);
CREATE INDEX IF NOT EXISTS idx_live_fixtures_date ON live_fixtures(fixture_date);
