/**
 * GET /api/runs/:id/patch.diff (docs/04-API.md) — concatenated verified
 * patches only (flaky_tests.status = 'fix_verified'). 404 no_verified_fixes
 * when there are none.
 */

import { NextResponse } from "next/server";
import { errorResponse } from "@/lib/api-errors";
import { buildPatchDiff } from "@/lib/report";
import { findRunByIdOrSlug } from "@/lib/run-lookup";
import { createServerClient } from "@/lib/supabase";

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ idOrSlug: string }> }
): Promise<NextResponse> {
  const { idOrSlug } = await params;

  let client;
  try {
    client = createServerClient();
  } catch {
    return errorResponse(500, "internal_error", "Server is misconfigured (missing Supabase credentials).");
  }

  try {
    const run = await findRunByIdOrSlug(client, idOrSlug);
    if (!run) {
      return errorResponse(404, "run_not_found", `No run found for '${idOrSlug}'.`);
    }

    const { data, error } = await client
      .from("flaky_tests")
      .select("test_id, fix_patch")
      .eq("run_id", run.id)
      .eq("status", "fix_verified");
    if (error) throw new Error(error.message);

    const diff = buildPatchDiff(data ?? []);
    if (!diff) {
      return errorResponse(404, "no_verified_fixes", "No verified fixes are available for this run.");
    }

    return new NextResponse(diff, {
      status: 200,
      headers: { "content-type": "text/x-diff; charset=utf-8" },
    });
  } catch (err) {
    return errorResponse(500, "internal_error", err instanceof Error ? err.message : "Unexpected error.");
  }
}
