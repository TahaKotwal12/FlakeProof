"use client";

import { ChevronDown, ChevronUp, Pin, PinOff } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import type { RunEvent } from "@/lib/types";

const LEVEL_CLASSES: Record<string, string> = {
  info: "text-status-info",
  warn: "text-status-flaky",
  error: "text-status-fail",
  success: "text-status-pass",
};

export function LiveConsole({ events, defaultOpen = true }: { events: RunEvent[]; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  const [pinned, setPinned] = useState(true);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (pinned && open && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [events, pinned, open]);

  function handleScroll() {
    const el = scrollRef.current;
    if (!el) return;
    setPinned(el.scrollHeight - el.scrollTop - el.clientHeight < 24);
  }

  return (
    <div className="rounded-lg border border-border bg-card">
      <div className="flex items-center justify-between border-b border-border px-3 py-2">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground hover:text-foreground"
          aria-expanded={open}
        >
          {open ? <ChevronUp className="size-3.5" /> : <ChevronDown className="size-3.5" />}
          Console
          <span className="font-mono text-muted-foreground/70">({events.length})</span>
        </button>
        {open && (
          <button
            type="button"
            onClick={() => setPinned((p) => !p)}
            className={cn(
              "flex items-center gap-1 text-xs",
              pinned ? "text-status-info" : "text-muted-foreground hover:text-foreground"
            )}
            title={pinned ? "Auto-scrolling to newest" : "Pin to bottom"}
          >
            {pinned ? <Pin className="size-3.5" /> : <PinOff className="size-3.5" />}
          </button>
        )}
      </div>
      {open && (
        <div
          ref={scrollRef}
          onScroll={handleScroll}
          // "collapsed to last 3 lines by default on mobile" (docs/07-UI-SPEC.md): a
          // short max-height on mobile plus pin-to-bottom auto-scroll naturally
          // shows just the tail, without separate mobile-only markup.
          className="max-h-24 overflow-y-auto px-3 py-2 font-mono text-[11px] leading-relaxed sm:max-h-96"
        >
          {events.length === 0 ? (
            <p className="text-muted-foreground">No events yet.</p>
          ) : (
            events.map((event) => (
              <div key={event.id} className="flex gap-2 py-px">
                <span className="shrink-0 text-muted-foreground/60">
                  {new Date(event.ts).toLocaleTimeString()}
                </span>
                <span className={cn("shrink-0", LEVEL_CLASSES[event.level] ?? "text-muted-foreground")}>
                  [{event.stage}]
                </span>
                <span className="break-words text-foreground/90">{event.message}</span>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
