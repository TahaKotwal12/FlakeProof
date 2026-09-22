import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { RunPageClient } from "@/components/run/run-page-client";
import { ErrorState } from "@/components/error-state";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { getRunDetail } from "@/lib/run-detail";
import { createServerClient } from "@/lib/supabase";

export const dynamic = "force-dynamic";

interface PageProps {
  params: Promise<{ slug: string }>;
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { slug } = await params;
  try {
    const client = createServerClient();
    const detail = await getRunDetail(client, slug);
    if (!detail) return { title: "Run not found" };
    return { title: `${detail.run.repo_owner}/${detail.run.repo_name}` };
  } catch {
    return { title: "Run" };
  }
}

export default async function RunPage({ params }: PageProps) {
  const { slug } = await params;

  let client;
  try {
    client = createServerClient();
  } catch {
    return (
      <div className="flex min-h-screen flex-col">
        <SiteHeader />
        <main className="mx-auto w-full max-w-xl flex-1 px-4 py-16 sm:px-6">
          <ErrorState
            title="Can't load this run"
            description="FlakeProof's database isn't configured yet."
          />
        </main>
        <SiteFooter />
      </div>
    );
  }

  const detail = await getRunDetail(client, slug);
  if (!detail) {
    notFound();
  }

  return <RunPageClient initialData={detail} slug={slug} />;
}
