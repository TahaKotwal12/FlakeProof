import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/**
 * Faded grid-of-squares illustration (CSS/SVG only, no image assets) echoing
 * the SandboxGrid's fork-square motif — docs/07-UI-SPEC.md Polish checklist:
 * "empty-state illustrations (CSS/SVG only)".
 */
function GridIllustration() {
  const cols = 10;
  const rows = 4;
  return (
    <svg
      width={cols * 14}
      height={rows * 14}
      viewBox={`0 0 ${cols * 14} ${rows * 14}`}
      fill="none"
      aria-hidden="true"
      className="text-border"
    >
      {Array.from({ length: rows }, (_, row) =>
        Array.from({ length: cols }, (_, col) => {
          const distanceFromCenter = Math.abs(row - (rows - 1) / 2) + Math.abs(col - (cols - 1) / 2);
          return (
            <rect
              key={`${row}-${col}`}
              x={col * 14}
              y={row * 14}
              width={9}
              height={9}
              rx={2}
              fill="currentColor"
              opacity={Math.max(0.08, 0.4 - distanceFromCenter * 0.045)}
            />
          );
        })
      )}
    </svg>
  );
}

export function EmptyState({
  icon,
  title,
  description,
  action,
  illustration = true,
  className,
}: {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: ReactNode;
  /** Set false to omit the decorative grid illustration (default: shown). */
  illustration?: boolean;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center gap-3 rounded-xl border border-dashed border-border px-6 py-12 text-center",
        className
      )}
    >
      {illustration && <GridIllustration />}
      {icon && <div className="text-muted-foreground">{icon}</div>}
      <p className="text-sm font-medium text-foreground">{title}</p>
      {description && <p className="max-w-sm text-sm text-muted-foreground">{description}</p>}
      {action}
    </div>
  );
}
