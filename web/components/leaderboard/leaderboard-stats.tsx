import { formatCount } from "@/lib/format";
import type { LeaderboardData } from "@/lib/leaderboard";

export function LeaderboardStats({ stats }: { stats: LeaderboardData["heroStats"] }) {
  const items = [
    { label: "Repos scanned", value: stats.reposScanned },
    { label: "Identical runs executed", value: stats.identicalRunsExecuted },
    { label: "Flaky tests caught", value: stats.flakyTestsCaught },
    { label: "Fixes verified", value: stats.fixesVerified },
  ];

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      {items.map((item) => (
        <div key={item.label} className="rounded-xl border border-border bg-card p-4 text-center">
          <p className="font-mono text-2xl font-semibold tabular-nums text-foreground sm:text-3xl">
            {formatCount(item.value)}
          </p>
          <p className="mt-1 text-xs text-muted-foreground">{item.label}</p>
        </div>
      ))}
    </div>
  );
}
