import { NextRequest } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createQueueSupabaseMock, type MockSupaResult } from "../helpers/mock-supabase";

vi.mock("@/lib/supabase", () => ({
  createServerClient: vi.fn(),
}));
vi.mock("@/lib/slug", () => ({
  generateSlug: () => "TESTSLUG01",
}));

import { createServerClient } from "@/lib/supabase";
import { POST } from "@/app/api/runs/route";

function postRequest(body: unknown, headers: Record<string, string> = {}): NextRequest {
  return new NextRequest("http://127.0.0.1:4310/api/runs", {
    method: "POST",
    headers: { "content-type": "application/json", "x-forwarded-for": "203.0.113.9", ...headers },
    body: JSON.stringify(body),
  });
}

function mockClient(queue: MockSupaResult[]) {
  const client = createQueueSupabaseMock(queue);
  vi.mocked(createServerClient).mockReturnValue(client as never);
  return client;
}

beforeEach(() => {
  vi.mocked(createServerClient).mockReset();
});

describe("POST /api/runs", () => {
  it("creates a queued run on the happy path", async () => {
    mockClient([
      { data: null, error: null }, // no active duplicate for this repo
      { data: null, error: null, count: 0 }, // per-IP rate count
      { data: null, error: null, count: 0 }, // global active-run count
      {
        data: { id: "8f14e2b0-0000-4000-8000-000000000000", slug: "TESTSLUG01", status: "queued" },
        error: null,
      }, // insert
    ]);

    const res = await POST(postRequest({ repo_url: "https://github.com/yourname/flakeproof-demo" }));
    const body = await res.json();

    expect(res.status).toBe(201);
    expect(body).toEqual({
      run_id: "8f14e2b0-0000-4000-8000-000000000000",
      slug: "TESTSLUG01",
      url: "/runs/TESTSLUG01",
      status: "queued",
    });
  });

  it("rejects a malformed repo_url with 422 invalid_repo_url", async () => {
    mockClient([]); // no DB calls should happen before validation fails

    const res = await POST(postRequest({ repo_url: "not-a-url" }));
    const body = await res.json();

    expect(res.status).toBe(422);
    expect(body.error.code).toBe("invalid_repo_url");
  });

  it("rejects a non-GitHub URL with 422 invalid_repo_url", async () => {
    mockClient([]);

    const res = await POST(postRequest({ repo_url: "https://gitlab.com/owner/repo" }));
    const body = await res.json();

    expect(res.status).toBe(422);
    expect(body.error.code).toBe("invalid_repo_url");
  });

  it("rejects an out-of-schema config with 422 invalid_config", async () => {
    mockClient([]);

    const res = await POST(
      postRequest({
        repo_url: "https://github.com/yourname/flakeproof-demo",
        config: { detect_runs: "twenty" },
      })
    );
    const body = await res.json();

    expect(res.status).toBe(422);
    expect(body.error.code).toBe("invalid_config");
  });

  it("returns 409 run_already_active with the existing slug when the repo already has a live run", async () => {
    mockClient([
      { data: { id: "existing-id", slug: "EXISTING01", status: "detecting" }, error: null },
    ]);

    const res = await POST(postRequest({ repo_url: "https://github.com/yourname/flakeproof-demo" }));
    const body = await res.json();

    expect(res.status).toBe(409);
    expect(body.error.code).toBe("run_already_active");
    expect(body.slug).toBe("EXISTING01");
  });

  it("returns 429 rate_limited once an IP has started 30 runs in the last hour", async () => {
    mockClient([
      { data: null, error: null }, // no active duplicate
      { data: null, error: null, count: 30 }, // already at the per-IP cap
    ]);

    const res = await POST(postRequest({ repo_url: "https://github.com/yourname/flakeproof-demo" }));
    const body = await res.json();

    expect(res.status).toBe(429);
    expect(body.error.code).toBe("rate_limited");
  });

  it("returns 429 rate_limited once the global active-run cap is reached", async () => {
    mockClient([
      { data: null, error: null }, // no active duplicate
      { data: null, error: null, count: 0 }, // under the per-IP cap
      { data: null, error: null, count: 5 }, // already at the global active cap
    ]);

    const res = await POST(postRequest({ repo_url: "https://github.com/yourname/flakeproof-demo" }));
    const body = await res.json();

    expect(res.status).toBe(429);
    expect(body.error.code).toBe("rate_limited");
  });
});
