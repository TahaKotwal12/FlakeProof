/**
 * Groupings over `RunStatus` derived from the state machine in
 * docs/03-PIPELINE.md:
 *
 *   queued -> provisioning -> detecting -> (diagnosing -> fixing -> verifying ->) reporting -> done
 *                                                                                            -> failed
 *   queued/provisioning/detecting -> canceled
 *
 * Only queued/provisioning/detecting have an explicit `-> canceled` edge in
 * that diagram, so those are the only statuses POST /cancel accepts.
 */

import type { RunStatus } from "./types";

export const ALL_RUN_STATUSES: RunStatus[] = [
  "queued",
  "provisioning",
  "detecting",
  "diagnosing",
  "fixing",
  "verifying",
  "reporting",
  "done",
  "failed",
  "canceled",
];

export const TERMINAL_STATUSES: RunStatus[] = ["done", "failed", "canceled"];

export const ACTIVE_STATUSES: RunStatus[] = ALL_RUN_STATUSES.filter(
  (status) => !TERMINAL_STATUSES.includes(status)
);

export const CANCELABLE_STATUSES: RunStatus[] = ["queued", "provisioning", "detecting"];

export function isRunStatus(value: string): value is RunStatus {
  return (ALL_RUN_STATUSES as string[]).includes(value);
}
