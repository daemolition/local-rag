import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import type { ReindexStatus } from "@/lib/types";

const IDLE: ReindexStatus = { running: false, queue: [], current: null, results: [] };

/** Status des Neu-Indexierens; pollt nur, solange ein Lauf aktiv ist. */
export function useReindex(onFinished?: () => void) {
  const [status, setStatus] = useState<ReindexStatus>(IDLE);
  const wasRunning = useRef(false);
  const finished = useRef(onFinished);
  finished.current = onFinished;

  const refresh = useCallback(async () => {
    try {
      const next = await api.get<ReindexStatus>("/api/reindex/status");
      setStatus(next);
      if (wasRunning.current && !next.running) finished.current?.();
      wasRunning.current = next.running;
    } catch {
      /* Status ist nur Anzeige */
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (!status.running) return;
    const timer = setInterval(() => void refresh(), 2000);
    return () => clearInterval(timer);
  }, [status.running, refresh]);

  return { status, refresh };
}
