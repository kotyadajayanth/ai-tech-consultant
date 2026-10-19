# EVALS.md

> EVERY NUMBER HERE MUST COME FROM A REAL RUN. Do not fill a cell you have not measured. Write `pending`.

## How to run
| Task | Command | Output |
|---|---|---|
| 1 | Start the API with `ANSWER_MODEL=<model>`, then `python evaluation/run_eval.py --label <model>` (cases in `evaluation/cases.csv`) | `evaluation/results_<label>.csv` |
| 2 | `npm run eval -- --label <name> --draft-model <model> [--holdout]` | `evaluation/results_<label>.csv` |
| 3 | [write a small runner over your 3 transcripts + hand-made reference scopes] | pending |

Cost: set `PRICE_IN` / `PRICE_OUT` ($ per million tokens, from the pricing page) and compute from the token counts the APIs return.

## Method
Dataset sizes, who wrote the expected answers, hold-out split (Task 2 has 17 emails flagged `holdout`; don't tune on them): [fill]

## Results (≥20 cases per task, ≥2 models)
| Task | Model | Cases | Quality | Median latency | p95 latency | Cost / task | Failures |
|---|---|---|---|---|---|---|---|
| Knowledge | pending | pending | pending | pending | pending | pending | pending |
| Inbox | pending | pending | pending | pending | pending | pending | pending |
| Scope | pending | pending | pending | pending | pending | pending | pending |

## Model-choice decisions (20–30 cases each)
pending

## Failures found, and what I changed
pending (keep failed cases in the CSVs)

## Prompt versions
| Version | Change | Why | Before → after (same cases) |
|---|---|---|---|
| v1 | initial | | |
