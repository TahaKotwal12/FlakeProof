import { FlaskConical } from "lucide-react";
import { EmptyState } from "@/components/empty-state";
import type { FlakyTest } from "@/lib/types";
import { FlakeCard } from "./flake-card";

export function FindingsList({ flakyTests }: { flakyTests: FlakyTest[] }) {
  if (flakyTests.length === 0) {
    return (
      <EmptyState
        icon={<FlaskConical className="size-6" />}
        title="No flaky tests found yet"
        description="Findings appear here live as each fork's results come in."
      />
    );
  }

  return (
    <div className="flex flex-col gap-3">
      {flakyTests.map((flake) => (
        <FlakeCard key={flake.test_id} flake={flake} />
      ))}
    </div>
  );
}
