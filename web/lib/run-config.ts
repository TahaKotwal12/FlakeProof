/**
 * RunConfig defaults and clamping (docs/03-PIPELINE.md "RunConfig").
 *
 * POST /api/runs "clamp[s] config to allowed ranges" rather than rejecting
 * numbers that are merely out of range — invalid *types* are a 422
 * `invalid_config` (see lib/validation.ts), but a `detect_runs` of 1000 is
 * silently clamped down to 30, not rejected.
 */

import type { RunConfig } from "./types";

export const PERTURBATION_VALUES = [
  "alone",
  "order",
  "cpu_stress",
  "time_shift",
  "net_off",
  "seed",
] as const;

export const DEFAULT_RUN_CONFIG: RunConfig = {
  detect_runs: 20,
  verify_runs: 20,
  max_flaky_to_fix: 3,
  per_run_timeout_s: 900,
  install_timeout_s: 900,
  install_max_attempts: 4,
  perturbations: [...PERTURBATION_VALUES],
  diagnose_runs_per_perturbation: 6,
  base_image: "python:3.12-slim",
  tavily_enrichment: true,
  pinned: false,
};

export const CONFIG_CLAMPS = {
  detect_runs: { min: 5, max: 30 },
  verify_runs: { min: 5, max: 30 },
  // 0 is valid on purpose (docs/07-UI-SPEC.md's "max fixes" slider goes 0–5):
  // detection-only, no fix attempts, is a legitimate run mode.
  max_flaky_to_fix: { min: 0, max: 5 },
} as const;

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, Math.round(value)));
}

/** Merge a partial, already type-validated config over the defaults, then clamp the bounded fields. */
export function clampRunConfig(input: Partial<RunConfig> | undefined): RunConfig {
  const merged: RunConfig = { ...DEFAULT_RUN_CONFIG, ...input };

  merged.detect_runs = clamp(merged.detect_runs, CONFIG_CLAMPS.detect_runs.min, CONFIG_CLAMPS.detect_runs.max);
  merged.verify_runs = clamp(merged.verify_runs, CONFIG_CLAMPS.verify_runs.min, CONFIG_CLAMPS.verify_runs.max);
  merged.max_flaky_to_fix = clamp(
    merged.max_flaky_to_fix,
    CONFIG_CLAMPS.max_flaky_to_fix.min,
    CONFIG_CLAMPS.max_flaky_to_fix.max
  );

  return merged;
}
