import { describe, expect, it } from "vitest";
import { isEligible, isUnchanged, mayAutoSend, recordReview, revoke, setAutoSend, type AutonomyState } from "../src/autonomy.js";

describe("20-consecutive-unchanged rule", () => {
  it("whitespace is not a change, a word is", () => {
    expect(isUnchanged("Hi  there\n", "Hi there")).toBe(true);
    expect(isUnchanged("Hi there", "Hi, there")).toBe(false);
  });
  it("becomes eligible at 20, not 19", () => {
    const st: AutonomyState = {};
    for (let i = 0; i < 19; i++) recordReview(st, "how_to", "sent_unchanged");
    expect(isEligible(st, "how_to")).toBe(false);
    recordReview(st, "how_to", "sent_unchanged");
    expect(isEligible(st, "how_to")).toBe(true);
  });
  it("an edit resets the streak and revokes autonomy", () => {
    const st: AutonomyState = {};
    for (let i = 0; i < 20; i++) recordReview(st, "how_to", "sent_unchanged");
    setAutoSend(st, "how_to", true);
    recordReview(st, "how_to", "sent_edited");
    expect(st.how_to).toMatchObject({ streak: 0, autoSendEnabled: false });
  });
  it("refunds can never be autonomous, even with 20 clean reviews", () => {
    const st: AutonomyState = {};
    for (let i = 0; i < 25; i++) recordReview(st, "refund_cancellation", "sent_unchanged");
    expect(isEligible(st, "refund_cancellation")).toBe(false);
    expect(() => setAutoSend(st, "refund_cancellation", true)).toThrow();
  });
  it("eligibility alone sends nothing, and per-email conditions still apply", () => {
    const st: AutonomyState = {};
    for (let i = 0; i < 20; i++) recordReview(st, "how_to", "sent_unchanged");
    const email = { category: "how_to" as const, risk: "low", needsHuman: false, knowledgeAnswered: true };
    expect(mayAutoSend(st, email)).toBe(false);
    setAutoSend(st, "how_to", true);
    expect(mayAutoSend(st, email)).toBe(true);
    expect(mayAutoSend(st, { ...email, risk: "medium" })).toBe(false);
    expect(mayAutoSend(st, { ...email, knowledgeAnswered: false })).toBe(false);
    revoke(st, "how_to", "eval regression");
    expect(mayAutoSend(st, email)).toBe(false);
  });
});
