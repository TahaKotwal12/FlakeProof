"use client";

import { Download, Link as LinkIcon } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";

export function ExportBar({ slug, hasVerifiedFixes }: { slug: string; hasVerifiedFixes: boolean }) {
  async function copyLink() {
    try {
      await navigator.clipboard.writeText(window.location.href);
      toast.success("Link copied");
    } catch {
      toast.error("Couldn't copy link");
    }
  }

  return (
    <div className="flex flex-wrap gap-2">
      <Button variant="outline" size="sm" asChild className="gap-1.5">
        <a href={`/api/runs/${slug}/report.md`} download={`flakeproof-${slug}-report.md`}>
          <Download className="size-3.5" />
          Download report.md
        </a>
      </Button>
      <Button variant="outline" size="sm" disabled={!hasVerifiedFixes} asChild={hasVerifiedFixes} className="gap-1.5">
        {hasVerifiedFixes ? (
          <a href={`/api/runs/${slug}/patch.diff`} download={`flakeproof-${slug}-patch.diff`}>
            <Download className="size-3.5" />
            Download patch.diff
          </a>
        ) : (
          <span className="flex items-center gap-1.5" title="No verified fixes on this run yet">
            <Download className="size-3.5" />
            Download patch.diff
          </span>
        )}
      </Button>
      <Button variant="outline" size="sm" className="gap-1.5" onClick={copyLink}>
        <LinkIcon className="size-3.5" />
        Copy shareable link
      </Button>
    </div>
  );
}
