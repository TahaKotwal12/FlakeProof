export function Hero() {
  return (
    <div className="flex flex-col items-center gap-4 pt-16 pb-10 text-center sm:pt-24">
      <p className="font-mono text-xs tracking-widest text-status-flaky uppercase">FlakeProof</p>
      <h1 className="max-w-3xl text-balance text-3xl font-semibold tracking-tight sm:text-5xl">
        Flaky-test tools watch your CI and guess.
        <br />
        <span className="text-primary">FlakeProof runs the experiment.</span>
      </h1>
      <p className="max-w-2xl text-balance text-sm text-muted-foreground sm:text-base">
        Paste a repo. Get proof, root causes, and verified fixes — powered by NVIDIA Nemotron on
        Nebius Token Factory Sandboxes.
      </p>
    </div>
  );
}
