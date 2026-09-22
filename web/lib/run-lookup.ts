/**
 * Resolve the `:idOrSlug` path param used across the run-detail routes
 * (docs/04-API.md GET /api/runs/:idOrSlug, .../events, .../cancel,
 * .../report.md, .../patch.diff) to a `runs` row — checked against `slug`
 * first (what every client actually has, per POST /api/runs's `url` field),
 * falling back to `id` only when the param looks like a UUID.
 */

import type { SupabaseClient } from "@supabase/supabase-js";
import type { Run } from "./types";

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function isUuid(value: string): boolean {
  return UUID_RE.test(value);
}

export async function findRunByIdOrSlug(
  client: SupabaseClient,
  idOrSlug: string
): Promise<Run | null> {
  const bySlug = await client.from("runs").select("*").eq("slug", idOrSlug).maybeSingle();
  if (bySlug.error) throw new Error(bySlug.error.message);
  if (bySlug.data) return bySlug.data as Run;

  if (isUuid(idOrSlug)) {
    const byId = await client.from("runs").select("*").eq("id", idOrSlug).maybeSingle();
    if (byId.error) throw new Error(byId.error.message);
    if (byId.data) return byId.data as Run;
  }

  return null;
}
