/**
 * GET /api/runs/:idOrSlug — full run detail (docs/04-API.md).
 *
 * The composite payload backing the run page and the polling fallback:
 * the run row, its flaky-test findings, aggregate stats, a tail of the
 * event log, the sandbox branching audit trail, and LLM usage totals.
 * Query logic lives in lib/run-detail.ts, shared with the run page's
 * server component.
 */

import { NextResponse } from "next/server";
import { errorResponse } from "@/lib/api-errors";
import { getRunDetail } from "@/lib/run-detail";
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
    const detail = await getRunDetail(client, idOrSlug);
    if (!detail) {
      return errorResponse(404, "run_not_found", `No run found for '${idOrSlug}'.`);
    }
    return NextResponse.json(detail);
  } catch (err) {
    return errorResponse(500, "internal_error", err instanceof Error ? err.message : "Unexpected error.");
  }
}
