import { createServer, type IncomingMessage, type ServerResponse } from "node:http";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { z } from "zod";
import { REQUIRED_STREAK, isEligible, setAutoSend } from "./autonomy.js";
import { HttpKnowledgeClient } from "./knowledgeClient.js";
import { ClaudeLLM } from "./llm.js";
import { processEmail, review, type Deps } from "./pipeline.js";
import { Store } from "./store.js";
import { CATEGORIES, type Category } from "./types.js";

const here = path.dirname(fileURLToPath(import.meta.url));
const deps: Deps = {
  llm: new ClaudeLLM(),
  knowledge: new HttpKnowledgeClient(process.env.KNOWLEDGE_URL ?? "http://localhost:8001", process.env.KB_API_KEY),
  store: new Store(process.env.INBOX_DB ?? "data/inbox.json"),
  models: { classify: process.env.CLASSIFY_MODEL ?? "claude-haiku-5-5", draft: process.env.DRAFT_MODEL ?? "claude-sonnet-5-5" },
  promptVersion: process.env.PROMPT_VERSION ?? "v1",
};

const EmailIn = z.object({ from: z.string().min(3).max(200), subject: z.string().max(300), body: z.string().min(1).max(20_000) });
const Send = z.object({ finalReply: z.string().max(20_000).optional(), reason: z.string().max(500).optional() });
const Reject = z.object({ replacement: z.string().min(1).max(20_000), reason: z.string().min(1).max(500) });

function readBody(req: IncomingMessage): Promise<unknown> {
  return new Promise((resolve, reject) => {
    let data = "";
    req.on("data", (c: Buffer) => { data += c; if (data.length > 100_000) { reject(new Error("body too large")); req.destroy(); } });
    req.on("end", () => { try { resolve(data ? JSON.parse(data) : {}); } catch { reject(new Error("invalid JSON")); } });
  });
}
const json = (res: ServerResponse, code: number, body: unknown) => { res.writeHead(code, { "content-type": "application/json" }); res.end(JSON.stringify(body)); };

const server = createServer(async (req, res) => {
  const url = new URL(req.url ?? "/", "http://x");
  const p = url.pathname;
  try {
    if (req.method === "GET" && p === "/") { res.writeHead(200, { "content-type": "text/html" }); res.end(readFileSync(path.join(here, "..", "public", "index.html"))); return; }
    if (req.method === "GET" && p === "/api/drafts") return json(res, 200, deps.store.db.drafts);
    if (req.method === "GET" && p === "/api/autonomy") {
      const st = deps.store.db.autonomy;
      return json(res, 200, { required: REQUIRED_STREAK, categories: CATEGORIES.map((c) => ({ category: c, streak: st[c]?.streak ?? 0, eligible: isEligible(st, c), enabled: st[c]?.autoSendEnabled ?? false, revokedReason: st[c]?.revokedReason ?? null })) });
    }
    if (req.method === "POST" && p === "/api/emails") return json(res, 201, await processEmail(deps, EmailIn.parse(await readBody(req))));
    let m = p.match(/^\/api\/drafts\/([\w-]+)\/(send|reject|expert)$/);
    if (req.method === "POST" && m) {
      const body = await readBody(req);
      const [, id, act] = m as unknown as [string, string, string];
      const action = act === "send" ? { type: "send" as const, ...Send.parse(body) } : act === "reject" ? { type: "reject" as const, ...Reject.parse(body) } : { type: "expert" as const };
      return json(res, 200, review(deps, id, action));
    }
    m = p.match(/^\/api\/autonomy\/(\w+)$/);
    if (req.method === "POST" && m) {
      const c = z.enum(CATEGORIES).parse(m[1]) as Category;
      setAutoSend(deps.store.db.autonomy, c, z.object({ enabled: z.boolean() }).parse(await readBody(req)).enabled);
      deps.store.save();
      return json(res, 200, { ok: true });
    }
    json(res, 404, { error: "not found" });
  } catch (e) {
    const msg = e instanceof z.ZodError ? e.issues.map((i) => i.message).join("; ") : (e as Error).message;
    json(res, e instanceof z.ZodError ? 422 : 400, { error: msg });
  }
});
server.listen(Number(process.env.PORT ?? 3000), () => console.log(`Inbox Agent on http://localhost:${process.env.PORT ?? 3000}`));
