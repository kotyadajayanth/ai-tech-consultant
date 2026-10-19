"""Human-expert loop. An expert answer becomes a versioned, separate knowledge record (kind='expert')
only after it is approved. It is never merged into article text."""
import json
import os

from .store import replace_chunks

EVAL_QUEUE = os.path.join(os.path.dirname(__file__), "..", "evaluation", "escalated_questions.jsonl")


def create(conn, question: str, evidence: str, reason: str) -> int:
    with conn:
        cur = conn.execute("INSERT INTO escalations(question, evidence, reason) VALUES(?,?,?)", (question, evidence, reason))
    return cur.lastrowid


def resolve(conn, embedder, esc_id: int, answer: str, approved: bool, expert: str) -> dict:
    row = conn.execute("SELECT * FROM escalations WHERE id=?", (esc_id,)).fetchone()
    if row is None:
        raise KeyError(esc_id)
    version = row["version"] + (1 if row["status"] == "resolved" else 0)
    with conn:
        conn.execute("UPDATE escalations SET status='resolved', answer=?, approved=?, expert=?, version=?, "
                     "resolved_at=CURRENT_TIMESTAMP WHERE id=?", (answer, int(approved), expert, version, esc_id))
    url = f"expert://{esc_id}"
    if approved:
        replace_chunks(conn, embedder, url, [{"kind": "expert", "title": f"Expert answer #{esc_id} (v{version})",
                                              "heading": row["question"],
                                              "text": f"Expert-approved answer to: {row['question']}\n{answer}"}])
        try:  # the question joins the evaluation set
            with open(EVAL_QUEUE, "a", encoding="utf-8") as f:
                f.write(json.dumps({"question": row["question"], "expected_source": url}) + "\n")
        except OSError:
            pass
    else:
        with conn:  # un-approved (or revoked) answers must not be retrievable
            ids = [r[0] for r in conn.execute("SELECT id FROM chunks WHERE url=?", (url,))]
            for i in ids:
                conn.execute("DELETE FROM chunks_fts WHERE chunk_id=?", (i,))
            conn.execute("DELETE FROM chunks WHERE url=?", (url,))
    return {"id": esc_id, "version": version, "approved": approved}
