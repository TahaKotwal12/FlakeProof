/**
 * Maps `runs.status` (+ event stages, + whether any flakes were found) onto
 * the 7-step PipelineStepper (docs/07-UI-SPEC.md: "7 steps (Intake,
 * Provision, Detect, Diagnose, Fix, Verify, Report) with states
 * pending/running(pulse)/done/failed/skipped").
 *
 * There's no dedicated `run.status` value per step — the DB's `claim_next_run`
 * RPC moves queued -> provisioning directly, and `detecting -> reporting` is a
 * valid direct edge when no flakes are found (docs/03-PIPELINE.md state
 * diagram) — so this infers step state from status plus, for failed/canceled
 * runs, the furthest `run_events.stage` seen.
 */

import type { RunEvent, RunStatus } from "./types";

export type StepState = "pending" | "running" | "done" | "failed" | "canceled" | "skipped";

export interface PipelineStep {
  key: string;
  label: string;
  state: StepState;
}

const STEP_DEFS = [
  { key: "s0_intake", label: "Intake" },
  { key: "s1_provision", label: "Provision" },
  { key: "s2_detect", label: "Detect" },
  { key: "s3_diagnose", label: "Diagnose" },
  { key: "s4_fix", label: "Fix" },
  { key: "s5_verify", label: "Verify" },
  { key: "s6_report", label: "Report" },
] as const;

const DIAGNOSTIC_RANGE = [3, 4, 5]; // Diagnose, Fix, Verify — skippable when detect found nothing

const STATUS_TO_STEP_INDEX: Partial<Record<RunStatus, number>> = {
  provisioning: 1,
  detecting: 2,
  diagnosing: 3,
  fixing: 4,
  verifying: 5,
  reporting: 6,
  done: 7, // past the last index: everything before it is done
};

export function computePipelineSteps(
  status: RunStatus,
  events: RunEvent[],
  hasFlakyFindings: boolean
): PipelineStep[] {
  if (status === "queued") {
    return STEP_DEFS.map((s) => ({ ...s, state: "pending" as StepState }));
  }

  if (status === "failed" || status === "canceled") {
    const seenStages = new Set(events.map((e) => e.stage));
    let stoppedIndex = 0;
    STEP_DEFS.forEach((s, i) => {
      if (seenStages.has(s.key)) stoppedIndex = i;
    });
    return STEP_DEFS.map((s, i) => {
      if (i < stoppedIndex) return { ...s, state: "done" };
      if (i === stoppedIndex) return { ...s, state: status };
      return { ...s, state: "pending" };
    });
  }

  const currentIndex = STATUS_TO_STEP_INDEX[status] ?? 0;
  const skipDiagnostics = !hasFlakyFindings && currentIndex >= 6;

  return STEP_DEFS.map((s, i) => {
    if (i < currentIndex) {
      if (skipDiagnostics && DIAGNOSTIC_RANGE.includes(i)) return { ...s, state: "skipped" };
      return { ...s, state: "done" };
    }
    if (i === currentIndex) return { ...s, state: "running" };
    return { ...s, state: "pending" };
  });
}
