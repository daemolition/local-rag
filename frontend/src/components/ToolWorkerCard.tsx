import { useCallback, useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, errorMessage } from "@/lib/api";

interface ToolWorkerView {
  url: string;
  timeout_s: number;
  memory_mb: number;
  max_output_chars: number;
  token_configured: boolean;
  reachable: boolean;
  version: string;
  error: string;
  sql_url: string;
  sql_row_limit: number;
  sql_timeout_s: number;
  sql_max_cell_chars: number;
  sql_reachable: boolean;
  sql_version: string;
}

// Status und Limits des Tool-Workers (führt Pandas-Code isoliert in einem eigenen Container aus).
export function ToolWorkerCard() {
  const [cfg, setCfg] = useState<ToolWorkerView | null>(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      setCfg(await api.get<ToolWorkerView>("/api/admin/tool-worker"));
    } catch (e) {
      toast.error(errorMessage(e));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (!cfg) return null;

  type NumKey = "timeout_s" | "memory_mb" | "max_output_chars" | "sql_row_limit" | "sql_timeout_s" | "sql_max_cell_chars";
  const num = (k: NumKey, label: string, hint: string) => (
    <div className="space-y-1">
      <Label className="text-xs">{label}</Label>
      <Input
        inputMode="numeric"
        value={String(cfg[k])}
        onChange={(e) => setCfg({ ...cfg, [k]: Number(e.target.value.replace(/\D/g, "")) || 0 })}
      />
      <p className="text-xs text-muted-foreground">{hint}</p>
    </div>
  );

  const save = async () => {
    setSaving(true);
    try {
      const { url, timeout_s, memory_mb, max_output_chars, sql_url, sql_row_limit, sql_timeout_s, sql_max_cell_chars } = cfg;
      setCfg(
        await api.put<ToolWorkerView>("/api/admin/tool-worker", {
          url,
          timeout_s,
          memory_mb,
          max_output_chars,
          sql_url,
          sql_row_limit,
          sql_timeout_s,
          sql_max_cell_chars,
        }),
      );
      toast.success("Gespeichert");
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card>
      <CardContent className="space-y-3 p-4">
        <div className="flex items-start justify-between gap-2">
          <div>
            <h2 className="font-semibold">Tool-Worker</h2>
            <p className="text-sm text-muted-foreground">
              Pandas-Auswertungen (CSV/Excel) laufen isoliert in einem eigenen Container. Ohne erreichbaren Worker
              meldet die Auswertung „Codeausführung nicht verfügbar“, der Chat läuft weiter.
            </p>
          </div>
          <span
            className={`shrink-0 rounded-full px-2 py-0.5 text-xs ${
              cfg.reachable ? "bg-emerald-500/15 text-emerald-600" : "bg-destructive/15 text-destructive"
            }`}
          >
            {cfg.reachable ? `Erreichbar${cfg.version ? ` · v${cfg.version}` : ""}` : "Nicht erreichbar"}
          </span>
        </div>
        {!cfg.token_configured && (
          <p className="text-sm text-destructive">
            TOOL_WORKER_TOKEN ist in der App nicht gesetzt (Umgebung oder .env).
          </p>
        )}
        <div className="space-y-1">
          <Label className="text-xs">Adresse</Label>
          <Input value={cfg.url} onChange={(e) => setCfg({ ...cfg, url: e.target.value })} />
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          {num("timeout_s", "Zeitlimit (s)", "1–300")}
          {num("memory_mb", "Speicher (MB)", "128–8192")}
          {num("max_output_chars", "Ausgabe (Zeichen)", "1000–200000")}
        </div>
        <div className="flex items-start justify-between gap-2 pt-2">
          <div>
            <h3 className="text-sm font-semibold">SQL-Worker</h3>
            <p className="text-xs text-muted-foreground">Fragt SQL-Datenbanken lesend ab (Knowledge „SQL-Datenbank“).</p>
          </div>
          <span
            className={`shrink-0 rounded-full px-2 py-0.5 text-xs ${
              cfg.sql_reachable ? "bg-emerald-500/15 text-emerald-600" : "bg-destructive/15 text-destructive"
            }`}
          >
            {cfg.sql_reachable ? `Erreichbar${cfg.sql_version ? ` · v${cfg.sql_version}` : ""}` : "Nicht erreichbar"}
          </span>
        </div>
        <div className="space-y-1">
          <Label className="text-xs">Adresse</Label>
          <Input value={cfg.sql_url} onChange={(e) => setCfg({ ...cfg, sql_url: e.target.value })} />
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          {num("sql_row_limit", "Max. Zeilen", "1–1000")}
          {num("sql_timeout_s", "Zeitlimit (s)", "1–120")}
          {num("sql_max_cell_chars", "Zelle (Zeichen)", "50–5000")}
        </div>
        <Button size="sm" onClick={save} disabled={saving}>
          {saving ? <Loader2 className="size-4 animate-spin" /> : null}
          Speichern
        </Button>
      </CardContent>
    </Card>
  );
}
