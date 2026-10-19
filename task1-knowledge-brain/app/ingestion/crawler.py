"""Polite, resumable ingestion: sitemap -> diff -> fetch -> parse -> chunk -> embed -> save.
Safeguards: concurrency cap + delay, exponential backoff, per-page checkpoint, failure isolation,
robots.txt, idempotent re-index (unchanged content hash => nothing is touched)."""
import asyncio
import datetime as dt
import mimetypes
import urllib.robotparser
from dataclasses import dataclass, field
from urllib.parse import urlparse

import httpx

from ..chunking import chunk_article
from ..config import Settings
from ..store import deactivate_url, replace_chunks
from .parser import parse_article
from .sitemap import diff_manifest, parse_sitemap


@dataclass
class Report:
    added: int = 0
    updated: int = 0
    unchanged: int = 0
    removed: int = 0
    failed: int = 0
    skipped_robots: int = 0
    errors: dict[str, str] = field(default_factory=dict)


class HttpFetcher:
    """get(url) -> (status_code, body_bytes, content_type). Raises on network errors."""

    def __init__(self, settings: Settings) -> None:
        self._c = httpx.AsyncClient(headers={"User-Agent": settings.user_agent}, timeout=20, follow_redirects=True)
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self._ua = settings.user_agent

    async def allowed(self, url: str) -> bool:
        host = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
        if host not in self._robots:
            rp = urllib.robotparser.RobotFileParser()
            try:
                r = await self._c.get(host + "/robots.txt")
                rp.parse(r.text.splitlines() if r.status_code == 200 else [])
            except httpx.HTTPError:
                rp.parse([])
            self._robots[host] = rp
        return self._robots[host].can_fetch(self._ua, url)

    async def get(self, url: str):
        r = await self._c.get(url)
        return r.status_code, r.content, r.headers.get("content-type", "")

    async def close(self) -> None:
        await self._c.aclose()


async def _get_with_retry(fetcher, url: str, s: Settings):
    """Retry network errors and 429/5xx with exponential backoff. Other 4xx are permanent."""
    last: Exception | None = None
    for attempt in range(s.max_retries + 1):
        try:
            status, body, ctype = await fetcher.get(url)
            if status == 429 or status >= 500:
                last = RuntimeError(f"HTTP {status}")
            else:
                return status, body, ctype
        except (httpx.HTTPError, asyncio.TimeoutError) as e:
            last = e
        await asyncio.sleep(min(30.0, s.delay_s * (2 ** attempt)))
    raise RuntimeError(f"gave up after retries: {last}")


async def _sitemap_entries(fetcher, s: Settings):
    status, body, _ = await _get_with_retry(fetcher, s.sitemap_url, s)
    if status != 200:
        raise RuntimeError(f"sitemap returned HTTP {status}")
    pages, children = parse_sitemap(body.decode("utf-8", "replace"))
    for child in children:
        st, b, _ = await _get_with_retry(fetcher, child, s)
        if st == 200:
            more, _ = parse_sitemap(b.decode("utf-8", "replace"))
            pages.extend(more)
    return list({e.url: e for e in pages}.values())


async def _describe_images(conn, brain, article, fetcher) -> list[dict]:
    """One searchable chunk per screenshot. Cached by image URL so we pay for each image once."""
    rows = []
    for sec in article.sections:
        for img in sec.images:
            cached = conn.execute("SELECT description FROM image_cache WHERE image_url=?", (img.url,)).fetchone()
            desc = cached[0] if cached else None
            if desc is None and brain.llm is not None and brain.settings.enable_vision:
                try:
                    status, body, ctype = await fetcher.get(img.url)
                    mt = (ctype.split(";")[0] or mimetypes.guess_type(img.url)[0] or "image/png")
                    if status == 200 and mt in ("image/png", "image/jpeg", "image/gif", "image/webp"):
                        desc = await brain.llm.describe_image(
                            image=body, media_type=mt, model=brain.settings.vision_model,
                            context=f"{article.title} / {sec.heading}. Text before image: {img.context}. Alt: {img.alt}")
                        with conn:
                            conn.execute("INSERT OR REPLACE INTO image_cache VALUES(?,?,?)",
                                         (img.url, desc, brain.settings.vision_model))
                except Exception:  # an image failure must never fail the article
                    desc = None
            if desc or img.alt:
                rows.append({"kind": "image", "title": article.title, "heading": sec.heading, "image_url": img.url,
                             "text": f"[Screenshot in '{article.title}' > '{sec.heading}'] {desc or ''} {img.alt}".strip()})
    return rows


