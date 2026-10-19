import Anthropic from "@anthropic-ai/sdk";

export interface JsonCall { system: string; user: string; model: string; maxTokens?: number }
export interface JsonResult { text: string; inputTokens: number; outputTokens: number; latencyMs: number }
export interface LLM { completeJson(c: JsonCall): Promise<JsonResult> }

export class ClaudeLLM implements LLM {
  private client = new Anthropic(); // reads ANTHROPIC_API_KEY
  async completeJson(c: JsonCall): Promise<JsonResult> {
    const t0 = Date.now();
    const r = await this.client.messages.create({
      model: c.model, max_tokens: c.maxTokens ?? 1000, system: c.system,
      messages: [{ role: "user", content: c.user }],
    });
    const text = r.content.map((b) => (b.type === "text" ? b.text : "")).join("");
    return { text, inputTokens: r.usage.input_tokens, outputTokens: r.usage.output_tokens, latencyMs: Date.now() - t0 };
  }
}

/** Pull the first JSON object out of a model reply (handles ```json fences). */
export function extractJson(text: string): unknown {
  const s = text.indexOf("{"), e = text.lastIndexOf("}");
  if (s === -1 || e === -1) throw new Error("model did not return JSON");
  return JSON.parse(text.slice(s, e + 1));
}
