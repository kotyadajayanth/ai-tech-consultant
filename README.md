# AI Tech Consultant

One shared **Knowledge Brain** (Task 1, Python) that two apps call over HTTP: an **Inbox Agent** (Task 2, TypeScript) that drafts email replies, and **Meeting to Scope** (Task 3, Python) that turns client-meeting transcripts into a scope, estimate and proposal. Humans approve everything that reaches a customer.

## Prerequisites
Python 3.11+, Node 20+, an Anthropic API key.

## Run
```bash
cp .env.example .env        # set ANTHROPIC_API_KEY (never commit .env)
./run_all.sh                # installs and starts all three apps
curl -X POST 'localhost:8001/ingestion/run?limit=15'   # first time: ingest 15 pages, then check /ingestion/status
```
| App | URL |
|---|---|
| Knowledge Brain (chat; API docs at `/docs`) | http://localhost:8001 |
| Inbox Agent (review screen) | http://localhost:3000 |
| Meeting to Scope | http://localhost:8003 |

## Tests
`./run_tests.sh` runs the unit tests for all three tasks (no API key or network needed; models are faked).
Real quality/cost/speed numbers come from the eval runners in each task's `evaluation/` folder. See `EVALS.md`.

## Layout
`task1-knowledge-brain/` · `task2-inbox-agent/` · `task3-meeting-to-scope/` · `DESIGN.md` · `EVALS.md` · `AI_LOG.md`

## Known limits
Email sending is simulated (outbox only). See DESIGN.md, "What breaks".
