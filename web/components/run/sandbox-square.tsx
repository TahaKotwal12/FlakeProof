"use client";

import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";
import type { SandboxOp } from "@/lib/types";

type Phase = "spawning" | "flashing" | "settled";

const SPAWN_MS = 180;
const FLASH_MS = 350;

/**
 * One fork in the grid. `sandbox_ops` rows only ever arrive already
 * terminal (no separate "started"/"finished" events), so the
 * spawn → running → pass/fail sequence in docs/07-UI-SPEC.md is
 * approximated locally: appear as a pulsing gray square, then (for a
 * failure) flash solid red before settling into the persistent amber-ring
 * "flaky evidence" state.
 */
export function SandboxSquare({ op }: { op: SandboxOp }) {
  const failed = op.status !== "ok" || (op.exit_code != null && op.exit_code !== 0);
  const [phase, setPhase] = useState<Phase>("spawning");

  useEffect(() => {
    const toNext = setTimeout(() => setPhase(failed ? "flashing" : "settled"), SPAWN_MS);
    const toSettled = failed ? setTimeout(() => setPhase("settled"), SPAWN_MS + FLASH_MS) : null;
    return () => {
      clearTimeout(toNext);
      if (toSettled) clearTimeout(toSettled);
    };
  }, [failed]);

  const label = `${op.label ?? op.kind} — ${failed ? "failed" : "passed"}${
    op.duration_ms != null ? ` in ${op.duration_ms}ms` : ""
  }`;

  return (
    <div
      role="img"
      aria-label={label}
      title={label}
      className={cn(
        "size-3.5 rounded-[3px] transition-all duration-200 motion-reduce:transition-none sm:size-4",
        phase === "spawning" && "scale-75 animate-pulse bg-muted opacity-60",
        phase === "flashing" && "scale-100 bg-status-fail opacity-100",
        phase === "settled" && !failed && "scale-100 bg-status-pass opacity-100",
        phase === "settled" && failed && "scale-100 bg-status-fail/25 opacity-100 ring-2 ring-status-flaky"
      )}
    />
  );
}
