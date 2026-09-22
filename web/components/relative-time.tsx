"use client";

import { useEffect, useState } from "react";
import { formatRelativeTime } from "@/lib/format";

/**
 * Renders the ISO date verbatim on the server (avoids a hydration mismatch
 * from server/client "now" drift) then swaps to a relative label after
 * mount, refreshing every 30s.
 */
export function RelativeTime({ iso, className }: { iso: string; className?: string }) {
  const [label, setLabel] = useState<string | null>(null);

  useEffect(() => {
    setLabel(formatRelativeTime(iso));
    const interval = setInterval(() => setLabel(formatRelativeTime(iso)), 30_000);
    return () => clearInterval(interval);
  }, [iso]);

  return (
    <time dateTime={iso} className={className} suppressHydrationWarning>
      {label ?? new Date(iso).toLocaleString()}
    </time>
  );
}
