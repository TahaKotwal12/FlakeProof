import { ExternalLink } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { MarkdownLite } from "@/components/markdown-lite";
import { formatPercent } from "@/lib/format";
import { FLAKY_STATUS_META, PERTURBATION_LABELS, ROOT_CAUSE_LABELS, TONE_CLASSES } from "@/lib/status-meta";
import type { FlakyTest } from "@/lib/types";
import { cn } from "@/lib/utils";
import { DiffViewer } from "./diff-viewer";
import { EvidenceMatrixTable } from "./evidence-matrix-table";

function triggeringCondition(flake: FlakyTest): string {
  const matrix = flake.evidence?.matrix;
  if (!matrix) return "none";
  let best: string = "none";
  let bestRate = -1;
  for (const [key, result] of Object.entries(matrix)) {
    if (!result || result.runs === 0) continue;
    const rate = result.failures / result.runs;
    if (rate > bestRate) {
      bestRate = rate;
      best = key;
    }
  }
  return best;
}

function DiagnosisTab({ flake }: { flake: FlakyTest }) {
  return (
    <div className="flex flex-col gap-4">
      {flake.root_cause && (
        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <Badge variant="outline" className="border-transparent bg-status-flaky/15 text-status-flaky">
              {ROOT_CAUSE_LABELS[flake.root_cause] ?? flake.root_cause}
            </Badge>
            {flake.confidence != null && (
              <span className="font-mono text-xs text-muted-foreground">
                {Math.round(flake.confidence * 100)}% confidence
              </span>
            )}
          </div>
          {flake.confidence != null && (
            <Progress
              value={flake.confidence * 100}
              className="h-1"
              aria-label={`Diagnosis confidence: ${Math.round(flake.confidence * 100)}%`}
            />
          )}
        </div>
      )}
      {flake.diagnosis_md ? (
        <MarkdownLite text={flake.diagnosis_md} />
      ) : (
        <p className="text-sm text-muted-foreground">Diagnosis in progress…</p>
      )}
      <div>
        <p className="mb-2 text-xs font-medium text-muted-foreground">Evidence matrix</p>
        <EvidenceMatrixTable evidence={flake.evidence} />
      </div>
    </div>
  );
}

function FixTab({ flake }: { flake: FlakyTest }) {
  if (!flake.fix_patch) {
    return (
      <p className="text-sm text-muted-foreground">
        {flake.status === "skipped" ? "No compliant patch could be generated for this test." : "Fix in progress…"}
      </p>
    );
  }
  return (
    <div className="flex flex-col gap-3">
      {flake.fix_rationale_md && <MarkdownLite text={flake.fix_rationale_md} />}
      <DiffViewer diff={flake.fix_patch} />
    </div>
  );
}

function ProofTab({ flake }: { flake: FlakyTest }) {
  if (flake.verify_total == null) {
    return <p className="text-sm text-muted-foreground">Verification hasn&apos;t run yet.</p>;
  }
  const condition = triggeringCondition(flake);
  return (
    <div className="flex flex-col gap-4">
      <p className="text-xs text-muted-foreground">
        Triggering condition: <span className="text-foreground">{PERTURBATION_LABELS[condition] ?? condition}</span>
      </p>
      <div className="grid grid-cols-2 gap-3">
        <div className="rounded-lg border border-border p-3 text-center">
          <p className="text-[10px] font-semibold tracking-wide text-muted-foreground uppercase">Before</p>
          <p className="font-mono text-2xl font-semibold tabular-nums text-status-fail">
            {flake.verify_before_failures ?? "?"}/{flake.verify_total}
          </p>
          <p className="text-xs text-muted-foreground">failed</p>
        </div>
        <div className="rounded-lg border border-border p-3 text-center">
          <p className="text-[10px] font-semibold tracking-wide text-muted-foreground uppercase">After</p>
          <p
            className={cn(
              "font-mono text-2xl font-semibold tabular-nums",
              flake.verify_after_failures === 0 ? "text-status-pass" : "text-status-fail"
            )}
          >
            {flake.verify_after_failures ?? "?"}/{flake.verify_total}
          </p>
          <p className="text-xs text-muted-foreground">failed</p>
        </div>
      </div>
    </div>
  );
}

