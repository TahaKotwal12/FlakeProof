import Link from "next/link";
import { SearchX } from "lucide-react";
import { Button } from "@/components/ui/button";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";

export function NotFoundRun() {
  return (
    <div className="flex min-h-screen flex-col">
      <SiteHeader />
      <main className="flex flex-1 flex-col items-center justify-center gap-4 px-4 text-center">
        <SearchX className="size-10 text-muted-foreground" />
        <h1 className="text-lg font-medium text-foreground">We couldn&apos;t find that run</h1>
        <p className="max-w-sm text-sm text-muted-foreground">
          The link might be wrong, or this run may have been cleaned up — runs older than 30 days are removed
          automatically unless pinned.
        </p>
        <Button asChild>
          <Link href="/">Back to home</Link>
        </Button>
      </main>
      <SiteFooter />
    </div>
  );
}
