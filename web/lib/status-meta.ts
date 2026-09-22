/**
 * Color/label metadata for `runs.status` (docs/07-UI-SPEC.md status colors:
 * pass green, fail red, flaky amber, info/running blue). Kept framework-free
 * so it can be reused by both server and client components.
 */

import type { FlakyStatus, RunStatus } from "./types";

export type StatusTone = "pass" | "fail" | "flaky" | "info" | "neutral";

export const TONE_CLASSES: Record<StatusTone, { text: string; bg: string; ring: string }> = {
  pass: { text: "text-status-pass", bg: "bg-status-pass/15", ring: "ring-status-pass/30" },
  fail: { text: "text-status-fail", bg: "bg-status-fail/15", ring: "ring-status-fail/30" },
  flaky: { text: "text-status-flaky", bg: "bg-status-flaky/15", ring: "ring-status-flaky/30" },
  info: { text: "text-status-info", bg: "bg-status-info/15", ring: "ring-status-info/30" },
  neutral: { text: "text-muted-foreground", bg: "bg-muted", ring: "ring-border" },
};

export interface RunStatusMeta {
  label: string;
  tone: StatusTone;
  pulse: boolean;
}

export const RUN_STATUS_META: Record<RunStatus, RunStatusMeta> = {
  queued: { label: "Queued", tone: "neutral", pulse: false },
  provisioning: { label: "Provisioning", tone: "info", pulse: true },
  detecting: { label: "Detecting", tone: "info", pulse: true },
  diagnosing: { label: "Diagnosing", tone: "info", pulse: true },
  fixing: { label: "Fixing", tone: "info", pulse: true },
  verifying: { label: "Verifying", tone: "info", pulse: true },
  reporting: { label: "Reporting", tone: "info", pulse: true },
  done: { label: "Done", tone: "pass", pulse: false },
  failed: { label: "Failed", tone: "fail", pulse: false },
  canceled: { label: "Canceled", tone: "neutral", pulse: false },
};

export const FLAKY_STATUS_META: Record<FlakyStatus, RunStatusMeta> = {
  detected: { label: "Detected", tone: "flaky", pulse: false },
  diagnosing: { label: "Diagnosing", tone: "info", pulse: true },
  diagnosed: { label: "Diagnosed", tone: "flaky", pulse: false },
  fixing: { label: "Fixing", tone: "info", pulse: true },
  fix_proposed: { label: "Fix proposed", tone: "info", pulse: false },
  verifying: { label: "Verifying", tone: "info", pulse: true },
  fix_verified: { label: "✅ Fix verified", tone: "pass", pulse: false },
  fix_failed: { label: "⚠️ Fix failed", tone: "fail", pulse: false },
  skipped: { label: "⏭ Skipped", tone: "neutral", pulse: false },
};

export const ROOT_CAUSE_LABELS: Record<string, string> = {
  async_race: "Async race",
  order_dependent: "Order-dependent",
  time_dependent: "Time-dependent",
  network_external: "External network",
  randomness: "Randomness",
  resource_leak: "Resource leak",
  concurrency_shared_state: "Concurrency / shared state",
  unknown: "Unknown",
};

export const PERTURBATION_LABELS: Record<string, string> = {
  alone: "Alone",
  order: "Order shuffle",
  cpu_stress: "CPU stress",
  time_shift: "Clock shift",
  net_off: "Network cut",
  seed: "Seed change",
  none: "None",
};
