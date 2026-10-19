from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import REFUND, FakeFetcher
from app.ingestion.crawler import ingest


async def _seed(brain):
    f = FakeFetcher({"https://h.test/a2": (200, REFUND.encode())},
                    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://h.test/a2</loc></url></urlset>')
    await ingest(brain, f)


async def test_escalation_roundtrip(brain):
    await _seed(brain)
    c = TestClient(create_app(brain))
    r = c.post("/query", json={"question": "Do you support bitcoin payouts xylophone?"})
    assert r.status_code == 200 and r.json()["status"] == "insufficient_evidence"
    esc_id = r.json()["escalation_id"]
    assert esc_id and c.get("/escalations").json()[0]["id"] == esc_id
    assert c.post(f"/escalations/{esc_id}/resolve", json={"answer": "Bitcoin payouts are not supported.", "approved": True}).status_code == 200
    brain.llm.replies.append({"sufficient": True, "answer": "Not supported.", "source_ids": [1], "notes": ""})
    r2 = c.post("/query", json={"question": "Do you support bitcoin payouts xylophone?"}).json()
    assert r2["status"] == "answered" and r2["sources"][0]["kind"] == "expert"   # expert answer flowed back into memory


def test_validation_auth_and_health(brain):
    c = TestClient(create_app(brain))
    assert c.post("/query", json={"question": "hi"}).status_code == 422
    assert c.get("/health").json()["status"] == "ok"
    brain.settings.__class__  # frozen settings: build a keyed one
    from dataclasses import replace
    brain.settings = replace(brain.settings, api_key="k")
    assert c.get("/ingestion/status").status_code == 401
    assert c.get("/ingestion/status", headers={"x-api-key": "k"}).status_code == 200
