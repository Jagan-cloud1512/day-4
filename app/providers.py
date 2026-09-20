"""Model providers. The agent only knows `generate`. (Given.)"""
from dataclasses import dataclass, field
from typing import Any


class AgentError(Exception):
    """A run could not finish. `retryable` says whether trying again later could work."""

    def __init__(self, code: str, message: str, retryable: bool = False):
        super().__init__(message)
        self.code, self.message, self.retryable = code, message, retryable


@dataclass
class ToolCall:
    name: str
    args: dict


@dataclass
class ModelTurn:
    text: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    raw: Any = None


class GeminiProvider:
    def __init__(self, model: str):
        from google import genai

        self.client = genai.Client()
        self.model = model

    def _to_gemini(self, contents: list[dict]):
        from google.genai import types

        out: list = []
        for c in contents:
            if c["role"] == "user":
                out.append(types.Content(role="user", parts=[types.Part.from_text(text=c["text"])]))
            elif c["role"] == "model":
                if c.get("raw") is not None:
                    out.append(c["raw"])
                    continue
                parts = [types.Part.from_text(text=c["text"])] if c.get("text") else []
                parts += [types.Part.from_function_call(name=t["name"], args=t["args"])
                          for t in c.get("tool_calls", [])]
                out.append(types.Content(role="model", parts=parts))
            elif c["role"] == "tool":
                part = types.Part.from_function_response(name=c["name"], response=c["result"])
                if out and out[-1].role == "user" and all(p.function_response for p in out[-1].parts):
                    out[-1].parts.append(part)
                else:
                    out.append(types.Content(role="user", parts=[part]))
        return out

    def generate(self, system: str, contents: list[dict], tools: list) -> ModelTurn:
        from google.genai import errors, types

        config = types.GenerateContentConfig(
            system_instruction=system,
            tools=tools,
            temperature=0,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        try:
            resp = self.client.models.generate_content(
                model=self.model, contents=self._to_gemini(contents), config=config)
        except errors.APIError as e:
            if e.code == 429:
                raise AgentError("provider_rate_limited", "Model quota exhausted. Wait a minute.", True) from e
            if e.code and e.code >= 500:
                raise AgentError("provider_unavailable", "Model provider failed.", True) from e
            raise AgentError("provider_error", str(e), False) from e

        content = resp.candidates[0].content if resp.candidates else None
        parts = (content.parts or []) if content else []
        text = "".join(p.text for p in parts if p.text and not p.thought) or None
        calls = [ToolCall(fc.name, dict(fc.args or {})) for fc in (resp.function_calls or [])]
        usage = resp.usage_metadata
        return ModelTurn(text=text, tool_calls=calls,
                         tokens_in=(usage.prompt_token_count or 0) if usage else 0,
                         tokens_out=(usage.candidates_token_count or 0) if usage else 0,
                         raw=content)


class GroqProvider:
    def __init__(self, model: str):
        import os
        from groq import Groq

        self.client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
        self.model = model

    def _build_tools(self, functions: list) -> list[dict]:
        import inspect
        import typing

        tools = []
        for fn in functions:
            hints = typing.get_type_hints(fn)
            sig = inspect.signature(fn)
            props, required = {}, []
            for name, param in sig.parameters.items():
                ann = hints.get(name)
                json_type = "string"
                if ann is int:
                    json_type = "integer"
                elif ann is float:
                    json_type = "number"
                elif ann is bool:
                    json_type = "boolean"
                props[name] = {"type": json_type}
                if param.default is inspect.Parameter.empty:
                    required.append(name)
            tools.append({
                "type": "function",
                "function": {
                    "name": fn.__name__,
                    "description": (inspect.getdoc(fn) or "")[:1024],
                    "parameters": {"type": "object", "properties": props, "required": required},
                },
            })
        return tools

    def _to_messages(self, system: str, contents: list[dict]) -> list[dict]:
        msgs = [{"role": "system", "content": system}]
        for c in contents:
            if c["role"] == "user":
                msgs.append({"role": "user", "content": c["text"]})
            elif c["role"] == "model":
                msg = {"role": "assistant"}
                if c.get("text"):
                    msg["content"] = c["text"]
                calls = c.get("tool_calls", [])
                if calls:
                    msg["tool_calls"] = [
                        {"id": f"call_{i}", "type": "function",
                         "function": {"name": tc["name"],
                                      "arguments": __import__("json").dumps(tc["args"])}}
                        for i, tc in enumerate(calls)
                    ]
                    if "content" not in msg:
                        msg["content"] = ""
                msgs.append(msg)
            elif c["role"] == "tool":
                import json as _json
                msgs.append({"role": "tool", "tool_call_id": f"call_{self._find_call_index(msgs, c['name'])}",
                              "content": _json.dumps(c["result"], default=str)})
        return msgs

    @staticmethod
    def _find_call_index(msgs: list[dict], tool_name: str) -> int:
        for msg in reversed(msgs):
            for i, tc in enumerate(msg.get("tool_calls") or []):
                if tc["function"]["name"] == tool_name:
                    return i
        return 0

    def generate(self, system: str, contents: list[dict], tools: list) -> ModelTurn:
        import json as _json

        groq_tools = self._build_tools(tools) if tools else None
        messages = self._to_messages(system, contents)
        try:
            resp = self.client.chat.completions.create(
                model=self.model, messages=messages, tools=groq_tools,
                tool_choice="auto" if groq_tools else None, temperature=0, max_tokens=2048)
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "rate" in err_str.lower():
                raise AgentError("provider_rate_limited", "Groq quota exhausted. Wait a minute.", True) from e
            if "500" in err_str or "503" in err_str:
                raise AgentError("provider_unavailable", "Groq provider failed.", True) from e
            raise AgentError("provider_error", err_str, False) from e

        choice = resp.choices[0]
        text = choice.message.content or None
        calls = []
        for tc in choice.message.tool_calls or []:
            args = _json.loads(tc.function.arguments) if tc.function.arguments else {}
            calls.append(ToolCall(tc.function.name, args))
        usage = resp.usage
        return ModelTurn(text=text, tool_calls=calls,
                         tokens_in=usage.prompt_tokens if usage else 0,
                         tokens_out=usage.completion_tokens if usage else 0)


class ScriptedProvider:
    """Replays a fixed list of turns in call order. No network, no quota. Used by the tests."""

    model = "mock"

    def __init__(self, script: list, loop: bool = False):
        self.original, self.script, self.loop = list(script), list(script), loop
        self.calls: list[list[dict]] = []

    def generate(self, system: str, contents: list[dict], tools: list) -> ModelTurn:
        self.calls.append([dict(c) for c in contents])
        if not self.script and self.loop:
            self.script = list(self.original)
        if not self.script:
            return ModelTurn(text="(mock) script exhausted")
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


class PositionalMock:
    model = "mock"

    def __init__(self, turns: list[ModelTurn], slow: float = 0.0):
        self.turns, self.slow = turns, slow
        self.calls: list[list[dict]] = []

    def generate(self, system: str, contents: list[dict], tools: list) -> ModelTurn:
        import time

        self.calls.append([dict(c) for c in contents])
        last_user = max(i for i, c in enumerate(contents) if c["role"] == "user")
        position = sum(1 for c in contents[last_user:] if c["role"] == "model")
        if self.slow:
            time.sleep(self.slow)
        if position >= len(self.turns):
            return ModelTurn(text="(mock) nothing more to do.")
        return self.turns[position]


class RoutedMock:
    """Several scripted conversations in one mock: picks a script by a phrase in the current request,
    then answers by position (like PositionalMock). Used by the demo and the tests."""

    model = "mock"

    def __init__(self, routes: dict[str, list[ModelTurn]], slow: float = 0.0):
        self.routes, self.slow = routes, slow
        self.calls: list[list[dict]] = []

    def generate(self, system: str, contents: list[dict], tools: list) -> ModelTurn:
        import time

        self.calls.append([dict(c) for c in contents])
        last_user = max(i for i, c in enumerate(contents) if c["role"] == "user")
        request = contents[last_user]["text"]
        position = sum(1 for c in contents[last_user:] if c["role"] == "model")
        if self.slow:
            time.sleep(self.slow)
        for phrase, turns in self.routes.items():
            if phrase.lower() in request.lower():
                return turns[position] if position < len(turns) else ModelTurn(text="(mock) done.")
        return ModelTurn(text="(mock) I have no script for that request.")


def _call(name, **args):
    return ModelTurn(text=None, tool_calls=[ToolCall(name, args)], tokens_in=100, tokens_out=10)


def demo_providers(slow: float = 0.0) -> dict:
    """Scripted models for the three agents, covering the two demo questions."""
    return {
        "supervisor": RoutedMock({
            "oscilloscope": [
                _call("ask_inventory", question="Is there an oscilloscope available?"),
                _call("ask_booking", request="Book equipment 1 (Oscilloscope DSO-X2000) and send the student a confirmation."),
                ModelTurn(text="(mock) Great news! The oscilloscope is available and has been booked for you. A confirmation has been sent."),
            ],
            "Arduino": [
                _call("ask_inventory", question="Find Arduino Mega Kit"),
                _call("ask_booking", request="Book equipment 2 (Arduino Mega Kit) for the student."),
                ModelTurn(text="(mock) The Arduino Mega Kit is on the shelf, but you can't book it: your fine of Rs 75 exceeds the Rs 50 limit."),
            ],
        }, slow),
        "inventory": RoutedMock({
            "oscilloscope": [_call("search_equipment", text="oscilloscope"),
                             ModelTurn(text="(mock) Equipment 1, Oscilloscope DSO-X2000: 3 units available. Requires electronics training.")],
            "Arduino": [_call("search_equipment", text="Arduino"),
                        ModelTurn(text="(mock) Equipment 2, Arduino Mega Kit: 5 units available. No training required.")],
        }, slow),
        "booking": RoutedMock({
            "Book equipment 1": [
                _call("check_can_book", equipment_id=1),
                ModelTurn(text=None, tool_calls=[
                    ToolCall("book_equipment", {"equipment_id": 1}),
                    ToolCall("notify_student", {"message": "Your booking for Oscilloscope DSO-X2000 is confirmed."})],
                    tokens_in=150, tokens_out=25),
                ModelTurn(text="(mock) Booked equipment 1 and sent the confirmation."),
            ],
            "Book equipment 2": [
                _call("check_can_book", equipment_id=2),
                ModelTurn(text="(mock) Not booked: the student's fine of Rs 75 is above the Rs 50 limit."),
            ],
        }, slow),
    }
