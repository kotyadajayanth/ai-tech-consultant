"""Agent 3: Scope. Model writes the narrative parts; the 'agreed requirements' table comes from data, not the model."""
from ..config import Settings
from ..llm import LLM, load_prompt
from ..models import Requirement
from .analyst import _count


async def build_scope(llm: LLM, s: Settings, reqs: list[Requirement], facts: dict, questions: list[str], usage: dict,
                      update_ids: set[str] | None = None) -> dict:
    active = [r for r in reqs if not r.removed]
    payload = [{"id": r.id, "description": r.description, "status": r.status, "priority": r.priority,
                "feasibility": r.feasibility, "note": r.feasibility_note} for r in active]
    res = await llm.complete_json(role="scope", system=load_prompt(s.prompt_version, "scope"), model=s.main_model,
                                  user=f"<requirements>{payload}</requirements>\n<facts>{facts}</facts>\n<open_questions>{questions}</open_questions>")
    _count(usage, res)
    d = res.data
    known = {r.id for r in active}
    for rid, crit in (d.get("acceptance") or {}).items():
        r = next((x for x in active if x.id == rid), None)
        if r and isinstance(crit, list) and (update_ids is None or rid in update_ids):  # approved criteria stay untouched
            r.acceptance_criteria = [str(c) for c in crit][:5]
    d["deliverables"] = [x for x in d.get("deliverables", []) if isinstance(x, dict)]
    for x in d["deliverables"]:
        x["requirement_ids"] = [i for i in x.get("requirement_ids", []) if i in known]   # no invented ids
    return d


def render_scope_md(project_name: str, reqs: list[Requirement], facts: dict, scope: dict, questions: list[str]) -> str:
    L = [f"# Scope of Work: {project_name}", "", "## 1. Objective", scope.get("objective", ""), "", "## 2. Current problem", scope.get("current_problem", ""), "",
         "## 3. Requirements (from the meetings)", "| ID | Requirement | Status | Priority | Source | Product check |", "|---|---|---|---|---|---|"]
    for r in reqs:
        if r.removed:
            continue
        src = ("“" + r.quote + "”" if r.quote_verified else "(no verified quote)") + (" [inferred]" if r.origin == "inferred" else "")
        L.append(f"| {r.id} | {r.description} | {r.status} | {r.priority} | {src} | {r.feasibility.replace('_', ' ')} |")
    L += ["", "## 4. Proposed solution", scope.get("proposed_solution", ""), "", "## 5. Deliverables"]
    L += [f"- **{d.get('name', '')}** ({', '.join(d.get('requirement_ids', []))}): {d.get('verification', '')}" for d in scope.get("deliverables", [])]
    L += ["", "## 6. Exclusions"] + [f"- {x}" for x in scope.get("exclusions", [])]
    L += ["", "## 7. Assumptions and dependencies"] + [f"- {x}" for x in scope.get("assumptions", [])]
    L += [f"- Client-stated {k.replace('_', ' ')}: {v}" for k, v in facts.items()]
    L += ["", "## 8. Acceptance criteria (proposed, to be confirmed by the client)"]
    for r in reqs:
        if not r.removed and r.acceptance_criteria:
            L += [f"- {r.id}: " + "; ".join(r.acceptance_criteria)]
    L += ["", "## 9. Client responsibilities"] + [f"- {x}" for x in scope.get("client_responsibilities", [])]
    L += ["", "## 10. Open questions and risks"] + [f"- {x}" for x in questions + scope.get("risks", [])]
    return "\n".join(L)
