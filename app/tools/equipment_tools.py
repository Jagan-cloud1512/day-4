"""Lab equipment tools, split between two specialist agents. Descriptions are prompts."""
from datetime import datetime, timezone

from app.equipment_db import EquipmentDb
from app.idempotency import notification_dedupe_key
from app.tools.dispatch import dispatch


class Toolset:
    SIDE_EFFECTS: tuple[str, ...] = ()
    DELEGATES: tuple[str, ...] = ()
    TOOL_NAMES: tuple[str, ...] = ()

    def functions(self) -> dict:
        return {n: getattr(self, n) for n in self.TOOL_NAMES}

    def call(self, name: str, args: dict) -> dict:
        return dispatch(self.functions(), name, args)


class InventoryTools(Toolset):
    """Read-only. The inventory agent can look, never change."""

    TOOL_NAMES = ("search_equipment", "get_equipment")

    def __init__(self, db: EquipmentDb):
        self.db = db

    def search_equipment(self, text: str) -> dict:
        """Find lab equipment by words from the name, category or description.

        Use for "do you have ...", "is <name> available", "equipment for <subject>". Returns at most
        five matches. Read-only: changes nothing. To book equipment, that is the booking desk's job.

        Args:
            text: A few words from the name, category or description, e.g. "oscilloscope" or "microcontrollers".

        Returns:
            {"equipment": [{"equipment_id", "name", "category", "units_available", "requires_training"}]}.
            An empty list means no match; try fewer or different words.
        """
        if not text.strip():
            return {"error": "empty_query", "hint": "Pass a few words from the name, category or description."}
        items = self.db.search_equipment(text)
        return {"equipment": [{"equipment_id": e["id"], "name": e["name"], "category": e["category"],
                                "units_available": e["units_available"],
                                "requires_training": e["requires_training"]} for e in items]}

    def get_equipment(self, equipment_id: int) -> dict:
        """Get one equipment item's details and how many units are available right now.

        Use when you already have an equipment_id from search_equipment and need its current
        availability or full description. Read-only: changes nothing.

        Args:
            equipment_id: Integer id returned by search_equipment.

        Returns:
            {"equipment_id", "name", "category", "description", "units_total", "units_available",
             "requires_training"}.
        """
        e = self.db.get_equipment(equipment_id)
        if e is None:
            return {"error": "unknown_equipment", "hint": "Use search_equipment to find the equipment_id first."}
        return {"equipment_id": e["id"], "name": e["name"], "category": e["category"],
                "description": e["description"], "units_total": e["units_total"],
                "units_available": e["units_available"], "requires_training": e["requires_training"]}


class BookingTools(Toolset):
    """The booking desk, bound to ONE student. The model cannot pick a different roll number."""

    TOOL_NAMES = ("get_student", "check_can_book", "book_equipment", "notify_student")
    SIDE_EFFECTS = ("book_equipment", "notify_student")

    def __init__(self, db: EquipmentDb, roll_no: str, clock=lambda: datetime.now(timezone.utc)):
        self.db, self.roll_no, self.clock = db, roll_no, clock

    def _student(self) -> dict:
        s = self.db.get_student(self.roll_no)
        if s is None:
            raise LookupError(f"student {self.roll_no} not found")
        return s

    def get_student(self) -> dict:
        """Get the current student's lab record: name, department, fine due, training certs and bookings.

        Use for "what have I booked", "am I trained for ...", "what do I owe". Read-only: changes nothing.

        Returns:
            {"roll_no", "name", "dept", "fine_due", "max_bookings", "training": [str],
             "bookings": [{"equipment_id", "name"}]}.
        """
        s = self._student()
        return {"roll_no": s["roll_no"], "name": s["name"], "dept": s["dept"],
                "fine_due": s["fine_due"], "max_bookings": s["max_bookings"],
                "training": self.db.student_training(s["id"]),
                "bookings": self.db.active_bookings(s["id"])}

    def check_can_book(self, equipment_id: int) -> dict:
        """Decide whether the current student may book this equipment, using lab policy and training records.

        Use BEFORE book_equipment. The decision comes from the policy table and training records:
        never decide it yourself. Read-only: changes nothing.

        Args:
            equipment_id: Integer id of the equipment to check.

        Returns:
            {"can_book": bool, "reasons": [str]}. Every reason is a rule the student currently breaks.
        """
        s = self._student()
        reasons = []
        fine_limit = self.db.policy("max_fine_to_book")
        if s["fine_due"] > fine_limit:
            reasons.append(f"fine due Rs {s['fine_due']} is above the Rs {fine_limit} limit")
        held = len(self.db.active_bookings(s["id"]))
        if held >= s["max_bookings"]:
            reasons.append(f"already holds {held} of {s['max_bookings']} allowed bookings")
        equip = self.db.get_equipment(equipment_id)
        if equip is None:
            return {"can_book": False, "reasons": ["unknown equipment id"]}
        if equip["requires_training"] and not self.db.has_training(s["id"], equip["requires_training"]):
            reasons.append(f"requires {equip['requires_training']} training certification")
        return {"can_book": not reasons, "reasons": reasons}

    def book_equipment(self, equipment_id: int) -> dict:
        """Book one unit of equipment for the current student. CHANGES DATA: takes a unit off the shelf.

        Use only when the student has asked to book this equipment and check_can_book allowed it.
        Asking again for the same equipment is safe and returns the existing booking.

        Args:
            equipment_id: Integer id returned by search_equipment.

        Returns:
            {"equipment_id", "name", "status": "booked" | "already_booked"}, or an error:
            not_allowed (with reasons), unknown_equipment, or no_units (none available right now).
        """
        verdict = self.check_can_book(equipment_id)
        if not verdict["can_book"]:
            return {"error": "not_allowed", "reasons": verdict["reasons"],
                    "hint": "Explain the reasons to the student. Do not retry."}
        equip = self.db.get_equipment(equipment_id)
        if equip is None:
            return {"error": "unknown_equipment", "hint": "Ask inventory for the right equipment_id."}
        status = self.db.book(self._student()["id"], equipment_id)
        if status == "no_units":
            return {"error": "no_units", "hint": "No unit is available. Tell the student; do not retry."}
        return {"equipment_id": equipment_id, "name": equip["name"], "status": status}

    def notify_student(self, message: str) -> dict:
        """Send the current student a short text message. CHANGES DATA: a message goes out.

        Use to confirm something that just happened, such as a booking. The same message on the
        same day is sent only once. Never use it to answer a question; reply in the chat instead.

        Args:
            message: 1 to 160 characters.

        Returns:
            {"notification_id", "status": "queued", "duplicate": bool}.
        """
        if not message.strip() or len(message) > 160:
            return {"error": "invalid_message", "hint": "message must be 1 to 160 characters."}
        key = notification_dedupe_key(self.roll_no, message, self.clock().date())
        notification_id, created = self.db.record_notification(self.roll_no, message, key)
        return {"notification_id": notification_id, "status": "queued", "duplicate": not created}
