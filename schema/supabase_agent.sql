-- Supabase (PostgreSQL) schema for the agent memory and job queue database.
-- Run this in the Supabase SQL Editor to create all tables.

CREATE TABLE IF NOT EXISTS thread (
    id          TEXT PRIMARY KEY,
    student_id  TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS message (
    id          SERIAL PRIMARY KEY,
    thread_id   TEXT NOT NULL REFERENCES thread (id),
    seq         INTEGER NOT NULL,
    role        TEXT NOT NULL CHECK (role IN ('user', 'model')),
    text        TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (thread_id, seq)
);

CREATE TABLE IF NOT EXISTS run (
    id                TEXT PRIMARY KEY,
    thread_id         TEXT NOT NULL REFERENCES thread (id),
    status            TEXT NOT NULL CHECK (status IN
                          ('queued', 'running', 'succeeded', 'failed', 'cancelled', 'dead')),
    model             TEXT NOT NULL,
    tokens_in         INTEGER NOT NULL DEFAULT 0,
    tokens_out        INTEGER NOT NULL DEFAULT 0,
    attempts          INTEGER NOT NULL DEFAULT 0,
    max_attempts      INTEGER NOT NULL DEFAULT 3,
    available_at      DOUBLE PRECISION NOT NULL,
    lease_owner       TEXT,
    lease_until       DOUBLE PRECISION,
    cancel_requested  INTEGER NOT NULL DEFAULT 0 CHECK (cancel_requested IN (0, 1)),
    error_code        TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at        TIMESTAMPTZ,
    finished_at       TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS run_claimable ON run (status, available_at);

CREATE TABLE IF NOT EXISTS run_step (
    id          SERIAL PRIMARY KEY,
    run_id      TEXT NOT NULL REFERENCES run (id),
    seq         INTEGER NOT NULL,
    kind        TEXT NOT NULL CHECK (kind IN ('model', 'tool')),
    tokens_in   INTEGER NOT NULL DEFAULT 0,
    tokens_out  INTEGER NOT NULL DEFAULT 0,
    text        TEXT,
    tool_calls  TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (run_id, seq)
);

CREATE TABLE IF NOT EXISTS tool_call (
    id              SERIAL PRIMARY KEY,
    run_step_id     INTEGER NOT NULL UNIQUE REFERENCES run_step (id),
    tool_name       TEXT NOT NULL,
    args            TEXT NOT NULL,
    result          TEXT NOT NULL,
    ok              INTEGER NOT NULL CHECK (ok IN (0, 1)),
    latency_ms      INTEGER NOT NULL,
    idempotency_key TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Enable Row Level Security (optional, for production)
-- ALTER TABLE thread ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE message ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE run ENABLE ROW LEVEL SECURITY;
