import Link from "next/link";
import { FlaskConical } from "lucide-react";
import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { RetryButton } from "@/components/retry-button";
import { listRecentRuns } from "@/lib/run-list";
import { createServerClient } from "@/lib/supabase";
import { RunCard } from "./run-card";

export async function RecentRunsGallery() {
  let client;
  try {
    client = createServerClient();
  } catch {
    return (
      <ErrorState
        title="Can't load recent runs"
        description="FlakeProof's database isn't configured yet."
      />
    );
  }

  try {
    const { runs } = await listRecentRuns(client, { limit: 9 });

    if (runs.length === 0) {
      return (
        <EmptyState
          icon={<FlaskConical className="size-6" />}
          title="No public runs yet. Yours can be first."
          description="Paste a repo above and start the first experiment."
        />
      );
    }

    return (
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {runs.map((run) => (
          <RunCard key={run.id} run={run} />
        ))}
      </div>
    );
  } catch {
    return <ErrorState title="Can't load recent runs" action={<RetryButton />} />;
  }
}

export function RecentRunsHeader() {
  return (
    <div className="mb-4 flex items-center justify-between">
      <h2 className="text-sm font-medium text-muted-foreground">Recent runs</h2>
      <Link href="/leaderboard" className="text-xs text-muted-foreground hover:text-foreground">
        View leaderboard →
      </Link>
    </div>
  );
}
