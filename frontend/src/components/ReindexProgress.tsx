import { Loader2 } from "lucide-react";
import type { ReindexStatus } from "@/lib/types";

/** Fortschritt des laufenden Neu-Indexierens (Dokument x von y). */
export function ReindexProgress({ status }: { status: ReindexStatus }) {
  if (!status.running) return null;
  const cur = status.current;
  const pct = cur && cur.total > 0 ? Math.round((cur.done / cur.total) * 100) : 0;
  return (
    <div className="space-y-1.5 rounded-lg border border-border-base bg-surface px-3 py-2 text-sm">
      <div className="flex items-center gap-2">
        <Loader2 className="size-4 animate-spin" />
        {cur
          ? `„${cur.name}“ wird neu indexiert: Dokument ${cur.done} von ${cur.total}`
          : "Neu indexieren startet …"}
        {status.queue.length > 1 ? (
          <span className="text-muted-foreground">
            · danach noch {status.queue.length - 1} weitere
          </span>
        ) : null}
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-border-base">
        <div className="h-full bg-primary transition-all" style={{ width: `${pct}%` }} />
      </div>
      <p className="text-xs text-muted-foreground">
        Die Suche läuft währenddessen unverändert weiter. Einlesen, Löschen und Umbenennen
        sind für dieses Knowledge kurz gesperrt.
      </p>
    </div>
  );
}
