/**
 * Shared error response shape for the FlakeProof REST API (docs/04-API.md):
 *
 *   { "error": { "code": "unsupported_stack", "message": "..." } }
 *
 * Every route handler under app/api should return errors through
 * `errorResponse()` so the shape never drifts between routes.
 */

import { NextResponse } from "next/server";

export interface ApiErrorBody {
  error: { code: string; message: string };
}

export function errorResponse(
  status: number,
  code: string,
  message: string,
  extra?: Record<string, unknown>
): NextResponse {
  return NextResponse.json({ error: { code, message }, ...extra }, { status });
}
