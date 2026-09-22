/**
 * Leaderboard data (docs/07-UI-SPEC.md "4. Leaderboard /leaderboard"):
 * done runs with their worst-offender flaky test, plus hero stat totals.
 *
 * `flaky_tests` doesn't carry a rank/rate summary on `runs` beyond
 * `totals.flaky_found`, so the "worst offender" (highest failure_rate) is
 * fetched separately for the listed runs and matched up in JS.
 */

import type { SupabaseClient } from "@supabase/supabase-js";
import type { Run, RunTotals } from "./types";

const MAX_ROWS = 100;

export interface LeaderboardRow {
  id: string;
  slug: string;
  repo_owner: string;
  repo_name: string;
  repo_url: string;
  commit_sha: string | null;
  totals: RunTotals | null;
  worstOffender: { test_id: string; failure_rate: number } | null;
}

export interface LeaderboardData {
  rows: LeaderboardRow[];
  spotlights: LeaderboardRow[];
  heroStats: {
    reposScanned: number;
    identicalRunsExecuted: number;
    flakyTestsCaught: number;
    fixesVerified: number;
  };
}

export async function getLeaderboardData(client: SupabaseClient): Promise<LeaderboardData> {
  const { data: runsData, error: runsError } = await client
    .from("runs")
    .select("id, slug, repo_owner, repo_name, repo_url, commit_sha, totals, config")
    .eq("status", "done")
    .order("created_at", { ascending: false })
    .limit(MAX_ROWS);
  if (runsError) throw new Error(runsError.message);

  const runs = (runsData ?? []) as unknown as Array<
    Pick<Run, "id" | "slug" | "repo_owner" | "repo_name" | "repo_url" | "commit_sha" | "totals" | "config">
  >;
  const pinnedRunIds = new Set(runs.filter((r) => r.config?.pinned).map((r) => r.id));

  const worstByRun = new Map<string, { test_id: string; failure_rate: number }>();
  if (runs.length > 0) {
    const runIds = runs.map((r) => r.id);
    const { data: flakyData, error: flakyError } = await client
      .from("flaky_tests")
      .select("run_id, test_id, failure_rate")
      .in("run_id", runIds)
      .order("failure_rate", { ascending: false });
    if (flakyError) throw new Error(flakyError.message);

    for (const row of flakyData ?? []) {
      if (!worstByRun.has(row.run_id)) {
        worstByRun.set(row.run_id, { test_id: row.test_id, failure_rate: row.failure_rate });
      }
    }
  }

  const rows: LeaderboardRow[] = runs
    .map((run) => ({
      id: run.id,
      slug: run.slug,
      repo_owner: run.repo_owner,
      repo_name: run.repo_name,
      repo_url: run.repo_url,
      commit_sha: run.commit_sha,
      totals: run.totals,
      worstOffender: worstByRun.get(run.id) ?? null,
    }))
    .sort((a, b) => (b.totals?.flaky_found ?? 0) - (a.totals?.flaky_found ?? 0));

  const heroStats = rows.reduce(
    (acc, row) => {
      acc.reposScanned += 1;
      acc.identicalRunsExecuted += row.totals?.detect_runs ?? 0;
      acc.flakyTestsCaught += row.totals?.flaky_found ?? 0;
      acc.fixesVerified += row.totals?.fixed_verified ?? 0;
      return acc;
    },
    { reposScanned: 0, identicalRunsExecuted: 0, flakyTestsCaught: 0, fixesVerified: 0 }
  );

  // Spotlights: runs explicitly pinned (runs.config.pinned, set at submission
  // time or via worker/scripts/batch_scan.py's evidence runs) with at least
  // one verified fix — the hand-picked "best proof" examples for judges,
  // separate from the sortable full table.
  const spotlights = rows
    .filter((row) => (row.totals?.fixed_verified ?? 0) > 0)
    .filter((row) => pinnedRunIds.has(row.id))
    .slice(0, 3);

  return { rows, spotlights, heroStats };
}
