"use client";

import { useMemo } from "react";
import { Skeleton } from "@/components/skeleton";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { useRunLive } from "@/hooks/use-run-live";
import { computePipelineSteps } from "@/lib/pipeline-steps";
import type { RunDetail } from "@/lib/run-detail";
import { AlwaysFailingCallout } from "./always-failing-callout";
import { ConnectionDot } from "./connection-dot";
import { ExportBar } from "./export-bar";
import { FindingsList } from "./findings-list";
import { LiveConsole } from "./live-console";
import { MethodologyFootnote } from "./methodology-footnote";
import { NemotronPanel } from "./nemotron-panel";
import { PipelineStepper } from "./pipeline-stepper";
import { RunHeader } from "./run-header";
import { RunMetaCard } from "./run-meta-card";
import { SandboxGrid } from "./sandbox-grid";
import { StatusBanner } from "./status-banner";
import { VerdictBanner } from "./verdict-banner";

function QueuedPlaceholder() {
  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-muted-foreground">Waiting for a worker… usually a few seconds.</p>
      <div className="flex flex-wrap gap-1">
        {Array.from({ length: 20 }).map((_, i) => (
          <Skeleton key={i} className="size-4 rounded-[3px]" />
        ))}
      </div>
    </div>
  );
}

export function RunPageClient({ initialData, slug }: { initialData: RunDetail; slug: string }) {
  const { data, connection } = useRunLive(initialData, slug);
  const { run, flaky_tests: flakyTests, stats, events_tail: events, sandbox_tree: sandboxTree, llm_usage: llmUsage } =
    data;

  const pipelineSteps = useMemo(
    () => computePipelineSteps(run.status, events, flakyTests.length > 0),
    [run.status, events, flakyTests.length]
  );

  const forksExecuted = useMemo(() => sandboxTree.filter((op) => op.kind === "fork_run").length, [sandboxTree]);
  const fixedVerifiedCount = useMemo(
    () => flakyTests.filter((f) => f.status === "fix_verified").length,
    [flakyTests]
  );

  const isDone = run.status === "done";
  const isTerminalFailure = run.status === "failed" || run.status === "canceled";

  function handleCanceled() {
    // Optimistic-ish: the realtime `runs` UPDATE subscription (or the next
    // poll) will land the authoritative status; this just avoids a stale UI
    // if neither fires immediately.
    window.location.reload();
  }

  return (
    <div className="flex min-h-screen flex-col">
      <SiteHeader />
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8 sm:px-6">
        <div className="mb-2 flex items-center justify-between gap-2">
          <RunHeader run={run} />
        </div>
        <div className="mb-6 flex justify-end">
          <ConnectionDot state={connection} />
        </div>

        <StatusBanner run={run} />

        <div className="mt-6 grid gap-6 lg:grid-cols-3">
          <div className="flex flex-col gap-6 lg:col-span-2">
            <PipelineStepper steps={pipelineSteps} />

            {isDone ? (
              <VerdictBanner
                run={run}
                flakyCount={flakyTests.length}
                fixedVerifiedCount={fixedVerifiedCount}
                testsCollected={stats.tests_collected}
              />
            ) : run.status === "queued" ? (
              <QueuedPlaceholder />
            ) : (
              <SandboxGrid sandboxOps={sandboxTree} />
            )}

            <FindingsList flakyTests={flakyTests} />

            {isDone && <AlwaysFailingCallout tests={stats.always_failing} detectRuns={run.config.detect_runs} />}
            {isDone && <ExportBar slug={run.slug} hasVerifiedFixes={fixedVerifiedCount > 0} />}

            {isDone ? (
              <MethodologyFootnote run={run} sandboxForks={forksExecuted} llmCalls={llmUsage.calls} />
            ) : (
              <LiveConsole events={events} defaultOpen={isTerminalFailure || !isDone} />
            )}
          </div>

          <div className="flex flex-col gap-4">
            <NemotronPanel status={run.status} llmUsage={llmUsage} forksExecuted={forksExecuted} />
            <RunMetaCard run={run} onCanceled={handleCanceled} />
          </div>
        </div>
      </main>
      <SiteFooter />
    </div>
  );
}
