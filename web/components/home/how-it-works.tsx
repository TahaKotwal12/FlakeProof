const STEPS = [
  {
    n: "01",
    title: "Clone into a checkpoint",
    body: "Your repo is cloned and installed inside a Token Factory Sandbox — one clean, reproducible checkpoint.",
  },
  {
    n: "02",
    title: "Fork into 20 identical VMs",
    body: "The checkpoint is forked into bit-identical branches and the suite runs in every one, in parallel.",
  },
  {
    n: "03",
    title: "Perturb: order, clock, CPU, network",
    body: "Controlled experiments isolate which condition — order, timing, CPU pressure, network — triggers each flake.",
  },
  {
    n: "04",
    title: "Fix with Nemotron, verify with 20 more",
    body: "NVIDIA Nemotron proposes a patch; fresh forks re-run under the triggering condition to prove it works.",
  },
];

export function HowItWorks() {
  return (
    <section className="mx-auto w-full max-w-5xl px-4 py-16 sm:px-6">
      <h2 className="mb-8 text-center text-sm font-medium text-muted-foreground">How it works</h2>
      <ol className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
        {STEPS.map((step) => (
          <li key={step.n} className="flex flex-col gap-2">
            <span className="font-mono text-2xl font-semibold text-primary">{step.n}</span>
            <h3 className="text-sm font-medium text-foreground">{step.title}</h3>
            <p className="text-sm text-muted-foreground">{step.body}</p>
          </li>
        ))}
      </ol>
    </section>
  );
}
