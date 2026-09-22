/**
 * Types mirroring supabase/migrations/0001_init.sql (enums + tables) and the
 * RunConfig shape documented in docs/03-PIPELINE.md.
 */

// ============ enums ============

export type RunStatus =
  | "queued"
  | "provisioning"
  | "detecting"
  | "diagnosing"
  | "fixing"
  | "verifying"
  | "reporting"
  | "done"
  | "failed"
  | "canceled";

export type TestOutcome = "passed" | "failed" | "error" | "skipped" | "timeout";

export type ResultPhase = "detect" | "diagnose" | "verify_before" | "verify_after";

export type FlakyStatus =
  | "detected"
  | "diagnosing"
  | "diagnosed"
  | "fixing"
  | "fix_proposed"
  | "verifying"
  | "fix_verified"
  | "fix_failed"
  | "skipped";

export type RootCause =
  | "async_race"
  | "order_dependent"
  | "time_dependent"
  | "network_external"
  | "randomness"
  | "resource_leak"
  | "concurrency_shared_state"
  | "unknown";

// The perturbations run during diagnosis (docs/03-PIPELINE.md). `test_results.perturbation`
// also allows 'none' for phases where no perturbation was applied (detect/verify).
export type Perturbation =
  | "alone"
  | "order"
  | "cpu_stress"
  | "time_shift"
  | "net_off"
  | "seed";

export type ResultPerturbation = "none" | Perturbation;

export type RunEventLevel = "info" | "warn" | "error" | "success";

// ============ RunConfig (stored in runs.config; see docs/03-PIPELINE.md) ============

export interface RunConfig {
  detect_runs: number; // forks in the detection wave (min 5, max 30), default 20
  verify_runs: number; // forks per verification wave (min 5, max 30), default 20
  max_flaky_to_fix: number; // top-N by failure rate get diagnosis+fix (max 5), default 3
  per_run_timeout_s: number; // pytest wall clock per branch, default 900
  install_timeout_s: number; // default 900
  install_max_attempts: number; // agent-assisted install retry budget, default 4
  perturbations: Perturbation[];
  diagnose_runs_per_perturbation: number; // default 6
  base_image: string; // default 'python:3.12-slim'
  tavily_enrichment: boolean;
  pinned: boolean;
}

// runs.totals jsonb shape, written by S6 (see 02-DATABASE.md)
export interface RunTotals {
  tests_collected: number;
  detect_runs: number;
  flaky_found: number;
  always_failing: number;
  fixed_verified: number;
  fix_failed: number;
  sandbox_forks: number;
  llm_calls: number;
  wall_clock_s: number;
}

// flaky_tests.evidence jsonb shape (see 03-PIPELINE.md)
export interface PerturbationResult {
  runs: number;
  failures: number;
}

export interface SampleFailure {
  perturbation: string;
  message: string;
  log_tail: string;
}

export interface FlakyEvidence {
  baseline_failure_rate: number;
  matrix: Partial<Record<Perturbation, PerturbationResult>>;
  sample_failures: SampleFailure[];
}

// flaky_tests.known_reports jsonb shape (Tavily findings, docs/05-LLM-PROMPTS.md P7)
export interface KnownReport {
  title: string;
  url: string;
  snippet: string;
  relevance?: string;
}

// ============ tables ============

export interface Run {
  id: string;
  slug: string;
  repo_url: string;
  repo_owner: string;
  repo_name: string;
  git_ref: string | null;
  commit_sha: string | null;
  status: RunStatus;
  error: string | null;
  config: RunConfig;
  totals: RunTotals | null;
  env_image_id: string | null;
  test_framework: string | null;
  ip_hash: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  updated_at: string;
}

export interface RunEvent {
  id: number;
  run_id: string;
  ts: string;
  stage: string; // 's0_intake' ... 's6_report', 'system'
  level: RunEventLevel;
  message: string;
  payload: Record<string, unknown> | null;
}

export interface TestStat {
  id: number;
  run_id: string;
  test_id: string;
  file_path: string;
  pass_count: number;
  fail_count: number;
  error_count: number;
  timeout_count: number;
  mean_duration_ms: number | null;
  is_flaky: boolean;
  is_always_failing: boolean;
}

export interface TestResult {
  id: number;
  run_id: string;
  test_id: string;
  phase: ResultPhase;
  branch_index: number;
  perturbation: ResultPerturbation;
  outcome: TestOutcome;
  duration_ms: number | null;
  failure_message: string | null;
  failure_log: string | null;
}

export interface FlakyTest {
  id: string;
  run_id: string;
  test_id: string;
  file_path: string;
  failure_rate: number;
  status: FlakyStatus;
  root_cause: RootCause | null;
  confidence: number | null;
  diagnosis_md: string | null;
  evidence: FlakyEvidence | null;
  known_reports: KnownReport[] | null;
  fix_patch: string | null;
  fix_rationale_md: string | null;
  verify_before_failures: number | null;
  verify_after_failures: number | null;
  verify_total: number | null;
}

export type LlmCallPurpose =
  | "install_fix"
  | "failure_parse"
  | "root_cause"
  | "patch_gen"
  | "patch_review"
  | "report"
  | "tavily_summarize";

export interface LlmCall {
  id: number;
  run_id: string | null;
  ts: string;
  stage: string;
  purpose: LlmCallPurpose;
  model: string;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  latency_ms: number | null;
  ok: boolean;
}

export type SandboxOpKind = "create_env" | "run" | "fork_run" | "read_file" | "write_file";

export interface SandboxOp {
  id: number;
  run_id: string;
  ts: string;
  kind: SandboxOpKind;
  label: string | null;
  image_in: string | null;
  image_out: string | null;
  exit_code: number | null;
  duration_ms: number | null;
  status: "ok" | "error" | "timeout";
}
