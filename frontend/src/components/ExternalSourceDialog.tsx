import { useEffect, useState } from "react";
import { Loader2, Play } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { api, errorMessage } from "@/lib/api";
import { Switch } from "@/components/ui/switch";
import type { ExternalAccess, ExternalSource, Knowledge, ModelSpec } from "@/lib/types";

interface Facts {
  collections: string[];
  points?: number;
  dense_vectors?: Record<string, number>;
  sparse_vectors?: string[];
  sample_payload?: Record<string, unknown> | null;
}

interface Connection {
  id: number;
  name: string;
  enabled: boolean;
}

const FIELD_LABELS: [keyof ExternalSource["fields"], string][] = [
  ["text", "Textfeld"],
  ["filename", "Dateiname"],
  ["title", "Titel"],
  ["page_start", "Seite (von)"],
  ["page_end", "Seite (bis)"],
  ["chunk_index", "Abschnittsnummer"],
  ["group", "Dokument-ID (für Nachbarn)"],
  ["headers", "Überschriften"],
];

const EMPTY_FIELDS: ExternalSource["fields"] = {
  text: "page_content",
  filename: "filename",
  title: "title",
  headers: "headers",
  page_start: "page_start",
  page_end: "page_end",
  chunk_index: "chunk_index",
  group: "file_group_id",
};

// "mandant=A|B" je Zeile -> feste Bedingung (Feld, Werte)
function parseStatic(text: string): { field: string; values: string[] }[] {
  return text
    .split("\n")
    .map((line) => {
      const [field, rest = ""] = line.split("=");
      return { field: field.trim(), values: rest.split("|").map((v) => v.trim()).filter(Boolean) };
    })
    .filter((c) => c.field);
}

const EMPTY_ACCESS: ExternalAccess = {
  enabled: false,
  user_field: "",
  user_attr: "username",
  group_field: "",
  groups_from: "local",
  static: [],
  admins_unfiltered: false,
};

