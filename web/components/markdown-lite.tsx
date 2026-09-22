/**
 * Minimal hand-rolled markdown renderer for `diagnosis_md` / `fix_rationale_md`
 * (docs/07-UI-SPEC.md: "diagnosis_md rendered") — headings, **bold**, `code`,
 * "- " lists, and paragraphs. No markdown library; parses straight into React
 * nodes (never dangerouslySetInnerHTML) so LLM-authored text can't inject HTML.
 */

import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

function renderInline(text: string, keyPrefix: string): ReactNode[] {
  const parts: ReactNode[] = [];
  const pattern = /(\*\*(.+?)\*\*|`(.+?)`)/g;
  let lastIndex = 0;
  let i = 0;
  let match: RegExpExecArray | null;

  while ((match = pattern.exec(text))) {
    if (match.index > lastIndex) parts.push(text.slice(lastIndex, match.index));
    if (match[2] !== undefined) {
      parts.push(<strong key={`${keyPrefix}-b-${i++}`}>{match[2]}</strong>);
    } else if (match[3] !== undefined) {
      parts.push(
        <code key={`${keyPrefix}-c-${i++}`} className="rounded bg-muted px-1 py-0.5 font-mono text-[0.85em]">
          {match[3]}
        </code>
      );
    }
    lastIndex = pattern.lastIndex;
  }
  if (lastIndex < text.length) parts.push(text.slice(lastIndex));
  return parts;
}

export function MarkdownLite({ text, className }: { text: string; className?: string }) {
  const blocks = text.trim().split(/\n\s*\n/);

  return (
    <div className={className}>
      {blocks.map((block, bi) => {
        const heading = /^(#{1,4})\s+(.*)$/.exec(block.trim());
        if (heading) {
          const level = heading[1].length;
          return (
            <p
              key={bi}
              className={cn(
                "mt-3 mb-1.5 text-foreground first:mt-0",
                level <= 2 ? "text-sm font-semibold" : "text-sm font-medium"
              )}
            >
              {renderInline(heading[2], `h${bi}`)}
            </p>
          );
        }

        const lines = block.split("\n").filter((l) => l.trim().length > 0);
        const isList = lines.length > 0 && lines.every((l) => /^\s*[-*]\s+/.test(l));
        if (isList) {
          return (
            <ul key={bi} className="mb-2 list-disc space-y-0.5 pl-5 text-sm text-foreground/90 last:mb-0">
              {lines.map((line, li) => (
                <li key={li}>{renderInline(line.replace(/^\s*[-*]\s+/, ""), `l${bi}-${li}`)}</li>
              ))}
            </ul>
          );
        }

        return (
          <p key={bi} className="mb-2 text-sm leading-relaxed text-foreground/90 last:mb-0">
            {renderInline(block.replace(/\n/g, " "), `p${bi}`)}
          </p>
        );
      })}
    </div>
  );
}
