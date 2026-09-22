import { cn } from "@/lib/utils";
import type { ConnectionState } from "@/hooks/use-run-live";

const DOT_CLASSES: Record<ConnectionState, string> = {
  live: "bg-status-pass",
  connecting: "bg-muted-foreground animate-pulse",
  polling: "bg-status-flaky",
};

const LABELS: Record<ConnectionState, string> = {
  live: "Live",
  connecting: "Connecting…",
  polling: "Polling (live updates unavailable)",
};

export function ConnectionDot({ state }: { state: ConnectionState }) {
  return (
    <span className="flex items-center gap-1.5 text-xs text-muted-foreground" title={LABELS[state]}>
      <span className={cn("size-1.5 rounded-full", DOT_CLASSES[state])} />
      {LABELS[state]}
    </span>
  );
}
