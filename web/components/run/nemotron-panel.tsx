import { Loader2 } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatCount } from "@/lib/format";
import type { RunStatus } from "@/lib/types";

// Live activity proxy: the composite GET's llm_usage is {calls, by_model}
// only (docs/04-API.md), no per-call purpose/timestamp, so "what Nemotron
// is doing right now" is inferred from the run's current stage instead.
const ACTIVITY_LABEL: Partial<Record<RunStatus, string>> = {
  provisioning: "Fixing install errors…",
  detecting: "Parsing test results…",
  diagnosing: "Diagnosing root cause…",
  fixing: "Generating patch…",
  verifying: "Reviewing the patch…",
  reporting: "Writing the report…",
};

export function NemotronPanel({
  status,
  llmUsage,
  forksExecuted,
}: {
  status: RunStatus;
  llmUsage: { calls: number; by_model: Record<string, number> };
  forksExecuted: number;
}) {
  const models = Object.entries(llmUsage.by_model);
  const activity = ACTIVITY_LABEL[status];

  return (
    <Card className="gap-3 p-4">
      <CardHeader className="p-0">
        <CardTitle className="text-xs font-medium text-muted-foreground">
          Powered by NVIDIA Nemotron on Nebius Token Factory
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3 p-0">
        <div className="flex items-baseline gap-2">
          <span className="font-mono text-2xl font-semibold tabular-nums">{formatCount(llmUsage.calls)}</span>
          <span className="text-xs text-muted-foreground">LLM calls</span>
        </div>

        {models.length > 0 && (
          <ul className="flex flex-col gap-1 text-xs">
            {models.map(([model, count]) => (
              <li key={model} className="flex items-center justify-between">
                <span className="font-mono text-muted-foreground">{model}</span>
                <span className="font-mono tabular-nums text-foreground">{count}</span>
              </li>
            ))}
          </ul>
        )}

        {activity && (
          <p className="flex items-center gap-1.5 text-xs text-status-info">
            <Loader2 className="size-3 animate-spin" />
            {activity}
          </p>
        )}

        <div className="flex items-baseline gap-2 border-t border-border pt-3">
          <span className="font-mono text-lg font-semibold tabular-nums">{formatCount(forksExecuted)}</span>
          <span className="text-xs text-muted-foreground">sandbox forks executed</span>
        </div>
      </CardContent>
    </Card>
  );
}
