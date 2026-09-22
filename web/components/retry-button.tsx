"use client";

import { RotateCw } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/button";

/** Re-runs the current route's server components (docs/07-UI-SPEC.md Polish
 * checklist: "Error toasts with retry actions") — used by ErrorState instances
 * that back a server-rendered data fetch, where there's no client-side
 * request to simply re-issue.
 */
export function RetryButton() {
  const router = useRouter();
  const [retrying, setRetrying] = useState(false);

  return (
    <Button
      size="sm"
      variant="outline"
      className="gap-1.5"
      disabled={retrying}
      onClick={() => {
        setRetrying(true);
        router.refresh();
        setTimeout(() => setRetrying(false), 1000);
      }}
    >
      <RotateCw className={retrying ? "size-3.5 animate-spin" : "size-3.5"} />
      {retrying ? "Retrying…" : "Retry"}
    </Button>
  );
}
