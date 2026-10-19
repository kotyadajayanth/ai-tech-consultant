"""Index, deactivate and search chunks (hybrid: vector + keyword, merged with reciprocal-rank fusion)."""
import sqlite3
from dataclasses import dataclass

import numpy as np

from .embeddings import tokenize


@dataclass
class Hit:
    chunk_id: int
    url: str
    title: str
    heading: str
    text: str
    kind: str
    image_url: str | None
    cosine: float
    rrf: float
    kw: bool = False  # matched on content words (keyword search)


def replace_chunks(conn: sqlite3.Connection, embedder, url: str, rows: list[dict]) -> int:
    """Idempotent: removes the page's old chunks, inserts the new ones in one transaction."""
    vecs = embedder.embed([r["text"] for r in rows]) if rows else []
    with conn:
        _delete_url(conn, url)
        for i, (r, v) in enumerate(zip(rows, vecs)):
            cur = conn.execute(
                "INSERT INTO chunks(url, idx, kind, title, heading, text, image_url, embedding) VALUES(?,?,?,?,?,?,?,?)",
                (url, i, r.get("kind", "text"), r.get("title"), r.get("heading"), r["text"], r.get("image_url"),
                 v.astype(np.float32).tobytes()))
            conn.execute("INSERT INTO chunks_fts(text, chunk_id) VALUES(?,?)", (r["text"], cur.lastrowid))
    return len(rows)


def _delete_url(conn: sqlite3.Connection, url: str) -> None:
    ids = [r[0] for r in conn.execute("SELECT id FROM chunks WHERE url=?", (url,))]
    for i in ids:
        conn.execute("DELETE FROM chunks_fts WHERE chunk_id=?", (i,))
    conn.execute("DELETE FROM chunks WHERE url=?", (url,))


def deactivate_url(conn: sqlite3.Connection, url: str) -> None:
    """Removed article: it must stop appearing in answers."""
    with conn:
        _delete_url(conn, url)
        conn.execute("UPDATE pages SET status='removed' WHERE url=?", (url,))


def search(conn: sqlite3.Connection, embedder, query: str, k: int = 6) -> list[Hit]:
    rows = conn.execute("SELECT id, url, title, heading, text, kind, image_url, embedding FROM chunks WHERE active=1").fetchall()
    if not rows:
        return []
    mat = np.vstack([np.frombuffer(r["embedding"], dtype=np.float32) for r in rows])
    cos = mat @ embedder.embed([query])[0]
    vec_rank = {rows[i]["id"]: r for r, i in enumerate(np.argsort(-cos)[: k * 3])}
    toks = tokenize(query)
    kw_rank: dict[int, int] = {}
    if toks:
        q = " OR ".join(f'"{t}"' for t in toks)
        for r, row in enumerate(conn.execute(
                "SELECT chunk_id FROM chunks_fts WHERE chunks_fts MATCH ? ORDER BY rank LIMIT ?", (q, k * 3))):
            kw_rank[row[0]] = r
    by_id = {r["id"]: (r, float(cos[i])) for i, r in enumerate(rows)}
    scored = []
    for cid in set(vec_rank) | set(kw_rank):
        rrf = (1 / (60 + vec_rank[cid]) if cid in vec_rank else 0) + (1 / (60 + kw_rank[cid]) if cid in kw_rank else 0)
        scored.append((rrf, cid))
    hits = []
    for rrf, cid in sorted(scored, reverse=True)[:k]:
        r, c = by_id[cid]
        hits.append(Hit(cid, r["url"], r["title"] or "", r["heading"] or "", r["text"], r["kind"], r["image_url"], c, rrf, cid in kw_rank))
    return hits
