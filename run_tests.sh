#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
for t in task1-knowledge-brain task3-meeting-to-scope; do
  [ -d $t/.venv ] || python3 -m venv $t/.venv
  $t/.venv/bin/pip install -q -r $t/requirements.txt
  (cd $t && .venv/bin/python -m pytest -q)
done
(cd task2-inbox-agent && npm install --silent && npm run -s typecheck && npm test --silent)
