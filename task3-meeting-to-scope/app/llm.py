import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

PROMPTS = Path(__file__).resolve().parent.parent / "prompts"


@dataclass
class JsonResult:
    data: dict
    input_tokens: int = 0
    output_tokens: int = 0
    latency_s: float = 0.0


class LLM(Protocol):
    async def complete_json(self, *, role: str, system: str, user: str, model: str, max_tokens: int = 3000) -> JsonResult: ...


def load_prompt(version: str, role: str) -> str:
    """Prompts are versioned files: prompts/<version>/<role>.md"""
    return (PROMPTS / version / f"{role}.md").read_text(encoding="utf-8")


def parse_json(text: str) -> dict:
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    s, e = text.find("{"), text.rfind("}")
    if s == -1 or e == -1:
        raise ValueError("model did not return JSON")
    return json.loads(text[s:e + 1])


class ClaudeLLM:
    def __init__(self) -> None:
        from anthropic import AsyncAnthropic
        self._c = AsyncAnthropic()

    async def complete_json(self, *, role: str, system: str, user: str, model: str, max_tokens: int = 3000) -> JsonResult:
        t0 = time.perf_counter()
        last = ""
        for attempt in range(2):  # one retry with the validation error
            r = await self._c.messages.create(model=model, max_tokens=max_tokens, system=system,
                                              messages=[{"role": "user", "content": user if not last else f"{user}\n\nYour previous reply was invalid ({last}). Return valid JSON only."}])
            text = "".join(b.text for b in r.content if b.type == "text")
            try:
                return JsonResult(parse_json(text), r.usage.input_tokens, r.usage.output_tokens, time.perf_counter() - t0)
            except ValueError as e:
                last = str(e)[:150]
        raise RuntimeError(f"{role}: model output was not valid JSON twice")
