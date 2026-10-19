import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "prompts");

/** Prompts live in files and are versioned by folder (v1, v2...). The version is stored with every draft. */
export function loadPrompt(version: string, name: "classify" | "draft"): string {
  return readFileSync(path.join(root, version, `${name}.md`), "utf8");
}
