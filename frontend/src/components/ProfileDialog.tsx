import { useEffect, useState } from "react";
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
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { api, errorMessage } from "@/lib/api";
import type {
  ModelEntry,
  ProfileConfig,
  RetrievalProfile,
} from "@/lib/types";

const CHAT_MODEL = "__chat__";

interface Defaults {
  config: ProfileConfig;
  prompt: string;
}

interface ProfileDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  // Ohne Wert: neues Profil mit den Standardwerten.
  profile: RetrievalProfile | null;
  defaults: Defaults | null;
  models: ModelEntry[];
  onSaved: () => void;
}

function Num({
  id,
  label,
  hint,
  value,
  onChange,
  step,
}: {
  id: string;
  label: string;
  hint?: string;
  value: number | "" | null;
  onChange: (v: number | "") => void;
  step?: string;
}) {
  return (
    <div className="space-y-1">
      <Label htmlFor={id} className="text-xs">
        {label}
      </Label>
      <Input
        id={id}
        type="number"
        step={step ?? "1"}
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value === "" ? "" : Number(e.target.value))}
        placeholder={hint}
      />
    </div>
  );
}

function Section({
  title,
  hint,
  children,
}: {
  title: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="space-y-3 rounded-xl border border-border-base p-4">
      <div>
        <h3 className="text-sm font-semibold">{title}</h3>
        {hint ? <p className="text-xs text-muted-foreground">{hint}</p> : null}
      </div>
      {children}
    </section>
  );
}