function EvidenceTab({ flake }: { flake: FlakyTest }) {
  const sample = flake.evidence?.sample_failures ?? [];
  return (
    <div className="flex flex-col gap-4">
      {sample.length > 0 ? (
        <div className="flex flex-col gap-3">
          {sample.map((s, i) => (
            <div key={i} className="rounded-lg border border-border p-3">
              <p className="mb-1 text-xs text-muted-foreground">
                {PERTURBATION_LABELS[s.perturbation] ?? s.perturbation} — {s.message}
              </p>
              <pre className="overflow-x-auto font-mono text-[11px] whitespace-pre text-status-fail/90">
                {s.log_tail}
              </pre>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">No sample failure logs recorded.</p>
      )}
      {flake.known_reports && flake.known_reports.length > 0 && (
        <div>
          <p className="mb-2 text-xs font-medium text-muted-foreground">Known reports</p>
          <div className="flex flex-wrap gap-1.5">
            {flake.known_reports.map((report) => (
              <a
                key={report.url}
                href={report.url}
                target="_blank"
                rel="noopener noreferrer"
                title={report.relevance ? `${report.title} — ${report.relevance}` : report.title}
                className={cn(
                  "inline-flex max-w-full items-center gap-1 rounded-full border border-border",
                  "bg-secondary/40 px-2.5 py-1 text-xs text-foreground transition-colors hover:bg-secondary"
                )}
              >
                <span className="truncate">{report.title}</span>
                <ExternalLink className="size-3 shrink-0 text-muted-foreground" />
              </a>
            ))}
          </div>
          <p className="mt-2 text-[10px] text-muted-foreground">Search context by Tavily</p>
        </div>
      )}
    </div>
  );
}

const SECTIONS = [
  { key: "diagnosis", label: "Diagnosis", Component: DiagnosisTab },
  { key: "fix", label: "Fix", Component: FixTab },
  { key: "proof", label: "Proof", Component: ProofTab },
  { key: "evidence", label: "Evidence", Component: EvidenceTab },
] as const;

function FlakeCardHeader({ flake }: { flake: FlakyTest }) {
  const statusMeta = FLAKY_STATUS_META[flake.status];
  const statusTone = TONE_CLASSES[statusMeta.tone];

  return (
    <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-4 py-3">
      <p className="font-mono text-sm font-medium break-all text-foreground">{flake.test_id}</p>
      <div className="flex items-center gap-2">
        <Badge variant="outline" className="border-transparent bg-status-flaky/15 font-mono text-status-flaky">
          {formatPercent(flake.failure_rate)}
        </Badge>
        <Badge variant="outline" className={cn("border-transparent", statusTone.bg, statusTone.text)}>
          {statusMeta.label}
        </Badge>
      </div>
    </div>
  );
}

export function FlakeCard({ flake }: { flake: FlakyTest }) {
  return (
    <Card className="gap-0 overflow-hidden p-0">
      <FlakeCardHeader flake={flake} />

      {/* Desktop/tablet: tabs. */}
      <div className="hidden p-4 sm:block">
        <Tabs defaultValue="diagnosis">
          <TabsList>
            {SECTIONS.map((section) => (
              <TabsTrigger key={section.key} value={section.key}>
                {section.label}
              </TabsTrigger>
            ))}
          </TabsList>
          {SECTIONS.map(({ key, Component }) => (
            <TabsContent key={key} value={key} className="pt-4">
              <Component flake={flake} />
            </TabsContent>
          ))}
        </Tabs>
      </div>

      {/* Mobile: accordion (native <details> — no extra dependency, free a11y). */}
      <div className="divide-y divide-border sm:hidden">
        {SECTIONS.map(({ key, label, Component }) => (
          <details key={key} className="group px-4 py-3" open={key === "diagnosis"}>
            <summary className="cursor-pointer list-none text-sm font-medium text-foreground marker:hidden">
              <span className="flex items-center justify-between">
                {label}
                <span className="text-muted-foreground transition-transform group-open:rotate-180">⌄</span>
              </span>
            </summary>
            <div className="pt-3">
              <Component flake={flake} />
            </div>
          </details>
        ))}
      </div>
    </Card>
  );
}
