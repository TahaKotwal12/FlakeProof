import { Skeleton } from "@/components/skeleton";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";

/**
 * Route-level Suspense fallback for the run page (docs/07-UI-SPEC.md Polish
 * checklist: "Skeletons for every data region; no layout shift on load").
 * Mirrors RunPageClient's structure so the real content doesn't jump when it lands.
 */
export default function RunLoading() {
  return (
    <div className="flex min-h-screen flex-col">
      <SiteHeader />
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8 sm:px-6">
        <div className="mb-2 flex items-center justify-between gap-3">
          <Skeleton className="h-7 w-56" />
          <Skeleton className="h-6 w-20 rounded-full" />
        </div>
        <div className="mb-6 flex justify-end">
          <Skeleton className="h-4 w-12" />
        </div>

        <div className="mt-6 grid gap-6 lg:grid-cols-3">
          <div className="flex flex-col gap-6 lg:col-span-2">
            <div className="flex items-center gap-2">
              {Array.from({ length: 7 }).map((_, i) => (
                <Skeleton key={i} className="size-6 rounded-full" />
              ))}
            </div>

            <div className="flex flex-wrap gap-1">
              {Array.from({ length: 20 }).map((_, i) => (
                <Skeleton key={i} className="size-4 rounded-[3px]" />
              ))}
            </div>

            <div className="flex flex-col gap-3">
              <Skeleton className="h-24 w-full rounded-xl" />
              <Skeleton className="h-24 w-full rounded-xl" />
            </div>

            <Skeleton className="h-48 w-full rounded-xl" />
          </div>

          <div className="flex flex-col gap-4">
            <Skeleton className="h-40 w-full rounded-xl" />
            <Skeleton className="h-56 w-full rounded-xl" />
          </div>
        </div>
      </main>
      <SiteFooter />
    </div>
  );
}
