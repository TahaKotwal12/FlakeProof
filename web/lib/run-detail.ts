/**
 * The composite run-detail payload (docs/04-API.md GET /api/runs/:idOrSlug):
 * run + flaky_tests + stats + events_tail + sandbox_tree + llm_usage.
 *
 * Shared by the API route handler and the run page's server component so
 * the page can render its first paint straight from the DB instead of doing
 * a same-origin fetch back through its own API during SSR.
 */

import type { SupabaseClient } from "@supabase/supabase-js";
import { findRunByIdOrSlug } from "./run-lookup";
import type { FlakyTest, Run, RunEvent, SandboxOp } from "./types";

const EVENTS_TAIL_LIMIT = 50;

export interface RunDetail {
  run: Run;
  flaky_tests: FlakyTest[];
  stats: { tests_collected: number; always_failing: string[] };
  events_tail: RunEvent[];
  sandbox_tree: SandboxOp[];
  llm_usage: { calls: number; by_model: Record<string, number> };
}

export async function getRunDetail(client: SupabaseClient, idOrSlug: string): Promise<RunDetail | null> {
  const run = await findRunByIdOrSlug(client, idOrSlug);
  if (!run) return null;

  const [flakyRes, testStatsRes, eventsRes, sandboxRes, llmRes] = await Promise.all([
    client
      .from("flaky_tests")
      .select(
        "test_id, file_path, failure_rate, status, root_cause, confidence, diagnosis_md, evidence, " +
          "known_reports, fix_patch, fix_rationale_md, verify_before_failures, verify_after_failures, verify_total"
      )
      .eq("run_id", run.id)
      .order("failure_rate", { ascending: false }),
    client.from("test_stats").select("test_id, is_always_failing").eq("run_id", run.id),
    client
      .from("run_events")
      .select("*")
      .eq("run_id", run.id)
      .order("id", { ascending: false })
      .limit(EVENTS_TAIL_LIMIT),
    client.from("sandbox_ops").select("*").eq("run_id", run.id).order("id", { ascending: true }),
    client.from("llm_calls").select("model").eq("run_id", run.id),
  ]);

  if (flakyRes.error) throw new Error(flakyRes.error.message);
  if (testStatsRes.error) throw new Error(testStatsRes.error.message);
  if (eventsRes.error) throw new Error(eventsRes.error.message);
  if (sandboxRes.error) throw new Error(sandboxRes.error.message);
  if (llmRes.error) throw new Error(llmRes.error.message);

  const testStats = testStatsRes.data ?? [];
  const alwaysFailing = testStats.filter((t) => t.is_always_failing).map((t) => t.test_id);
  const testsCollected = run.totals?.tests_collected ?? testStats.length;

  const byModel: Record<string, number> = {};
  for (const call of llmRes.data ?? []) {
    byModel[call.model] = (byModel[call.model] ?? 0) + 1;
  }

  return {
    run,
    flaky_tests: (flakyRes.data ?? []) as unknown as FlakyTest[],
    stats: { tests_collected: testsCollected, always_failing: alwaysFailing },
    events_tail: (eventsRes.data ?? []).slice().reverse() as unknown as RunEvent[],
    sandbox_tree: (sandboxRes.data ?? []) as unknown as SandboxOp[],
    llm_usage: { calls: (llmRes.data ?? []).length, by_model: byModel },
  };
}
