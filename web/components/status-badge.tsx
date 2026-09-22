import { Ban, CheckCircle2, Clock, Loader2, XCircle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { RUN_STATUS_META, TONE_CLASSES } from "@/lib/status-meta";
import type { RunStatus } from "@/lib/types";

function StatusIcon({ status }: { status: RunStatus }) {
  const meta = RUN_STATUS_META[status];
  const className = "size-3";
  if (meta.pulse) return <Loader2 className={cn(className, "animate-spin")} />;
  if (status === "done") return <CheckCircle2 className={className} />;
  if (status === "failed") return <XCircle className={className} />;
  if (status === "canceled") return <Ban className={className} />;
  return <Clock className={className} />;
}

export function StatusBadge({ status, className }: { status: RunStatus; className?: string }) {
  const meta = RUN_STATUS_META[status];
  const tone = TONE_CLASSES[meta.tone];

  return (
    <Badge
      variant="outline"
      className={cn("gap-1.5 border-transparent font-medium", tone.bg, tone.text, className)}
    >
      <StatusIcon status={status} />
      {meta.label}
    </Badge>
  );
}
