"""Orchestrates the 5 agents. Each stage has a defined input/output; the model never does arithmetic or approval."""
import datetime as dt

from .agents import analyst, estimator, feasibility, proposal, scope
from .config import Settings
from .diff import compare
from .kb_client import KnowledgeClient
from .llm import LLM
from .models import Project, Version
from .projects import ApprovalError, ProjectStore


async def run_meeting(llm: LLM, kb: KnowledgeClient, s: Settings, store: ProjectStore, p: Project, date: str, text: str) -> Version:
    baseline = p.baseline()
    if p.meetings and baseline is None:
        # Compare against an APPROVED baseline only; otherwise an unapproved AI draft could silently become the agreement.
        raise ApprovalError("approve the previous version before adding a follow-up meeting")
    meeting = store.add_meeting(p, date, text)
    usage: dict = {}
    reqs, facts, questions = await analyst.analyze(llm, s, meeting, baseline.requirements if baseline else None, usage)
    old = {r.id: r for r in (baseline.requirements if baseline else [])}
    changed_ids = None
    if baseline:
        diff = compare(baseline, reqs, {**baseline.facts, **facts})
        changed_ids = set(diff["out_of_scope_ids"])
        facts = {**baseline.facts, **facts}
    else:
        diff = None
    # only new/changed requirements are re-checked and re-estimated; the rest keep their approved numbers
    work = [r for r in reqs if not r.removed and (changed_ids is None or r.id in changed_ids)]
    await feasibility.check_all(llm, kb, s, work, usage)
    sc = await scope.build_scope(llm, s, reqs, facts, questions, usage, update_ids={w.id for w in work})
    await estimator.estimate(llm, s, work, usage)
    v = Version(number=len(p.versions) + 1, meeting_ids=[m.id for m in p.meetings], requirements=reqs, facts=facts,
                open_questions=questions, scope=sc, change_report=diff, currency=s.currency, usage=usage,
                prompt_version=s.prompt_version, created_at=dt.datetime.now(dt.timezone.utc).isoformat())
    estimator.set_totals(v, s.hourly_rate)
    v.scope_md = scope.render_scope_md(p.name, reqs, facts, sc, questions)
    v.proposal_md = await proposal.build_proposal(llm, s, p.name, v, usage)
    p.versions.append(v)
    store.save()
    return v
