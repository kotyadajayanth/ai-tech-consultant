import pytest

from app.agents.analyst import quote_is_real, split_transcript
from app.agents.estimator import totals
from app.models import EstTask, Requirement
from app.pipeline import run_meeting
from app.projects import ApprovalError
from tests.conftest import ANSWERED, MEETING_A, MEETING_C, FakeKB, FakeLLM

REQ_A = {"requirements": [
    {"description": "Search filters by price and category", "quote": "Price and category", "speaker": "Client", "status": "confirmed", "priority": "must", "origin": "explicit"},
    {"description": "Better mobile experience", "quote": "the site must work better on mobile", "speaker": "Client", "status": "unclear", "priority": "should", "origin": "explicit"}],
    "facts": {"delivery_date": "30 November"}, "open_questions": ["What does 'better on mobile' mean?"]}
SCOPE = {"objective": "Faster product search", "current_problem": "Search is weak", "proposed_solution": "Filters", "deliverables": [{"name": "Filters", "requirement_ids": ["REQ-001", "REQ-999"], "verification": "Filter by price"}],
         "acceptance": {"REQ-001": ["A customer can filter by price and category"]}, "exclusions": ["AI search"], "assumptions": [], "client_responsibilities": [], "risks": []}
EST_A = {"estimates": [{"requirement_id": "REQ-001", "tasks": [{"name": "Config", "low": 1, "likely": 2, "high": 3}]},
                       {"requirement_id": "REQ-002", "tasks": [{"name": "Bad", "low": 5, "likely": 2, "high": 3}]}]}  # invalid on purpose


def llm_a():
    return FakeLLM({"analyst_extract": [REQ_A], "feasibility": {"feasibility": "existing_configuration", "reason": "Settings > Search"},
                    "scope": [SCOPE], "estimator": [EST_A], "proposal_summary": {"summary": "We will improve search."}})


async def test_first_meeting(store, settings):
    p = store.new("Acme")
    v = await run_meeting(llm_a(), FakeKB({"price": ANSWERED}), settings, store, p, "2026-10-20", MEETING_A)
    r1, r2 = v.requirements
    assert r1.quote_verified and r1.feasibility == "existing_configuration"
    assert r2.feasibility == "needs_clarification"                       # no evidence => ask a human, never assume custom work
    assert r1.acceptance_criteria and v.scope["deliverables"][0]["requirement_ids"] == ["REQ-001"]   # invented id dropped
    assert r2.tasks == [] and r2.needs_estimate_review                   # invalid estimate rejected, not repaired
    assert v.totals["likely"] == 2 and v.price_estimate == 100.0         # arithmetic is code, not the model
    assert "Not yet confirmed" in v.proposal_md and "30 November" in v.proposal_md


async def test_knowledge_down_never_marks_custom(store, settings):
    p = store.new("Acme")
    v = await run_meeting(llm_a(), FakeKB({}, down=True), settings, store, p, "2026-10-20", MEETING_A)
    assert all(r.feasibility == "needs_clarification" for r in v.requirements)


async def test_approval_gate_and_followup_diff(store, settings):
    p = store.new("Acme")
    await run_meeting(llm_a(), FakeKB({"price": ANSWERED}), settings, store, p, "2026-10-20", MEETING_A)
    with pytest.raises(ApprovalError):
        store.send(p, 1)                                                  # unapproved => cannot reach the client
    with pytest.raises(ApprovalError):
        await run_meeting(llm_a(), FakeKB({}), settings, store, p, "2026-11-02", MEETING_C)   # no approved baseline yet
    store.approve(p, 1, "Dana")
    follow = FakeLLM({"analyst_extract": [{"requirements": [], "facts": {}, "open_questions": []}],
        "analyst_merge": {"requirements": [
            {"id": "REQ-002", "description": "Better mobile experience", "quote": "forget the mobile work", "status": "confirmed", "priority": "optional", "removed": True},
            {"id": None, "description": "Wishlist feature", "quote": "please add a wishlist feature", "status": "confirmed", "priority": "should", "origin": "explicit"}],
            "facts": {"delivery_date": "15 December"}, "open_questions": []},
        "feasibility": {"feasibility": "custom_development", "reason": "No wishlist in docs"}, "scope": [SCOPE],
        "estimator": [{"estimates": [{"requirement_id": "REQ-003", "tasks": [{"name": "Build wishlist", "low": 6, "likely": 10, "high": 16}]}]}],
        "proposal_summary": {"summary": "Updated plan."}})
    v2 = await run_meeting(follow, FakeKB({"wishlist": {"status": "answered", "answer": "No wishlist.", "sources": [{"url": "https://kb/x"}]}}), settings, store, p, "2026-11-02", MEETING_C)
    c = v2.change_report
    assert [x["id"] for x in c["added"]] == ["REQ-003"] and [x["id"] for x in c["removed"]] == ["REQ-002"]
    assert c["out_of_scope_ids"] == ["REQ-003"] and c["facts_changed"][0]["new"] == "15 December"
    assert v2.requirements[0].feasibility == "existing_configuration"      # untouched baseline requirement kept
    assert follow.calls.count("estimator") == 1 and v2.totals["likely"] == 12   # REQ-001 (2h) + REQ-003 (10h); removed work excluded
    assert v2.status == "draft" and p.baseline().number == 1                # baseline stays the approved version
    store.approve(p, 2, "Dana"); store.send(p, 2)
    with pytest.raises(ApprovalError):
        store.send(p, 2)                                                    # no double send


def test_helpers():
    parts = split_transcript("\n".join(f"Client: line {i} " + "x" * 50 for i in range(100)), max_chars=500)
    assert len(parts) > 5 and parts[1].splitlines()[0] == parts[0].splitlines()[-3]   # overlap kept
    assert quote_is_real("work better on MOBILE", MEETING_A) and not quote_is_real("we love AI", MEETING_A)
    t, price = totals([Requirement(id="R", description="d", tasks=[EstTask(name="a", low=1, likely=2, high=3)])], 0, "USD")
    assert t["likely"] == 2 and price is None                               # no rate configured => no price invented
