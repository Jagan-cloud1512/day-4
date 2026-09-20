"""equipment.db: students, equipment, bookings. Every SQL statement for the lab lives here."""
import json
import time
from collections.abc import Callable
from pathlib import Path

from app.db import connect, transaction

SCHEMA = Path(__file__).resolve().parent.parent / "schema" / "equipment.sql"


class EquipmentDb:
    def __init__(self, path: str = ":memory:", clock: Callable[[], float] = time.time):
        self.conn = connect(path)
        self.clock = clock

    def transaction(self):
        return transaction(self.conn)

    def migrate(self) -> None:
        self.conn.executescript(SCHEMA.read_text())
        if self.conn.execute("SELECT count(*) FROM student").fetchone()[0]:
            return
        with self.transaction() as c:
            c.executemany("INSERT INTO student VALUES (?, ?, ?, ?, ?, ?)", [
                (1, "22CS045", "Priya Raman", "CSE", 2, 0),
                (2, "22IT017", "Arjun Kumar", "IT", 2, 75),
                (3, "22EC031", "Divya Sekar", "ECE", 1, 0)])
            c.executemany("INSERT INTO training (student_id, category, certified_at) VALUES (?, ?, ?)", [
                (1, "electronics", 1_700_000_000.0),
                (1, "3dprinting", 1_700_100_000.0),
                (3, "electronics", 1_700_200_000.0)])
            c.executemany("INSERT INTO equipment VALUES (?, ?, ?, ?, ?, ?, ?, 0)", [
                (1, "Oscilloscope DSO-X2000", "electronics", "4-channel digital storage oscilloscope", 3, 3, "electronics"),
                (2, "Arduino Mega Kit", "microcontrollers", "Arduino Mega 2560 with sensors and breadboard", 5, 5, None),
                (3, "3D Printer Prusa MK4", "fabrication", "FDM 3D printer with PLA filament", 1, 1, "3dprinting"),
                (4, "Raspberry Pi 5 Kit", "microcontrollers", "RPi 5 with case, power supply and SD card", 4, 4, None),
                (5, "Logic Analyzer Saleae", "electronics", "8-channel USB logic analyzer", 2, 2, "electronics"),
                (6, "Soldering Station Hakko", "electronics", "Temperature-controlled soldering station", 2, 0, "electronics")])
            c.executemany("INSERT INTO policy VALUES (?, ?)", [
                ("max_fine_to_book", 50),
                ("max_active_bookings", 2)])
            c.execute("INSERT INTO booking (student_id, equipment_id, created_at) VALUES (3, 2, ?)",
                      (self.clock(),))
            c.execute("UPDATE equipment SET units_available = units_available - 1 WHERE id = 2")

    # ------------------------------------------------------------------ reads

    def get_student(self, roll_no: str) -> dict | None:
        r = self.conn.execute("SELECT * FROM student WHERE roll_no = ?", (roll_no,)).fetchone()
        return dict(r) if r else None

    def policy(self, name: str) -> int:
        return self.conn.execute("SELECT value FROM policy WHERE name = ?", (name,)).fetchone()[0]

    def student_training(self, student_id: int) -> list[str]:
        rows = self.conn.execute("SELECT category FROM training WHERE student_id = ? ORDER BY category",
                                 (student_id,)).fetchall()
        return [r["category"] for r in rows]

    def has_training(self, student_id: int, category: str) -> bool:
        return self.conn.execute("SELECT 1 FROM training WHERE student_id = ? AND category = ?",
                                 (student_id, category)).fetchone() is not None

    def active_bookings(self, student_id: int) -> list[dict]:
        rows = self.conn.execute(
            "SELECT b.equipment_id, e.name FROM booking b JOIN equipment e ON e.id = b.equipment_id"
            " WHERE b.student_id = ? ORDER BY b.id", (student_id,)).fetchall()
        return [dict(r) for r in rows]

    def search_equipment(self, text: str, limit: int = 5) -> list[dict]:
        like = f"%{text.strip()}%"
        rows = self.conn.execute(
            "SELECT id, name, category, description, units_available, requires_training FROM equipment"
            " WHERE name LIKE ? OR category LIKE ? OR description LIKE ? ORDER BY name LIMIT ?",
            (like, like, like, limit)).fetchall()
        return [dict(r) for r in rows]

    def get_equipment(self, equipment_id: int) -> dict | None:
        r = self.conn.execute("SELECT * FROM equipment WHERE id = ?", (equipment_id,)).fetchone()
        return dict(r) if r else None

    def count(self, table: str) -> int:
        assert table.isidentifier()
        return self.conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]

    # ------------------------------------------------------------------ safe writes

    def book(self, student_id: int, equipment_id: int) -> str:
        """Returns 'booked', 'already_booked' or 'no_units'. Safe to repeat."""
        with self.transaction() as c:
            if c.execute("SELECT 1 FROM booking WHERE student_id = ? AND equipment_id = ?",
                         (student_id, equipment_id)).fetchone():
                return "already_booked"
            version = c.execute("SELECT version FROM equipment WHERE id = ?",
                                (equipment_id,)).fetchone()[0]
            took = c.execute(
                "UPDATE equipment SET units_available = units_available - 1, version = version + 1"
                " WHERE id = ? AND units_available > 0 AND version = ?",
                (equipment_id, version)).rowcount
            if not took:
                return "no_units"
            c.execute("INSERT INTO booking (student_id, equipment_id, created_at) VALUES (?, ?, ?)",
                      (student_id, equipment_id, self.clock()))
            return "booked"

    def record_notification(self, roll_no: str, message: str, dedupe_key: str) -> tuple[int, bool]:
        cur = self.conn.execute(
            "INSERT INTO notification (roll_no, message, dedupe_key, created_at) VALUES (?, ?, ?, ?)"
            " ON CONFLICT (dedupe_key) DO NOTHING", (roll_no, message, dedupe_key, self.clock()))
        if cur.rowcount == 1:
            return cur.lastrowid, True
        return self.conn.execute("SELECT id FROM notification WHERE dedupe_key = ?",
                                 (dedupe_key,)).fetchone()[0], False

    def once(self, key: str, tool_name: str, effect: Callable[[], dict]) -> tuple[dict, bool]:
        """Run a side effect at most once per idempotency key; the effect and its key commit together."""
        with self.transaction() as c:
            row = c.execute("SELECT result FROM idempotency WHERE key = ?", (key,)).fetchone()
            if row is not None:
                return json.loads(row["result"]), False
            result = effect()
            c.execute("INSERT INTO idempotency (key, tool_name, result, created_at) VALUES (?, ?, ?, ?)",
                      (key, tool_name, json.dumps(result, default=str), self.clock()))
            return result, True
