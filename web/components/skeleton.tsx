import { cn } from "@/lib/utils";

/** Hand-rolled skeleton block (not a shadcn primitive — just a styled div) for loading states. */
export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-md bg-muted", className)} />;
}
