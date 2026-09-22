"use client";

import { Share2 } from "lucide-react";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { RelativeTime } from "@/components/relative-time";
import { CANCELABLE_STATUSES } from "@/lib/run-status";
import { shortSha } from "@/lib/format";
import type { Run } from "@/lib/types";
import { CancelDialog } from "./cancel-dialog";

export function RunMetaCard({ run, onCanceled }: { run: Run; onCanceled: () => void }) {
  const cancelable = (CANCELABLE_STATUSES as string[]).includes(run.status);

  async function copyLink() {
    try {
      await navigator.clipboard.writeText(window.location.href);
      toast.success("Link copied");
    } catch {
      toast.error("Couldn't copy link");
    }
  }

  return (
    <Card className="gap-3 p-4">
      <CardHeader className="p-0">
        <CardTitle className="text-xs font-medium text-muted-foreground">Run details</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3 p-0 text-sm">
        <dl className="flex flex-col gap-1.5">
          <div className="flex items-center justify-between">
            <dt className="text-muted-foreground">Commit</dt>
            <dd className="font-mono text-foreground">{shortSha(run.commit_sha)}</dd>
          </div>
          <div className="flex items-center justify-between">
            <dt className="text-muted-foreground">Detect runs</dt>
            <dd className="font-mono text-foreground">{run.config.detect_runs}</dd>
          </div>
          <div className="flex items-center justify-between">
            <dt className="text-muted-foreground">Max fixes</dt>
            <dd className="font-mono text-foreground">{run.config.max_flaky_to_fix}</dd>
          </div>
          <div className="flex items-center justify-between">
            <dt className="text-muted-foreground">Base image</dt>
            <dd className="truncate font-mono text-foreground" title={run.config.base_image}>
              {run.config.base_image}
            </dd>
          </div>
          <div className="flex items-center justify-between">
            <dt className="text-muted-foreground">Created</dt>
            <dd className="text-foreground">
              <RelativeTime iso={run.created_at} />
            </dd>
          </div>
          {run.finished_at && (
            <div className="flex items-center justify-between">
              <dt className="text-muted-foreground">Finished</dt>
              <dd className="text-foreground">
                <RelativeTime iso={run.finished_at} />
              </dd>
            </div>
          )}
        </dl>

        <div className="flex flex-col gap-2 border-t border-border pt-3">
          <Button variant="outline" size="sm" className="w-full gap-1.5" onClick={copyLink}>
            <Share2 className="size-3.5" />
            Copy shareable link
          </Button>
          {cancelable && <CancelDialog runId={run.id} onCanceled={onCanceled} />}
        </div>
      </CardContent>
    </Card>
  );
}
