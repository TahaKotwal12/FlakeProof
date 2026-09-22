/**
 * Groups the flat `sandbox_ops` audit log into "waves" for SandboxGrid
 * (docs/07-UI-SPEC.md: "A grid of small squares, one per fork in the
 * current wave"). There's no `wave_id` column in the schema — only a
 * free-text `label` (docs/03-PIPELINE.md examples: "detect fork #i",
 * "diagnose {perturbation} fork #i (test_id)") — so wave boundaries are
 * inferred heuristically from that label, with a safe fallback for any
 * shape that doesn't match.
 */

import { PERTURBATION_LABELS } from "./status-meta";
import { shortImageId } from "./format";
import type { SandboxOp } from "./types";

export type WaveKind = "detect" | "diagnose" | "verify_before" | "verify_after" | "other";

export interface SandboxWave {
  key: string;
  title: string;
  ops: SandboxOp[];
  failures: number;
  kind: WaveKind;
  /** Test id parsed from a "(test_id)" suffix in the label, when present. */
  testId: string | null;
}

export interface VerifyPair {
  testId: string;
  before: SandboxWave | null;
  after: SandboxWave | null;
}

function isFailedOp(op: SandboxOp): boolean {
  return op.status !== "ok" || (op.exit_code != null && op.exit_code !== 0);
}

function waveGroupKey(label: string): string {
  return label.replace(/#\d+/g, "").replace(/\s+/g, " ").trim();
}

function extractTestId(label: string): string | null {
  const match = /\(([^)]+)\)\s*$/.exec(label);
  return match ? match[1] : null;
}

function classifyWave(label: string): WaveKind {
  const lower = label.toLowerCase();
  if (lower.includes("verify before")) return "verify_before";
  if (lower.includes("verify after")) return "verify_after";
  if (lower.startsWith("diagnose")) return "diagnose";
  if (lower.startsWith("detect")) return "detect";
  return "other";
}

function describeWave(kind: WaveKind, groupKey: string, count: number, testId: string | null, firstOp: SandboxOp): string {
  const n = `${count} identical fork${count === 1 ? "" : "s"}`;
  switch (kind) {
    case "detect":
      return `Detection: ${n} from checkpoint ${shortImageId(firstOp.image_in)}`;
    case "diagnose": {
      const match = /diagnose\s+(\w+)\s+fork/i.exec(groupKey);
      const perturbationKey = match?.[1];
      const perturbationLabel = perturbationKey ? (PERTURBATION_LABELS[perturbationKey] ?? perturbationKey) : groupKey;
      return `Perturbation: ${perturbationLabel} ×${count}${testId ? ` — ${testId}` : ""}`;
    }
    case "verify_before":
      return `Verify BEFORE ×${count}${testId ? ` — ${testId}` : ""}`;
    case "verify_after":
      return `Verify AFTER ×${count}${testId ? ` — ${testId}` : ""}`;
    default:
      return `${groupKey} ×${count}`;
  }
}

export function groupSandboxWaves(ops: SandboxOp[]): SandboxWave[] {
  const forkOps = ops.filter((op) => op.kind === "fork_run");
  const order: string[] = [];
  const groups = new Map<string, SandboxOp[]>();

  for (const op of forkOps) {
    const key = waveGroupKey(op.label ?? op.kind);
    if (!groups.has(key)) {
      groups.set(key, []);
      order.push(key);
    }
    groups.get(key)!.push(op);
  }

  return order.map((key) => {
    const groupOps = groups.get(key)!;
    const label = groupOps[0].label ?? "";
    const kind = classifyWave(label);
    const testId = extractTestId(label);
    return {
      key,
      title: describeWave(kind, key, groupOps.length, testId, groupOps[0]),
      ops: groupOps,
      failures: groupOps.filter(isFailedOp).length,
      kind,
      testId,
    };
  });
}

/** Pulls matching verify_before/verify_after waves (by test id) out for the side-by-side layout. */
export function pairVerifyWaves(waves: SandboxWave[]): { pairs: VerifyPair[]; rest: SandboxWave[] } {
  const verifyByTestId = new Map<string, VerifyPair>();
  const rest: SandboxWave[] = [];

  for (const wave of waves) {
    if ((wave.kind === "verify_before" || wave.kind === "verify_after") && wave.testId) {
      const existing = verifyByTestId.get(wave.testId) ?? { testId: wave.testId, before: null, after: null };
      if (wave.kind === "verify_before") existing.before = wave;
      else existing.after = wave;
      verifyByTestId.set(wave.testId, existing);
    } else {
      rest.push(wave);
    }
  }

  return { pairs: Array.from(verifyByTestId.values()), rest };
}
