import Link from "next/link";
import { Card } from "@/components/ui/card";
import { RelativeTime } from "@/components/relative-time";
import { StatusBadge } from "@/components/status-badge";
import { runHeadlineStat } from "@/lib/format";
import type { RunListItem } from "@/lib/run-list";

export function RunCard({ run }: { run: RunListItem }) {
  const headline = runHeadlineStat(run.totals);

  return (
    <Link href={`/runs/${run.slug}`} className="group block">
      <Card className="h-full gap-3 p-4 transition-colors group-hover:bg-secondary/40">
        <div className="flex items-start justify-between gap-2">
          <p className="truncate font-mono text-sm font-medium text-foreground">
            {run.repo_owner}/{run.repo_name}
          </p>
          <StatusBadge status={run.status} />
        </div>
        <p className="text-sm text-muted-foreground">{headline ?? "In progress…"}</p>
        <RelativeTime iso={run.finished_at ?? run.created_at} className="text-xs text-muted-foreground/80" />
      </Card>
    </Link>
  );
}
