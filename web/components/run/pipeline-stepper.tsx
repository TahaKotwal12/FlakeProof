import { Ban, Check, Loader2, SkipForward, X } from "lucide-react";
import { cn } from "@/lib/utils";
import type { PipelineStep, StepState } from "@/lib/pipeline-steps";

const STATE_CLASSES: Record<StepState, { circle: string; label: string }> = {
  pending: { circle: "border-border bg-transparent text-muted-foreground", label: "text-muted-foreground" },
  running: { circle: "border-status-info bg-status-info/15 text-status-info", label: "text-foreground" },
  done: { circle: "border-status-pass bg-status-pass/15 text-status-pass", label: "text-foreground" },
  failed: { circle: "border-status-fail bg-status-fail/15 text-status-fail", label: "text-status-fail" },
  canceled: { circle: "border-border bg-muted text-muted-foreground", label: "text-muted-foreground" },
  skipped: { circle: "border-border bg-transparent text-muted-foreground", label: "text-muted-foreground/70" },
};

function StepIcon({ state }: { state: StepState }) {
  const className = "size-3.5";
  switch (state) {
    case "done":
      return <Check className={className} />;
    case "running":
      return <Loader2 className={cn(className, "animate-spin")} />;
    case "failed":
      return <X className={className} />;
    case "canceled":
      return <Ban className={className} />;
    case "skipped":
      return <SkipForward className={className} />;
    default:
      return <span className="size-1.5 rounded-full bg-current" />;
  }
}

export function PipelineStepper({ steps }: { steps: PipelineStep[] }) {
  return (
    <ol className="-mx-4 flex items-center gap-1 overflow-x-auto px-4 py-1 sm:mx-0 sm:gap-2 sm:overflow-visible sm:px-0">
      {steps.map((step, i) => {
        const classes = STATE_CLASSES[step.state];
        return (
          <li key={step.key} className="flex shrink-0 items-center gap-1 sm:gap-2">
            <div className="flex flex-col items-center gap-1">
              <span
                className={cn(
                  "flex size-6 items-center justify-center rounded-full border transition-colors",
                  classes.circle
                )}
                title={`${step.label}: ${step.state}`}
              >
                <StepIcon state={step.state} />
              </span>
              <span className={cn("text-[10px] font-medium whitespace-nowrap", classes.label)}>{step.label}</span>
            </div>
            {i < steps.length - 1 && (
              <span
                aria-hidden
                className={cn(
                  "mb-4 h-px w-4 shrink-0 sm:w-8",
                  step.state === "done" || step.state === "skipped" ? "bg-status-pass/40" : "bg-border"
                )}
              />
            )}
          </li>
        );
      })}
    </ol>
  );
}
