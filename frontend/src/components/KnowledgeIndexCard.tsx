import { useCallback, useEffect, useState } from "react";
import { ListTree, Loader2, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { Markdown } from "@/components/Markdown";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { api, errorMessage } from "@/lib/api";

interface IndexInfo {
  available: boolean;
  enabled: boolean;
  markdown: string | null;
  updated_at: string | null;
}

// Das Inhaltsverzeichnis (index.md) des Knowledge: Dokumente mit Gliederung, Tabellen und Datendateien.
// Genau das bekommt das Modell zur Orientierung (kleine Verzeichnisse mit der Frage, große per Werkzeug).
export function KnowledgeIndexCard({
  knowledgeId,
  canWrite,
  refreshKey,
}: {
  knowledgeId: number;
  canWrite: boolean;
  // ändert sich nach Upload/Löschen und lädt das Verzeichnis neu
  refreshKey?: unknown;
}) {
  const [info, setInfo] = useState<IndexInfo | null>(null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setInfo(await api.get<IndexInfo>(`/api/knowledge/${knowledgeId}/index`));
    } catch (e) {
      toast.error(errorMessage(e));
    }
  }, [knowledgeId]);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  if (!info || !info.available) return null;

  const regenerate = async () => {
    setBusy(true);
    try {
      setInfo(await api.post<IndexInfo>(`/api/knowledge/${knowledgeId}/index/refresh`));
      toast.success("Inhaltsverzeichnis neu erzeugt");
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card>
      <CardContent className="p-0">
        <Collapsible open={open} onOpenChange={setOpen}>
          <div className="flex items-center gap-2 px-4 py-3">
            <CollapsibleTrigger className="flex min-w-0 flex-1 items-center gap-2 text-left">
              <ListTree className="size-5 shrink-0" />
              <span className="text-lg font-semibold">Inhaltsverzeichnis</span>
              <span className="truncate text-xs text-muted-foreground">
                {!info.enabled
                  ? "abgeschaltet (Administration › Einlesen & Modelle)"
                  : info.updated_at
                    ? `index.md · Stand ${new Date(info.updated_at).toLocaleString("de-DE")}`
                    : "index.md"}
              </span>
            </CollapsibleTrigger>
            {canWrite && info.enabled ? (
              <Button size="sm" variant="secondary" onClick={regenerate} disabled={busy}>
                {busy ? <Loader2 className="size-4 animate-spin" /> : <RefreshCw className="size-4" />}
                Neu erzeugen
              </Button>
            ) : null}
          </div>
          <CollapsibleContent>
            <div className="space-y-2 border-t border-border-base px-4 py-3">
              <p className="text-xs text-muted-foreground">
                Das Modell liest dieses Verzeichnis zur Orientierung (welche Dokumente und Tabellen es gibt). Es wird nach jedem
                Einlesen, Löschen und Umbenennen automatisch neu erzeugt.
              </p>
              {info.markdown ? (
                <Markdown content={info.markdown} />
              ) : (
                <p className="text-sm text-muted-foreground">Kein Inhaltsverzeichnis vorhanden.</p>
              )}
            </div>
          </CollapsibleContent>
        </Collapsible>
      </CardContent>
    </Card>
  );
}
