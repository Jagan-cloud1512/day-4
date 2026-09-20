"""Tools, rules in data, and writes that are safe to repeat."""
import inspect

import pytest

from app.tools.equipment_tools import BookingTools, InventoryTools


@pytest.mark.parametrize("cls", [InventoryTools, BookingTools])
def test_every_tool_is_described(cls):
    for name in cls.TOOL_NAMES:
        assert len(inspect.getdoc(getattr(cls, name)) or "") >= 120, name


def test_search_and_availability(db):
    items = InventoryTools(db).search_equipment("oscilloscope")["equipment"]
    assert [e["equipment_id"] for e in items] == [1] and items[0]["units_available"] == 3
    assert InventoryTools(db).search_equipment("  ")["error"] == "empty_query"


def test_policy_comes_from_the_database(db):
    arjun = BookingTools(db, "22IT017")
    result = arjun.check_can_book(2)
    assert result == {"can_book": False, "reasons": ["fine due Rs 75 is above the Rs 50 limit"]}
    db.conn.execute("UPDATE policy SET value = 100 WHERE name = 'max_fine_to_book'")
    assert arjun.check_can_book(2)["can_book"] is True


def test_booking_limit(db):
    assert BookingTools(db, "22EC031").check_can_book(4)["reasons"] == [
        "already holds 1 of 1 allowed bookings"]


def test_training_requirement_enforced(db):
    result = BookingTools(db, "22IT017").check_can_book(1)
    assert "requires electronics training certification" in result["reasons"]


def test_book_refuses_when_policy_says_no_even_if_model_skips_check(db):
    assert BookingTools(db, "22IT017").book_equipment(2)["error"] == "not_allowed"
    assert db.count("booking") == 1


def test_booking_twice_is_not_an_error(db):
    desk = BookingTools(db, "22CS045")
    assert desk.book_equipment(1)["status"] == "booked"
    assert desk.book_equipment(1)["status"] == "already_booked"
    assert db.get_equipment(1)["units_available"] == 2


def test_last_unit_goes_to_one_student(db):
    assert BookingTools(db, "22CS045").book_equipment(3)["status"] == "booked"
    db.conn.execute("UPDATE student SET max_bookings = 3 WHERE roll_no = '22EC031'")
    db.conn.execute("INSERT INTO training (student_id, category, certified_at) VALUES (3, '3dprinting', 1700300000.0)")
    assert BookingTools(db, "22EC031").book_equipment(3)["error"] == "no_units"


def test_same_text_same_day_is_sent_once(db):
    desk = BookingTools(db, "22CS045")
    first, second = desk.notify_student("Booked."), desk.notify_student("Booked.")
    assert first["notification_id"] == second["notification_id"] and second["duplicate"] is True


def test_the_desk_cannot_act_for_another_student(db):
    params = {n: list(inspect.signature(getattr(BookingTools, n)).parameters) for n in BookingTools.TOOL_NAMES}
    assert all("roll_no" not in p for p in params.values())


def test_search_multiple_results(db):
    items = InventoryTools(db).search_equipment("electronics")["equipment"]
    assert len(items) >= 3


def test_get_equipment_unknown(db):
    assert InventoryTools(db).get_equipment(999)["error"] == "unknown_equipment"
