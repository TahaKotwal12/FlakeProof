/**
 * The recent-runs listing query (docs/04-API.md GET /api/runs), shared by
 * the API route handler and the home page's RecentRunsGallery server
 * component.
 */

import type { SupabaseClient } from "@supabase/supabase-js";
import { isRunStatus } from "./run-status";
import type { Run, RunStatus, RunTotals } from "./types";

export type RunListItem = Pick<
  Run,
  "id" | "slug" | "repo_owner" | "repo_name" | "status" | "created_at" | "finished_at"
> & { totals: RunTotals | null };

export interface ListRunsOptions {
  limit?: number;
  offset?: number;
  status?: string | null;
  flakyOnly?: boolean;
}

export interface ListRunsResult {
  runs: RunListItem[];
  total: number;
}

export async function listRecentRuns(
  client: SupabaseClient,
  { limit = 20, offset = 0, status, flakyOnly = false }: ListRunsOptions = {}
): Promise<ListRunsResult> {
  const clampedLimit = Math.min(100, Math.max(1, Math.trunc(limit)));
  const clampedOffset = Math.max(0, Math.trunc(offset));

  let query = client
    .from("runs")
    .select("id, slug, repo_owner, repo_name, status, created_at, finished_at, totals", { count: "exact" })
    .order("created_at", { ascending: false })
    .range(clampedOffset, clampedOffset + clampedLimit - 1);

  if (status && isRunStatus(status)) {
    query = query.eq("status", status satisfies RunStatus);
  }
  if (flakyOnly) {
    // PostgREST cast-in-filter syntax: compare the jsonb totals.flaky_found
    // as an int rather than lexicographic text.
    query = query.filter("totals->>flaky_found::int", "gte", 1);
  }

  const { data, error, count } = await query;
  if (error) throw new Error(error.message);

  return { runs: (data ?? []) as RunListItem[], total: count ?? 0 };
}
