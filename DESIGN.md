# DESIGN.md

> DRAFT. The brief wants this in YOUR words and wants you to defend every line in the live review. Rewrite each section after you have read the code and run the apps. Replace the [brackets] with real findings.

## 1. The problem
A small software agency spends its time on three slow jobs: finding product answers, replying to customers, and turning vague meetings into scopes. Code got cheap, so these jobs are now the bottleneck. One shared knowledge service means all three jobs use the same correct facts, and any other business could plug in its own help center.

## 2. How the three tasks connect
```
 Help-center sitemap ──► [Task 1 Knowledge Brain, Python/FastAPI] ◄── expert answers (escalation queue)
                              │  POST /query  (HTTP only, typed contract)
              ┌───────────────┴────────────────┐
   [Task 2 Inbox Agent, TypeScript]   [Task 3 Meeting→Scope, Python]
   classify → knowledge → draft →      transcript → analyst → feasibility →
   human review → feedback →           scope → estimator → proposal →
   20-in-a-row rule                    diff vs APPROVED baseline → human approval
```
Tasks 2 and 3 never import Task 1 code. They only know its HTTP contract (`/query` returns `status`, `answer`, `sources`, `needs_human`).

## 3. Features chosen, and why
- **Abstain instead of guess.** A retrieval gate (no relevant chunk → no model call), a model "sufficient?" check, and citation validation. A wrong confident answer costs more than "I don't know".
- **Screenshots are searchable.** Each image gets a short vision description stored as its own chunk, linked to its article. Cached by URL so each image is paid for once.
- **Incremental daily update.** Sitemap diff by `lastmod`, then content hash. Unchanged pages are never re-embedded. Removed pages are deleted from search.
- **Expert answers are separate, versioned records** (`expert://id`), active only after approval, and the question joins the eval set.
- **Inbox: no draft is better than an invented draft.** If Task 1 is down, no reply is generated. Refunds, complaints, quotes and project requests can never become autonomous, whatever the streak.
- **20-in-a-row rule:** "same kind" = same category; "unchanged" = identical after whitespace normalisation. Any edit, rejection or expert escalation resets the streak and revokes auto-send. Eligibility sends nothing by itself: a human switches it on, and each email must still be low risk, answered with evidence, and not flagged.
- **Scope: code does the arithmetic.** The model proposes tasks; code validates `low ≤ likely ≤ high`, sums totals, and drops invalid estimates. Only the proposal's summary paragraph is model-written, so the proposal cannot disagree with the scope.
- **Follow-up meetings compare against the approved baseline,** never against an AI draft. If nothing is approved yet, the follow-up is refused.
- **Missing evidence ≠ custom work.** If Task 1 has no answer, the requirement becomes `needs_clarification` and goes to a human.

## 4. Features dropped (and why)
Real email (Gmail/IMAP) sending: simulated outbox instead. Calibrated confidence score: omitted from the API until measured. Reranker and knowledge graph: only if evals show hybrid search is not enough. Multi-tenant auth and per-company knowledge spaces. Postgres/pgvector. [Add yours.]

## 5. Model and storage choices
Claude everywhere. Defaults: `claude-sonnet-5-5` for answers, drafts, scoping and estimates; `claude-haiku-5-5` for classification, image descriptions and feasibility labels. **These are hypotheses until EVALS.md has 20–30 cases per decision.** [Replace with what the numbers say.]
Storage: SQLite + FTS5 + brute-force cosine in numpy. At a few thousand chunks this is fast, needs no setup and keeps the one-command run. At large scale, switch to pgvector. Embeddings: a hashing baseline (no download) vs `fastembed` [compare in EVALS.md].

## 6. What breaks / limitations (be honest)
- The HTML parser uses generic selectors. [Tune against the real help-center markup and note what you changed.]
- The hash embedder is weak on paraphrases. `MIN_RETRIEVAL_SCORE` must be tuned on your cases.
- Vision descriptions can be wrong; the prompt asks for "unclear" instead of guessing, but that is not guaranteed.
- JSON-file stores in Tasks 2 and 3 are single-process and not safe for concurrent writers.
- Task 2 and 3 screens have no login. Do not expose them publicly.
- Quote verification checks that a quote exists in the transcript, not that it supports the requirement.

## 7. Next steps
Prompt-improvement loop from edit history (versioned prompts + regression set), reranking, real email integration, auth, multi-tenant knowledge spaces.
