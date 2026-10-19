"""Thin wrapper around Claude so the rest of the code (and the tests) never touch the SDK."""
import base64
import json
import re
import time
from dataclasses import dataclass
from typing import Protocol


@dataclass
class JsonResult:
    data: dict
    input_tokens: int = 0
    output_tokens: int = 0
    latency_s: float = 0.0
    model: str = ""


class LLM(Protocol):
    async def complete_json(self, *, system: str, user: str, model: str, max_tokens: int = 1000) -> JsonResult: ...
    async def describe_image(self, *, image: bytes, media_type: str, context: str, model: str) -> str: ...


def parse_json(text: str) -> dict:
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("model did not return JSON")
    return json.loads(text[start : end + 1])


class ClaudeLLM:
    def __init__(self) -> None:
        from anthropic import AsyncAnthropic  # reads ANTHROPIC_API_KEY from the environment
        self._c = AsyncAnthropic()

    async def complete_json(self, *, system: str, user: str, model: str, max_tokens: int = 1000) -> JsonResult:
        t0 = time.perf_counter()
        r = await self._c.messages.create(model=model, max_tokens=max_tokens, system=system,
                                          messages=[{"role": "user", "content": user}])
        text = "".join(b.text for b in r.content if b.type == "text")
        return JsonResult(parse_json(text), r.usage.input_tokens, r.usage.output_tokens,
                          time.perf_counter() - t0, model)

    async def describe_image(self, *, image: bytes, media_type: str, context: str, model: str) -> str:
        prompt = ("This is a screenshot from a software help-center article. Context: " + context +
                  "\nList the visible interface labels, buttons, settings and values that a user would need, "
                  "in 2-4 short sentences. If something is unreadable, say 'unclear' instead of guessing.")
        r = await self._c.messages.create(model=model, max_tokens=400, messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": media_type,
                                         "data": base64.b64encode(image).decode()}},
            {"type": "text", "text": prompt}]}])
        return "".join(b.text for b in r.content if b.type == "text").strip()