// Externe Quelle (fremder Qdrant, nur lesen) anlegen oder ändern. Nichts wird geraten: Modell,
// Collection, Vektor- und Feldnamen trägt der Admin ein; "Verbindung testen" zeigt nur Fakten.
export function ExternalSourceDialog({
  open,
  onOpenChange,
  existing,
  onSaved,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  existing?: Knowledge | null;
  onSaved: () => void;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [url, setUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [collection, setCollection] = useState("");
  const [dense, setDense] = useState("");
  const [sparse, setSparse] = useState("");
  const [fields, setFields] = useState(EMPTY_FIELDS);
  const [access, setAccess] = useState<ExternalAccess>(EMPTY_ACCESS);
  const [staticText, setStaticText] = useState("");
  const [probe, setProbe] = useState({ username: "", groups: "", external: "" });
  const [probeResult, setProbeResult] = useState<{ blocked: boolean; count: number; samples: string[] } | null>(null);
  const [embedding, setEmbedding] = useState<ModelSpec>({ source: "hf", model: "" });
  const [connections, setConnections] = useState<Connection[]>([]);
  const [facts, setFacts] = useState<Facts | null>(null);
  const [testing, setTesting] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    setFacts(null);
    setApiKey("");
    const src = existing?.source_config;
    setName(existing?.name ?? "");
    setDescription(existing?.description ?? "");
    setUrl(src?.url ?? "");
    setCollection(src?.collection ?? "");
    setDense(src?.dense_vector ?? "");
    setSparse(src?.sparse_vector ?? "");
    setFields({ ...EMPTY_FIELDS, ...(src?.fields ?? {}) });
    setAccess({ ...EMPTY_ACCESS, ...(src?.access ?? {}) });
    setStaticText(
      (src?.access?.static ?? []).map((c) => `${c.field}=${c.values.join("|")}`).join("\n"),
    );
    setProbeResult(null);
    api.get<Connection[]>("/api/connections").then(setConnections).catch(() => {});
    if (existing) {
      // Das Modell der Quelle steht am Knowledge (embedding_spec als JSON)
      try {
        const spec = JSON.parse((existing as unknown as { embedding_spec?: string }).embedding_spec ?? "{}");
        setEmbedding(spec.model ? spec : { source: "hf", model: "" });
      } catch {
        setEmbedding({ source: "hf", model: "" });
      }
    } else {
      setEmbedding({ source: "hf", model: "" });
    }
  }, [open, existing]);

  const source = () => ({
    kind: "qdrant",
    url: url.trim(),
    api_key: apiKey,
    collection: collection.trim(),
    dense_vector: dense.trim(),
    sparse_vector: sparse.trim(),
    fields,
    access: { ...access, static: parseStatic(staticText) },
  });

  const filterTest = async () => {
    try {
      const split = (t: string) => t.split(",").map((x) => x.trim()).filter(Boolean);
      setProbeResult(
        await api.post("/api/knowledge/external/filter-test", {
          knowledge_id: existing?.id,
          source: source(),
          identity: {
            username: probe.username.trim(),
            display_name: probe.username.trim(),
            groups: split(probe.groups),
            external_groups: split(probe.external),
          },
        }),
      );
    } catch (e) {
      setProbeResult(null);
      toast.error(errorMessage(e));
    }
  };

  const test = async () => {
    setTesting(true);
    setFacts(null);
    try {
      setFacts(
        await api.post<Facts>("/api/knowledge/external/test", {
          knowledge_id: existing?.id,
          source: source(),
        }),
      );
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setTesting(false);
    }
  };

  const save = async () => {
    setBusy(true);
    try {
      const body = { name: name.trim(), description: description.trim(), source: source(), embedding };
      if (existing) await api.patch(`/api/knowledge/${existing.id}`, body);
      else await api.post("/api/knowledge", { ...body, kind: "external" });
      toast.success(existing ? "Quelle gespeichert" : "Externe Quelle angelegt");
      onSaved();
      onOpenChange(false);
    } catch (e) {
      toast.error(errorMessage(e), { duration: 12000 });
    } finally {
      setBusy(false);
    }
  };

  const valid = name.trim() && url.trim() && collection.trim() && embedding.model.trim() &&
    (embedding.source !== "endpoint" || embedding.connection_id);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[92vh] overflow-y-auto sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>{existing ? "Externe Quelle bearbeiten" : "Externe Quelle anbinden"}</DialogTitle>
          <DialogDescription>
            Ein fremder Qdrant wird nur gelesen, nie verändert. Das Embedding-Modell muss das sein,
            mit dem die Quelle aufgebaut wurde, sonst findet die Suche nichts Passendes.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1">
              <Label className="text-xs">Name</Label>
              <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="z. B. Handbuch-Archiv" />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Beschreibung</Label>
              <Textarea rows={1} value={description} onChange={(e) => setDescription(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Adresse des Qdrant</Label>
              <Input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="http://qdrant.firma.de:6333" />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">API-Key</Label>
              <Input
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder={existing?.source_config?.has_key ? "•••••••• (leer = behalten)" : "optional"}
              />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Collection</Label>
              <Input
                list="ext-collections"
                value={collection}
                onChange={(e) => setCollection(e.target.value)}
              />
              <datalist id="ext-collections">
                {(facts?.collections ?? []).map((c) => (
                  <option key={c} value={c} />
                ))}
              </datalist>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label className="text-xs">Dense-Vektor (leer = unbenannt)</Label>
                <Input value={dense} onChange={(e) => setDense(e.target.value)} />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Sparse-Vektor (leer = keiner)</Label>
                <Input value={sparse} onChange={(e) => setSparse(e.target.value)} />
              </div>
            </div>
          </div>

          <div className="space-y-2 rounded-lg border border-border-base p-3">
            <p className="text-sm font-medium">Embedding-Modell der Quelle (Pflicht)</p>
            <div className="grid gap-3 sm:grid-cols-3">
              <Select
                value={embedding.source}
                onValueChange={(v) =>
                  setEmbedding({
                    source: v as ModelSpec["source"],
                    model: embedding.model,
                    connection_id: v === "endpoint" ? connections.find((c) => c.enabled)?.id : undefined,
                  })
                }
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="hf">HuggingFace (lokal)</SelectItem>
                  <SelectItem value="endpoint">Endpoint (Verbindung)</SelectItem>
                  <SelectItem value="fastembed">fastembed (ONNX)</SelectItem>
                </SelectContent>
              </Select>
              {embedding.source === "endpoint" ? (
                <Select
                  value={embedding.connection_id ? String(embedding.connection_id) : ""}
                  onValueChange={(v) => setEmbedding({ ...embedding, connection_id: Number(v) })}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Verbindung" />
                  </SelectTrigger>
                  <SelectContent>
                    {connections.filter((c) => c.enabled).map((c) => (
                      <SelectItem key={c.id} value={String(c.id)}>
                        {c.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              ) : null}
              <Input
                className={embedding.source === "endpoint" ? "" : "sm:col-span-2"}
                value={embedding.model}
                onChange={(e) => setEmbedding({ ...embedding, model: e.target.value })}
                placeholder="z. B. BAAI/bge-m3"
              />
            </div>
          </div>

          <details className="rounded-lg border border-border-base p-3">
            <summary className="cursor-pointer text-sm font-medium">Feldnamen im Payload der Quelle</summary>
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              {FIELD_LABELS.map(([key, label]) => (
                <div key={key} className="space-y-1">
                  <Label className="text-xs">{label}</Label>
                  <Input value={fields[key]} onChange={(e) => setFields({ ...fields, [key]: e.target.value })} />
                </div>
              ))}
            </div>
          </details>

          <details className="rounded-lg border border-border-base p-3" open={access.enabled}>
            <summary className="cursor-pointer text-sm font-medium">
              Zugriffsfilter (Benutzer und Gruppen){access.enabled ? " · aktiv" : ""}
            </summary>
            <div className="mt-3 space-y-3">
              <div className="flex items-start justify-between rounded-lg border border-border-base px-3 py-2">
                <div>
                  <Label className="text-sm">Treffer nach Benutzer und Gruppen filtern</Label>
                  <p className="text-xs text-muted-foreground">
                    Der Filter läuft in der Abfrage an der Quelle. Ohne passende Identität liefert die Quelle
                    nichts (nie ungefiltert).
                  </p>
                </div>
                <Switch checked={access.enabled} onCheckedChange={(v) => setAccess({ ...access, enabled: v })} />
              </div>
              {access.enabled ? (
                <>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <div className="space-y-1">
                      <Label className="text-xs">Feld mit dem Benutzer (optional)</Label>
                      <Input value={access.user_field} placeholder="z. B. owner" onChange={(e) => setAccess({ ...access, user_field: e.target.value })} />
                    </div>
                    <div className="space-y-1">
                      <Label className="text-xs">Benutzer als</Label>
                      <Select value={access.user_attr} onValueChange={(v) => setAccess({ ...access, user_attr: v as ExternalAccess["user_attr"] })}>
                        <SelectTrigger><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="username">Benutzername</SelectItem>
                          <SelectItem value="display_name">Anzeigename</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-1">
                      <Label className="text-xs">Feld mit den Gruppen (optional)</Label>
                      <Input value={access.group_field} placeholder="z. B. allowed_groups" onChange={(e) => setAccess({ ...access, group_field: e.target.value })} />
                    </div>
                    <div className="space-y-1">
                      <Label className="text-xs">Gruppen aus</Label>
                      <Select value={access.groups_from} onValueChange={(v) => setAccess({ ...access, groups_from: v as ExternalAccess["groups_from"] })}>
                        <SelectTrigger><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="local">lokalen Gruppen</SelectItem>
                          <SelectItem value="external">Gruppen aus LDAP/OIDC</SelectItem>
                          <SelectItem value="both">beiden</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs">Feste Bedingungen für alle (eine pro Zeile: feld=Wert1|Wert2)</Label>
                    <Textarea rows={2} value={staticText} onChange={(e) => setStaticText(e.target.value)} placeholder="mandant=A" className="font-mono text-xs" />
                  </div>
                  <div className="flex items-center justify-between rounded-lg border border-border-base px-3 py-2">
                    <Label className="text-sm">Admins ohne Filter</Label>
                    <Switch checked={access.admins_unfiltered} onCheckedChange={(v) => setAccess({ ...access, admins_unfiltered: v })} />
                  </div>
                  <div className="space-y-2 rounded-lg bg-surface-muted p-3">
                    <p className="text-xs font-medium">Filter testen (ohne zu speichern)</p>
                    <div className="grid gap-2 sm:grid-cols-3">
                      <Input value={probe.username} onChange={(e) => setProbe({ ...probe, username: e.target.value })} placeholder="Benutzername" />
                      <Input value={probe.groups} onChange={(e) => setProbe({ ...probe, groups: e.target.value })} placeholder="lokale Gruppen, mit Komma" />
                      <Input value={probe.external} onChange={(e) => setProbe({ ...probe, external: e.target.value })} placeholder="externe Gruppen, mit Komma" />
                    </div>
                    <Button variant="outline" size="sm" onClick={() => void filterTest()} disabled={!url.trim() || !collection.trim()}>
                      Filter testen
                    </Button>
                    {probeResult ? (
                      <p className="text-xs">
                        {probeResult.blocked
                          ? "Gesperrt: Der Benutzer hat keine passende Identität, die Quelle liefert nichts."
                          : `${probeResult.count} Treffer sichtbar${probeResult.samples.length ? `, z. B.: ${probeResult.samples.join(" · ")}` : ""}`}
                      </p>
                    ) : null}
                  </div>
                </>
              ) : null}
            </div>
          </details>

          <div className="space-y-2">
            <Button variant="outline" size="sm" onClick={() => void test()} disabled={testing || !url.trim()}>
              {testing ? <Loader2 className="size-4 animate-spin" /> : <Play className="size-4" />}
              Verbindung testen
            </Button>
            {facts ? (
              <div className="space-y-1 rounded-lg bg-surface-muted p-3 text-xs">
                <p>Erreichbar. Collections: {facts.collections.join(", ") || "keine"}</p>
                {facts.points !== undefined ? (
                  <>
                    <p>
                      {facts.points} Punkte · Dense-Vektoren:{" "}
                      {Object.entries(facts.dense_vectors ?? {})
                        .map(([n, s]) => `${n || "(unbenannt)"} = ${s} Dim.`)
                        .join(", ")}
                      {facts.sparse_vectors?.length ? ` · Sparse: ${facts.sparse_vectors.join(", ")}` : " · kein Sparse"}
                    </p>
                    {facts.sample_payload ? (
                      <p>
                        Beispiel-Payload-Felder:{" "}
                        <code>{Object.keys(facts.sample_payload).join(", ")}</code>
                      </p>
                    ) : null}
                  </>
                ) : (
                  <p className="text-muted-foreground">Collection eintragen und erneut testen für Details.</p>
                )}
              </div>
            ) : null}
          </div>
        </div>

        <DialogFooter>
          <Button variant="secondary" onClick={() => onOpenChange(false)}>
            Abbrechen
          </Button>
          <Button onClick={() => void save()} disabled={!valid || busy}>
            {busy ? <Loader2 className="size-4 animate-spin" /> : null}
            {existing ? "Speichern" : "Anbinden"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
