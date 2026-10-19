import type { KnowledgeAnswer } from "./types.js";

export class KnowledgeUnavailable extends Error {}

export interface KnowledgeClient { query(question: string, context?: string): Promise<KnowledgeAnswer> }

/** Typed client for Task 1's HTTP API. It never touches Task 1's internals. */
export class HttpKnowledgeClient implements KnowledgeClient {
  constructor(private baseUrl: string, private apiKey?: string, private timeoutMs = 30_000) {}
  async query(question: string, context = ""): Promise<KnowledgeAnswer> {
    const ctl = new AbortController();
    const t = setTimeout(() => ctl.abort(), this.timeoutMs);
    try {
      const r = await fetch(`${this.baseUrl}/query`, {
        method: "POST", signal: ctl.signal,
        headers: { "content-type": "application/json", ...(this.apiKey ? { "x-api-key": this.apiKey } : {}) },
        body: JSON.stringify({ question, context, escalate: true }),
      });
      if (!r.ok) throw new KnowledgeUnavailable(`knowledge service returned HTTP ${r.status}`);
      return (await r.json()) as KnowledgeAnswer;
    } catch (e) {
      if (e instanceof KnowledgeUnavailable) throw e;
      throw new KnowledgeUnavailable(`knowledge service unreachable: ${(e as Error).message}`);
    } finally {
      clearTimeout(t);
    }
  }
}
