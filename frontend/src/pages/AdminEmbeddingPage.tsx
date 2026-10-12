import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, Loader2, Play } from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { ReindexProgress } from "@/components/ReindexProgress";
import { api, errorMessage } from "@/lib/api";
import { useReindex } from "@/lib/useReindex";
import type {
  EmbeddingOverview,
  ModelEntry,
  ModelsResponse,
  IngestSettings,
  ModelSpec,
  ModelStatus,
} from "@/lib/types";

interface Connection {
  id: number;
  name: string;
  enabled: boolean;
}

// Von fastembed unterstützte Modelle (Auswahl)
const FASTEMBED_MODELS: Record<"embedding" | "reranker", string[]> = {
  embedding: ["sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"],
  reranker: ["BAAI/bge-reranker-base", "jinaai/jina-reranker-v2-base-multilingual"],
};

function StatusBadge({ status }: { status?: ModelStatus }) {
  if (!status) return null;
  if (status.state === "ready")
    return (
      <Badge variant="secondary">
        geladen{status.dimension ? ` · ${status.dimension} Dim.` : ""}
        {status.seconds ? ` · ${status.seconds}s` : ""}
      </Badge>
    );
  if (status.state === "loading")
    return (
      <Badge variant="secondary">
        <Loader2 className="mr-1 size-3 animate-spin" />
        lädt …
      </Badge>
    );
  if (status.state === "error")
    return (
      <Badge variant="destructive" title={status.error}>
        Fehler
      </Badge>
    );
  return <Badge variant="outline">noch nicht geladen</Badge>;
}

