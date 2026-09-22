/**
 * POST /api/runs — start an analysis.
 * GET  /api/runs — recent runs (gallery / leaderboard data).
 *
 * docs/04-API.md section A.
 */

import { NextResponse, type NextRequest } from "next/server";
import type { SupabaseClient } from "@supabase/supabase-js";
import { errorResponse } from "@/lib/api-errors";
import { computeIpHash, getClientIp } from "@/lib/ip";
import { clampRunConfig } from "@/lib/run-config";
import { listRecentRuns } from "@/lib/run-list";
import { generateSlug } from "@/lib/slug";
import { createServerClient } from "@/lib/supabase";
import { ACTIVE_STATUSES } from "@/lib/run-status";
import { createRunBodySchema, formatZodIssue, normalizeRepoUrl } from "@/lib/validation";

// docs/04-API.md specs "> 5 runs/hour per IP" / "> 2 globally active" — the
// Nth request that would bring the count to N+1 above the limit is rejected,
// so the limit itself is still the max allowed. Temporarily raised for
// manual/evidence-run testing; drop back to 5/2 before any real deploy.
const RATE_LIMIT_PER_IP_PER_HOUR = 30;
const RATE_LIMIT_GLOBAL_ACTIVE = 5;

function getClient(): SupabaseClient | null {
  try {
    return createServerClient();
  } catch {
    return null;
  }
}

export async function POST(req: NextRequest): Promise<NextResponse> {
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return errorResponse(422, "invalid_repo_url", "Request body must be valid JSON.");
  }

  const parsedBody = createRunBodySchema.safeParse(body);
  if (!parsedBody.success) {
    const configIssue = parsedBody.error.issues.find((issue) => issue.path[0] === "config");
    if (configIssue) {
      return errorResponse(422, "invalid_config", formatZodIssue(configIssue));
    }
    // Any other structural problem (missing/malformed repo_url, bad git_ref) —
    // there's no dedicated code for git_ref, so it shares invalid_repo_url.
    return errorResponse(422, "invalid_repo_url", formatZodIssue(parsedBody.error.issues[0]));
  }

  const normalized = normalizeRepoUrl(parsedBody.data.repo_url);
  if (!normalized) {
    return errorResponse(
      422,
      "invalid_repo_url",
      "repo_url must be a GitHub repository URL like https://github.com/owner/repo."
    );
  }

  const config = clampRunConfig(parsedBody.data.config);
  const ipHash = computeIpHash(getClientIp(req));

  const client = getClient();
  if (!client) {
    return errorResponse(500, "internal_error", "Server is misconfigured (missing Supabase credentials).");
  }

  try {
    // 1. Duplicate active run for this repo? (409 run_already_active)
    const dup = await client
      .from("runs")
      .select("id, slug, status")
      .eq("repo_owner", normalized.owner)
      .eq("repo_name", normalized.repo)
      .in("status", ACTIVE_STATUSES)
      .order("created_at", { ascending: false })
      .limit(1)
      .maybeSingle();
    if (dup.error) throw new Error(dup.error.message);
    if (dup.data) {
      return errorResponse(
        409,
        "run_already_active",
        `An active run for ${normalized.owner}/${normalized.repo} already exists.`,
        { slug: dup.data.slug }
      );
    }

    // 2. Per-IP rate limit (429 rate_limited)
    const oneHourAgo = new Date(Date.now() - 60 * 60 * 1000).toISOString();
    const ipRate = await client
      .from("runs")
      .select("id", { count: "exact", head: true })
      .eq("ip_hash", ipHash)
      .gte("created_at", oneHourAgo);
    if (ipRate.error) throw new Error(ipRate.error.message);
    if ((ipRate.count ?? 0) >= RATE_LIMIT_PER_IP_PER_HOUR) {
      return errorResponse(429, "rate_limited", "Too many runs started from this IP in the last hour.");
    }

    // 3. Global active-run cap (429 rate_limited)
    const activeCount = await client
      .from("runs")
      .select("id", { count: "exact", head: true })
      .in("status", ACTIVE_STATUSES);
    if (activeCount.error) throw new Error(activeCount.error.message);
    if ((activeCount.count ?? 0) >= RATE_LIMIT_GLOBAL_ACTIVE) {
      return errorResponse(429, "rate_limited", "FlakeProof is at capacity; please try again shortly.");
    }

    // 4. Insert
    const slug = generateSlug();
    const inserted = await client
      .from("runs")
      .insert({
        slug,
        repo_url: normalized.url,
        repo_owner: normalized.owner,
        repo_name: normalized.repo,
        git_ref: parsedBody.data.git_ref ?? null,
        status: "queued",
        config,
        ip_hash: ipHash,
      })
      .select("id, slug, status")
      .single();
    if (inserted.error) throw new Error(inserted.error.message);

    const row = inserted.data;
    return NextResponse.json(
      { run_id: row.id, slug: row.slug, url: `/runs/${row.slug}`, status: row.status },
      { status: 201 }
    );
  } catch (err) {
    return errorResponse(500, "internal_error", err instanceof Error ? err.message : "Unexpected error.");
  }
}

export async function GET(req: NextRequest): Promise<NextResponse> {
  const params = req.nextUrl.searchParams;

  const limitParam = Number(params.get("limit"));
  const limit = Number.isFinite(limitParam) && limitParam > 0 ? limitParam : 20;

  const offsetParam = Number(params.get("offset"));
  const offset = Number.isFinite(offsetParam) && offsetParam > 0 ? offsetParam : 0;

  const client = getClient();
  if (!client) {
    return errorResponse(500, "internal_error", "Server is misconfigured (missing Supabase credentials).");
  }

  try {
    const { runs, total } = await listRecentRuns(client, {
      limit,
      offset,
      status: params.get("status"),
      flakyOnly: params.get("flaky_only") === "true",
    });
    return NextResponse.json({ runs, total });
  } catch (err) {
    return errorResponse(500, "internal_error", err instanceof Error ? err.message : "Unexpected error.");
  }
}
