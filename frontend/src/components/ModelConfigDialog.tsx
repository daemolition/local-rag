import { useEffect, useState } from "react";
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
import type { Knowledge, ModelEntry, ModelsResponse } from "@/lib/types";
import { toast } from "sonner";

const PARAM_FIELDS = [
  { key: "temperature", label: "Temperatur", hint: "0 – 2" },
  { key: "top_p", label: "Top P", hint: "0 – 1" },
  { key: "top_k", label: "Top K", hint: "ganze Zahl" },
  { key: "max_tokens", label: "Max. Tokens", hint: "leer = unbegrenzt" },
  { key: "num_ctx", label: "Kontext (num_ctx)", hint: "Ollama" },
] as const;

const THINKING = ["none", "low", "medium", "high", "max"];
const DEFAULT_THINKING = "default";

interface ModelConfigDialogProps {
  model: ModelEntry | null;
  knowledge: Knowledge[];
  webSearchAvailable?: boolean;
  webSearchMasked?: boolean;
  paramDefaults?: ModelsResponse["param_defaults"];
  compaction?: ModelsResponse["compaction"];
  onOpenChange: (open: boolean) => void;
  onSaved: () => void;
}

export function ModelConfigDialog({
  model,
  knowledge,
  webSearchAvailable = false,
  webSearchMasked = false,
  paramDefaults,
  compaction,
  onOpenChange,
  onSaved,
}: ModelConfigDialogProps) {
  const [name, setName] = useState("");
  const [visible, setVisible] = useState(true);
  const [prompt, setPrompt] = useState("");
  const [webSearch, setWebSearch] = useState(false);
  const [params, setParams] = useState<Record<string, string>>({});
  const [thinking, setThinking] = useState(DEFAULT_THINKING);
  const [knowledgeIds, setKnowledgeIds] = useState<number[]>([]);
  const [allowExtra, setAllowExtra] = useState(true);
  const [busy, setBusy] = useState(false);
  // Eingabe-Budget = Kontext − Ausgabe; Compaction ab (100 − Luft) % davon
  const budgetInfo = (() => {
    const pick = (key: "num_ctx" | "max_tokens") => {
      const own = parseInt(params[key] ?? "", 10);
      if (Number.isFinite(own)) return own;
      const d = paramDefaults?.[key];
      return typeof d === "number" ? d : null;
    };
    const window = pick("num_ctx");
    if (!window || !compaction) return null;
    const out = pick("max_tokens") ?? Math.ceil((window * compaction.output_reserve_percent) / 100);
    const usable = window - out;
    return { window, out, usable, trigger: Math.floor((usable * (100 - compaction.headroom_percent)) / 100) };
  })();
  const defaultFor = (key: string, hint: string) => {
    const v = paramDefaults?.[key as keyof NonNullable<typeof paramDefaults>];
    if (v === undefined) return hint;
    return v === null || v === "" ? hint : `Standard: ${v}`;
  };

  useEffect(() => {
    if (!model) return;
    const cfg = model.config;
    setName(model.is_clone ? (cfg?.name ?? model.name) : (cfg?.name ?? ""));
    setVisible(cfg?.visible ?? true);
    setPrompt(cfg?.system_prompt ?? "");
    setWebSearch(cfg?.web_search ?? false);
    const p: Record<string, string> = {};
    for (const f of PARAM_FIELDS) {
      const v = cfg?.params?.[f.key];
      if (v !== undefined) p[f.key] = String(v);
    }
    setParams(p);
    setThinking(cfg?.params?.thinking ?? DEFAULT_THINKING);
    setKnowledgeIds(cfg?.knowledge_ids ?? []);
    setAllowExtra(cfg?.allow_extra_knowledge ?? true);
  }, [model]);

  const save = async () => {
    if (!model) return;
    setBusy(true);
    try {
      await api.put("/api/models/config", {
        ref: model.ref,
        name,
        visible,
        system_prompt: prompt,
        web_search: webSearch && webSearchAvailable,
        params: {
          ...params,
          thinking: thinking === DEFAULT_THINKING ? "" : thinking,
        },
        knowledge_ids: knowledgeIds,
        allow_extra_knowledge: allowExtra,
      });
      toast.success("Modell gespeichert");
      onSaved();
      onOpenChange(false);
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const toggleKnowledge = (id: number, on: boolean) =>
    setKnowledgeIds((prev) =>
      on ? [...new Set([...prev, id])] : prev.filter((x) => x !== id),
    );

  return (
    <Dialog open={model !== null} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>
            {model?.is_clone ? "Klon konfigurieren" : "Modell konfigurieren"}
          </DialogTitle>
          <DialogDescription>
            {model?.model_id} · {model?.connection_name}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6">
          <div className="space-y-2">
            <Label htmlFor="mc-name">{model?.is_clone ? "Name" : "Anzeigename (Alias)"}</Label>
            <Input
              id="mc-name"
              value={name}
              placeholder={model?.is_clone ? undefined : model?.model_id}
              onChange={(e) => setName(e.target.value)}
            />
            {!model?.is_clone ? (
              <p className="text-xs text-muted-foreground">
                So heißt das Modell im Chat. Leer lassen für die Original-ID.
              </p>
            ) : null}
          </div>

          <div className="flex items-center justify-between rounded-lg border border-border-base px-3 py-2">
            <div>
              <Label htmlFor="mc-visible" className="cursor-pointer">
                Im Chat sichtbar
              </Label>
              <p className="text-xs text-muted-foreground">
                Ausblenden z. B. für Embedding-Modelle.
              </p>
            </div>
            <Switch id="mc-visible" checked={visible} onCheckedChange={setVisible} />
          </div>

          <section className="space-y-2">
            <Label htmlFor="mc-prompt">Prompt</Label>
            <Textarea
              id="mc-prompt"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              rows={6}
              placeholder="Zusätzliche Anweisungen, z. B. Tonfall und Fachgebiet…"
            />
            <p className="text-xs text-muted-foreground">
              Wird an die Standard-Anweisungen (Seite Modelle) angehängt, z. B. für die Brand Voice dieses Modells.
              Die Regeln für Werkzeuge und Quellen sind fest eingebaut.
            </p>
          </section>

          <section className="space-y-2">
            <h3 className="text-sm font-semibold">Werkzeuge</h3>
            <div className="flex items-start justify-between gap-4 rounded-lg border border-border-base px-3 py-2">
              <div>
                <Label htmlFor="mc-web" className="cursor-pointer">
                  Websuche (SearXNG)
                </Label>
                <p className="text-xs text-muted-foreground">
                  {webSearchAvailable
                    ? webSearchMasked
                      ? "Das Modell darf im Web recherchieren. Suchanfragen werden vorher durch den PII-Filter maskiert."
                      : "Das Modell darf im Web recherchieren. Achtung: Ohne PII-Filter gehen Suchanfragen unmaskiert an SearXNG und die Suchmaschinen."
                    : "Nicht verfügbar: Dafür muss SearXNG unter Administration › Tools eingerichtet sein, dazu ein PII-Filter oder die Freigabe „Auch ohne PII-Filter erlauben“."}
                </p>
              </div>
              <Switch
                id="mc-web"
                checked={webSearch && webSearchAvailable}
                disabled={!webSearchAvailable}
                onCheckedChange={setWebSearch}
              />
            </div>
          </section>

          <section className="space-y-2">
            <h3 className="text-sm font-semibold">Parameter</h3>
            <p className="text-xs text-muted-foreground">
              Leere Felder verwenden den Standardwert (grau angezeigt).
            </p>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {PARAM_FIELDS.map((f) => (
                <div key={f.key} className="space-y-1">
                  <Label htmlFor={`mc-${f.key}`} className="text-xs">
                    {f.label}
                  </Label>
                  <Input
                    id={`mc-${f.key}`}
                    inputMode="decimal"
                    value={params[f.key] ?? ""}
                    onChange={(e) =>
                      setParams((prev) => ({ ...prev, [f.key]: e.target.value }))
                    }
                    placeholder={defaultFor(f.key, f.hint)}
                  />
                </div>
              ))}
              {budgetInfo ? (
                <p
                  className={`text-xs sm:col-span-2 ${budgetInfo.usable < 1024 ? "text-destructive" : "text-muted-foreground"}`}
                >
                  {budgetInfo.usable < 1024
                    ? `Eingabe-Budget nur ${budgetInfo.usable} Token (Kontext ${budgetInfo.window} − Ausgabe ${budgetInfo.out}): zu klein, die Compaction ist für dieses Modell aus.`
                    : `Eingabe-Budget ${budgetInfo.usable} Token (Kontext ${budgetInfo.window} − Ausgabe ${budgetInfo.out})${compaction?.enabled ? `, Compaction ab ${budgetInfo.trigger} Token.` : ", Compaction ist abgeschaltet."}`}
                </p>
              ) : null}
              <div className="space-y-1">
                <Label className="text-xs">Thinking</Label>
                <Select value={thinking} onValueChange={setThinking}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={DEFAULT_THINKING}>
                      Standard{paramDefaults?.thinking ? ` (${paramDefaults.thinking})` : ""}
                    </SelectItem>
                    {THINKING.map((t) => (
                      <SelectItem key={t} value={t}>
                        {t}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
          </section>

          <section className="space-y-2">
            <h3 className="text-sm font-semibold">Knowledge</h3>
            <p className="text-xs text-muted-foreground">
              Dieses Wissen durchsucht das Modell immer. Ohne Auswahl gilt die Auswahl im Chat.
            </p>
            {knowledgeIds.length > 0 ? (
              <label className="flex items-center justify-between gap-3 rounded-lg border border-border-base px-3 py-2 text-sm">
                <span>
                  Nutzer dürfen zusätzliches eigenes Knowledge wählen
                  <span className="block text-xs text-muted-foreground">
                    Aus: Das Modell durchsucht nur das Wissen oben (z. B. für einen kuratierten Fach-Assistenten).
                  </span>
                </span>
                <Switch checked={allowExtra} onCheckedChange={setAllowExtra} />
              </label>
            ) : null}
            {knowledge.length === 0 ? (
              <p className="text-sm text-muted-foreground">Kein Knowledge vorhanden.</p>
            ) : (
              <div className="max-h-44 space-y-1 overflow-y-auto rounded-lg border border-border-base p-2">
                {knowledge.map((k) => (
                  <label
                    key={k.id}
                    className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-sm hover:bg-hover"
                  >
                    <input
                      type="checkbox"
                      className="size-4"
                      checked={knowledgeIds.includes(k.id)}
                      onChange={(e) => toggleKnowledge(k.id, e.target.checked)}
                    />
                    <span className="truncate">{k.name}</span>
                  </label>
                ))}
              </div>
            )}
          </section>
        </div>

        <DialogFooter>
          <Button variant="secondary" onClick={() => onOpenChange(false)}>
            Abbrechen
          </Button>
          <Button onClick={save} disabled={busy || (model?.is_clone && !name.trim())}>
            Speichern
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
