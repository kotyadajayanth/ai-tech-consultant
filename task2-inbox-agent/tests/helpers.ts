import type { KnowledgeClient } from "../src/knowledgeClient.js";
import { KnowledgeUnavailable } from "../src/knowledgeClient.js";
import type { LLM } from "../src/llm.js";
import type { Deps } from "../src/pipeline.js";
import { Store } from "../src/store.js";
import type { KnowledgeAnswer } from "../src/types.js";

export class FakeLLM implements LLM {
  calls: string[] = [];
  constructor(public replies: string[]) {}
  async completeJson(c: { system: string; user: string }) { this.calls.push(c.user); return { text: this.replies.shift() ?? "{}", inputTokens: 1, outputTokens: 1, latencyMs: 1 }; }
}
export const answered: KnowledgeAnswer = { status: "answered", answer: "Open Design Settings and press Save Logo.", sources: [{ title: "Logo", url: "https://kb/logo", relevance: 0.9, kind: "text" }], needs_human: false, escalation_id: null };
export const fakeKb = (a: KnowledgeAnswer | Error): KnowledgeClient => ({ query: async () => { if (a instanceof Error) throw a; return a; } });
export const cls = (category: string, risk = "low") => JSON.stringify({ category, summary: "s", risk, urgent: false });
export const draft = (o: Partial<{ reply: string; sources_used: string[]; needs_human: boolean }> = {}) =>
  JSON.stringify({ reply: "Hi Sam, open Design Settings.", sources_used: ["https://kb/logo", "https://evil.example"], needs_human: false, follow_up_date: null, next_action: "send", ...o });
export const mkDeps = (llm: LLM, kb: KnowledgeClient): Deps => ({ llm, knowledge: kb, store: new Store(null), models: { classify: "c", draft: "d" }, promptVersion: "v1" });
export const email = { from: "sam@x.com", subject: "Change logo", body: "How do I change my logo?" };
export { KnowledgeUnavailable };
