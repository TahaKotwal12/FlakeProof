"use client";

import { Check, Copy } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { diffStats, parseUnifiedDiff } from "@/lib/diff";
import { cn } from "@/lib/utils";

const LINE_CLASSES: Record<string, string> = {
  add: "bg-status-pass/10 text-status-pass",
  remove: "bg-status-fail/10 text-status-fail",
  hunk: "text-status-info",
  file: "text-muted-foreground",
  meta: "text-muted-foreground/70",
  context: "text-foreground/80",
};

export function DiffViewer({ diff }: { diff: string }) {
  const [copied, setCopied] = useState(false);
  const lines = parseUnifiedDiff(diff);
  const { added, removed } = diffStats(lines);

  async function copyDiff() {
    try {
      await navigator.clipboard.writeText(diff);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      toast.error("Couldn't copy diff");
    }
  }

  return (
    <div className="overflow-hidden rounded-lg border border-border">
      <div className="flex items-center justify-between border-b border-border bg-muted/40 px-3 py-1.5">
        <p className="font-mono text-xs text-muted-foreground">
          <span className="text-status-pass">+{added}</span> <span className="text-status-fail">-{removed}</span>
        </p>
        <Button variant="ghost" size="xs" className="gap-1.5" onClick={copyDiff}>
          {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
          {copied ? "Copied" : "Copy"}
        </Button>
      </div>
      <div className="overflow-x-auto">
        <pre className="p-3 font-mono text-xs leading-relaxed">
          {lines.map((line, i) => (
            <div key={i} className={cn("whitespace-pre", LINE_CLASSES[line.type])}>
              {line.content || " "}
            </div>
          ))}
        </pre>
      </div>
    </div>
  );
}
