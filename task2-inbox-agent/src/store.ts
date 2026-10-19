import { existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import path from "node:path";
import type { AutonomyState } from "./autonomy.js";
import type { Draft } from "./types.js";

export interface AuditEvent { at: string; draftId: string; event: string; detail?: string }
export interface OutboxItem { draftId: string; to: string; subject: string; body: string; sentAt: string; auto: boolean }
export interface DbShape { drafts: Draft[]; autonomy: AutonomyState; audit: AuditEvent[]; outbox: OutboxItem[] }

/** JSON-file store (small, readable, zero setup). Writes are atomic (temp file + rename). */
export class Store {
  db: DbShape = { drafts: [], autonomy: {}, audit: [], outbox: [] };
  constructor(private file: string | null) {
    if (file && existsSync(file)) this.db = JSON.parse(readFileSync(file, "utf8")) as DbShape;
  }
  save(): void {
    if (!this.file) return;
    mkdirSync(path.dirname(this.file), { recursive: true });
    const tmp = `${this.file}.tmp`;
    writeFileSync(tmp, JSON.stringify(this.db, null, 2));
    renameSync(tmp, this.file);
  }
  audit(draftId: string, event: string, detail?: string): void {
    // audit log holds ids and events, not email bodies (personal data stays in drafts only)
    this.db.audit.push({ at: new Date().toISOString(), draftId, event, ...(detail ? { detail } : {}) });
  }
  get(id: string): Draft | undefined { return this.db.drafts.find((d) => d.id === id); }
}
