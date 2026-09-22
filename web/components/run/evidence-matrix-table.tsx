import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { PERTURBATION_LABELS } from "@/lib/status-meta";
import type { FlakyEvidence } from "@/lib/types";
import { cn } from "@/lib/utils";

export function EvidenceMatrixTable({ evidence }: { evidence: FlakyEvidence | null }) {
  const entries = Object.entries(evidence?.matrix ?? {}).filter(([, result]) => result);

  if (entries.length === 0) {
    return <p className="text-sm text-muted-foreground">No perturbation evidence recorded.</p>;
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Perturbation</TableHead>
          <TableHead>Failures</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {entries.map(([key, result]) => {
          const rate = result!.runs > 0 ? result!.failures / result!.runs : 0;
          return (
            <TableRow key={key}>
              <TableCell className="text-foreground">{PERTURBATION_LABELS[key] ?? key}</TableCell>
              <TableCell>
                <span
                  className={cn(
                    "inline-flex min-w-14 items-center justify-center rounded px-1.5 py-0.5 font-mono tabular-nums",
                    rate === 0 && "text-muted-foreground",
                    rate > 0 && rate < 0.5 && "bg-status-flaky/15 text-status-flaky",
                    rate >= 0.5 && "bg-status-fail/15 text-status-fail"
                  )}
                >
                  {result!.failures}/{result!.runs}
                </span>
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
