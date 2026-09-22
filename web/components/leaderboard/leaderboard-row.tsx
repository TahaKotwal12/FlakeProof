"use client";

import { useRouter } from "next/navigation";
import { TableCell, TableRow } from "@/components/ui/table";
import { formatPercent } from "@/lib/format";
import type { LeaderboardRow as LeaderboardRowData } from "@/lib/leaderboard";

export function LeaderboardRow({ row }: { row: LeaderboardRowData }) {
  const router = useRouter();

  return (
    <TableRow className="cursor-pointer" onClick={() => router.push(`/runs/${row.slug}`)}>
      <TableCell>
        <a
          href={row.repo_url}
          target="_blank"
          rel="noopener noreferrer"
          onClick={(e) => e.stopPropagation()}
          className="font-mono text-foreground hover:text-primary hover:underline"
        >
          {row.repo_owner}/{row.repo_name}
        </a>
      </TableCell>
      <TableCell className="font-mono tabular-nums">{row.totals?.tests_collected ?? "—"}</TableCell>
      <TableCell className="font-mono tabular-nums">{row.totals?.detect_runs ?? "—"}</TableCell>
      <TableCell className="font-mono tabular-nums">{row.totals?.flaky_found ?? 0}</TableCell>
      <TableCell>
        {row.worstOffender ? (
          <span className="font-mono text-xs">
            {row.worstOffender.test_id}{" "}
            <span className="text-muted-foreground">({formatPercent(row.worstOffender.failure_rate)})</span>
          </span>
        ) : (
          <span className="text-muted-foreground">—</span>
        )}
      </TableCell>
      <TableCell className="font-mono tabular-nums">{row.totals?.fixed_verified ?? 0}</TableCell>
      <TableCell>
        <a
          href={`/api/runs/${row.slug}/report.md`}
          onClick={(e) => e.stopPropagation()}
          className="text-xs text-muted-foreground hover:text-foreground hover:underline"
        >
          report.md
        </a>
      </TableCell>
    </TableRow>
  );
}
