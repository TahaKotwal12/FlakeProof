/**
 * Maps REST API error codes (docs/04-API.md) and `runs.error` values
 * (docs/03-PIPELINE.md failure modes) to human copy for toasts and banners.
 */

export const API_ERROR_COPY: Record<string, string> = {
  invalid_repo_url: "That doesn't look like a GitHub repository URL — try https://github.com/owner/repo.",
  invalid_config: "One of the advanced options is out of range — check detect runs and max fixes.",
  run_already_active: "This repo already has a run in progress.",
  rate_limited: "You've hit the rate limit — try again in a bit.",
  not_cancelable: "This run has already finished and can't be canceled.",
  run_not_found: "We couldn't find a run with that link.",
  no_verified_fixes: "This run doesn't have any verified fixes to export yet.",
  internal_error: "Something went wrong on our end — please try again.",
};

export function errorCodeToMessage(code: string, fallback?: string): string {
  return API_ERROR_COPY[code] ?? fallback ?? "Something went wrong — please try again.";
}

/** `runs.error` values written by the worker (docs/03-PIPELINE.md "Failure modes"). */
export const RUN_FAILURE_COPY: Record<string, string> = {
  repo_not_found: "We couldn't find that repository — double check the URL and that it's public.",
  repo_private: "FlakeProof only works on public repositories.",
  repo_too_large: "This repository is larger than the MVP supports (200 MB limit).",
  unsupported_stack: "The MVP only supports Python projects using pytest.",
  install_failed: "We couldn't get the project installed in a sandbox after several attempts.",
  run_timeout: "This run took longer than the 45-minute budget and was stopped.",
  worker_lost: "The worker lost track of this run (likely a restart) — feel free to start a new one.",
  internal_error: "Something went wrong while running this — feel free to try again.",
};

export function runFailureToMessage(error: string | null | undefined): string {
  if (!error) return "This run failed for an unspecified reason.";
  return RUN_FAILURE_COPY[error] ?? error;
}

/** "What you can try" hints shown alongside a failed run (docs/07-UI-SPEC.md). */
export function runFailureHint(error: string | null | undefined): string | null {
  switch (error) {
    case "unsupported_stack":
      return "MVP supports Python + pytest only — JS/Java/Go repos aren't supported yet.";
    case "repo_private":
      return "Make the repository public, or point FlakeProof at a public fork.";
    case "repo_too_large":
      return "Try a smaller repo, or a subdirectory checkout in a future run.";
    case "install_failed":
      return "Check that the repo installs cleanly with `pip install -e .` and lists pytest as a dependency.";
    case "run_timeout":
      return "Try again with fewer detect/verify runs, or a smaller max-fixes budget.";
    default:
      return null;
  }
}
