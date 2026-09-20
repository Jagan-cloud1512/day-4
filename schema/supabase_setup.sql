-- Run this ONCE in the Supabase SQL Editor to disable RLS and seed data.
-- RLS is disabled for simplicity in this course project.

-- Disable RLS on all tables
ALTER TABLE student DISABLE ROW LEVEL SECURITY;
ALTER TABLE training DISABLE ROW LEVEL SECURITY;
ALTER TABLE equipment DISABLE ROW LEVEL SECURITY;
ALTER TABLE policy DISABLE ROW LEVEL SECURITY;
ALTER TABLE booking DISABLE ROW LEVEL SECURITY;
ALTER TABLE notification DISABLE ROW LEVEL SECURITY;
ALTER TABLE idempotency DISABLE ROW LEVEL SECURITY;
ALTER TABLE thread DISABLE ROW LEVEL SECURITY;
ALTER TABLE message DISABLE ROW LEVEL SECURITY;
ALTER TABLE run DISABLE ROW LEVEL SECURITY;
ALTER TABLE run_step DISABLE ROW LEVEL SECURITY;
ALTER TABLE tool_call DISABLE ROW LEVEL SECURITY;

-- Seed students
INSERT INTO student (id, roll_no, name, dept, max_bookings, fine_due) VALUES
    (1, '22CS045', 'Priya Raman', 'CSE', 2, 0),
    (2, '22IT017', 'Arjun Kumar', 'IT', 2, 75),
    (3, '22EC031', 'Divya Sekar', 'ECE', 1, 0)
ON CONFLICT DO NOTHING;

-- Seed training certifications
INSERT INTO training (student_id, category, certified_at) VALUES
    (1, 'electronics', 1700000000.0),
    (1, '3dprinting', 1700100000.0),
    (3, 'electronics', 1700200000.0)
ON CONFLICT DO NOTHING;

-- Seed equipment
INSERT INTO equipment (id, name, category, description, units_total, units_available, requires_training, version) VALUES
    (1, 'Oscilloscope DSO-X2000', 'electronics', '4-channel digital storage oscilloscope', 3, 3, 'electronics', 0),
    (2, 'Arduino Mega Kit', 'microcontrollers', 'Arduino Mega 2560 with sensors and breadboard', 5, 4, NULL, 0),
    (3, '3D Printer Prusa MK4', 'fabrication', 'FDM 3D printer with PLA filament', 1, 1, '3dprinting', 0),
    (4, 'Raspberry Pi 5 Kit', 'microcontrollers', 'RPi 5 with case, power supply and SD card', 4, 4, NULL, 0),
    (5, 'Logic Analyzer Saleae', 'electronics', '8-channel USB logic analyzer', 2, 2, 'electronics', 0),
    (6, 'Soldering Station Hakko', 'electronics', 'Temperature-controlled soldering station', 2, 0, 'electronics', 0)
ON CONFLICT DO NOTHING;

-- Seed policies
INSERT INTO policy (name, value) VALUES
    ('max_fine_to_book', 50),
    ('max_active_bookings', 2)
ON CONFLICT DO NOTHING;

-- Seed existing booking (Divya has Arduino booked)
INSERT INTO booking (student_id, equipment_id, created_at)
    SELECT 3, 2, EXTRACT(EPOCH FROM NOW())
    WHERE NOT EXISTS (SELECT 1 FROM booking WHERE student_id = 3 AND equipment_id = 2);

-- Reset sequences to avoid id conflicts
SELECT setval(pg_get_serial_sequence('student', 'id'), (SELECT COALESCE(MAX(id), 1) FROM student));
SELECT setval(pg_get_serial_sequence('equipment', 'id'), (SELECT COALESCE(MAX(id), 1) FROM equipment));
