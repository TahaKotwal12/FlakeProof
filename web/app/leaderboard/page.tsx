import Link from "next/link";
import type { ReactNode } from "react";
import type { Metadata } from "next";
import { Button } from "@/components/ui/button";
import { ErrorState } from "@/components/error-state";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { LeaderboardEmpty } from "@/components/leaderboard/leaderboard-empty";
import { LeaderboardStats } from "@/components/leaderboard/leaderboard-stats";
import { LeaderboardTable } from "@/components/leaderboard/leaderboard-table";
import { getLeaderboardData } from "@/lib/leaderboard";
import { createServerClient } from "@/lib/supabase";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Leaderboard" };

function LeaderboardShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col">
      <SiteHeader />
      <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-10 sm:px-6">
        <h1 className="mb-1 text-2xl font-semibold text-foreground">Leaderboard</h1>
        <p className="mb-8 text-sm text-muted-foreground">Real OSS repos scanned by FlakeProof.</p>
        {children}
      </main>
      <SiteFooter />
    </div>
  );
}

export default async function LeaderboardPage() {
  let client;
  try {
    client = createServerClient();
  } catch {
    return (
      <LeaderboardShell>
        <ErrorState title="Can't load the leaderboard" description="FlakeProof's database isn't configured yet." />
      </LeaderboardShell>
    );
  }

  try {
    const { rows, heroStats } = await getLeaderboardData(client);
    return (
      <LeaderboardShell>
        <LeaderboardStats stats={heroStats} />
        <div className="mt-8">{rows.length === 0 ? <LeaderboardEmpty /> : <LeaderboardTable rows={rows} />}</div>
        <div className="mt-8 flex flex-col items-center gap-2 text-center text-xs text-muted-foreground">
          <p>Ranked by flaky tests caught, from completed public runs.</p>
          <Button asChild size="sm" variant="outline">
            <Link href="/">Scan your repo</Link>
          </Button>
        </div>
      </LeaderboardShell>
    );
  } catch {
    return (
      <LeaderboardShell>
        <ErrorState title="Can't load the leaderboard" description="Please refresh the page." />
      </LeaderboardShell>
    );
  }
}
