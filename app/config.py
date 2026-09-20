import os

from app.equipment_db import EquipmentDb
from app.memory import RunStore

AGENT_DB = os.environ.get("AGENT_DB", "agent.db")
EQUIPMENT_DB = os.environ.get("EQUIPMENT_DB", "equipment.db")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "qwen/qwen3.8-27b")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")


def open_stores() -> tuple[RunStore, EquipmentDb]:
    store, db = RunStore(AGENT_DB), EquipmentDb(EQUIPMENT_DB)
    store.migrate()
    db.migrate()
    return store, db


def make_providers(mock: bool, slow: float = 0.0) -> dict:
    """One provider per agent. With Groq all three share one client; each keeps its own prompt and tools."""
    if mock:
        from app.providers import demo_providers

        return demo_providers(slow)
    if os.environ.get("GROQ_API_KEY"):
        from app.providers import GroqProvider

        groq = GroqProvider(GROQ_MODEL)
        return {"supervisor": groq, "inventory": groq, "booking": groq}
    from app.providers import GeminiProvider

    gemini = GeminiProvider(GEMINI_MODEL)
    return {"supervisor": gemini, "inventory": gemini, "booking": gemini}
