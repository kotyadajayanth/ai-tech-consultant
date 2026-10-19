import { randomUUID } from "node:crypto";
import { isUnchanged, mayAutoSend, recordReview, REQUIRED_STREAK } from "./autonomy.js";
import { KnowledgeUnavailable, type KnowledgeClient } from "./knowledgeClient.js";
import { extractJson, type LLM } from "./llm.js";
import { loadPrompt } from "./prompts.js";
import type { Store } from "./store.js";
import { ClassificationSchema, DraftSchema, NEVER_AUTONOMOUS, type Classification, type Draft, type Email } from "./types.js";

export interface Deps {
  llm: LLM; knowledge: KnowledgeClient; store: Store;
  models: { classify: string; draft: string };
  promptVersion: string;
}
export { REQUIRED_STREAK };

/** Ask the model for JSON and validate it with a schema; retry once with the error message. */
async function structured<T>(deps: Deps, system: string, user: string, model: string, parse: (x: unknown) => T): Promise<T> {
  let lastErr = "";
  for (let i = 0; i < 2; i++) {
    const r = await deps.llm.completeJson({ system, user: i ? `${user}\n\nYour previous reply was invalid: ${lastErr}. Return valid JSON only.` : user, model });
    try { return parse(extractJson(r.text)); } catch (e) { lastErr = (e as Error).message.slice(0, 200); }
  }
  throw new Error(`model output failed validation twice: ${lastErr}`);
}

const emailBlock = (e: Email) => `<email from="${e.from}" subject="${e.subject}">\n${e.body}\n</email>`;

export async function processEmail(deps: Deps, input: Omit<Email, "id" | "receivedAt">): Promise<Draft> {
  const email: Email = { ...input, id: randomUUID(), receivedAt: new Date().toISOString() };
  const base = { id: randomUUID(), email, promptVersion: deps.promptVersion, model: deps.models.draft, autoSent: false, createdAt: new Date().toISOString() };

  // 1. classify (if the model fails twice we fall back to the safest option: a human handles it)
  let cls: Classification;
  try {
    cls = await structured(deps, loadPrompt(deps.promptVersion, "classify"), emailBlock(email), deps.models.classify, (x) => ClassificationSchema.parse(x));
  } catch {
    cls = { category: "other", summary: "Could not classify automatically", risk: "high", urgent: false };
  }

  // 2. facts from Task 1 (API only). If it is down we do NOT let the model improvise.
  let knowledge: Draft["knowledge"];
  try {
    knowledge = { available: true, answer: await deps.knowledge.query(`${email.subject}\n${email.body}`.slice(0, 1500), `Customer email category: ${cls.category}`) };
  } catch (e) {
    knowledge = { available: false, error: e instanceof KnowledgeUnavailable ? e.message : "unexpected knowledge error" };
  }
  if (!knowledge.available) {
    const d: Draft = { ...base, classification: cls, knowledge, reply: "", sourcesUsed: [], needsHuman: true,
      nextAction: "Knowledge service unavailable: write this reply manually or retry later.", followUpDate: null, status: "pending" };
    deps.store.db.drafts.unshift(d); deps.store.audit(d.id, "created_without_draft", knowledge.error); deps.store.save();
    return d;
  }

  // 3. draft
  const k = knowledge.answer!;
  const kBlock = k.status === "answered"
    ? `<knowledge status="answered">\n${k.answer}\nSources: ${k.sources.map((s) => s.url).join(", ")}\n</knowledge>`
    : `<knowledge status="insufficient_evidence">The knowledge base has no confirmed answer.</knowledge>`;
  let out;
  try {
    out = await structured(deps, loadPrompt(deps.promptVersion, "draft"),
      `${emailBlock(email)}\n<classification>${JSON.stringify(cls)}</classification>\n${kBlock}`, deps.models.draft, (x) => DraftSchema.parse(x));
  } catch {
    const d: Draft = { ...base, classification: cls, knowledge, reply: "", sourcesUsed: [], needsHuman: true,
      nextAction: "Draft generation failed validation: write manually.", followUpDate: null, status: "pending" };
    deps.store.db.drafts.unshift(d); deps.store.audit(d.id, "draft_failed"); deps.store.save();
    return d;
  }
  const allowed = new Set(k.sources.map((s) => s.url));
  const sourcesUsed = out.sources_used.filter((u) => allowed.has(u));      // no invented links/citations
  const needsHuman = out.needs_human || NEVER_AUTONOMOUS.includes(cls.category) || cls.risk === "high" || k.status !== "answered";

  const d: Draft = { ...base, classification: cls, knowledge, reply: out.reply, sourcesUsed, needsHuman,
    nextAction: out.next_action, followUpDate: out.follow_up_date, status: "pending" };
  deps.store.db.drafts.unshift(d);
  deps.store.audit(d.id, "drafted", `${cls.category}/${cls.risk}`);

  // 4. autonomy (only if a human switched it on AND this email passes the safety conditions)
  if (mayAutoSend(deps.store.db.autonomy, { category: cls.category, risk: cls.risk, needsHuman, knowledgeAnswered: k.status === "answered" })) {
    send(deps, d, d.reply, true);
  }
  deps.store.save();
  return d;
}

function send(deps: Deps, d: Draft, finalReply: string, auto: boolean): void {
  if (d.status !== "pending") throw new Error(`draft already ${d.status}`);   // no duplicate sends on retry
  d.status = "sent"; d.finalReply = finalReply; d.autoSent = auto; d.resolvedAt = new Date().toISOString();
  deps.store.db.outbox.push({ draftId: d.id, to: d.email.from, subject: `Re: ${d.email.subject}`, body: finalReply, sentAt: d.resolvedAt, auto });  // SIMULATED delivery
  deps.store.audit(d.id, auto ? "auto_sent" : "sent");
}

/** Human decisions. These are what the agent learns from. */
export function review(deps: Deps, id: string, action: { type: "send"; finalReply?: string; reason?: string } | { type: "reject"; replacement: string; reason: string } | { type: "expert"; reason?: string }): Draft {
  const d = deps.store.get(id);
  if (!d) throw new Error("draft not found");
  if (d.status !== "pending") throw new Error(`draft already ${d.status}`);
  const st = deps.store.db.autonomy;
  if (action.type === "send") {
    const finalReply = action.finalReply ?? d.reply;
    if (!finalReply.trim()) throw new Error("cannot send an empty reply");
    const unchanged = d.reply !== "" && isUnchanged(d.reply, finalReply);
    if (!unchanged && action.reason) d.correctionReason = action.reason;
    send(deps, d, finalReply, false);
    recordReview(st, d.classification.category, unchanged ? "sent_unchanged" : "sent_edited");
  } else if (action.type === "reject") {
    d.status = "rejected"; d.finalReply = action.replacement; d.correctionReason = action.reason; d.resolvedAt = new Date().toISOString();
    deps.store.db.outbox.push({ draftId: d.id, to: d.email.from, subject: `Re: ${d.email.subject}`, body: action.replacement, sentAt: d.resolvedAt, auto: false });
    recordReview(st, d.classification.category, "rejected");
    deps.store.audit(d.id, "rejected_replaced");
  } else {
    d.status = "expert"; d.correctionReason = action.reason ?? "needs expert"; d.resolvedAt = new Date().toISOString();
    recordReview(st, d.classification.category, "expert");
    deps.store.audit(d.id, "escalated_to_expert");
  }
  deps.store.save();
  return d;
}
