import { ExternalLink } from "lucide-react";
import { StatusBadge } from "@/components/status-badge";
import { shortSha } from "@/lib/format";
import type { Run } from "@/lib/types";

export function RunHeader({ run }: { run: Run }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <a
          href={run.repo_url}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-1 font-mono text-lg font-semibold text-foreground hover:text-primary"
        >
          {run.repo_owner}/{run.repo_name}
          <ExternalLink className="size-3.5 text-muted-foreground" />
        </a>
        {run.commit_sha && (
          <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs text-muted-foreground">
            @{shortSha(run.commit_sha)}
          </span>
        )}
        {run.git_ref && (
          <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs text-muted-foreground">
            {run.git_ref}
          </span>
        )}
      </div>
      <StatusBadge status={run.status} className="text-sm" />
    </div>
  );
}
