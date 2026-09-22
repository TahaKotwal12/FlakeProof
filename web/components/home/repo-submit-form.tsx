"use client";

import { ChevronDown, Loader2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { type FormEvent, useId, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { errorCodeToMessage } from "@/lib/error-copy";
import { cn } from "@/lib/utils";
import { normalizeRepoUrl } from "@/lib/validation";
import { RangeField } from "./range-field";

const DEFAULT_DETECT_RUNS = 20;
const DEFAULT_MAX_FIXES = 3;

interface CreateRunResponse {
  run_id?: string;
  slug?: string;
  url?: string;
  status?: string;
  error?: { code: string; message: string };
}

export function RepoSubmitForm() {
  const router = useRouter();
  const gitRefId = useId();

  const [repoUrl, setRepoUrl] = useState("");
  const [gitRef, setGitRef] = useState("");
  const [detectRuns, setDetectRuns] = useState(DEFAULT_DETECT_RUNS);
  const [maxFixes, setMaxFixes] = useState(DEFAULT_MAX_FIXES);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [urlError, setUrlError] = useState<string | null>(null);

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    void attemptSubmit();
  }

  async function attemptSubmit() {
    if (!normalizeRepoUrl(repoUrl)) {
      setUrlError("Enter a GitHub repo URL, like https://github.com/owner/repo.");
      return;
    }
    setUrlError(null);
    setSubmitting(true);

    try {
      const res = await fetch("/api/runs", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          repo_url: repoUrl.trim(),
          git_ref: gitRef.trim() || undefined,
          config: { detect_runs: detectRuns, max_flaky_to_fix: maxFixes },
        }),
      });
      const body: CreateRunResponse = await res.json();

      if (res.status === 201 && body.url) {
        router.push(body.url);
        return;
      }

      if (res.status === 409) {
        const slug = (body as CreateRunResponse & { slug?: string }).slug;
        toast.error("Already running", {
          description: body.error?.message ?? errorCodeToMessage("run_already_active"),
          action: slug ? { label: "View run", onClick: () => router.push(`/runs/${slug}`) } : undefined,
        });
        return;
      }

      if (res.status === 429) {
        toast.error("Rate limited", { description: errorCodeToMessage("rate_limited", body.error?.message) });
        return;
      }

      toast.error("Couldn't start run", {
        description: errorCodeToMessage(body.error?.code ?? "internal_error", body.error?.message),
        action: { label: "Retry", onClick: () => void attemptSubmit() },
      });
    } catch {
      toast.error("Network error", {
        description: "Couldn't reach FlakeProof — check your connection.",
        action: { label: "Retry", onClick: () => void attemptSubmit() },
      });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="mx-auto w-full max-w-xl">
      <div className="flex flex-col gap-2 sm:flex-row">
        <Input
          value={repoUrl}
          onChange={(e) => {
            setRepoUrl(e.target.value);
            if (urlError) setUrlError(null);
          }}
          placeholder="https://github.com/owner/repo"
          className="h-11 flex-1 font-mono text-sm"
          aria-invalid={urlError ? true : undefined}
          aria-describedby={urlError ? "repo-url-error" : undefined}
          autoComplete="off"
          spellCheck={false}
        />
        <Button type="submit" size="lg" className="h-11 gap-1.5 px-5" disabled={submitting}>
          {submitting && <Loader2 className="size-4 animate-spin" />}
          Run the experiment
        </Button>
      </div>
      {urlError && (
        <p id="repo-url-error" className="mt-1.5 text-xs text-status-fail">
          {urlError}
        </p>
      )}

      <button
        type="button"
        onClick={() => setAdvancedOpen((open) => !open)}
        className="mt-3 flex items-center gap-1 text-xs text-muted-foreground transition-colors hover:text-foreground"
        aria-expanded={advancedOpen}
      >
        <ChevronDown className={cn("size-3.5 transition-transform", advancedOpen && "rotate-180")} />
        Advanced
      </button>

      {advancedOpen && (
        <div className="mt-3 grid gap-4 rounded-lg border border-border bg-card p-4 sm:grid-cols-2">
          <div className="sm:col-span-2">
            <label className="mb-1.5 block text-xs font-medium text-muted-foreground" htmlFor={gitRefId}>
              Git ref{" "}
              <span className="text-muted-foreground/70">(branch, tag, or SHA — default branch if blank)</span>
            </label>
            <Input
              id={gitRefId}
              value={gitRef}
              onChange={(e) => setGitRef(e.target.value)}
              placeholder="main"
              className="font-mono text-sm"
            />
          </div>
          <RangeField
            id="detect-runs"
            label="Detect runs"
            value={detectRuns}
            onChange={setDetectRuns}
            min={5}
            max={30}
            hint="Identical forks used to prove flakiness."
          />
          <RangeField
            id="max-fixes"
            label="Max fixes"
            value={maxFixes}
            onChange={setMaxFixes}
            min={0}
            max={5}
            hint="0 = detect only, no fix attempts."
          />
        </div>
      )}
    </form>
  );
}
