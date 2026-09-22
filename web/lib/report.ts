/**
 * Renders GET /api/runs/:id/report.md and .../patch.diff from stored fields
 * only (docs/03-PIPELINE.md Stage 6 report sections; docs/04-API.md).
 *
 * There is no `report_md` column in `runs` — the schema (0001_init.sql)
 * only stores the structured findings (`flaky_tests`) and run metadata. The
 * markdown/diff are assembled on request from those rows rather than a
 * stored blob.
 */

import type { FlakyEvidence, FlakyTest, Run } from "./types";

function formatPercent(rate: number): string {
  return `${Math.round(rate * 100)}%`;
}

function renderEvidenceMatrix(evidence: FlakyEvidence | null): string {
  const entries = Object.entries(evidence?.matrix ?? {}).filter(([, result]) => result);
  if (entries.length === 0) {
    return "_No perturbation evidence recorded._";
  }

  const rows = entries.map(([key, result]) => `| ${key} | ${result!.failures}/${result!.runs} |`);
  return ["| Perturbation | Failures |", "| --- | --- |", ...rows].join("\n");
}

function renderFlakyCard(flake: FlakyTest, index: number): string {
  const lines: string[] = [];

  lines.push(`### ${index + 1}. \`${flake.test_id}\``);
  lines.push("");
  lines.push(`- **File:** \`${flake.file_path}\``);
  lines.push(`- **Failure rate (detect phase):** ${formatPercent(flake.failure_rate)}`);
  lines.push(`- **Status:** ${flake.status}`);
  if (flake.root_cause) {
    const confidence = flake.confidence != null ? ` (confidence ${flake.confidence.toFixed(2)})` : "";
    lines.push(`- **Root cause:** ${flake.root_cause}${confidence}`);
  }
  lines.push("");

  if (flake.diagnosis_md) {
    lines.push(flake.diagnosis_md.trim());
    lines.push("");
  }

  lines.push("**Evidence matrix**");
  lines.push("");
  lines.push(renderEvidenceMatrix(flake.evidence));
  lines.push("");

  if (flake.known_reports && flake.known_reports.length > 0) {
    lines.push("**Known reports**");
    lines.push("");
    for (const report of flake.known_reports) {
      lines.push(`- [${report.title}](${report.url}) — ${report.snippet}`);
    }
    lines.push("");
  }

  if (flake.verify_total != null) {
    lines.push(
      `**Verification:** before ${flake.verify_before_failures ?? "?"}/${flake.verify_total} failed, ` +
        `after ${flake.verify_after_failures ?? "?"}/${flake.verify_total} failed.`
    );
    lines.push("");
  }

  if (flake.fix_rationale_md) {
    lines.push("**Fix rationale**");
    lines.push("");
    lines.push(flake.fix_rationale_md.trim());
    lines.push("");
  }

  if (flake.fix_patch) {
    lines.push("```diff");
    lines.push(flake.fix_patch.trimEnd());
    lines.push("```");
    lines.push("");
  }

  return lines.join("\n");
}

export function renderReportMarkdown(run: Run, flakyTests: FlakyTest[]): string {
  const lines: string[] = [];
  const repoLabel = `${run.repo_owner}/${run.repo_name}`;
  const verifiedCount = flakyTests.filter((f) => f.status === "fix_verified").length;

  lines.push(`# FlakeProof Report — ${repoLabel}`);
  lines.push("");

  if (flakyTests.length === 0) {
    const detectRuns = run.totals?.detect_runs ?? run.config?.detect_runs;
    lines.push(
      detectRuns
        ? `**No flakiness detected in ${detectRuns} identical runs.**`
        : "**No flakiness detected.**"
    );
  } else {
    const headline = `**${flakyTests.length} flaky test${flakyTests.length === 1 ? "" : "s"} caught`;
    lines.push(verifiedCount > 0 ? `${headline} and ${verifiedCount} fixed with proof.**` : `${headline}.**`);
  }
  lines.push("");

  lines.push(`- **Status:** ${run.status}`);
  if (run.commit_sha) lines.push(`- **Commit:** \`${run.commit_sha}\``);
  if (run.finished_at) lines.push(`- **Finished:** ${run.finished_at}`);
  lines.push("");

  if (flakyTests.length > 0) {
    lines.push("## Flaky tests");
    lines.push("");
    flakyTests.forEach((flake, index) => lines.push(renderFlakyCard(flake, index)));
  }

  lines.push("## How FlakeProof proves flakiness");
  lines.push("");
  lines.push(
    "FlakeProof forks one sandbox checkpoint into N bit-identical environments and runs the " +
      "test suite in every fork. Same code, same starting state — any test with mixed outcomes " +
      "across forks is provably flaky, not a fluke of the environment. Root causes are then " +
      "isolated by controlled perturbation experiments, and every fix is verified empirically " +
      "with fresh forks before it appears in this report."
  );
  lines.push("");

  lines.push("## Reproduction");
  lines.push("");
  lines.push(`- **Repo:** ${run.repo_url}`);
  if (run.git_ref) lines.push(`- **Ref:** ${run.git_ref}`);
  if (run.commit_sha) lines.push(`- **Commit SHA:** \`${run.commit_sha}\``);
  lines.push(`- **Base image:** \`${run.config?.base_image ?? "unknown"}\``);
  lines.push("");
  lines.push("```json");
  lines.push(JSON.stringify(run.config ?? {}, null, 2));
  lines.push("```");
  lines.push("");

  return lines.join("\n");
}

/** Concatenated unified diffs for status='fix_verified' flakes only (docs/04-API.md GET .../patch.diff). */
export function buildPatchDiff(flakyTests: Array<Pick<FlakyTest, "test_id" | "fix_patch">>): string {
  return flakyTests
    .filter((f) => f.fix_patch && f.fix_patch.trim().length > 0)
    .map((f) => `# ${f.test_id}\n${f.fix_patch!.trimEnd()}`)
    .join("\n\n");
}
