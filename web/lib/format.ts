/** Small formatting helpers shared across the UI (relative time, percentages, ids). */

const RELATIVE_UNITS: Array<{ unit: Intl.RelativeTimeFormatUnit; ms: number }> = [
  { unit: "year", ms: 365 * 24 * 60 * 60 * 1000 },
  { unit: "month", ms: 30 * 24 * 60 * 60 * 1000 },
  { unit: "day", ms: 24 * 60 * 60 * 1000 },
  { unit: "hour", ms: 60 * 60 * 1000 },
  { unit: "minute", ms: 60 * 1000 },
  { unit: "second", ms: 1000 },
];

const relativeFormatter = new Intl.RelativeTimeFormat("en", { numeric: "auto" });

/** "3 minutes ago" / "in 2 hours" style relative label. */
export function formatRelativeTime(iso: string, now: Date = new Date()): string {
  const then = new Date(iso).getTime();
  const diffMs = then - now.getTime();
  const absMs = Math.abs(diffMs);

  if (absMs < 5000) return "just now";

  for (const { unit, ms } of RELATIVE_UNITS) {
    if (absMs >= ms || unit === "second") {
      const value = Math.round(diffMs / ms);
      return relativeFormatter.format(value, unit);
    }
  }
  return "just now";
}

export function formatPercent(rate: number): string {
  return `${Math.round(rate * 100)}%`;
}

export function shortSha(sha: string | null | undefined, length = 7): string {
  return sha ? sha.slice(0, length) : "—";
}

export function shortImageId(id: string | null | undefined, length = 10): string {
  if (!id) return "—";
  return id.length > length ? `${id.slice(0, length)}…` : id;
}

/** "1h 24m" / "38s" style short duration label. */
export function formatDurationShort(totalSeconds: number): string {
  if (totalSeconds < 60) return `${Math.max(0, Math.round(totalSeconds))}s`;
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = Math.round(totalSeconds % 60);
  if (minutes < 60) return seconds > 0 ? `${minutes}m ${seconds}s` : `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  const remMinutes = minutes % 60;
  return remMinutes > 0 ? `${hours}h ${remMinutes}m` : `${hours}h`;
}

export function formatCount(n: number): string {
  return new Intl.NumberFormat("en-US").format(n);
}

/** Run card headline stat (docs/07-UI-SPEC.md RecentRunsGallery: "3 flaky · 2 fixed ✓" / "clean in 20×"). */
export function runHeadlineStat(totals: { flaky_found: number; fixed_verified: number; detect_runs: number } | null): string | null {
  if (!totals) return null;
  if (totals.flaky_found === 0) return `clean in ${totals.detect_runs}×`;
  // "flaky" is the fixed adjective the spec uses ("3 flaky"), not a noun to pluralize.
  const flakyPart = `${totals.flaky_found} flaky`;
  return totals.fixed_verified > 0 ? `${flakyPart} · ${totals.fixed_verified} fixed ✓` : flakyPart;
}
