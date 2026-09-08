import { useEffect, useRef, useState } from 'react';
import type { LabClient } from '@lab/api/client';
import type { Stats } from '@lab/stats/types';
import { toQuery, type WorkingSet } from '@lab/stats/workingSet';

/** How often to re-read while a census is running. Long enough that a census
 *  job is not competing with the page for the database, short enough that a
 *  climbing coverage bar looks live. */
export const POLL_MS = 5000;

/** How often to re-read when no run is open. The database is not static
 *  between runs -- a slot is ingested, a store is re-baked, rows are dropped --
 *  and the page used to stop reading entirely, so the only way to see any of
 *  that was a reload, which redraws every chart. Slow enough to cost nothing
 *  against an idle database. */
export const IDLE_POLL_MS = 30000;

export interface StatsView {
  stats: Stats | null;
  error: string | null;
  /** A read is in flight over numbers already on screen. */
  busy: boolean;
  /** Whether a run is open, and so whether the page is re-reading by itself. */
  polling: boolean;
  reload: () => void;
}

/** The tallies for a working set, re-read while any run is unfinished.
 *
 *  Polling stops the moment nothing is open: the database is otherwise
 *  static, and a timer against it answers the same question forever. */
export function useStats(client: LabClient, set: WorkingSet,
                         intervalMs = POLL_MS,
                         idleMs = IDLE_POLL_MS): StatsView {
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [nonce, setNonce] = useState(0);
  const polling = stats?.runs.some((r) => r.open) ?? false;
  // Read by the timer, which outlives the render that armed it.
  const live = useRef(true);
  // Through a ref, not the dependency list: a caller building its client
  // inside the render passes a fresh object every time, and an effect keyed
  // on that identity tears down and re-reads on its own `setBusy`.
  const api = useRef(client);
  api.current = client;

  const query = toQuery(set).toString();

  useEffect(() => {
    live.current = true;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const read = async () => {
      setBusy(true);
      try {
        const next = await api.current.corpusStats(new URLSearchParams(query));
        if (!live.current) return;
        setStats(next);
        setError(null);
        timer = setTimeout(read, next.runs.some((r) => r.open) ? intervalMs : idleMs);
      } catch (e) {
        if (!live.current) return;
        setError(e instanceof Error ? e.message : String(e));
        // Keep the page reading through a locked database rather than
        // stranding it on the numbers it happened to have when the lock hit.
        timer = setTimeout(read, idleMs);
      } finally {
        if (live.current) setBusy(false);
      }
    };
    void read();

    return () => {
      live.current = false;
      if (timer) clearTimeout(timer);
    };
  }, [query, intervalMs, idleMs, nonce]);

  return { stats, error, busy, polling, reload: () => setNonce((n) => n + 1) };
}
