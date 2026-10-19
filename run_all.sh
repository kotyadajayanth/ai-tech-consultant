#!/usr/bin/env bash
# One command: ./run_all.sh   (installs deps, starts the 3 apps; Ctrl+C stops all)
set -euo pipefail
cd "$(dirname "$0")"
[ -f .env ] || { echo "Create .env first: cp .env.example .env and set ANTHROPIC_API_KEY"; exit 1; }
set -a; . ./.env; set +a
[ -n "${ANTHROPIC_API_KEY:-}" ] || { echo "ANTHROPIC_API_KEY is empty in .env"; exit 1; }
for t in task1-knowledge-brain task3-meeting-to-scope; do
  [ -d $t/.venv ] || python3 -m venv $t/.venv
  $t/.venv/bin/pip install -q -r $t/requirements.txt
done
(cd task2-inbox-agent && npm install --silent)
trap 'kill 0' EXIT
(cd task1-knowledge-brain && .venv/bin/uvicorn app.main:factory --factory --port 8001) &
(cd task2-inbox-agent && PORT=3000 KNOWLEDGE_URL=http://localhost:8001 npm start) &
(cd task3-meeting-to-scope && KNOWLEDGE_URL=http://localhost:8001 .venv/bin/uvicorn app.main:factory --factory --port 8003) &
echo "Task1 http://localhost:8001  |  Task2 http://localhost:3000  |  Task3 http://localhost:8003"
echo "First time: ingest 10-20 pages ->  curl -X POST 'localhost:8001/ingestion/run?limit=15'   then check /ingestion/status"
wait