async def ingest(brain, fetcher, limit: int | None = None) -> Report:
    s, conn, rep = brain.settings, brain.conn(), Report()
    current = await _sitemap_entries(fetcher, s)
    stored = {r["url"]: dict(r) for r in conn.execute("SELECT url, lastmod, status, attempts FROM pages")}
    d = diff_manifest(current, stored)
    for url in d.removed:
        deactivate_url(conn, url)
        rep.removed += 1
    now = lambda: dt.datetime.now(dt.timezone.utc).isoformat()
    todo = [(e, "new") for e in d.new] + [(e, "changed") for e in d.changed]
    # resume: pages from an interrupted/failed earlier run that are not finished yet
    for e in d.unchanged:
        st = stored[e.url]
        if st["status"] in ("pending", "failed") and st["attempts"] < s.max_total_attempts:
            todo.append((e, "retry"))
        else:
            rep.unchanged += 1
    if limit:
        todo = todo[:limit]
    with conn:
        for e, _ in todo:  # manifest saved BEFORE fetching: a restart knows what is left
            conn.execute("INSERT INTO pages(url, lastmod, status) VALUES(?,?, 'pending') ON CONFLICT(url) DO UPDATE SET "
                         "lastmod=excluded.lastmod, status=CASE WHEN pages.status='ok' THEN 'pending' ELSE pages.status END",
                         (e.url, e.lastmod))
    sem = asyncio.Semaphore(s.max_concurrency)

    async def work(e, kind):
        async with sem:
            c = brain.conn()
            try:
                if hasattr(fetcher, "allowed") and not await fetcher.allowed(e.url):
                    rep.skipped_robots += 1
                    c.execute("UPDATE pages SET status='failed', error='blocked by robots.txt' WHERE url=?", (e.url,)); c.commit()
                    return
                status, body, _ = await _get_with_retry(fetcher, e.url, s)
                if status in (404, 410):
                    deactivate_url(c, e.url); rep.removed += 1; return
                if status != 200:
                    raise RuntimeError(f"HTTP {status}")
                art = parse_article(e.url, body.decode("utf-8", "replace"))
                old = c.execute("SELECT content_hash, status FROM pages WHERE url=?", (e.url,)).fetchone()
                if old and old["content_hash"] == art.content_hash and old["status"] in ("ok", "pending") and kind != "retry" \
                        and c.execute("SELECT 1 FROM chunks WHERE url=?", (e.url,)).fetchone():
                    c.execute("UPDATE pages SET status='ok', error=NULL WHERE url=?", (e.url,)); c.commit()
                    rep.unchanged += 1; return
                rows = [{"kind": "text", "title": art.title, "heading": ch.heading, "text": ch.text} for ch in chunk_article(art)]
                rows += await _describe_images(c, brain, art, fetcher)
                replace_chunks(c, brain.embedder, e.url, rows)
                c.execute("UPDATE pages SET status='ok', content_hash=?, title=?, ingested_at=?, error=NULL WHERE url=?",
                          (art.content_hash, art.title, now(), e.url)); c.commit()
                if kind == "new": rep.added += 1
                else: rep.updated += 1
            except Exception as ex:  # failure isolation: record it, carry on
                c.execute("UPDATE pages SET status='failed', attempts=attempts+1, error=? WHERE url=?", (str(ex)[:300], e.url))
                c.commit(); rep.failed += 1; rep.errors[e.url] = str(ex)[:200]
            finally:
                c.close()
                await asyncio.sleep(s.delay_s)

    await asyncio.gather(*(work(e, k) for e, k in todo))
    return rep
