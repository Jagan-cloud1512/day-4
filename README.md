# Lab Equipment Booking Assistant

An end-to-end multi-agent system for campus lab equipment booking. A student asks a question in
plain English. A **supervisor** agent delegates to two **specialist** agents: an inventory
specialist that can only look, and a booking specialist that can book equipment and send texts.
The run is a job on a queue, and a worker that dies halfway through doesn't book the equipment
twice.

## System Architecture

```
student ─▶ queue (agent.db) ─▶ worker ─▶ supervisor ──ask_inventory──▶ inventory agent ─▶ search_equipment, get_equipment
                                                     └─ask_booking───▶ booking agent ──▶ get_student, check_can_book,
                                                                                          book_equipment*, notify_student*
                                                                            * side effects: run once per key
```

### Component Details

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                           Lab Equipment Booking System                       │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────┐    ┌───────────┐    ┌────────────────────────────────────────┐  │
│  │ Student  │───▶│  Queue    │───▶│           Worker                      │  │
│  │ (ask.py) │    │ (agent.db)│    │  ┌──────────────────────────────────┐ │  │
│  └─────────┘    └───────────┘    │  │       Supervisor Agent           │ │  │
│                                   │  │  (delegates only, no tools)      │ │  │
│                                   │  └────┬───────────────────┬────────┘ │  │
│                                   │       │                   │          │  │
│                                   │  ┌────▼─────────┐  ┌─────▼────────┐ │  │
│                                   │  │  Inventory   │  │   Booking    │ │  │
│                                   │  │  Specialist  │  │  Specialist  │ │  │
│                                   │  │  (read-only) │  │ (read+write) │ │  │
│                                   │  │              │  │  bound to    │ │  │
│                                   │  │ search_equip │  │  one student │ │  │
│                                   │  │ get_equip    │  │              │ │  │
│                                   │  └──────────────┘  │ get_student  │ │  │
│                                   │                     │ check_can_bk │ │  │
│                                   │                     │ book_equip*  │ │  │
│                                   │                     │ notify_stud* │ │  │
│                                   │                     └──────────────┘ │  │
│                                   └──────────────────────────────────────┘  │
│                                                                              │
│  ┌──────────────────┐  ┌──────────────────┐                                 │
│  │  equipment.db     │  │  agent.db         │                                │
│  │  ────────────     │  │  ────────         │                                │
│  │  student          │  │  thread           │                                │
│  │  training         │  │  message          │                                │
│  │  equipment        │  │  run (queue)      │                                │
│  │  booking          │  │  run_step         │                                │
│  │  policy           │  │  tool_call        │                                │
│  │  notification     │  │                   │                                │
│  │  idempotency      │  │                   │                                │
│  └──────────────────┘  └──────────────────┘                                 │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Key Design Choices

| Concept | Implementation |
|---|---|
| **Two databases** | `equipment.db` (domain data) and `agent.db` (memory + queue) |
| **Six tools** | 2 read-only (search, get) + 4 booking (get_student, check, book, notify) |
| **Business rules in data** | `policy` table: max_fine_to_book, max_active_bookings; `training` table for cert requirements |
| **Queue + worker** | Lease-based; dead worker's run is picked up by another |
| **Idempotency** | Every side effect runs through `EquipmentDb.once`; booking and notification are also safe to repeat on their own |
| **Multi-agent** | Supervisor delegates to inventory (no write tools) and booking (bound to one student) |
| **LLM Provider** | Groq (llama-3.3-70b-versatile) or Gemini; scripted mocks for tests/demo |

## Run it (no API key needed)

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python -m scripts.demo            # two questions, scripted models, every step printed
python -m scripts.demo --crash    # the worker dies right after booking; a second worker finishes: PASS
pytest                            # 12+ tests, under a second
```

## With Groq (set your API key)

```bash
export GROQ_API_KEY=your-key-here          # Windows: set GROQ_API_KEY=your-key-here

python -m scripts.demo --real                                      # same questions, real models
python -m scripts.worker                                           # terminal 1
python -m scripts.ask --student 22CS045 "Do you have an oscilloscope?"   # terminal 2
```

With Gemini instead (`export GEMINI_API_KEY=...`):

```bash
python -m scripts.demo --real
```

If `GROQ_API_KEY` is set, Groq is used. Otherwise falls back to Gemini.

## Seed Data

| Student | Fine | Max bookings | Training | What happens |
|---|---|---|---|---|
| 22CS045 Priya Raman | Rs 0 | 2 | electronics, 3dprinting | Can book |
| 22IT017 Arjun Kumar | Rs 75 | 2 | none | Refused: fine above Rs 50 policy |
| 22EC031 Divya Sekar | Rs 0 | 1 | electronics | Refused: already holds 1 booking |

Equipment: 1 Oscilloscope (3 units, needs electronics), 2 Arduino Mega (4 of 5 on shelf),
3 3D Printer Prusa (1 unit, needs 3dprinting), 4 Raspberry Pi 5 (4 units),
5 Logic Analyzer (2 units, needs electronics), 6 Soldering Station (0 on shelf, needs electronics).

## Where each requirement shows up

| Requirement | Where to look |
|---|---|
| Two SQLite databases | `schema/equipment.sql`, `schema/agent.sql` |
| Five+ tools with descriptions | `app/tools/equipment_tools.py` (6 tools, 120+ char docstrings) |
| Business rule in data | `policy` table + `training` table; `check_can_book` enforces even if model skips |
| Queue and worker | `app/memory.py`, `app/worker.py`, `app/runner.py` |
| Idempotency | `EquipmentDb.once`, `EquipmentDb.book` (safe to repeat), `record_notification` (dedupe) |
| Two+ agents | Supervisor → inventory specialist (read-only) + booking specialist (write) |
| Proof without key | `python -m scripts.demo`, `python -m scripts.demo --crash` prints PASS, `pytest` |
| Groq real-model run | `python -m scripts.demo --real` with GROQ_API_KEY set |

## Supabase Support

For cloud deployment, set `USE_SUPABASE=1` with `SUPABASE_URL` and `SUPABASE_KEY`.
Run `schema/supabase_library.sql` and `schema/supabase_agent.sql` in the Supabase SQL Editor
to create tables and seed data.
