import { Suspense } from "react";
import { Hero } from "@/components/home/hero";
import { HowItWorks } from "@/components/home/how-it-works";
import { RepoSubmitForm } from "@/components/home/repo-submit-form";
import { GallerySkeleton } from "@/components/home/gallery-skeleton";
import { RecentRunsGallery, RecentRunsHeader } from "@/components/home/recent-runs-gallery";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";

export const dynamic = "force-dynamic";

export default function Home() {
  return (
    <div className="flex min-h-screen flex-col">
      <SiteHeader />
      <main className="flex-1">
        <div className="px-4 sm:px-6">
          <Hero />
          <RepoSubmitForm />
        </div>

        <HowItWorks />

        <section className="mx-auto w-full max-w-5xl px-4 pb-20 sm:px-6">
          <RecentRunsHeader />
          <Suspense fallback={<GallerySkeleton />}>
            <RecentRunsGallery />
          </Suspense>
        </section>
      </main>
      <SiteFooter />
    </div>
  );
}
