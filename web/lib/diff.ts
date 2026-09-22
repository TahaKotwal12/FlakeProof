/**
 * Small unified-diff parser for DiffViewer — no diff library, just enough to
 * color-code a unified diff (docs/07-UI-SPEC.md FlakeCard "Fix" tab: "diff
 * viewer, mono, +green/-red lines").
 */

export type DiffLineType = "file" | "hunk" | "add" | "remove" | "context" | "meta";

export interface DiffLine {
  type: DiffLineType;
  content: string;
  /** Present for add/remove/context lines when the hunk declares starting line numbers. */
  oldLine?: number;
  newLine?: number;
}

const HUNK_HEADER_RE = /^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/;

export function parseUnifiedDiff(diffText: string): DiffLine[] {
  const lines: DiffLine[] = [];
  let oldLine = 0;
  let newLine = 0;

  for (const raw of diffText.split("\n")) {
    if (raw.startsWith("+++") || raw.startsWith("---")) {
      lines.push({ type: "file", content: raw });
      continue;
    }
    if (raw.startsWith("diff ") || raw.startsWith("index ") || raw.startsWith("new file") || raw.startsWith("deleted file")) {
      lines.push({ type: "meta", content: raw });
      continue;
    }
    const hunkMatch = HUNK_HEADER_RE.exec(raw);
    if (hunkMatch) {
      oldLine = Number(hunkMatch[1]);
      newLine = Number(hunkMatch[2]);
      lines.push({ type: "hunk", content: raw });
      continue;
    }
    if (raw.startsWith("+")) {
      lines.push({ type: "add", content: raw, newLine: newLine++ });
      continue;
    }
    if (raw.startsWith("-")) {
      lines.push({ type: "remove", content: raw, oldLine: oldLine++ });
      continue;
    }
    if (raw.length === 0 && lines.length === diffText.split("\n").length - 1) {
      // trailing blank line from a final \n — skip
      continue;
    }
    lines.push({ type: "context", content: raw, oldLine: oldLine++, newLine: newLine++ });
  }

  return lines;
}

/** Net (+added / -removed) line counts, for a compact summary badge. */
export function diffStats(lines: DiffLine[]): { added: number; removed: number } {
  let added = 0;
  let removed = 0;
  for (const line of lines) {
    if (line.type === "add") added++;
    if (line.type === "remove") removed++;
  }
  return { added, removed };
}
