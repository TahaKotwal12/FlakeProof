/**
 * Minimal fake Supabase client for route-handler unit tests.
 *
 * Each `.from(table)` call consumes the next canned response off `queue`,
 * in the exact order the handler under test issues its queries. Every
 * chain method (`.select`, `.eq`, `.in`, `.order`, ...) just returns the
 * same builder; the builder is a thenable so `await query` works for
 * count-only queries, and `.maybeSingle()` / `.single()` resolve directly.
 */

export interface MockSupaResult<T = unknown> {
  data: T;
  error: { message: string } | null;
  count?: number | null;
}

const CHAIN_METHODS = [
  "select",
  "eq",
  "neq",
  "gt",
  "gte",
  "lt",
  "lte",
  "in",
  "order",
  "limit",
  "range",
  "filter",
  "or",
  "not",
  "update",
  "insert",
  "delete",
] as const;

export function createQueueSupabaseMock(queue: MockSupaResult[]) {
  let cursor = 0;

  const next = (): MockSupaResult => {
    if (cursor >= queue.length) {
      throw new Error(`mock-supabase: no response queued for call #${cursor + 1}`);
    }
    return queue[cursor++];
  };

  function makeBuilder(): Record<string, unknown> {
    const builder: Record<string, unknown> = {};
    for (const method of CHAIN_METHODS) {
      builder[method] = () => builder;
    }
    builder.maybeSingle = async () => next();
    builder.single = async () => next();
    builder.then = (resolve: (value: MockSupaResult) => unknown, reject?: (reason: unknown) => unknown) =>
      Promise.resolve().then(() => next()).then(resolve, reject);
    return builder;
  }

  return {
    // eslint-disable-next-line @typescript-eslint/no-unused-vars -- table name isn't needed; calls are consumed in issue order
    from: (_table: string) => makeBuilder(),
    callsMade: () => cursor,
  };
}
