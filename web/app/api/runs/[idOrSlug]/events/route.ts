/**
 * GET /api/runs/:id/events?after={event_id} — incremental event feed
 * (docs/04-API.md). Polling fallback when realtime websockets are
 * unavailable; returns up to 200 events with `id > after`, oldest first.
 */

import { NextResponse, type NextRequest } from "next/server";
import { errorResponse } from "@/lib/api-errors";
import { findRunByIdOrSlug } from "@/lib/run-lookup";
import { createServerClient } from "@/lib/supabase";

const EVENTS_PAGE_LIMIT = 200;

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ idOrSlug: string }> }
): Promise<NextResponse> {
  const { idOrSlug } = await params;

  const afterParam = req.nextUrl.searchParams.get("after");
  const after = afterParam && /^\d+$/.test(afterParam) ? Number(afterParam) : 0;

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
      .from("run_events")
      .select("*")
      .eq("run_id", run.id)
      .gt("id", after)
      .order("id", { ascending: true })
      .limit(EVENTS_PAGE_LIMIT);
    if (error) throw new Error(error.message);

    const events = data ?? [];
    const lastId = events.length > 0 ? events[events.length - 1].id : after;

    return NextResponse.json({ events, last_id: lastId });
  } catch (err) {
    return errorResponse(500, "internal_error", err instanceof Error ? err.message : "Unexpected error.");
  }
}
