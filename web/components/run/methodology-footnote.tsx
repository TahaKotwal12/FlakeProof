import type { Run } from "@/lib/types";

export function MethodologyFootnote({
  run,
  sandboxForks,
  llmCalls,
}: {
  run: Run;
  sandboxForks: number;
  llmCalls: number;
}) {
  return (
    <details className="group rounded-lg border border-border p-4">
      <summary className="cursor-pointer list-none text-sm font-medium text-foreground marker:hidden">
        <span className="flex items-center justify-between">
          How FlakeProof proves flakiness
          <span className="text-muted-foreground transition-transform group-open:rotate-180">⌄</span>
        </span>
      </summary>
      <div className="mt-3 flex flex-col gap-3 text-xs text-muted-foreground">
        <p>
          FlakeProof forks one sandbox checkpoint into N bit-identical environments and runs the suite in every
          fork — same code, same starting state, so any test with mixed outcomes is provably flaky, not
          environment noise. Root causes are then isolated by controlled perturbation experiments, and every fix
          is verified empirically with fresh forks before it appears here.
        </p>
        <dl className="grid grid-cols-2 gap-x-4 gap-y-1">
          <dt>Base image</dt>
          <dd className="font-mono text-foreground">{run.config.base_image}</dd>
          <dt>Sandbox forks</dt>
          <dd className="font-mono text-foreground">{sandboxForks}</dd>
          <dt>LLM calls</dt>
          <dd className="font-mono text-foreground">{llmCalls}</dd>
        </dl>
        <pre className="overflow-x-auto rounded bg-muted p-2 font-mono text-[11px] text-foreground/80">
          {JSON.stringify(run.config, null, 2)}
        </pre>
        <div className="flex gap-3">
          <a href={run.repo_url} target="_blank" rel="noopener noreferrer" className="underline hover:text-foreground">
            Repository
          </a>
          <a
            href="https://nebiusglobalaihackathon.devpost.com/"
            target="_blank"
            rel="noopener noreferrer"
            className="underline hover:text-foreground"
          >
            Hackathon
          </a>
        </div>
      </div>
    </details>
  );
}
