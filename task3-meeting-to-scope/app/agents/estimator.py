"""Agent 4: Estimation. The model proposes tasks; CODE validates and adds up the totals."""
from pydantic import ValidationError

from ..config import Settings
from ..llm import LLM, load_prompt
from ..models import EstTask, Requirement, Version
from .analyst import _count


async def estimate(llm: LLM, s: Settings, reqs: list[Requirement], usage: dict) -> None:
    todo = [r for r in reqs if not r.removed]
    if not todo:
        return
    payload = [{"id": r.id, "description": r.description, "feasibility": r.feasibility, "note": r.feasibility_note,
                "acceptance_criteria": r.acceptance_criteria} for r in todo]
    res = await llm.complete_json(role="estimator", system=load_prompt(s.prompt_version, "estimator"),
                                  user=f"<requirements>{payload}</requirements>", model=s.main_model)
    _count(usage, res)
    by_id = {e.get("requirement_id"): e for e in res.data.get("estimates", [])}
    for r in todo:
        e = by_id.get(r.id)
        r.tasks, r.needs_estimate_review = [], True        # default: a human must estimate it
        if not e:
            continue
        try:
            r.tasks = [EstTask(**t) for t in e.get("tasks", [])]
            r.needs_estimate_review = bool(e.get("needs_review")) or r.feasibility in ("needs_clarification", "unchecked") or not r.tasks
        except (ValidationError, TypeError):
            r.tasks, r.needs_estimate_review = [], True    # invalid numbers are dropped, not repaired silently


def totals(reqs: list[Requirement], rate: float, currency: str) -> tuple[dict, float | None]:
    tasks = [t for r in reqs if not r.removed for t in r.tasks]
    t = {"low": round(sum(x.low for x in tasks), 1), "likely": round(sum(x.likely for x in tasks), 1),
         "high": round(sum(x.high for x in tasks), 1),
         "requirements_needing_review": sum(1 for r in reqs if not r.removed and r.needs_estimate_review)}
    return t, (round(t["likely"] * rate, 2) if rate > 0 else None)


def set_totals(v: Version, rate: float) -> None:
    v.totals, v.price_estimate = totals(v.requirements, rate, v.currency)
