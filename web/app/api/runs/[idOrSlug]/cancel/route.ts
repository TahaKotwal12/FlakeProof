/**
 * POST /api/runs/:id/cancel (docs/04-API.md).
 *
 * Only cancelable from the states with an explicit `-> canceled` edge in
 * the state diagram (docs/03-PIPELINE.md): queued, provisioning, detecting.
 */

import { NextResponse } from "next/server";
import { errorResponse } from "@/lib/api-errors";
import { findRunByIdOrSlug } from "@/lib/run-lookup";
import { CANCELABLE_STATUSES } from "@/lib/run-status";
import { createServerClient } from "@/lib/supabase";

export async function POST(
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

    if (!CANCELABLE_STATUSES.includes(run.status)) {
      return errorResponse(409, "not_cancelable", `Run is '${run.status}' and can no longer be canceled.`);
    }

    const { error } = await client
      .from("runs")
      .update({ status: "canceled", finished_at: new Date().toISOString() })
      .eq("id", run.id);
    if (error) throw new Error(error.message);

    return NextResponse.json({ status: "canceled" });
  } catch (err) {
    return errorResponse(500, "internal_error", err instanceof Error ? err.message : "Unexpected error.");
  }
}
