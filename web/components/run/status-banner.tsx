import { Ban, TriangleAlert } from "lucide-react";
import { runFailureHint, runFailureToMessage } from "@/lib/error-copy";
import type { Run } from "@/lib/types";

export function StatusBanner({ run }: { run: Run }) {
  if (run.status === "failed") {
    const hint = runFailureHint(run.error);
    return (
      <div className="flex flex-col gap-2 rounded-lg border border-status-fail/30 bg-status-fail/10 p-4">
        <div className="flex items-center gap-2 text-status-fail">
          <TriangleAlert className="size-4" />
          <p className="text-sm font-medium">{runFailureToMessage(run.error)}</p>
        </div>
        {hint && (
          <p className="pl-6 text-xs text-muted-foreground">
            <span className="font-medium text-foreground">What you can try:</span> {hint}
          </p>
        )}
      </div>
    );
  }

  if (run.status === "canceled") {
    return (
      <div className="flex items-center gap-2 rounded-lg border border-border bg-muted/40 p-4 text-muted-foreground">
        <Ban className="size-4" />
        <p className="text-sm">This run was canceled before it finished.</p>
      </div>
    );
  }

  return null;
}
