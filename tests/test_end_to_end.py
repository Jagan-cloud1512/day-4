"""The whole thing: queue, worker, supervisor, specialists, crash, replay."""
import pytest

from app.providers import demo_providers
from app.worker import Worker
from tests.conftest import SimulatedCrash

PRIYA = "Is an oscilloscope available? If it is, book it for me and send me a text."


def ask(store, roll_no, text):
    thread = store.create_thread(roll_no)
    return thread, store.enqueue(thread, text, "mock")


def test_a_question_goes_all_the_way_through(store, db):
    thread, run_id = ask(store, "22CS045", PRIYA)
    assert Worker(store, db, demo_providers(), worker_id="w").run_until_idle() == [(run_id, "succeeded")]
    run = store.get_run(run_id)
    assert [s["tool_name"] for s in run["steps"] if s["kind"] == "tool"] == ["ask_inventory", "ask_booking"]
    assert "booked" in store.load_history(thread)[-1]["text"].lower() or \
           "confirmation" in store.load_history(thread)[-1]["text"].lower()
    assert db.count("booking") == 2 and db.count("notification") == 1


def test_policy_refusal_is_a_normal_answer(store, db):
    thread, run_id = ask(store, "22IT017", "Can I book an Arduino Mega Kit?")
    Worker(store, db, demo_providers(), worker_id="w").run_until_idle()
    assert store.get_run(run_id)["status"] == "succeeded"
    assert "Rs 75" in store.load_history(thread)[-1]["text"] or "fine" in store.load_history(thread)[-1]["text"].lower()
    assert db.count("booking") == 1 and db.count("notification") == 0


def test_crash_inside_a_specialist_after_the_booking_does_not_duplicate_it(store, db, clock):
    _, run_id = ask(store, "22CS045", PRIYA)
    real_once = db.once

    def once_then_die(key, tool_name, effect):
        result = real_once(key, tool_name, effect)
        if tool_name == "book_equipment":
            raise SimulatedCrash()
        return result

    db.once = once_then_die
    with pytest.raises(SimulatedCrash):
        Worker(store, db, demo_providers(), worker_id="A", lease_seconds=30).run_once()
    db.once = real_once
    assert db.count("booking") == 2 and store.get_run(run_id)["status"] == "running"

    clock.advance(31)
    assert Worker(store, db, demo_providers(), worker_id="B", lease_seconds=30).run_until_idle() == [(run_id, "succeeded")]
    assert db.count("booking") == 2 and db.count("notification") == 1
    assert db.get_equipment(1)["units_available"] == 2 and store.get_run(run_id)["attempts"] == 2


def test_asking_twice_still_one_booking(store, db):
    for _ in range(2):
        ask(store, "22CS045", PRIYA)
    Worker(store, db, demo_providers(), worker_id="w").run_until_idle()
    assert db.count("booking") == 2 and db.count("notification") == 1
