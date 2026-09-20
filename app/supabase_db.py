"""Supabase (PostgreSQL) adapter for the equipment database.

Set these environment variables to use Supabase instead of SQLite:
    SUPABASE_URL=https://<project-ref>.supabase.co
    SUPABASE_KEY=<your-anon-or-service-role-key>
    USE_SUPABASE=1

The local SQLite mode remains the default for development, tests, and the demo.
"""
import json
import os
import time
from collections.abc import Callable
from pathlib import Path

SCHEMA = Path(__file__).resolve().parent.parent / "schema" / "supabase_library.sql"


def get_supabase_client():
    from supabase import create_client
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_KEY"]
    return create_client(url, key)


class SupabaseEquipmentDb:
    """Drop-in replacement for EquipmentDb that talks to Supabase/PostgreSQL."""

    def __init__(self, client=None, clock: Callable[[], float] = time.time):
        self.client = client or get_supabase_client()
        self.clock = clock

    def migrate(self) -> None:
        pass

    def get_student(self, roll_no: str) -> dict | None:
        r = self.client.table("student").select("*").eq("roll_no", roll_no).execute()
        return r.data[0] if r.data else None

    def policy(self, name: str) -> int:
        r = self.client.table("policy").select("value").eq("name", name).execute()
        return r.data[0]["value"]

    def student_training(self, student_id: int) -> list[str]:
        r = (self.client.table("training")
             .select("category")
             .eq("student_id", student_id)
             .order("category")
             .execute())
        return [row["category"] for row in r.data]

    def has_training(self, student_id: int, category: str) -> bool:
        r = (self.client.table("training")
             .select("id")
             .eq("student_id", student_id)
             .eq("category", category)
             .execute())
        return bool(r.data)

    def active_bookings(self, student_id: int) -> list[dict]:
        r = (self.client.table("booking")
             .select("equipment_id, equipment(name)")
             .eq("student_id", student_id)
             .order("id")
             .execute())
        return [{"equipment_id": row["equipment_id"], "name": row["equipment"]["name"]} for row in r.data]

    def search_equipment(self, text: str, limit: int = 5) -> list[dict]:
        like = f"%{text.strip()}%"
        r = (self.client.table("equipment")
             .select("id, name, category, description, units_available, requires_training")
             .or_(f"name.ilike.{like},category.ilike.{like},description.ilike.{like}")
             .order("name")
             .limit(limit)
             .execute())
        return r.data

    def get_equipment(self, equipment_id: int) -> dict | None:
        r = self.client.table("equipment").select("*").eq("id", equipment_id).execute()
        return r.data[0] if r.data else None

    def count(self, table: str) -> int:
        r = self.client.table(table).select("*", count="exact").limit(0).execute()
        return r.count or 0

    def book(self, student_id: int, equipment_id: int) -> str:
        existing = (self.client.table("booking")
                    .select("id")
                    .eq("student_id", student_id)
                    .eq("equipment_id", equipment_id)
                    .execute())
        if existing.data:
            return "already_booked"

        equip = self.client.table("equipment").select("units_available, version").eq("id", equipment_id).execute()
        if not equip.data or equip.data[0]["units_available"] <= 0:
            return "no_units"

        version = equip.data[0]["version"]
        update = (self.client.table("equipment")
                  .update({"units_available": equip.data[0]["units_available"] - 1, "version": version + 1})
                  .eq("id", equipment_id)
                  .eq("version", version)
                  .execute())
        if not update.data:
            return "no_units"

        self.client.table("booking").insert({
            "student_id": student_id, "equipment_id": equipment_id, "created_at": self.clock()
        }).execute()
        return "booked"

    def record_notification(self, roll_no: str, message: str, dedupe_key: str) -> tuple[int, bool]:
        existing = self.client.table("notification").select("id").eq("dedupe_key", dedupe_key).execute()
        if existing.data:
            return existing.data[0]["id"], False
        r = self.client.table("notification").insert({
            "roll_no": roll_no, "message": message, "dedupe_key": dedupe_key, "created_at": self.clock()
        }).execute()
        return r.data[0]["id"], True

    def once(self, key: str, tool_name: str, effect: Callable[[], dict]) -> tuple[dict, bool]:
        existing = self.client.table("idempotency").select("result").eq("key", key).execute()
        if existing.data:
            return json.loads(existing.data[0]["result"]), False
        result = effect()
        self.client.table("idempotency").insert({
            "key": key, "tool_name": tool_name,
            "result": json.dumps(result, default=str), "created_at": self.clock()
        }).execute()
        return result, True
