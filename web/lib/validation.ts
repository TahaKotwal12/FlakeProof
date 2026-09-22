/**
 * zod schemas + repo URL normalization for POST /api/runs (docs/04-API.md).
 */

import { z } from "zod";
import { PERTURBATION_VALUES } from "./run-config";

// Accepts (with or without scheme/www, with or without trailing `.git`/`/`):
//   github.com/owner/repo
//   https://github.com/owner/repo.git
//   https://www.github.com/owner/repo/
const GITHUB_URL_RE =
  /^(?:https?:\/\/)?(?:www\.)?github\.com\/([A-Za-z0-9](?:[A-Za-z0-9-]{0,38}))\/([A-Za-z0-9_.-]+?)(?:\.git)?\/?$/i;

export interface NormalizedRepo {
  owner: string;
  repo: string;
  url: string;
}

/** Normalize a user-submitted GitHub URL to `https://github.com/{owner}/{repo}`, or null if invalid. */
export function normalizeRepoUrl(input: string): NormalizedRepo | null {
  const trimmed = input.trim();
  const match = GITHUB_URL_RE.exec(trimmed);
  if (!match) return null;

  const [, owner, repo] = match;
  if (!owner || !repo) return null;
  if (owner.endsWith("-")) return null; // GitHub usernames can't end with a hyphen
  if (repo === "." || repo === "..") return null;

  return { owner, repo, url: `https://github.com/${owner}/${repo}` };
}

// All RunConfig keys are optional at the API level (defaults applied below via
// clampRunConfig); `.strict()` so an unrecognized key is a 422 invalid_config
// rather than silently ignored.
export const runConfigInputSchema = z
  .object({
    detect_runs: z.number().int().positive(),
    verify_runs: z.number().int().positive(),
    max_flaky_to_fix: z.number().int().nonnegative(), // 0 = detect-only, no fix attempts

    per_run_timeout_s: z.number().int().positive(),
    install_timeout_s: z.number().int().positive(),
    install_max_attempts: z.number().int().positive(),
    perturbations: z.array(z.enum(PERTURBATION_VALUES)).min(1),
    diagnose_runs_per_perturbation: z.number().int().positive(),
    base_image: z.string().min(1).max(200),
    tavily_enrichment: z.boolean(),
    pinned: z.boolean(),
  })
  .partial()
  .strict();

export const createRunBodySchema = z.object({
  repo_url: z.string().min(1),
  git_ref: z.string().trim().min(1).max(200).optional(),
  config: runConfigInputSchema.optional(),
});

export type CreateRunBody = z.infer<typeof createRunBodySchema>;

/** Render a zod issue as `path: message` for use in a 422 error message. */
export function formatZodIssue(issue: z.core.$ZodIssue): string {
  const path = issue.path.length > 0 ? issue.path.join(".") : "body";
  return `${path}: ${issue.message}`;
}
