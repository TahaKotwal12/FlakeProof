import Link from "next/link";
import { SearchX } from "lucide-react";
import { Button } from "@/components/ui/button";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";

export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-col">
      <SiteHeader />
      <main className="flex flex-1 flex-col items-center justify-center gap-4 px-4 text-center">
        <SearchX className="size-10 text-muted-foreground" />
        <h1 className="text-lg font-medium text-foreground">Page not found</h1>
        <p className="max-w-sm text-sm text-muted-foreground">
          That page doesn&apos;t exist. Check the link, or head back home.
        </p>
        <Button asChild>
          <Link href="/">Back to home</Link>
        </Button>
      </main>
      <SiteFooter />
    </div>
  );
}