function ModelEditor({
  kind,
  title,
  hint,
  spec,
  status,
  suggestions,
  connections,
  onChange,
}: {
  kind: "embedding" | "reranker";
  title: string;
  hint: string;
  spec: ModelSpec;
  status?: ModelStatus;
  suggestions: string[];
  connections: Connection[];
  onChange: (s: ModelSpec) => void;
}) {
  const [testing, setTesting] = useState(false);
  const [remote, setRemote] = useState<string[]>([]);
  const listId = `models-${kind}`;

  useEffect(() => {
    if (spec.source !== "endpoint" || !spec.connection_id) {
      setRemote([]);
      return;
    }
    api
      .get<string[]>(`/api/admin/embedding/remote-models?connection_id=${spec.connection_id}`)
      .then(setRemote)
      .catch(() => setRemote([]));
  }, [spec.source, spec.connection_id]);

  const test = async () => {
    setTesting(true);
    try {
      const r = await api.post<{ dimension?: number; ranking_ok?: boolean; seconds: number }>(
        "/api/admin/embedding/test",
        { kind, spec },
      );
      toast.success(
        kind === "embedding"
          ? `Funktioniert: ${r.dimension} Dimensionen, ${r.seconds}s`
          : `Funktioniert (${r.seconds}s)${r.ranking_ok === false ? ", aber die Testrangfolge war falsch" : ""}`,
      );
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setTesting(false);
    }
  };

  return (
    <Card>
      <CardContent className="space-y-3 p-4">
        <div className="flex items-center justify-between gap-2">
          <div>
            <h2 className="font-semibold">{title}</h2>
            <p className="text-sm text-muted-foreground">{hint}</p>
          </div>
          <StatusBadge status={status} />
        </div>
        {status?.state === "error" ? (
          <p className="text-sm text-destructive">{status.error}</p>
        ) : null}
        <div className="grid gap-3 sm:grid-cols-3">
          <div className="space-y-1">
            <Label className="text-xs">Quelle</Label>
            <Select
              value={spec.source}
              onValueChange={(v) =>
                onChange({
                  source: v as ModelSpec["source"],
                  model: spec.model,
                  connection_id: v === "endpoint" ? connections[0]?.id : undefined,
                })
              }
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="hf">HuggingFace (lokal)</SelectItem>
                <SelectItem value="endpoint">Endpoint (Connection)</SelectItem>
                <SelectItem value="fastembed">fastembed (ONNX, lokal)</SelectItem>
              </SelectContent>
            </Select>
          </div>
          {spec.source === "endpoint" ? (
            <div className="space-y-1">
              <Label className="text-xs">Connection</Label>
              <Select
                value={spec.connection_id ? String(spec.connection_id) : ""}
                onValueChange={(v) => onChange({ ...spec, connection_id: Number(v) })}
              >
                <SelectTrigger>
                  <SelectValue placeholder="wählen" />
                </SelectTrigger>
                <SelectContent>
                  {connections.map((c) => (
                    <SelectItem key={c.id} value={String(c.id)}>
                      {c.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          ) : null}
          <div className="space-y-1 sm:col-span-full">
            <Label className="text-xs">Modell</Label>
            <Input
              list={listId}
              value={spec.model}
              onChange={(e) => onChange({ ...spec, model: e.target.value })}
              placeholder={spec.source === "hf" ? "z. B. BAAI/bge-m3" : spec.source === "fastembed" ? "Modellname laut fastembed" : "Modellname am Endpoint"}
            />
            <datalist id={listId}>
              {(spec.source === "endpoint"
                ? remote
                : spec.source === "fastembed"
                  ? FASTEMBED_MODELS[kind]
                  : suggestions
              ).map((m) => (
                <option key={m} value={m} />
              ))}
            </datalist>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => void test()} disabled={testing}>
            {testing ? <Loader2 className="size-4 animate-spin" /> : <Play className="size-4" />}
            Testen
          </Button>
          {spec.source === "hf" ? (
            <span className="text-xs text-muted-foreground">
              Wird beim ersten Mal heruntergeladen; große Modelle laufen auf der CPU langsam.
            </span>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}

export function AdminEmbeddingPage() {
  const [data, setData] = useState<EmbeddingOverview | null>(null);
  const [connections, setConnections] = useState<Connection[]>([]);
  const [embedding, setEmbedding] = useState<ModelSpec | null>(null);
  const [reranker, setReranker] = useState<ModelSpec | null>(null);
  const [ingest, setIngest] = useState<IngestSettings | null>(null);
  const [saving, setSaving] = useState(false);
  const [chatModels, setChatModels] = useState<ModelEntry[]>([]);
  const [visionModel, setVisionModel] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const d = await api.get<EmbeddingOverview>("/api/admin/embedding");
      setData(d);
      const { status: _e, ...e } = d.embedding;
      const { status: _r, ...r } = d.reranker;
      setEmbedding((prev) => prev ?? e);
      setReranker((prev) => prev ?? r);
      setIngest((prev) => prev ?? d.ingest);
      setVisionModel((prev) => prev ?? d.vision_model ?? "");
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }, []);

  const { status: reindex, refresh } = useReindex(() => void load());

  useEffect(() => {
    void load();
    api.get<Connection[]>("/api/connections").then(setConnections).catch(() => {});
    api
      .get<ModelsResponse>("/api/models")
      .then((r) => setChatModels(r.models.filter((m) => m.available)))
      .catch(() => {});
  }, [load]);

  // Ladestatus der Modelle aktualisieren, solange eines noch lädt
  useEffect(() => {
    const loading = [data?.embedding.status, data?.reranker.status].some(
      (s) => s?.state === "loading",
    );
    if (!loading) return;
    const t = setInterval(async () => {
      try {
        setData(await api.get<EmbeddingOverview>("/api/admin/embedding"));
      } catch {
        /* nur Anzeige */
      }
    }, 2000);
    return () => clearInterval(t);
  }, [data]);

  const save = async () => {
    if (!embedding || !reranker || !ingest) return;
    setSaving(true);
    try {
      setData(await api.put<EmbeddingOverview>("/api/admin/embedding", { embedding, reranker, ingest, vision_model: visionModel ?? "" }));
      toast.success("Gespeichert. Neue Modelle werden im Hintergrund geladen.");
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setSaving(false);
    }
  };

  const reindexAll = async () => {
    try {
      await api.post("/api/reindex-all");
      await refresh();
    } catch (e) {
      toast.error(errorMessage(e));
    }
  };

  if (!data || !embedding || !reranker || !ingest) {
    return <div className="p-6 text-sm text-muted-foreground">Lädt …</div>;
  }

  const setNum = (key: "chunk_size" | "chunk_overlap", v: string) =>
    setIngest({ ...ingest, [key]: Number(v) });

  return (
    <div className="h-full overflow-y-auto">
    <div className="mx-auto max-w-3xl space-y-4 p-4 sm:p-6">
      <div>
        <h1 className="text-xl font-semibold">Einlesen & Modelle</h1>
        <p className="text-sm text-muted-foreground">
          Ein Embedding-Modell gilt für alle Knowledge-Bereiche. Die Vektor-Dimension
          wird automatisch aus dem Modell bestimmt.
          {data.device ? ` Rechengerät: ${data.device === "mps" ? "Apple Silicon (MPS)" : data.device === "cuda" ? "NVIDIA-GPU (CUDA)" : "CPU"}.` : ""}
        </p>
      </div>

      {data.stale.length > 0 ? (
        <div className="space-y-2 rounded-lg border border-amber-500/50 bg-amber-500/10 p-3 text-sm">
          <div className="flex items-center gap-2 font-medium">
            <AlertTriangle className="size-4" />
            {data.stale.length} Knowledge-Bereich(e) müssen neu indexiert werden
          </div>
          <p className="text-muted-foreground">
            {data.stale.map((k) => k.name).join(", ")}. Bis dahin werden sie weiter mit ihrem
            bisherigen Modell durchsucht, die Suche funktioniert also.
          </p>
          {data.stale.some((k) => k.error) ? (
            <p className="text-destructive">
              Letzter Fehler: {data.stale.find((k) => k.error)?.error}
            </p>
          ) : null}
          <Button size="sm" onClick={() => void reindexAll()} disabled={reindex.running}>
            Alle neu indexieren
          </Button>
        </div>
      ) : null}
      <ReindexProgress status={reindex} />

      <ModelEditor
        kind="embedding"
        title="Embedding"
        hint="Macht aus Text Vektoren für die Suche. Ein Wechsel erfordert Neu-Indexieren."
        spec={embedding}
        status={data.embedding.status}
        suggestions={data.suggestions.embedding}
        connections={connections.filter((c) => c.enabled)}
        onChange={setEmbedding}
      />
      <ModelEditor
        kind="reranker"
        title="Reranking"
        hint="Sortiert die Treffer neu. Ein Wechsel wirkt sofort, ohne Neu-Indexieren."
        spec={reranker}
        status={data.reranker.status}
        suggestions={data.suggestions.reranker}
        connections={connections.filter((c) => c.enabled)}
        onChange={setReranker}
      />

      <Card>
        <CardContent className="space-y-3 p-4">
          <h2 className="font-semibold">Bildbeschreibung und Kontext</h2>
          <p className="text-sm text-muted-foreground">
            Dieses Modell beschreibt Bilder in Dokumenten und ergänzt, wenn aktiv, den Kontext
            je Abschnitt. Es kommt aus den Verbindungen, auch Modelle, die im Chat ausgeblendet
            sind. Ohne Auswahl gilt das Standardmodell.
          </p>
          <div className="flex items-start justify-between rounded-lg border border-border-base px-3 py-2">
            <div>
              <Label className="text-sm">Bilder beschreiben</Label>
              <p className="text-xs text-muted-foreground">
                Aus: Bilder in Dokumenten werden übersprungen (schneller, aber ohne Bildinhalt).
              </p>
            </div>
            <Switch
              checked={ingest.vision_enabled}
              onCheckedChange={(v) => setIngest({ ...ingest, vision_enabled: v })}
            />
          </div>
          <Select
            value={visionModel || "__default__"}
            onValueChange={(v) => setVisionModel(v === "__default__" ? "" : v)}
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__default__">Standardmodell</SelectItem>
              {chatModels.map((m) => (
                <SelectItem key={m.ref} value={m.ref}>
                  {m.name} · {m.connection_name}
                  {m.visible ? "" : " (im Chat ausgeblendet)"}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="space-y-3 p-4">
          <h2 className="font-semibold">Zerlegen</h2>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1">
              <Label className="text-xs">Chunk-Größe (Zeichen)</Label>
              <Input
                type="number"
                value={ingest.chunk_size}
                onChange={(e) => setNum("chunk_size", e.target.value)}
              />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Überlappung</Label>
              <Input
                type="number"
                value={ingest.chunk_overlap}
                onChange={(e) => setNum("chunk_overlap", e.target.value)}
              />
            </div>
          </div>
          {(
            [
              ["context_enrichment", "Kontext je Chunk per LLM ergänzen", "bessere Treffer, deutlich langsameres Einlesen"],
              ["keep_original", "Originaldatei behalten", "aus: nur das Markdown bleibt, Neu-Indexieren nutzt dieses"],
              ["index_enabled", "Inhaltsverzeichnis (index.md) pro Knowledge", "das Modell liest es zuerst; spart Suchschritte"],
            ] as const
          ).map(([key, label, hint]) => (
            <div
              key={key}
              className="flex items-center justify-between rounded-lg border border-border-base px-3 py-2"
            >
              <div>
                <Label className="text-sm">{label}</Label>
                <p className="text-xs text-muted-foreground">{hint}</p>
              </div>
              <Switch
                checked={ingest[key]}
                onCheckedChange={(v) => setIngest({ ...ingest, [key]: v })}
              />
            </div>
          ))}
          <p className="text-xs text-muted-foreground">
            Änderungen an Größe, Überlappung und Anreicherung gelten für neue Dokumente; bestehende
            werden beim Neu-Indexieren angepasst.
          </p>
        </CardContent>
      </Card>

      <div className="flex justify-end">
        <Button onClick={() => void save()} disabled={saving}>
          {saving ? <Loader2 className="size-4 animate-spin" /> : null}
          Speichern
        </Button>
      </div>
    </div>
    </div>
  );
}
