import { NEVER_AUTONOMOUS, type Category } from "./types.js";

export const REQUIRED_STREAK = 20;

export interface CategoryState { streak: number; autoSendEnabled: boolean; revokedReason?: string }
export type AutonomyState = Partial<Record<Category, CategoryState>>;

/** "Without changing": only whitespace differences are ignored. Any other edit counts as a change. */
export function normalize(s: string): string {
  return s.replace(/\s+/g, " ").trim();
}
export function isUnchanged(generated: string, sent: string): boolean {
  return normalize(generated) === normalize(sent);
}

const get = (st: AutonomyState, c: Category): CategoryState => (st[c] ??= { streak: 0, autoSendEnabled: false });

/** Called once per HUMAN-reviewed draft. 'Same kind' = same category. */
export function recordReview(st: AutonomyState, category: Category, outcome: "sent_unchanged" | "sent_edited" | "rejected" | "expert"): void {
  const s = get(st, category);
  if (outcome === "sent_unchanged") { s.streak += 1; return; }
  s.streak = 0;                                  // any edit/rejection resets the count...
  if (s.autoSendEnabled) {                       // ...and takes autonomy away
    s.autoSendEnabled = false;
    s.revokedReason = `human ${outcome === "sent_edited" ? "edited" : outcome} a draft`;
  }
}

/** Eligible = enough clean reviews AND the category is allowed to ever be autonomous. */
export function isEligible(st: AutonomyState, category: Category): boolean {
  return !NEVER_AUTONOMOUS.includes(category) && get(st, category).streak >= REQUIRED_STREAK;
}

/** A human must switch it on (configurable + reversible). Eligibility alone never sends anything. */
export function setAutoSend(st: AutonomyState, category: Category, enabled: boolean): void {
  if (enabled && !isEligible(st, category)) throw new Error(`category '${category}' is not eligible for autonomous sending`);
  const s = get(st, category);
  s.autoSendEnabled = enabled;
  if (!enabled) s.revokedReason = "switched off by a human";
}

/** Per-email safety conditions on top of the category switch. */
export function mayAutoSend(st: AutonomyState, d: { category: Category; risk: string; needsHuman: boolean; knowledgeAnswered: boolean }): boolean {
  return get(st, d.category).autoSendEnabled && isEligible(st, d.category) && d.risk === "low" && !d.needsHuman && d.knowledgeAnswered;
}

/** Called by the regression eval or a reviewer flagging a bad auto-send. */
export function revoke(st: AutonomyState, category: Category, reason: string): void {
  const s = get(st, category);
  s.autoSendEnabled = false; s.streak = 0; s.revokedReason = reason;
}
