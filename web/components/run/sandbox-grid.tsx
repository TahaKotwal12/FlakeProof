import { pairVerifyWaves, groupSandboxWaves, type SandboxWave, type VerifyPair } from "@/lib/sandbox-waves";
import type { SandboxOp } from "@/lib/types";
import { SandboxSquare } from "./sandbox-square";

function WaveHeader({ wave }: { wave: SandboxWave }) {
  return (
    <div className="flex items-center justify-between gap-2 text-xs">
      <span className="text-foreground">{wave.title}</span>
      <span className="font-mono text-muted-foreground">
        {wave.failures}/{wave.ops.length} failed
      </span>
    </div>
  );
}

function WaveSquares({ ops }: { ops: SandboxOp[] }) {
  return (
    <div className="hidden flex-wrap gap-1 sm:flex" aria-hidden>
      {ops.map((op) => (
        <SandboxSquare key={op.id} op={op} />
      ))}
    </div>
  );
}

function WaveSection({ wave }: { wave: SandboxWave }) {
  return (
    <div className="flex flex-col gap-1.5">
      <WaveHeader wave={wave} />
      <WaveSquares ops={wave.ops} />
    </div>
  );
}

function VerifyPairSection({ pair }: { pair: VerifyPair }) {
  return (
    <div className="rounded-lg border border-border p-3">
      <p className="mb-2 font-mono text-xs text-muted-foreground">{pair.testId}</p>
      <div className="grid gap-3 sm:grid-cols-2">
        {(["before", "after"] as const).map((side) => {
          const wave = pair[side];
          return (
            <div key={side} className="flex flex-col gap-1.5">
              <span className="text-[10px] font-semibold tracking-wide text-muted-foreground uppercase">
                {side}
              </span>
              {wave ? (
                <>
                  <p className="font-mono text-2xl font-semibold tabular-nums text-foreground">
                    {wave.failures}/{wave.ops.length}{" "}
                    <span className="text-sm font-normal text-muted-foreground">failed</span>
                  </p>
                  <WaveSquares ops={wave.ops} />
                </>
              ) : (
                <p className="text-xs text-muted-foreground">Pending…</p>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function WaveSummaryChips({ waves, pairs }: { waves: SandboxWave[]; pairs: VerifyPair[] }) {
  const allWaves = [
    ...waves,
    ...pairs.flatMap((p) => [p.before, p.after].filter((w): w is SandboxWave => w !== null)),
  ];

  if (allWaves.length === 0) return null;

  return (
    <div className="flex flex-wrap gap-2">
      {allWaves.map((wave) => (
        <span
          key={wave.key + wave.title}
          className="rounded-full border border-border bg-muted/50 px-2.5 py-1 text-xs text-muted-foreground"
        >
          {wave.title} · <span className="font-mono">{wave.failures}/{wave.ops.length}</span>
        </span>
      ))}
    </div>
  );
}

export function SandboxGrid({ sandboxOps, collapsed = false }: { sandboxOps: SandboxOp[]; collapsed?: boolean }) {
  const allWaves = groupSandboxWaves(sandboxOps);
  const { pairs, rest } = pairVerifyWaves(allWaves);

  if (allWaves.length === 0) {
    return <p className="text-sm text-muted-foreground">Waiting for the first sandbox forks…</p>;
  }

  if (collapsed) {
    return <WaveSummaryChips waves={rest} pairs={pairs} />;
  }

  return (
    <div className="flex flex-col gap-4">
      {rest.map((wave) => (
        <WaveSection key={wave.key} wave={wave} />
      ))}
      {pairs.map((pair) => (
        <VerifyPairSection key={pair.testId} pair={pair} />
      ))}
    </div>
  );
}
