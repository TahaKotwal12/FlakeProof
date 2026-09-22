"use client";

import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { errorCodeToMessage } from "@/lib/error-copy";

export function CancelDialog({
  runId,
  onCanceled,
}: {
  runId: string;
  onCanceled: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [canceling, setCanceling] = useState(false);

  async function confirmCancel() {
    setCanceling(true);
    try {
      const res = await fetch(`/api/runs/${runId}/cancel`, { method: "POST" });
      const body = await res.json();
      if (res.ok) {
        onCanceled();
        setOpen(false);
        toast.success("Run canceled");
        return;
      }
      toast.error("Couldn't cancel", {
        description: errorCodeToMessage(body.error?.code ?? "internal_error", body.error?.message),
        action: { label: "Retry", onClick: () => void confirmCancel() },
      });
    } catch {
      toast.error("Network error", {
        description: "Couldn't reach FlakeProof — check your connection.",
        action: { label: "Retry", onClick: () => void confirmCancel() },
      });
    } finally {
      setCanceling(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="destructive" size="sm" className="w-full">
          Cancel run
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Cancel this run?</DialogTitle>
          <DialogDescription>
            The worker will stop after its current wave finishes. This can&apos;t be undone.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)} disabled={canceling}>
            Keep running
          </Button>
          <Button variant="destructive" onClick={confirmCancel} disabled={canceling}>
            {canceling ? "Canceling…" : "Cancel run"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
