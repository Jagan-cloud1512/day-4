import json
import os
import sys

DIM, CYAN, YELLOW, RED, GREEN, MAGENTA, RESET = "\033[2m", "\033[36m", "\033[33m", "\033[31m", "\033[32m", "\033[35m", "\033[0m"
if os.name == "nt":
    os.system("")
    if sys.stdout.encoding and sys.stdout.encoding.lower().replace("-", "") != "utf8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ARROW_R = "->"
ARROW_L = "<-"


def short(obj, limit=130) -> str:
    text = json.dumps(obj, default=str)
    return text if len(text) <= limit else text[: limit - 3] + "..."


def print_step(step: dict) -> None:
    """Supervisor steps at the margin, specialist steps indented under the delegation that ran them."""
    agent = step.get("agent", "supervisor")
    if step["kind"] == "model":
        return
    if step["kind"] == "delegate":
        print(f"  {YELLOW}supervisor {ARROW_R} {step['tool']}{RESET}{DIM}({short(step['args'], 100)}){RESET}")
    elif agent == "supervisor":
        answer = step["result"].get("answer") or step["result"].get("error")
        colour = DIM if step["ok"] else RED
        print(f"  {colour}           {ARROW_L} {short(answer, 110)}{RESET}")
    else:
        colour = MAGENTA if step["ok"] else RED
        print(f"      {colour}{agent} {ARROW_R} {step['tool']}{RESET}{DIM}({short(step['args'], 80)}){RESET}")
        note = f"  {GREEN}[replayed: stored result, nothing done again]{RESET}" if step.get("replayed") else ""
        print(f"      {DIM}{' ' * len(agent)} {ARROW_L} {short(step['result'], 100)}{RESET}{note}")
