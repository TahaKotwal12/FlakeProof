import Link from "next/link";
import { Sparkles } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { formatPercent } from "@/lib/format";
import type { LeaderboardRow } from "@/lib/leaderboard";

/**
 * Hand-picked "best proof" runs (docs/06-CURSOR-PROMPTS.md Prompt 13:
 * "2-3 spotlight runs with verified fixes are pinned") -- runs.config.pinned,
 * shown above the sortable full table since they're curated, not ranked.
 */
export function SpotlightRuns({ runs }: { runs: LeaderboardRow[] }) {
  if (runs.length === 0) return null;

  return (
    <div className="mb-8">
      <div className="mb-3 flex items-center gap-1.5 text-sm font-medium text-foreground">
        <Sparkles className="size-4 text-primary" />
        Spotlight: proven fixes
      </div>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {runs.map((run) => (
          <Link key={run.id} href={`/runs/${run.slug}`} className="group block">
            <Card className="h-full gap-2 p-4 transition-colors group-hover:bg-secondary/40">
              <p className="truncate font-mono text-sm font-medium text-foreground">
                {run.repo_owner}/{run.repo_name}
              </p>
              <div className="flex flex-wrap items-center gap-1.5">
                <Badge variant="outline" className="border-transparent bg-status-pass/15 text-status-pass">
                  {run.totals?.fixed_verified ?? 0} fix{(run.totals?.fixed_verified ?? 0) === 1 ? "" : "es"} verified
                </Badge>
                <Badge variant="outline" className="border-transparent bg-status-flaky/15 text-status-flaky">
                  {run.totals?.flaky_found ?? 0} flaky
                </Badge>
              </div>
              {run.worstOffender && (
                <p className="truncate font-mono text-xs text-muted-foreground">
                  {run.worstOffender.test_id} ({formatPercent(run.worstOffender.failure_rate)})
                </p>
              )}
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}
