import { Skeleton } from "@/components/skeleton";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";

/** Route-level Suspense fallback (docs/07-UI-SPEC.md Polish checklist: "Skeletons
 * for every data region; no layout shift on load"), mirroring LeaderboardPage's layout.
 */
export default function LeaderboardLoading() {
  return (
    <div className="flex min-h-screen flex-col">
      <SiteHeader />
      <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-10 sm:px-6">
        <h1 className="mb-1 text-2xl font-semibold text-foreground">Leaderboard</h1>
        <p className="mb-8 text-sm text-muted-foreground">Real OSS repos scanned by FlakeProof.</p>

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-20 w-full rounded-xl" />
          ))}
        </div>

        <div className="mt-8 flex flex-col gap-2">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-10 w-full rounded-lg" />
          ))}
        </div>
      </main>
      <SiteFooter />
    </div>
  );
}
