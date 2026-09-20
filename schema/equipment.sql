-- equipment.db: students, equipment, bookings. The agent's memory is in agent.db.

CREATE TABLE IF NOT EXISTS student (
    id           INTEGER PRIMARY KEY,
    roll_no      TEXT NOT NULL UNIQUE,
    name         TEXT NOT NULL,
    dept         TEXT NOT NULL,
    max_bookings INTEGER NOT NULL DEFAULT 2,
    fine_due     INTEGER NOT NULL DEFAULT 0 CHECK (fine_due >= 0)      -- rupees
);

CREATE TABLE IF NOT EXISTS training (
    id            INTEGER PRIMARY KEY,
    student_id    INTEGER NOT NULL REFERENCES student (id),
    category      TEXT NOT NULL,
    certified_at  REAL NOT NULL,
    UNIQUE (student_id, category)
);

CREATE TABLE IF NOT EXISTS equipment (
    id                INTEGER PRIMARY KEY,
    name              TEXT NOT NULL,
    category          TEXT NOT NULL,
    description       TEXT NOT NULL,
    units_total       INTEGER NOT NULL,
    units_available   INTEGER NOT NULL CHECK (units_available >= 0),
    requires_training TEXT,          -- NULL = open to all, else the training category name
    version           INTEGER NOT NULL DEFAULT 0
);

-- Business rules live in data, not in prompts.
CREATE TABLE IF NOT EXISTS policy (
    name   TEXT PRIMARY KEY,
    value  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS booking (
    id            INTEGER PRIMARY KEY,
    student_id    INTEGER NOT NULL REFERENCES student (id),
    equipment_id  INTEGER NOT NULL REFERENCES equipment (id),
    created_at    REAL NOT NULL,
    UNIQUE (student_id, equipment_id)
);

CREATE TABLE IF NOT EXISTS notification (
    id          INTEGER PRIMARY KEY,
    roll_no     TEXT NOT NULL,
    message     TEXT NOT NULL,
    dedupe_key  TEXT NOT NULL UNIQUE,
    created_at  REAL NOT NULL
);

-- Idempotency keys live next to the side effects they guard.
CREATE TABLE IF NOT EXISTS idempotency (
    key         TEXT PRIMARY KEY,
    tool_name   TEXT NOT NULL,
    result      TEXT NOT NULL,
    created_at  REAL NOT NULL
);
