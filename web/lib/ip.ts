/**
 * Client IP extraction + hashing for rate limiting (POST /api/runs).
 *
 * docs/04-API.md / docs/02-DATABASE.md: `runs.ip_hash` = sha256(ip + UTC-date
 * salt). Hashing (rather than storing the raw IP) keeps the publicly
 * readable `runs` table (see RLS policies in 0001_init.sql) from leaking
 * visitor IPs; salting per UTC day means the hash for a given visitor
 * rotates daily instead of being a stable long-term identifier.
 */

import { createHash } from "node:crypto";
import type { NextRequest } from "next/server";

export function getClientIp(req: NextRequest): string {
  const forwardedFor = req.headers.get("x-forwarded-for");
  if (forwardedFor) {
    const first = forwardedFor.split(",")[0]?.trim();
    if (first) return first;
  }

  const realIp = req.headers.get("x-real-ip");
  if (realIp?.trim()) return realIp.trim();

  return "unknown";
}

export function computeIpHash(ip: string, now: Date = new Date()): string {
  const utcDateSalt = now.toISOString().slice(0, 10); // "YYYY-MM-DD"
  return createHash("sha256").update(`${ip}:${utcDateSalt}`).digest("hex");
}
