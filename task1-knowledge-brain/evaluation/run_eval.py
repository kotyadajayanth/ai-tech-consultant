"""Run the evaluation cases against a RUNNING Knowledge Brain and write REAL measurements.
Usage: python evaluation/run_eval.py --label sonnet-5-5   (restart the API with a different ANSWER_MODEL to compare)

cases.csv columns: case_id, question, expected_source_url, must_abstain (1/0), notes
Write at least 20 cases AFTER you have ingested the help center and read the real articles:
  - directly answerable | multi-article | answer only in a screenshot | not in the help center (must_abstain=1)
Nothing is invented here: columns stay empty if a measurement could not be taken."""
import argparse
import csv
import json
import os
import time
import urllib.request

PRICE_PER_MTOK = {"in": float(os.getenv("PRICE_IN", "0")), "out": float(os.getenv("PRICE_OUT", "0"))}  # set from the pricing page


def post(url, body, key):
    req = urllib.request.Request(url, json.dumps(body).encode(), {"content-type": "application/json", **({"x-api-key": key} if key else {})})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read()), (time.perf_counter() - t0) * 1000


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8001")
    ap.add_argument("--label", required=True, help="model/config label written to the results file")
    ap.add_argument("--cases", default="evaluation/cases.csv")
    a = ap.parse_args()
    key = os.getenv("KB_API_KEY")
    rows = []
    for c in csv.DictReader(open(a.cases, encoding="utf-8")):
        row = {"task": "knowledge", "case_id": c["case_id"], "model": a.label, "passed": "", "failure_reason": ""}
        try:
            r, ms = post(a.base + "/query", {"question": c["question"], "escalate": False}, key)
            urls = [s["url"] for s in r["sources"]]
            abstained = r["status"] == "insufficient_evidence"
            if c["must_abstain"] == "1":
                ok, why = abstained, "" if abstained else "answered something that is not in the help center"
            else:
                ok = (not abstained) and c["expected_source_url"] in urls
                why = "" if ok else ("abstained" if abstained else "expected source not cited")
            row.update(latency_ms=int(ms), passed=int(ok), failure_reason=why, answer=r["answer"][:300], sources=" ".join(urls))
        except Exception as e:
            row.update(failure_reason=f"error: {e}")
        rows.append(row)
    out = f"evaluation/results_{a.label}.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["task", "case_id", "model", "latency_ms", "passed", "failure_reason", "answer", "sources"])
        w.writeheader(); [w.writerow({k: r.get(k, "") for k in w.fieldnames}) for r in rows]
    done = [r for r in rows if r["passed"] != ""]
    print(f"{len(done)}/{len(rows)} measured, passed {sum(r['passed'] for r in done)}  -> {out}")
