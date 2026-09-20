-- Supabase (PostgreSQL) schema for the equipment domain database.
-- Run this in the Supabase SQL Editor to create all tables.

CREATE TABLE IF NOT EXISTS student (
    id           SERIAL PRIMARY KEY,
    roll_no      TEXT NOT NULL UNIQUE,
    name         TEXT NOT NULL,
    dept         TEXT NOT NULL,
    max_bookings INTEGER NOT NULL DEFAULT 2,
    fine_due     INTEGER NOT NULL DEFAULT 0 CHECK (fine_due >= 0)
);

CREATE TABLE IF NOT EXISTS training (
    id            SERIAL PRIMARY KEY,
    student_id    INTEGER NOT NULL REFERENCES student (id),
    category      TEXT NOT NULL,
    certified_at  DOUBLE PRECISION NOT NULL,
    UNIQUE (student_id, category)
);

CREATE TABLE IF NOT EXISTS equipment (
    id                SERIAL PRIMARY KEY,
    name              TEXT NOT NULL,
    category          TEXT NOT NULL,
    description       TEXT NOT NULL,
    units_total       INTEGER NOT NULL,
    units_available   INTEGER NOT NULL CHECK (units_available >= 0),
    requires_training TEXT,
    version           INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS policy (
    name   TEXT PRIMARY KEY,
    value  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS booking (
    id            SERIAL PRIMARY KEY,
    student_id    INTEGER NOT NULL REFERENCES student (id),
    equipment_id  INTEGER NOT NULL REFERENCES equipment (id),
    created_at    DOUBLE PRECISION NOT NULL,
    UNIQUE (student_id, equipment_id)
);

CREATE TABLE IF NOT EXISTS notification (
    id          SERIAL PRIMARY KEY,
    roll_no     TEXT NOT NULL,
    message     TEXT NOT NULL,
    dedupe_key  TEXT NOT NULL UNIQUE,
    created_at  DOUBLE PRECISION NOT NULL
);

CREATE TABLE IF NOT EXISTS idempotency (
    key         TEXT PRIMARY KEY,
    tool_name   TEXT NOT NULL,
    result      TEXT NOT NULL,
    created_at  DOUBLE PRECISION NOT NULL
);

-- Seed data
INSERT INTO student (id, roll_no, name, dept, max_bookings, fine_due) VALUES
    (1, '22CS045', 'Priya Raman', 'CSE', 2, 0),
    (2, '22IT017', 'Arjun Kumar', 'IT', 2, 75),
    (3, '22EC031', 'Divya Sekar', 'ECE', 1, 0)
ON CONFLICT DO NOTHING;

INSERT INTO training (student_id, category, certified_at) VALUES
    (1, 'electronics', 1700000000.0),
    (1, '3dprinting', 1700100000.0),
    (3, 'electronics', 1700200000.0)
ON CONFLICT DO NOTHING;

INSERT INTO equipment (id, name, category, description, units_total, units_available, requires_training, version) VALUES
    (1, 'Oscilloscope DSO-X2000', 'electronics', '4-channel digital storage oscilloscope', 3, 3, 'electronics', 0),
    (2, 'Arduino Mega Kit', 'microcontrollers', 'Arduino Mega 2560 with sensors and breadboard', 5, 5, NULL, 0),
    (3, '3D Printer Prusa MK4', 'fabrication', 'FDM 3D printer with PLA filament', 1, 1, '3dprinting', 0),
    (4, 'Raspberry Pi 5 Kit', 'microcontrollers', 'RPi 5 with case, power supply and SD card', 4, 4, NULL, 0),
    (5, 'Logic Analyzer Saleae', 'electronics', '8-channel USB logic analyzer', 2, 2, 'electronics', 0),
    (6, 'Soldering Station Hakko', 'electronics', 'Temperature-controlled soldering station', 2, 0, 'electronics', 0)
ON CONFLICT DO NOTHING;

INSERT INTO policy (name, value) VALUES
    ('max_fine_to_book', 50),
    ('max_active_bookings', 2)
ON CONFLICT DO NOTHING;

INSERT INTO booking (student_id, equipment_id, created_at)
    SELECT 3, 2, EXTRACT(EPOCH FROM NOW())
    WHERE NOT EXISTS (SELECT 1 FROM booking WHERE student_id = 3 AND equipment_id = 2);

UPDATE equipment SET units_available = units_available - 1
    WHERE id = 2 AND units_available = 5;

-- Reset sequences
SELECT setval('student_id_seq', (SELECT MAX(id) FROM student));
SELECT setval('equipment_id_seq', (SELECT MAX(id) FROM equipment));
