"""A supervisor that delegates to two specialists."""
from app.agents import SupervisorTools, run_specialist, run_tool
from app.providers import ModelTurn, ScriptedProvider, ToolCall, demo_providers
from app.tools.equipment_tools import InventoryTools


def test_the_supervisor_only_has_delegation_tools(db):
    tools = SupervisorTools(db, demo_providers(), "22CS045")
    assert set(tools.functions()) == {"ask_inventory", "ask_booking"}
    assert set(tools.DELEGATES) == set(tools.TOOL_NAMES)


def test_inventory_specialist_answers_a_question(db):
    result, replayed = run_tool(SupervisorTools(db, demo_providers(), "22CS045"), db, "k1", "ask_inventory",
                                {"question": "Is there an oscilloscope available?"})
    assert result["agent"] == "inventory" and result["tools_used"] == ["search_equipment"] and not replayed
    assert "3 units" in result["answer"] or "available" in result["answer"].lower()


def test_booking_specialist_books_and_notifies_for_the_bound_student(db):
    result, _ = run_tool(SupervisorTools(db, demo_providers(), "22CS045"), db, "k1", "ask_booking",
                         {"request": "Book equipment 1 (Oscilloscope DSO-X2000) and send the student a confirmation."})
    assert result["tools_used"] == ["check_can_book", "book_equipment", "notify_student"]
    assert [b["equipment_id"] for b in db.active_bookings(1)] == [1]
    assert db.count("notification") == 1


def test_a_repeated_delegation_with_the_same_key_does_nothing_twice(db):
    tools = SupervisorTools(db, demo_providers(), "22CS045")
    args = {"request": "Book equipment 1 (Oscilloscope DSO-X2000) and send the student a confirmation."}
    run_tool(tools, db, "same-key", "ask_booking", args)
    run_tool(tools, db, "same-key", "ask_booking", args)
    assert db.count("booking") == 2 and db.count("notification") == 1 and db.count("idempotency") == 2


def test_bad_delegation_arguments_are_fed_back(db):
    result, _ = run_tool(SupervisorTools(db, demo_providers(), "22CS045"), db, "k", "ask_booking", {"request": ""})
    assert result["error"] == "invalid_arguments"


def test_a_looping_specialist_stops(db):
    looping = ScriptedProvider([ModelTurn(text=None, tool_calls=[ToolCall("search_equipment", {"text": "scope"})])], loop=True)
    result = run_specialist("inventory", "sys", InventoryTools(db), db=db, provider=looping, task="x", parent_key="k")
    assert result["error"] == "specialist_step_limit"


def test_specialists_see_only_their_own_task(db):
    providers = demo_providers()
    run_tool(SupervisorTools(db, providers, "22CS045"), db, "k", "ask_inventory",
             {"question": "Find oscilloscope"})
    seen = providers["inventory"].calls[0]
    assert seen == [{"role": "user", "text": "Find oscilloscope"}]
    assert providers["booking"].calls == []
