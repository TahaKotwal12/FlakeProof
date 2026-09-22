"use client";

import { useEffect, useRef, useState } from "react";
import type { RealtimeChannel } from "@supabase/supabase-js";
import type { RunDetail } from "@/lib/run-detail";
import { createBrowserClient } from "@/lib/supabase";
import type { FlakyTest, Run, RunEvent, SandboxOp } from "@/lib/types";

export type ConnectionState = "live" | "connecting" | "polling";

const TERMINAL_STATUSES = new Set(["done", "failed", "canceled"]);
const POLL_INTERVAL_MS = 5000;
const CONNECT_GRACE_MS = 8000;

/**
 * Drives the run page's live state: the 4 realtime subscriptions from
 * docs/02-DATABASE.md ("Realtime subscriptions used by the UI") merged into
 * `initialData`, with a 5s polling fallback when the websocket drops
 * (docs/07-UI-SPEC.md: "Websocket drop → silent switch to 5s polling").
 * Finished runs (deep links) skip live wiring entirely.
 */
export function useRunLive(initialData: RunDetail, slug: string) {
  const [data, setData] = useState<RunDetail>(initialData);
  const [connection, setConnection] = useState<ConnectionState>(
    TERMINAL_STATUSES.has(initialData.run.status) ? "live" : "connecting"
  );
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Stop polling (realtime channel is left connected — harmless, cheap) once
  // the run reaches a terminal state, however it got there.
  useEffect(() => {
    if (TERMINAL_STATUSES.has(data.run.status) && pollTimerRef.current) {
      clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
      setConnection("live");
    }
  }, [data.run.status]);

  useEffect(() => {
    if (TERMINAL_STATUSES.has(initialData.run.status)) {
      return; // deep-linked finished run: composite GET already has everything
    }

    let client;
    try {
      client = createBrowserClient();
    } catch {
      setConnection("polling");
      return;
    }

    const runId = initialData.run.id;
    let stopped = false;
    let channel: RealtimeChannel | null = null;

    async function refetch() {
      try {
        const res = await fetch(`/api/runs/${slug}`, { cache: "no-store" });
        if (!res.ok) return;
        const fresh: RunDetail = await res.json();
        if (!stopped) setData(fresh);
      } catch {
        // keep last known state; the next poll or realtime event will catch up
      }
    }

    function startPolling() {
      if (stopped || pollTimerRef.current) return;
      setConnection("polling");
      pollTimerRef.current = setInterval(refetch, POLL_INTERVAL_MS);
    }

    const connectGrace = setTimeout(startPolling, CONNECT_GRACE_MS);

    channel = client
      .channel(`run-${runId}`)
      .on(
        "postgres_changes",
        { event: "UPDATE", schema: "public", table: "runs", filter: `id=eq.${runId}` },
        (payload) => {
          setData((prev) => ({ ...prev, run: payload.new as Run }));
        }
      )
      .on(
        "postgres_changes",
        { event: "INSERT", schema: "public", table: "run_events", filter: `run_id=eq.${runId}` },
        (payload) => {
          const row = payload.new as RunEvent;
          setData((prev) =>
            prev.events_tail.some((e) => e.id === row.id)
              ? prev
              : { ...prev, events_tail: [...prev.events_tail, row] }
          );
        }
      )
      .on(
        "postgres_changes",
        { event: "INSERT", schema: "public", table: "sandbox_ops", filter: `run_id=eq.${runId}` },
        (payload) => {
          const row = payload.new as SandboxOp;
          setData((prev) =>
            prev.sandbox_tree.some((s) => s.id === row.id)
              ? prev
              : { ...prev, sandbox_tree: [...prev.sandbox_tree, row] }
          );
        }
      )
      .on(
        "postgres_changes",
        { event: "INSERT", schema: "public", table: "flaky_tests", filter: `run_id=eq.${runId}` },
        (payload) => {
          const row = payload.new as FlakyTest;
          setData((prev) =>
            prev.flaky_tests.some((f) => f.test_id === row.test_id)
              ? prev
              : { ...prev, flaky_tests: [...prev.flaky_tests, row] }
          );
        }
      )
      .on(
        "postgres_changes",
        { event: "UPDATE", schema: "public", table: "flaky_tests", filter: `run_id=eq.${runId}` },
        (payload) => {
          const row = payload.new as FlakyTest;
          setData((prev) => ({
            ...prev,
            flaky_tests: prev.flaky_tests.some((f) => f.test_id === row.test_id)
              ? prev.flaky_tests.map((f) => (f.test_id === row.test_id ? row : f))
              : [...prev.flaky_tests, row],
          }));
        }
      )
      .subscribe((status) => {
        if (stopped) return;
        if (status === "SUBSCRIBED") {
          clearTimeout(connectGrace);
          if (pollTimerRef.current) {
            clearInterval(pollTimerRef.current);
            pollTimerRef.current = null;
          }
          setConnection("live");
          void refetch(); // catch up on anything missed while connecting
        } else if (status === "CHANNEL_ERROR" || status === "TIMED_OUT" || status === "CLOSED") {
          startPolling();
        }
      });

    return () => {
      stopped = true;
      clearTimeout(connectGrace);
      if (pollTimerRef.current) {
        clearInterval(pollTimerRef.current);
        pollTimerRef.current = null;
      }
      if (channel) client.removeChannel(channel);
    };
    // initialData is the server-rendered snapshot: only its identity at mount matters.
  }, [initialData.run.id, initialData.run.status, slug]);

  return { data, connection };
}
