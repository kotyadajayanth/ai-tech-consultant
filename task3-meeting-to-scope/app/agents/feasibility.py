"""Agent 2: Product Feasibility. Asks Task 1 (over its API) what the product already does."""
import asyncio

from ..config import Settings
from ..kb_client import KnowledgeClient, KnowledgeUnavailable
from ..llm import LLM, load_prompt
from ..models import Requirement
from .analyst import _count


async def _check(llm: LLM, kb: KnowledgeClient, s: Settings, r: Requirement, usage: dict) -> None:
    try:
        k = await kb.query(f"Does the product already support this, and how? {r.description}")
    except KnowledgeUnavailable as e:
        r.feasibility, r.feasibility_note = "needs_clarification", f"Knowledge service unavailable ({e}); not checked."
        return
    r.evidence_urls = [x["url"] for x in k.get("sources", [])][:5]
    if k.get("status") != "answered":
        # No evidence is NOT proof the feature is missing: ask a human, never assume custom work.
        r.feasibility, r.feasibility_note = "needs_clarification", "Knowledge base has no confirmed answer; ask a product expert."
        return
    res = await llm.complete_json(role="feasibility", system=load_prompt(s.prompt_version, "feasibility"), model=s.fast_model,
                                  user=f"<requirement>{r.description}</requirement>\n<knowledge>{k['answer']}\nSources: {r.evidence_urls}</knowledge>")
    _count(usage, res)
    f = res.data.get("feasibility")
    r.feasibility = f if f in ("existing_configuration", "existing_with_limitation", "custom_development") else "needs_clarification"
    r.feasibility_note = str(res.data.get("reason", ""))[:400]


async def check_all(llm: LLM, kb: KnowledgeClient, s: Settings, reqs: list[Requirement], usage: dict) -> None:
    await asyncio.gather(*(_check(llm, kb, s, r, usage) for r in reqs if not r.removed))
