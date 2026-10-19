import httpx

from app.chunking import chunk_article
from app.ingestion.crawler import ingest
from app.ingestion.parser import parse_article
from app.ingestion.sitemap import SitemapEntry, diff_manifest, parse_sitemap
from app.rag import answer_question
from app.store import search
from tests.conftest import ART, REFUND, SITEMAP, FakeFetcher


def test_sitemap_dedupes_and_validates():
    pages, kids = parse_sitemap(SITEMAP)
    assert [p.url for p in pages] == ["https://h.test/a1", "https://h.test/a2"] and kids == []


def test_diff_detects_new_changed_removed():
    cur = [SitemapEntry("u1", "2"), SitemapEntry("u2", "1"), SitemapEntry("u4", "1")]
    stored = {"u1": {"lastmod": "1", "status": "ok"}, "u2": {"lastmod": "1", "status": "ok"}, "u3": {"lastmod": "1", "status": "ok"}}
    d = diff_manifest(cur, stored)
    assert [e.url for e in d.changed] == ["u1"] and [e.url for e in d.new] == ["u4"] \
        and [e.url for e in d.unchanged] == ["u2"] and d.removed == ["u3"]


def test_parser_strips_noise_and_keeps_table_together():
    a = parse_article("https://h.test/a1", ART)
    text = " ".join(b for s in a.sections for b in s.blocks)
    assert "MENU" not in text and "FOOTER" not in text
    assert "Format | Max size\nPNG | 2MB" in text
    assert a.sections[-1].images and a.sections[-1].images[0].url == "https://h.test/img/logo.png"
    assert chunk_article(a)


async def test_ingest_idempotent_removal_and_failure_isolation(brain):
    sm = SITEMAP.replace("not-a-url", "https://h.test/a3")
    f = FakeFetcher({"https://h.test/a1": (200, ART.encode()), "https://h.test/a2": (200, REFUND.encode()),
                     "https://h.test/a3": (200, httpx.ConnectError("boom"))}, sm)
    r1 = await ingest(brain, f)
    assert (r1.added, r1.failed) == (2, 1)                       # one bad page did not stop the others
    n1 = brain.conn().execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    r2 = await ingest(brain, f)                                  # same content again
    assert r2.added == 0 and brain.conn().execute("SELECT COUNT(*) FROM chunks").fetchone()[0] == n1  # no duplicates
    f.sitemap = sm.replace('<url><loc>https://h.test/a2</loc><lastmod>2026-01-01</lastmod></url>', "")
    r3 = await ingest(brain, f)
    assert r3.removed == 1
    hits = search(brain.conn(), brain.embedder, "refunds processed business days")
    assert all("a2" not in h.url for h in hits)                  # removed article is gone from answers


async def test_screenshot_text_is_searchable(brain):
    f = FakeFetcher({"https://h.test/a1": (200, ART.encode())}, SITEMAP.split("<url><loc>https://h.test/a2")[0] + "</urlset>")
    await ingest(brain, f)
    hits = search(brain.conn(), brain.embedder, "Save Logo button screenshot")
    assert any(h.kind == "image" for h in hits)


async def test_answer_cites_and_abstains(brain):
    f = FakeFetcher({"https://h.test/a2": (200, REFUND.encode())},
                    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://h.test/a2</loc></url></urlset>')
    await ingest(brain, f)
    brain.llm.replies.append({"sufficient": True, "answer": "Within 5 business days.", "source_ids": [1, 99], "notes": ""})
    a = await answer_question(brain, "How long do refunds take?")
    assert a.status == "answered" and [s["url"] for s in a.sources] == ["https://h.test/a2"]   # invented id 99 dropped
    calls = brain.llm.calls
    b = await answer_question(brain, "zzzz qqqq unrelated xylophone")
    assert b.status == "insufficient_evidence" and b.needs_human and brain.llm.calls == calls  # no LLM call, no guess
    brain.llm.replies.append({"sufficient": False, "answer": "", "source_ids": [], "notes": "not covered"})
    c = await answer_question(brain, "How long do refunds take for crypto?")
    assert c.status == "insufficient_evidence"
