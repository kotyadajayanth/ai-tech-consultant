"""Agent 5: Proposal + review. Only the executive summary is model-written. Everything with numbers or
commitments is assembled from data, so the proposal cannot disagree with the scope and estimate."""
from ..config import Settings
from ..llm import LLM, load_prompt
from ..models import Version
from .analyst import _count


async def build_proposal(llm: LLM, s: Settings, name: str, v: Version, usage: dict) -> str:
    active = [r for r in v.requirements if not r.removed]
    facts = {"project": name, "requirements": [r.description for r in active if r.feasibility != "needs_clarification"],
             "unverified_requirements": [r.description for r in active if r.feasibility == "needs_clarification"], "client_facts": v.facts}
    res = await llm.complete_json(role="proposal_summary", system=load_prompt(s.prompt_version, "proposal_summary"),
                                  user=f"<facts>{facts}</facts>", model=s.fast_model)
    _count(usage, res)
    t = v.totals
    L = [f"# Proposal: {name}", "", "## Executive summary", res.data.get("summary", ""), "", "## Scope and deliverables"]
    L += [f"- **{r.id}** {r.description} — {r.feasibility.replace('_', ' ')}" for r in active if r.feasibility != "needs_clarification"]
    pending = [r for r in active if r.feasibility == "needs_clarification"]
    if pending:
        L += ["", "## Not yet confirmed (not included as commitments)"] + [f"- {r.id} {r.description}: {r.feasibility_note}" for r in pending]
    L += ["", "## Estimated effort", f"Total: **{t.get('likely', 0)} hours** most likely (range {t.get('low', 0)}–{t.get('high', 0)} h).",
          "| Requirement | Low | Likely | High |", "|---|---|---|---|"]
    for r in active:
        if r.tasks:
            L.append(f"| {r.id}{' (needs review)' if r.needs_estimate_review else ''} | {sum(x.low for x in r.tasks)} | {sum(x.likely for x in r.tasks)} | {sum(x.high for x in r.tasks)} |")
    if v.price_estimate is not None:
        L.append(f"\nIndicative price at the configured rate: {v.price_estimate} {v.currency}. This is an estimate, not a quote, until approved.")
    L += ["", "## Timeline", v.facts.get("delivery_date") and f"Client-requested delivery: {v.facts['delivery_date']}. Not confirmed by us until estimates are approved."
          or "No delivery date has been agreed."]
    L += ["", "## Exclusions and risks"] + [f"- {x}" for x in v.scope.get("exclusions", []) + v.scope.get("risks", [])]
    L += ["", "## Open questions"] + [f"- {q}" for q in v.open_questions]
    if v.change_report:
        L += ["", "## What changed since the approved scope", _changes_md(v.change_report)]
    L += ["", "## Next steps", "1. Client confirms the open questions.", "2. We confirm the estimate.", "3. Both sides approve the scope."]
    return "\n".join(L)


def _changes_md(c: dict) -> str:
    out = []
    for k, label in (("added", "Added"), ("modified", "Modified"), ("removed", "Removed")):
        out += [f"- {label}: {i['id']} {i['description']}" for i in c.get(k, [])]
    out += [f"- Out of scope vs approved baseline (quote separately): {', '.join(c.get('out_of_scope_ids', [])) or 'none'}"]
    out += [f"- {f['key'].replace('_', ' ')} changed: “{f['old']}” → “{f['new']}”" for f in c.get("facts_changed", [])]
    return "\n".join(out)
