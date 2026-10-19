import { describe, expect, it } from "vitest";
import { recordReview, setAutoSend } from "../src/autonomy.js";
import { processEmail, review } from "../src/pipeline.js";
import { answered, cls, draft, email, fakeKb, FakeLLM, KnowledgeUnavailable, mkDeps } from "./helpers.js";

describe("inbox pipeline", () => {
  it("drafts from evidence and drops invented source links", async () => {
    const d = await processEmail(mkDeps(new FakeLLM([cls("how_to"), draft()]), fakeKb(answered)), email);
    expect(d.sourcesUsed).toEqual(["https://kb/logo"]);
    expect(d.status).toBe("pending");
  });
  it("does not fabricate a reply when the knowledge service is down", async () => {
    const llm = new FakeLLM([cls("how_to")]);
    const d = await processEmail(mkDeps(llm, fakeKb(new KnowledgeUnavailable("down"))), email);
    expect(d.reply).toBe("");
    expect(d.knowledge.available).toBe(false);
    expect(llm.calls.length).toBe(1);        // only the classifier ran, no drafting call
  });
  it("forces human approval for refunds even if the model says it is fine", async () => {
    const d = await processEmail(mkDeps(new FakeLLM([cls("refund_cancellation", "high"), draft({ needs_human: false })]), fakeKb(answered)), email);
    expect(d.needsHuman).toBe(true);
  });
  it("retries once on invalid JSON then falls back to a human", async () => {
    const d = await processEmail(mkDeps(new FakeLLM(["nope", "still nope"]), fakeKb(answered)), email);
    expect(d.classification).toMatchObject({ category: "other", risk: "high" });
  });
  it("cannot send the same draft twice; edit is recorded", async () => {
    const deps = mkDeps(new FakeLLM([cls("how_to"), draft()]), fakeKb(answered));
    const d = await processEmail(deps, email);
    review(deps, d.id, { type: "send", finalReply: "Edited reply", reason: "too long" });
    expect(deps.store.db.outbox.length).toBe(1);
    expect(() => review(deps, d.id, { type: "send" })).toThrow(/already sent/);
    expect(d.correctionReason).toBe("too long");
    expect(deps.store.db.autonomy.how_to?.streak).toBe(0);
  });
  it("auto-sends only after a human enabled it; an expert escalation then revokes it", async () => {
    const deps = mkDeps(new FakeLLM(Array.from({ length: 23 }, () => [cls("how_to"), draft()]).flat()), fakeKb(answered));
    for (let i = 0; i < 20; i++) { const d = await processEmail(deps, email); review(deps, d.id, { type: "send" }); }
    const d1 = await processEmail(deps, email);
    expect(d1.autoSent).toBe(false);                         // eligible, but nobody switched it on
    review(deps, d1.id, { type: "send" });
    setAutoSend(deps.store.db.autonomy, "how_to", true);
    const d2 = await processEmail(deps, email);
    expect(d2.autoSent).toBe(true);
    expect(d2.status).toBe("sent");
    const d3 = await processEmail(deps, email);             // second auto-send is also fine...
    expect(d3.autoSent).toBe(true);
    recordReview(deps.store.db.autonomy, "how_to", "expert"); // ...until a human flags a problem
    expect(deps.store.db.autonomy.how_to!.autoSendEnabled).toBe(false);
  });
});
