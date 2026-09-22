/**
 * GET /api/runs/:id/report.md (docs/04-API.md) — the full report, assembled
 * from stored fields (see lib/report.ts for why there's no stored blob).
 */

import { NextResponse } from "next/server";
import { errorResponse } from "@/lib/api-errors";
import { renderReportMarkdown } from "@/lib/report";
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

    const { data: flakyTests, error } = await client
      .from("flaky_tests")
      .select("*")
      .eq("run_id", run.id)
      .order("failure_rate", { ascending: false });
    if (error) throw new Error(error.message);

    const markdown = renderReportMarkdown(run, flakyTests ?? []);

    return new NextResponse(markdown, {
      status: 200,
      headers: { "content-type": "text/markdown; charset=utf-8" },
    });
  } catch (err) {
    return errorResponse(500, "internal_error", err instanceof Error ? err.message : "Unexpected error.");
  }
}
