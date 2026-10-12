import { useCallback, useEffect, useState } from "react";
import { Loader2, Mic, Play, Search, ShieldCheck } from "lucide-react";
import type { ReactNode } from "react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { api, errorMessage } from "@/lib/api";

interface ToolsOverview {
  stt: { base_url: string; model: string; has_key: boolean };
  search: { url: string; categories: string };
  pii: { url: string; enabled: boolean; has_key: boolean };
  web_search_available: boolean;
}

type Kind = "stt" | "search" | "pii";

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <div className="space-y-1">
      <Label className="text-xs">{label}</Label>
      {children}
      {hint ? <p className="text-xs text-muted-foreground">{hint}</p> : null}
    </div>
  );
}

function ToolCard({
  icon,
  title,
  hint,
  badge,
  onTest,
  testing,
  children,
}: {
  icon: ReactNode;
  title: string;
  hint: string;
  badge?: ReactNode;
  onTest: () => void;
  testing: boolean;
  children: ReactNode;
}) {
  return (
    <Card>
      <CardContent className="space-y-3 p-4">
        <div className="flex items-start justify-between gap-2">
          <div>
            <h2 className="flex items-center gap-2 font-semibold">
              {icon}
              {title}
            </h2>
            <p className="text-sm text-muted-foreground">{hint}</p>
          </div>
          {badge}
        </div>
        <div className="grid gap-3 sm:grid-cols-2">{children}</div>
        <Button variant="outline" size="sm" onClick={onTest} disabled={testing}>
          {testing ? <Loader2 className="size-4 animate-spin" /> : <Play className="size-4" />}
          Testen
        </Button>
      </CardContent>
    </Card>
  );
}

