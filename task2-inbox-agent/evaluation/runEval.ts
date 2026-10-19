/**
 * Runs the dataset through the REAL pipeline (needs the Knowledge Brain running + ANTHROPIC_API_KEY)
 * and writes measured results. Nothing is simulated or invented.
 *   npm run eval -- --label sonnet-5-5 --draft-model claude-sonnet-5-5 [--holdout]
 * Compare models by re-running with another --draft-model / --classify-model.
 */
import { readFileSync, writeFileSync } from "node:fs";
import { HttpKnowledgeClient } from "../src/knowledgeClient.js";
import { ClaudeLLM } from "../src/llm.js";
import { processEmail, type Deps } from "../src/pipeline.js";
import { Store } from "../src/store.js";
import { NEVER_AUTONOMOUS, type Category } from "../src/types.js";

interface Row { id: string; category: Category; risk: string; subject: string; body: string; holdout: boolean }
const arg = (n: string, d: string) => { const i = process.argv.indexOf(`--${n}`); return i > -1 ? (process.argv[i + 1] ?? d) : d; };
const label = arg("label", "run");
const onlyHoldout = process.argv.includes("--holdout");
const deps: Deps = {
  llm: new ClaudeLLM(), knowledge: new HttpKnowledgeClient(process.env.KNOWLEDGE_URL ?? "http://localhost:8001", process.env.KB_API_KEY),
  store: new Store(null), models: { classify: arg("classify-model", "claude-haiku-5-5"), draft: arg("draft-model", "claude-sonnet-5-5") },
  promptVersion: arg("prompt", "v1"),
};
const rows = (JSON.parse(readFileSync("data/emails.json", "utf8")) as Row[]).filter((r) => (onlyHoldout ? r.holdout : !r.holdout));
const out = ["task,case_id,model,expected,actual,latency_ms,passed,failure_reason"];
for (const r of rows) {
  const t0 = Date.now();
  try {
    const d = await processEmail(deps, { from: "eval@example.com", subject: r.subject, body: r.body });
    const okCat = d.classification.category === r.category;
    const unsafe = NEVER_AUTONOMOUS.includes(r.category) && !d.needsHuman;      // safety: money/commitment emails must need a human
    const why = [okCat ? "" : "wrong category", unsafe ? "UNSAFE: not flagged for human" : "", d.knowledge.available ? "" : "knowledge down"].filter(Boolean).join("; ");
    out.push(`inbox,${r.id},${label},${r.category},${d.classification.category},${Date.now() - t0},${why ? 0 : 1},"${why}"`);
  } catch (e) { out.push(`inbox,${r.id},${label},${r.category},,,"",error: ${(e as Error).message.replace(/[",\n]/g, " ")}`); }
}
writeFileSync(`evaluation/results_${label}.csv`, out.join("\n") + "\n");
console.log(`wrote evaluation/results_${label}.csv (${rows.length} cases)`);
