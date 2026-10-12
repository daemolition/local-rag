import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { FileText, Layers, NotebookText, Plug, Plus } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ExternalSourceDialog } from "@/components/ExternalSourceDialog";
import { KnowledgeDialog } from "@/components/KnowledgeDialog";
import { useAuth } from "@/context/AuthContext";
import { api, errorMessage } from "@/lib/api";
import type { Knowledge } from "@/lib/types";

export function KnowledgePage() {
  const navigate = useNavigate();
  const [items, setItems] = useState<Knowledge[]>([]);
  const [loading, setLoading] = useState(true);
  const [createOpen, setCreateOpen] = useState(false);
  const [externalOpen, setExternalOpen] = useState(false);
  const { hasRole } = useAuth();

  const load = useCallback(() => {
    api
      .get<Knowledge[]>("/api/knowledge")
      .then(setItems)
      .catch((e) => toast.error(errorMessage(e)))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const create = async (values: { name: string; description: string }) => {
    try {
      const created = await api.post<Knowledge>("/api/knowledge", values);
      navigate(`/knowledge/${created.id}`);
    } catch (e) {
      toast.error(errorMessage(e));
      throw e;
    }
  };

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-5xl space-y-6 p-6">
        <div className="flex flex-col items-start justify-between gap-4 border-b border-border-base pb-4 sm:flex-row sm:items-center">
          <div>
            <h1 className="text-2xl font-semibold">Knowledge</h1>
            <p className="text-sm text-muted-foreground">
              Wissensbereiche mit eigener Vektor-Collection. Im Chat wählst du,
              welche durchsucht werden.
            </p>
          </div>
          <div className="flex gap-2">
            {hasRole("admin") ? (
              <Button variant="secondary" onClick={() => setExternalOpen(true)}>
                <Plug className="size-4" />
                Externe Quelle
              </Button>
            ) : null}
            <Button onClick={() => setCreateOpen(true)}>
              <Plus className="size-4" />
              Neues Knowledge
            </Button>
          </div>
        </div>

        {loading ? (
          <p className="text-muted-foreground">Lade…</p>
        ) : (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
            {items.map((k) => (
              <Link key={k.id} to={`/knowledge/${k.id}`} className="block">
                <Card className="h-full p-4 transition-colors hover:bg-surface-subtle">
                  <CardContent className="flex h-full flex-col gap-3 p-0">
                    <div className="flex items-start gap-3">
                      <div className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-surface-muted">
                        <NotebookText className="size-5 text-muted-foreground" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <h2 className="truncate font-semibold">{k.name}</h2>
                        <span className="text-xs text-muted-foreground">
                          {k.is_default ? "Standard · " : ""}
                          {k.kind === "external" ? "extern · " : ""}
                          {k.is_public ? "öffentlich" : "privat"}
                          {k.can_write ? "" : " · nur lesen"}
                        </span>
                      </div>
                    </div>
                    <p className="line-clamp-3 flex-1 text-sm text-muted-foreground">
                      {k.description || "Keine Beschreibung"}
                    </p>
                    <div className="flex gap-4 text-xs text-muted-foreground">
                      <span className="flex items-center gap-1">
                        <FileText className="size-3.5" />
                        {k.kind === "external" ? "Fremder Vektorspeicher" : `${k.document_count} Dokumente`}
                      </span>
                      <span className="flex items-center gap-1">
                        <Layers className="size-3.5" />
                        {k.chunk_count ?? "–"} Chunks
                      </span>
                    </div>
                  </CardContent>
                </Card>
              </Link>
            ))}
          </div>
        )}
      </div>

      <ExternalSourceDialog
        open={externalOpen}
        onOpenChange={setExternalOpen}
        onSaved={load}
      />
      <KnowledgeDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        title="Neues Knowledge"
        confirmLabel="Anlegen"
        onSubmit={create}
      />
    </div>
  );
}
