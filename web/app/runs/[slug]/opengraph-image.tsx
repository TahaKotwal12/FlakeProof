import { ImageResponse } from "next/og";
import { runHeadlineStat } from "@/lib/format";
import { findRunByIdOrSlug } from "@/lib/run-lookup";
import { createServerClient } from "@/lib/supabase";

export const size = { width: 1200, height: 630 };
export const contentType = "image/png";
export const alt = "FlakeProof run report";

/**
 * Per-run OG image (docs/07-UI-SPEC.md Polish checklist): "dark card with
 * repo name + headline stat" — what gets shared on X/LinkedIn.
 */
export default async function OpengraphImage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;

  let repoLabel = "FlakeProof";
  let headline = "Proof, not guesses.";

  try {
    const client = createServerClient();
    const run = await findRunByIdOrSlug(client, slug);
    if (run) {
      repoLabel = `${run.repo_owner}/${run.repo_name}`;
      const stat = runHeadlineStat(run.totals);
      // Satori's default font has no "✓" glyph (renders as a missing-glyph
      // box) -- runHeadlineStat's checkmark is fine in the real UI (a real
      // font stack) but not here, so it's dropped for this image only.
      headline = (stat ?? (run.status === "failed" ? "Run failed" : "Run in progress…")).replace(/\s*✓$/, "");
    }
  } catch {
    // Supabase unreachable or run not found — fall back to the defaults above.
  }

  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          padding: 64,
          background: "#0a0e14",
          color: "#e6eaf2",
          fontFamily: "monospace",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              width: 56,
              height: 56,
              borderRadius: 12,
              background: "#f59e0b",
              color: "#1a1203",
              fontSize: 28,
              fontWeight: 700,
            }}
          >
            F/
          </div>
          <div style={{ display: "flex", fontSize: 28, fontWeight: 600 }}>FlakeProof</div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div style={{ display: "flex", fontSize: 32, color: "#8a96a8" }}>{repoLabel}</div>
          <div style={{ display: "flex", fontSize: 56, fontWeight: 700, color: "#f59e0b" }}>{headline}</div>
        </div>

        <div style={{ display: "flex", fontSize: 22, color: "#8a96a8" }}>
          Powered by NVIDIA Nemotron on Nebius Token Factory Sandboxes
        </div>
      </div>
    ),
    { ...size }
  );
}
