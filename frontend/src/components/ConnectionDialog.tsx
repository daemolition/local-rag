import { useEffect, useState } from "react";
import { CheckCircle2, Loader2, XCircle } from "lucide-react";
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
import { Switch } from "@/components/ui/switch";
import { api, errorMessage } from "@/lib/api";
import type { Connection } from "@/lib/types";

type Kind = Connection["kind"];

const KINDS: { value: Kind; label: string; hint: string }[] = [
  { value: "llm", label: "OpenAI-kompatibel", hint: "Chat-Modelle (LiteLLM, vLLM, Ollama, OpenAI). Claude und andere Anbieter laufen über LiteLLM." },
  { value: "tei", label: "Text Embeddings Inference", hint: "HuggingFace TEI für Embedding oder Reranking (ein Modell je Server, auch auf ARM)." },
  { value: "infinity", label: "Infinity", hint: "Infinity-Server für Embedding und Reranking (mehrere Modelle je Server)." },
];

const PRESETS: Record<Kind, { label: string; url: string }[]> = {
  llm: [
    { label: "OpenAI", url: "https://api.openai.com/v1" },
    { label: "LiteLLM", url: "http://localhost:4000/v1" },
    { label: "Ollama", url: "http://localhost:11434/v1" },
    { label: "vLLM", url: "http://localhost:8000/v1" },
  ],
  tei: [{ label: "TEI", url: "http://localhost:8080" }],
  infinity: [{ label: "Infinity", url: "http://localhost:7997" }],
};

export interface ConnectionValues {
  name: string;
  base_url: string;
  kind: Kind;
  // Leer beim Bearbeiten = gespeicherten Key behalten.
  api_key: string;
  enabled: boolean;
}

interface ConnectionDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  // Ohne Wert: neue Connection.
  connection?: Connection | null;
  onSubmit: (values: ConnectionValues) => Promise<void>;
}

type TestState =
  | { state: "idle" }
  | { state: "running" }
  | { state: "ok"; message: string }
  | { state: "error"; message: string };

export function ConnectionDialog({
  open,
  onOpenChange,
  connection,
  onSubmit,
}: ConnectionDialogProps) {
  const [name, setName] = useState("");
  const [kind, setKind] = useState<Kind>("llm");
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [enabled, setEnabled] = useState(true);
  const [busy, setBusy] = useState(false);
  const [test, setTest] = useState<TestState>({ state: "idle" });

  useEffect(() => {
    if (!open) return;
    setName(connection?.name ?? "");
    setKind(connection?.kind ?? "llm");
    setBaseUrl(connection?.base_url ?? "");
    setApiKey("");
    setEnabled(connection?.enabled ?? true);
    setTest({ state: "idle" });
  }, [open, connection]);

  const runTest = async () => {
    setTest({ state: "running" });
    try {
      const res = await api.post<{ success: boolean; message: string }>(
        "/api/connections/test",
        { id: connection?.id, kind, base_url: baseUrl, api_key: apiKey },
      );
      setTest({ state: "ok", message: res.message });
    } catch (e) {
      setTest({ state: "error", message: errorMessage(e) });
    }
  };

  const submit = async () => {
    setBusy(true);
    try {
      await onSubmit({ name, kind, base_url: baseUrl, api_key: apiKey, enabled });
      onOpenChange(false);
    } finally {
      setBusy(false);
    }
  };

  const valid = name.trim() !== "" && /^https?:\/\//.test(baseUrl.trim());

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {connection ? "Connection bearbeiten" : "Neue Connection"}
          </DialogTitle>
          <DialogDescription>
            {KINDS.find((k) => k.value === kind)?.hint}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-2">
            <Label>Typ</Label>
            <div className="flex flex-wrap gap-1.5">
              {KINDS.map((k) => (
                <button
                  key={k.value}
                  type="button"
                  onClick={() => {
                    setKind(k.value);
                    setTest({ state: "idle" });
                  }}
                  className={`rounded-full border px-3 py-1 text-sm ${
                    kind === k.value
                      ? "border-primary bg-primary/10 text-foreground"
                      : "border-border-base text-muted-foreground hover:bg-hover"
                  }`}
                >
                  {k.label}
                </button>
              ))}
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="conn-name">Name</Label>
            <Input
              id="conn-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="z. B. LiteLLM Produktion"
              autoFocus
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="conn-url">Base-URL</Label>
            <Input
              id="conn-url"
              value={baseUrl}
              onChange={(e) => {
                setBaseUrl(e.target.value);
                setTest({ state: "idle" });
              }}
              placeholder={kind === "llm" ? "https://host:4000/v1" : "http://host:8080"}
              spellCheck={false}
            />
            <div className="flex flex-wrap gap-1.5">
              {PRESETS[kind].map((p) => (
                <button
                  key={p.label}
                  type="button"
                  onClick={() => setBaseUrl(p.url)}
                  className="rounded-full border border-border-base px-2.5 py-0.5 text-xs text-muted-foreground hover:bg-hover"
                >
                  {p.label}
                </button>
              ))}
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="conn-key">API-Key</Label>
            <Input
              id="conn-key"
              type="password"
              autoComplete="off"
              value={apiKey}
              onChange={(e) => {
                setApiKey(e.target.value);
                setTest({ state: "idle" });
              }}
              placeholder={
                connection?.has_key ? "Gespeichert, leer lassen zum Behalten" : "sk-…"
              }
            />
          </div>

          <div className="flex items-center justify-between rounded-lg border border-border-base px-3 py-2">
            <Label htmlFor="conn-enabled" className="cursor-pointer">
              Aktiv
            </Label>
            <Switch id="conn-enabled" checked={enabled} onCheckedChange={setEnabled} />
          </div>

          <div className="space-y-2">
            <Button
              type="button"
              variant="secondary"
              size="sm"
              disabled={!/^https?:\/\//.test(baseUrl.trim()) || test.state === "running"}
              onClick={runTest}
            >
              {test.state === "running" ? (
                <Loader2 className="size-4 animate-spin" />
              ) : null}
              Verbindung testen
            </Button>
            {test.state === "ok" ? (
              <p className="flex items-center gap-1.5 text-sm text-green-600 dark:text-green-400">
                <CheckCircle2 className="size-4 shrink-0" />
                {test.message}
              </p>
            ) : null}
            {test.state === "error" ? (
              <p className="flex items-start gap-1.5 text-sm text-destructive">
                <XCircle className="mt-0.5 size-4 shrink-0" />
                {test.message}
              </p>
            ) : null}
          </div>
        </div>

        <DialogFooter>
          <Button variant="secondary" onClick={() => onOpenChange(false)}>
            Abbrechen
          </Button>
          <Button onClick={submit} disabled={!valid || busy}>
            {connection ? "Speichern" : "Anlegen"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