export function ProfileDialog({
  open,
  onOpenChange,
  profile,
  defaults,
  models,
  onSaved,
}: ProfileDialogProps) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [cfg, setCfg] = useState<ProfileConfig | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open || !defaults) return;
    setName(profile?.name ?? "");
    setDescription(profile?.description ?? "");
    setCfg(structuredClone(profile?.config ?? defaults.config));
  }, [open, profile, defaults]);

  if (!cfg || !defaults) {
    return null;
  }

  const patch = <K extends keyof ProfileConfig>(key: K, value: Partial<ProfileConfig[K]>) =>
    setCfg((c) =>
      c ? { ...c, [key]: { ...(c[key] as object), ...(value as object) } } : c,
    );

  const save = async () => {
    // Leere optionale Zahlenfelder bedeuten "aus".
    const body: ProfileConfig = structuredClone(cfg);
    if (body.search.dense_min_score === "") body.search.dense_min_score = null;
    if (body.rerank.min_score === "") body.rerank.min_score = null;
    setBusy(true);
    try {
      if (profile) {
        await api.patch(`/api/retrieval/profiles/${profile.id}`, {
          name,
          description,
          config: body,
        });
      } else {
        await api.post("/api/retrieval/profiles", { name, description, config: body });
      }
      toast.success("Profil gespeichert");
      onSaved();
      onOpenChange(false);
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const qe = cfg.query_enhancement;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[92vh] overflow-y-auto sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>{profile ? "Profil bearbeiten" : "Neues Profil"}</DialogTitle>
          <DialogDescription>
            Steuert, wie aus einem Knowledge die passenden Textstellen geholt werden.
            Änderungen wirken sofort, ein erneutes Einlesen ist nicht nötig.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1">
              <Label htmlFor="p-name">Name</Label>
              <Input id="p-name" value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="p-desc">Beschreibung</Label>
              <Input
                id="p-desc"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
            </div>
          </div>

          <Section
            title="Suche"
            hint="Hybrid kombiniert semantische (Dense) und Stichwort-Suche (BM25). Die Gewichte steuern, welche mehr zählt."
          >
            <div className="grid gap-3 sm:grid-cols-3">
              <div className="space-y-1">
                <Label className="text-xs">Modus</Label>
                <Select
                  value={cfg.search.mode}
                  onValueChange={(v) => patch("search", { mode: v as ProfileConfig["search"]["mode"] })}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="hybrid">Hybrid</SelectItem>
                    <SelectItem value="dense">Nur semantisch</SelectItem>
                    <SelectItem value="sparse">Nur Stichwörter</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Fusion (nur Hybrid)</Label>
                <Select
                  value={cfg.search.fusion}
                  onValueChange={(v) => patch("search", { fusion: v as ProfileConfig["search"]["fusion"] })}
                  disabled={cfg.search.mode !== "hybrid"}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="rrf">RRF (mit Gewichten)</SelectItem>
                    <SelectItem value="dbsf">DBSF (Score-basiert)</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <Num
                id="p-cand"
                label="Kandidaten je Suche"
                value={cfg.search.candidates}
                onChange={(v) => patch("search", { candidates: v })}
              />
              <Num
                id="p-dw"
                label="Gewicht semantisch"
                step="0.1"
                value={cfg.search.dense_weight}
                onChange={(v) => patch("search", { dense_weight: v })}
              />
              <Num
                id="p-sw"
                label="Gewicht Stichwörter"
                step="0.1"
                value={cfg.search.sparse_weight}
                onChange={(v) => patch("search", { sparse_weight: v })}
              />
              <Num
                id="p-dmin"
                label="Mindest-Ähnlichkeit (semantisch)"
                hint="leer = aus"
                step="0.05"
                value={cfg.search.dense_min_score}
                onChange={(v) => patch("search", { dense_min_score: v })}
              />
            </div>
          </Section>

          <Section
            title="Query-Enhancement"
            hint="Ein LLM erzeugt zusätzliche Suchfragen. Mit allen wird gesucht, die besten Treffer gehen an das Chat-Modell. Kostet einen LLM-Aufruf pro Suche."
          >
            <div className="grid gap-3 sm:grid-cols-3">
              <div className="space-y-1">
                <Label className="text-xs">Modus</Label>
                <Select
                  value={qe.mode}
                  onValueChange={(v) => patch("query_enhancement", { mode: v as typeof qe.mode })}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="off">Aus</SelectItem>
                    <SelectItem value="multi_query">Mehrere Suchfragen</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <Num
                id="p-nq"
                label="Anzahl Fragen"
                value={qe.n_queries}
                onChange={(v) => patch("query_enhancement", { n_queries: v })}
              />
              <Num
                id="p-qt"
                label="Temperatur"
                step="0.1"
                value={qe.temperature}
                onChange={(v) => patch("query_enhancement", { temperature: v })}
              />
              <div className="space-y-1 sm:col-span-2">
                <Label className="text-xs">Helfer-Modell</Label>
                <Select
                  value={qe.model_ref ?? CHAT_MODEL}
                  onValueChange={(v) =>
                    patch("query_enhancement", { model_ref: v === CHAT_MODEL ? null : v })
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={CHAT_MODEL}>Das gerade chattende Modell</SelectItem>
                    {models.map((m) => (
                      <SelectItem key={m.ref} value={m.ref}>
                        {m.name} ({m.connection_name})
                        {m.visible ? "" : " · im Chat ausgeblendet"}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <Num
                id="p-qto"
                label="Timeout (Sekunden)"
                value={qe.timeout_s}
                onChange={(v) => patch("query_enhancement", { timeout_s: v })}
              />
            </div>
            <div className="flex items-center justify-between rounded-lg border border-border-base px-3 py-2">
              <Label htmlFor="p-orig" className="cursor-pointer text-sm">
                Originalfrage zusätzlich suchen
              </Label>
              <Switch
                id="p-orig"
                checked={qe.include_original}
                onCheckedChange={(v) => patch("query_enhancement", { include_original: v })}
              />
            </div>
            <div className="space-y-1">
              <div className="flex items-center justify-between">
                <Label htmlFor="p-prompt" className="text-xs">
                  Prompt (Platzhalter: <code>{"{frage}"}</code>, <code>{"{anzahl}"}</code>)
                </Label>
                <Button
                  type="button"
                  variant="ghost"
                  size="xs"
                  onClick={() => patch("query_enhancement", { prompt: defaults.prompt })}
                >
                  Standard-Prompt
                </Button>
              </div>
              <Textarea
                id="p-prompt"
                rows={6}
                value={qe.prompt}
                onChange={(e) => patch("query_enhancement", { prompt: e.target.value })}
                className="font-mono text-xs"
              />
              <p className="text-xs text-muted-foreground">
                Das Helfer-LLM läuft ohne Thinking und ohne Begrenzung der Ausgabelänge.
              </p>
            </div>
          </Section>

          <Section
            title="Reranking"
            hint="Ein Cross-Encoder sortiert die besten Kandidaten gegen die Originalfrage neu. Meist der größte Qualitätsgewinn, kostet etwas Rechenzeit. Das Modell wird zentral unter „Einlesen & Modelle“ gewählt."
          >
            <div className="flex items-center justify-between rounded-lg border border-border-base px-3 py-2">
              <Label htmlFor="p-rr" className="cursor-pointer text-sm">
                Reranking aktiv
              </Label>
              <Switch
                id="p-rr"
                checked={cfg.rerank.enabled}
                onCheckedChange={(v) => patch("rerank", { enabled: v })}
              />
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <Num
                id="p-rrc"
                label="Kandidaten"
                value={cfg.rerank.candidates}
                onChange={(v) => patch("rerank", { candidates: v })}
              />
              <Num
                id="p-rrm"
                label="Mindest-Score"
                hint="leer = aus"
                step="0.1"
                value={cfg.rerank.min_score}
                onChange={(v) => patch("rerank", { min_score: v })}
              />
            </div>
          </Section>

          <Section
            title="Ergebnis"
            hint="Kontext-Erweiterung braucht Dokumente, die mit dieser Version eingelesen wurden (Chunk-Reihenfolge)."
          >
            <div className="grid gap-3 sm:grid-cols-3">
              <Num
                id="p-k"
                label="Treffer an das LLM"
                value={cfg.final_k}
                onChange={(v) => setCfg((c) => (c ? { ...c, final_k: v } : c))}
              />
              <Num
                id="p-nb"
                label="Nachbar-Chunks (je Seite)"
                value={cfg.neighbors}
                onChange={(v) => setCfg((c) => (c ? { ...c, neighbors: v } : c))}
              />
              <Num
                id="p-lm"
                label="MMR-Lambda (0 = vielfältig, 1 = relevant)"
                step="0.1"
                value={cfg.mmr.lambda_mult}
                onChange={(v) => patch("mmr", { lambda_mult: v })}
              />
            </div>
            <div className="flex items-center justify-between rounded-lg border border-border-base px-3 py-2">
              <Label htmlFor="p-mmr" className="cursor-pointer text-sm">
                MMR (Doppelte Treffer vermeiden)
              </Label>
              <Switch
                id="p-mmr"
                checked={cfg.mmr.enabled}
                onCheckedChange={(v) => patch("mmr", { enabled: v })}
              />
            </div>
          </Section>
        </div>

        <DialogFooter>
          <Button variant="secondary" onClick={() => onOpenChange(false)}>
            Abbrechen
          </Button>
          <Button onClick={save} disabled={busy || !name.trim()}>
            Speichern
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
