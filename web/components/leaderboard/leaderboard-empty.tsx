import Link from "next/link";
import { Trophy } from "lucide-react";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/empty-state";

export function LeaderboardEmpty() {
  return (
    <EmptyState
      icon={<Trophy className="size-6" />}
      title="The public scan is coming — run your own repo meanwhile."
      action={
        <Button asChild size="sm">
          <Link href="/">Scan your repo</Link>
        </Button>
      }
    />
  );
}
