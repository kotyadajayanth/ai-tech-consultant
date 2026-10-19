"""Agent 1: Transcript Analyst. Long transcripts are processed in parts, then merged."""
import re

from ..config import Settings
from ..llm import LLM, load_prompt
from ..models import Meeting, Requirement


def split_transcript(text: str, max_chars: int = 6000, overlap_lines: int = 3) -> list[str]:
    """Split on line boundaries (speaker turns), keeping a few lines of overlap so context is not cut."""
    lines = [l for l in text.splitlines() if l.strip()]
    parts, cur, size = [], [], 0
    for line in lines:
        if cur and size + len(line) > max_chars:
            parts.append("\n".join(cur))
            cur = cur[-overlap_lines:]
            size = sum(len(x) for x in cur)
        cur.append(line)
        size += len(line)
    if cur:
        parts.append("\n".join(cur))
    return parts or [""]


def _norm(s: str) -> str:
    return re.sub(r"\W+", " ", s.lower()).strip()


def quote_is_real(quote: str, transcript: str) -> bool:
    """The reviewer must be able to trust a quote: it has to be in the source text."""
    return bool(quote.strip()) and _norm(quote) in _norm(transcript)


def _next_id(existing: list[str]) -> str:
    nums = [int(m.group(1)) for i in existing if (m := re.match(r"REQ-(\d+)$", i))]
    return f"REQ-{(max(nums) + 1 if nums else 1):03d}"


async def analyze(llm: LLM, s: Settings, meeting: Meeting, baseline: list[Requirement] | None, usage: dict):
    """Returns (requirements for the new version, facts, open_questions)."""
    parts = split_transcript(meeting.text, s.chunk_chars)
    extracted = []
    for p in parts:
        r = await llm.complete_json(role="analyst_extract", system=load_prompt(s.prompt_version, "analyst_extract"),
                                    user=f"<transcript_part>\n{p}\n</transcript_part>", model=s.main_model)
        _count(usage, r)
        extracted.append(r.data)
    if len(extracted) == 1 and not baseline:
        merged = extracted[0]                      # nothing to merge: save a model call
    else:
        base = [{"id": b.id, "description": b.description, "priority": b.priority, "status": b.status} for b in baseline or []]
        r = await llm.complete_json(role="analyst_merge", system=load_prompt(s.prompt_version, "analyst_merge"),
                                    user=f"<extracted>{extracted}</extracted>\n<baseline>{base}</baseline>", model=s.main_model)
        _count(usage, r)
        merged = r.data
    reqs: dict[str, Requirement] = {b.id: b.model_copy(deep=True) for b in baseline or []}
    for item in merged.get("requirements", []):
        rid = item.get("id")
        if rid not in reqs:                         # unknown or null id => a new requirement
            rid = _next_id(list(reqs))
            reqs[rid] = Requirement(id=rid, description=item.get("description", "").strip() or "(empty)")
        r_ = reqs[rid]
        r_.description = item.get("description", r_.description).strip() or r_.description
        r_.status = item.get("status") if item.get("status") in ("confirmed", "unclear", "disputed") else "unclear"
        r_.priority = item.get("priority") if item.get("priority") in ("must", "should", "optional") else "should"
        r_.origin = "inferred" if item.get("origin") == "inferred" else "explicit"
        r_.removed = bool(item.get("removed", False))
        r_.dependencies = [d for d in item.get("dependencies", []) if isinstance(d, str)]
        q = item.get("quote", "")
        r_.quote, r_.quote_verified = q, quote_is_real(q, meeting.text)
        r_.speaker, r_.meeting_id = item.get("speaker", ""), meeting.id
    facts = {k: v for k, v in (merged.get("facts") or {}).items() if isinstance(v, str) and v.strip()}
    return list(reqs.values()), facts, [q for q in merged.get("open_questions", []) if isinstance(q, str)]


def _count(usage: dict, r) -> None:
    usage["input_tokens"] = usage.get("input_tokens", 0) + r.input_tokens
    usage["output_tokens"] = usage.get("output_tokens", 0) + r.output_tokens
    usage["llm_calls"] = usage.get("llm_calls", 0) + 1
