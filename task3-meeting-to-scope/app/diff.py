"""Compare a new meeting's requirements with the APPROVED baseline (by stable requirement id)."""
import re

from .models import Requirement, Version


def _n(s: str) -> str:
    return re.sub(r"\W+", " ", s.lower()).strip()


def compare(baseline: Version, new_reqs: list[Requirement], new_facts: dict[str, str]) -> dict:
    old = {r.id: r for r in baseline.requirements}
    added, modified, removed = [], [], []
    for r in new_reqs:
        o = old.get(r.id)
        item = {"id": r.id, "description": r.description}
        if o is None:
            if not r.removed:
                added.append(item)
        elif r.removed and not o.removed:
            removed.append(item)
        elif not r.removed and (_n(o.description) != _n(r.description) or o.priority != r.priority or o.status != r.status):
            modified.append({**item, "before": o.description, "priority_before": o.priority, "priority_after": r.priority})
    keys = set(baseline.facts) | set(new_facts)
    facts_changed = [{"key": k, "old": baseline.facts.get(k, ""), "new": new_facts.get(k, "")} for k in sorted(keys)
                     if _n(baseline.facts.get(k, "")) != _n(new_facts.get(k, ""))]
    # Anything new or changed is outside what the client approved, so it needs a fresh estimate and a separate quote.
    return {"added": added, "modified": modified, "removed": removed, "facts_changed": facts_changed,
            "out_of_scope_ids": [i["id"] for i in added + modified], "baseline_version": baseline.number}
