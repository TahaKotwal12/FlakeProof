export function AlwaysFailingCallout({ tests, detectRuns }: { tests: string[]; detectRuns: number }) {
  if (tests.length === 0) return null;

  return (
    <div className="rounded-lg border border-status-flaky/30 bg-status-flaky/5 p-4">
      <p className="text-sm font-medium text-status-flaky">
        {tests.length} {tests.length === 1 ? "test" : "tests"} failed in all {detectRuns} runs — broken, not
        flaky. Excluded from fixing.
      </p>
      <ul className="mt-2 flex flex-col gap-1">
        {tests.map((t) => (
          <li key={t} className="font-mono text-xs text-muted-foreground">
            {t}
          </li>
        ))}
      </ul>
    </div>
  );
}
