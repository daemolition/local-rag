import { useCallback, useEffect, useState } from "react";
import { Copy, Pencil, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { ProfileDialog } from "@/components/ProfileDialog";
import { RetrievalTestPanel } from "@/components/RetrievalTestPanel";
import { api, errorMessage } from "@/lib/api";
import type {
  Knowledge,
  ModelEntry,
  ModelsResponse,
  ProfileConfig,
  RetrievalProfile,
} from "@/lib/types";

function summary(c: ProfileConfig): string[] {
  const parts = [
    c.search.mode === "hybrid"
      ? `Hybrid (${c.search.fusion.toUpperCase()})`
      : c.search.mode === "dense"
        ? "Semantisch"
        : "Stichwörter",
    `${c.final_k} Treffer`,
  ];
  if (c.query_enhancement.mode !== "off") parts.push(`${c.query_enhancement.n_queries} Suchfragen per LLM`);
  if (c.rerank.enabled) parts.push("Reranking");
  if (c.mmr.enabled) parts.push("MMR");
  if (Number(c.neighbors) > 0) parts.push(`±${c.neighbors} Nachbar-Chunks`);
  return parts;
}

export function AdminRetrievalPage() {
  const [profiles, setProfiles] = useState<RetrievalProfile[]>([]);
  const [knowledge, setKnowledge] = useState<Knowledge[]>([]);
  const [defaults, setDefaults] = useState<{ config: ProfileConfig; prompt: string } | null>(null);
  const [models, setModels] = useState<ModelEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [dialog, setDialog] = useState<{ open: boolean; profile: RetrievalProfile | null }>({
    open: false,
    profile: null,
  });
  const [deleteTarget, setDeleteTarget] = useState<RetrievalProfile | null>(null);

  const load = useCallback(async () => {
    try {
      const [p, k] = await Promise.all([
        api.get<RetrievalProfile[]>("/api/retrieval/profiles"),
        api.get<Knowledge[]>("/api/knowledge"),
      ]);
      setProfiles(p);
      setKnowledge(k);
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    api.get<{ config: ProfileConfig; prompt: string }>("/api/retrieval/defaults").then(setDefaults).catch(() => {});
    api
      .get<ModelsResponse>("/api/models")
      .then((r) => setModels(r.models.filter((m) => m.available)))
      .catch(() => {});
  }, [load]);

  const duplicate = async (p: RetrievalProfile) => {
    try {
      await api.post("/api/retrieval/profiles", {
        name: `${p.name} (Kopie)`,
        description: p.description,
        config: p.config,
      });
      await load();
    } catch (e) {
      toast.error(errorMessage(e));
    }
  };

  const remove = async () => {
    if (!deleteTarget) return;
    try {
      await api.del(`/api/retrieval/profiles/${deleteTarget.id}`);
      toast.success("Profil gelöscht");
      await load();
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setDeleteTarget(null);
    }
  };

  const usage = (p: RetrievalProfile) =>
    knowledge.filter((k) =>
      p.is_default ? k.retrieval_profile_id === null : k.retrieval_profile_id === p.id,
    );

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-5xl space-y-6 p-6">
        <div className="flex flex-col items-start justify-between gap-4 border-b border-border-base pb-4 sm:flex-row sm:items-center">
          <div>
            <h1 className="text-2xl font-semibold">Retrieval-Profile</h1>
            <p className="text-sm text-muted-foreground">
              Wie aus einem Knowledge die passenden Textstellen geholt werden. Ein Profil wird am
              Knowledge ausgewählt und lässt sich dort jederzeit wechseln.
            </p>
          </div>
          <Button onClick={() => setDialog({ open: true, profile: null })} disabled={!defaults}>
            <Plus className="size-4" />
            Neues Profil
          </Button>
        </div>

        {loading ? (
          <p className="text-muted-foreground">Lade…</p>
        ) : (
          <div className="space-y-3">
            {profiles.map((p) => {
              const used = usage(p);
              return (
                <Card key={p.id}>
                  <CardContent className="flex flex-wrap items-start gap-3 p-4">
                    <div className="min-w-0 flex-1 space-y-1.5">
                      <p className="flex items-center gap-2 font-semibold">
                        {p.name}
                        {p.is_default ? <Badge>Standard</Badge> : null}
                      </p>
                      {p.description ? (
                        <p className="text-sm text-muted-foreground">{p.description}</p>
                      ) : null}
                      <div className="flex flex-wrap gap-1">
                        {summary(p.config).map((s) => (
                          <Badge key={s} variant="secondary">
                            {s}
                          </Badge>
                        ))}
                      </div>
                      <p className="text-xs text-muted-foreground">
                        {used.length === 0
                          ? "Keinem Knowledge zugeordnet"
                          : `Verwendet von: ${used.map((k) => k.name).join(", ")}`}
                      </p>
                    </div>
                    <div className="flex items-center gap-1">
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        title="Bearbeiten"
                        onClick={() => setDialog({ open: true, profile: p })}
                        disabled={!defaults}
                      >
                        <Pencil className="size-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        title="Duplizieren"
                        onClick={() => void duplicate(p)}
                      >
                        <Copy className="size-4" />
                      </Button>
                      {!p.is_default ? (
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          title="Löschen"
                          onClick={() => setDeleteTarget(p)}
                        >
                          <Trash2 className="size-4" />
                        </Button>
                      ) : null}
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        )}

        {!loading && knowledge.length > 0 ? (
          <RetrievalTestPanel knowledge={knowledge} profiles={profiles} onApplied={() => void load()} />
        ) : null}
      </div>

      <ProfileDialog
        open={dialog.open}
        onOpenChange={(o) => setDialog((d) => ({ ...d, open: o }))}
        profile={dialog.profile}
        defaults={defaults}
        models={models}
        onSaved={() => void load()}
      />
      <ConfirmDialog
        open={deleteTarget !== null}
        onOpenChange={(o) => !o && setDeleteTarget(null)}
        title="Profil löschen?"
        description={
          deleteTarget
            ? `„${deleteTarget.name}“ wird gelöscht. Knowledge mit diesem Profil nutzt danach das Standardprofil.`
            : undefined
        }
        confirmLabel="Löschen"
        destructive
        onConfirm={remove}
      />
    </div>
  );
}
