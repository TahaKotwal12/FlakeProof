import { shortSha } from "@/lib/format";
import type { Run } from "@/lib/types";

export function VerdictBanner({
  run,
  flakyCount,
  fixedVerifiedCount,
  testsCollected,
}: {
  run: Run;
  flakyCount: number;
  fixedVerifiedCount: number;
  testsCollected: number;
}) {
  const detectRuns = run.totals?.detect_runs ?? run.config.detect_runs;
  const headline =
    flakyCount === 0
      ? `Clean: no flakiness in ${detectRuns} identical runs`
      : `${flakyCount} flaky ${flakyCount === 1 ? "test" : "tests"} caught${
          fixedVerifiedCount > 0 ? ` · ${fixedVerifiedCount} fixed with proof` : ""
        }`;

  return (
    <div className="rounded-xl border border-border bg-card p-5">
      <p className="text-xl font-semibold text-foreground">{headline}</p>
      <p className="mt-1 text-sm text-muted-foreground">
        Proven by forking one sandbox checkpoint into identical VMs and comparing outcomes — not guessed from CI
        history.
      </p>
      <p className="mt-2 font-mono text-xs text-muted-foreground">
        Scanned {testsCollected} tests at {shortSha(run.commit_sha)}
      </p>
    </div>
  );
}