export function AdminToolsPage() {
  const [data, setData] = useState<ToolsOverview | null>(null);
  const [stt, setStt] = useState({ base_url: "", model: "", api_key: "" });
  const [search, setSearch] = useState({ url: "", categories: "general" });
  const [pii, setPii] = useState({ url: "", enabled: true, api_key: "" });
  const [testing, setTesting] = useState<Kind | null>(null);
  const [saving, setSaving] = useState(false);

  const apply = (d: ToolsOverview) => {
    setData(d);
    setStt({ base_url: d.stt.base_url, model: d.stt.model, api_key: "" });
    setSearch({ url: d.search.url, categories: d.search.categories });
    setPii({ url: d.pii.url, enabled: d.pii.enabled, api_key: "" });
  };

  const load = useCallback(async () => {
    try {
      apply(await api.get<ToolsOverview>("/api/admin/tools"));
    } catch (e) {
      toast.error(errorMessage(e));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const save = async () => {
    setSaving(true);
    try {
      apply(await api.put<ToolsOverview>("/api/admin/tools", { stt, search, pii }));
      toast.success("Gespeichert");
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setSaving(false);
    }
  };

  const test = async (kind: Kind) => {
    const values = kind === "stt" ? stt : kind === "search" ? search : pii;
    setTesting(kind);
    try {
      const r = await api.post<{ message?: string; details?: string }>("/api/admin/tools/test", {
        kind,
        values,
      });
      toast.success((r.message || "Test erfolgreich") + (r.details ? ` – ${r.details}` : ""));
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setTesting(null);
    }
  };

  if (!data) return <div className="p-6 text-sm text-muted-foreground">Lädt …</div>;

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-5xl space-y-6 p-6">
        <div>
          <h1 className="text-xl font-semibold">Tools</h1>
          <p className="text-sm text-muted-foreground">
            Zusatzdienste für Spracheingabe und Websuche. Die Websuche schaltest du je Modell
            zu (Modelle › Konfigurieren), sie ist nur mit aktivem PII-Filter möglich.
          </p>
        </div>

        <ToolCard
          icon={<Mic className="size-4" />}
          title="Spracheingabe"
          hint="OpenAI-kompatibler Speech-to-Text-Dienst (z. B. Parakeet) für den Mikrofon-Knopf im Chat."
          badge={
            <Badge variant={data.stt.base_url ? "secondary" : "outline"}>
              {data.stt.base_url ? "eingerichtet" : "nicht eingerichtet"}
            </Badge>
          }
          onTest={() => void test("stt")}
          testing={testing === "stt"}
        >
          <Field label="Adresse (Base-URL)">
            <Input
              value={stt.base_url}
              onChange={(e) => setStt({ ...stt, base_url: e.target.value })}
              placeholder="http://parakeet:5001/v1"
            />
          </Field>
          <Field label="Modell">
            <Input
              value={stt.model}
              onChange={(e) => setStt({ ...stt, model: e.target.value })}
              placeholder="nemo-parakeet-tdt-0.6b-v3"
            />
          </Field>
          <Field
            label="API-Key"
            hint={data.stt.has_key ? "Ein Key ist gespeichert. Leer lassen, um ihn zu behalten." : undefined}
          >
            <Input
              type="password"
              value={stt.api_key}
              onChange={(e) => setStt({ ...stt, api_key: e.target.value })}
              placeholder={data.stt.has_key ? "••••••••" : "optional"}
            />
          </Field>
        </ToolCard>

        <ToolCard
          icon={<ShieldCheck className="size-4" />}
          title="PII-Filter"
          hint="Maskiert personenbezogene Daten in Anfragen, bevor sie das System verlassen (entityguard)."
          badge={
            <Badge variant={data.pii.url && data.pii.enabled ? "secondary" : "outline"}>
              {data.pii.url && data.pii.enabled ? "aktiv" : "aus"}
            </Badge>
          }
          onTest={() => void test("pii")}
          testing={testing === "pii"}
        >
          <Field label="Adresse (vollständiger Endpoint)">
            <Input
              value={pii.url}
              onChange={(e) => setPii({ ...pii, url: e.target.value })}
              placeholder="http://entityguard:9500/api/v1/sanitize"
            />
          </Field>
          <Field
            label="API-Key"
            hint={data.pii.has_key ? "Ein Key ist gespeichert. Leer lassen, um ihn zu behalten." : undefined}
          >
            <Input
              type="password"
              value={pii.api_key}
              onChange={(e) => setPii({ ...pii, api_key: e.target.value })}
              placeholder={data.pii.has_key ? "••••••••" : "optional"}
            />
          </Field>
          <div className="flex items-center justify-between rounded-lg border border-border-base px-3 py-2 sm:col-span-2">
            <div>
              <Label className="text-sm">PII-Filter verwenden</Label>
              <p className="text-xs text-muted-foreground">
                Aus: Nachrichten gehen ungefiltert ans Modell und die Websuche ist nicht verfügbar.
              </p>
            </div>
            <Switch
              checked={pii.enabled}
              onCheckedChange={(v) => setPii({ ...pii, enabled: v })}
            />
          </div>
        </ToolCard>

        <ToolCard
          icon={<Search className="size-4" />}
          title="Websuche (SearXNG)"
          hint="Metasuchmaschine, die ein Modell als Werkzeug nutzen darf. Standard ist aus; zuschaltbar je Modell."
          badge={
            <Badge variant={data.web_search_available ? "secondary" : "outline"}>
              {data.web_search_available
                ? "bereit"
                : data.search.url
                  ? "braucht PII-Filter"
                  : "nicht eingerichtet"}
            </Badge>
          }
          onTest={() => void test("search")}
          testing={testing === "search"}
        >
          <Field label="Adresse">
            <Input
              value={search.url}
              onChange={(e) => setSearch({ ...search, url: e.target.value })}
              placeholder="http://searxng:8080"
            />
          </Field>
          <Field label="Kategorien" hint="Komma-getrennt, z. B. general,news,science">
            <Input
              value={search.categories}
              onChange={(e) => setSearch({ ...search, categories: e.target.value })}
            />
          </Field>
        </ToolCard>

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
