export function SiteFooter() {
  return (
    <footer className="border-t border-border">
      <div className="mx-auto flex max-w-6xl flex-col items-center gap-2 px-4 py-8 text-center text-xs text-muted-foreground sm:flex-row sm:justify-between sm:px-6 sm:text-left">
        <p>
          <a
            href="https://github.com/TahaKotwal12/FlakeProof"
            target="_blank"
            rel="noopener noreferrer"
            className="hover:text-foreground"
          >
            FlakeProof
          </a>{" "}
          · Built for the Nebius x NVIDIA Global AI Hackathon · MIT licensed
        </p>
        <p>Enrichment search powered by Tavily</p>
      </div>
    </footer>
  );
}
