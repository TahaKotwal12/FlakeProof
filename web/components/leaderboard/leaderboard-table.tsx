import { Table, TableBody, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { LeaderboardRow as LeaderboardRowData } from "@/lib/leaderboard";
import { LeaderboardRow } from "./leaderboard-row";

export function LeaderboardTable({ rows }: { rows: LeaderboardRowData[] }) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Repo</TableHead>
          <TableHead>Tests</TableHead>
          <TableHead>Detect runs</TableHead>
          <TableHead>Flaky found</TableHead>
          <TableHead>Worst offender</TableHead>
          <TableHead>Fixed</TableHead>
          <TableHead>Report</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((row) => (
          <LeaderboardRow key={row.id} row={row} />
        ))}
      </TableBody>
    </Table>
  );
}
