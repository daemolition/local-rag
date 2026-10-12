import { useCallback, useEffect, useState } from "react";
import { Loader2, RotateCcw } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { api, errorMessage } from "@/lib/api";

interface CompactionSettings {
  enabled: boolean;
  headroom_percent: number;
  keep_percent: number;
  output_reserve_percent: number;
  prompt: string;
  default_prompt: string;
}

// Einstellungen der automatischen Compaction (Eingabe-Budget = Kontext − Ausgabe, Zusammenfassen ab 100 − Luft %).
export function CompactionCard() {
  const [cfg, setCfg] = useState<CompactionSettings | null>(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      setCfg(await api.get<CompactionSettings>("/api/admin/compaction"));
    } catch (e) {
      toast.error(errorMessage(e));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (!cfg) return null;

  const num = (k: "headroom_percent" | "keep_percent" | "output_reserve_percent", label: string, hint: string) => (
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
      const { default_prompt: _d, ...body } = cfg;
      setCfg(await api.put<CompactionSettings>("/api/admin/compaction", body));
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
            <h2 className="font-semibold">Kontext & Compaction</h2>
            <p className="text-sm text-muted-foreground">
              Eingabe-Budget eines Modells = Kontext − Ausgabe (in der Modell-Konfiguration). Ab
              (100 − Luft) % davon fasst die App den älteren Verlauf automatisch zusammen, damit der
              Kontext nie überläuft. Die Originalnachrichten bleiben erhalten.
            </p>
          </div>
          <label className="flex items-center gap-2 text-sm">
            <Switch checked={cfg.enabled} onCheckedChange={(v) => setCfg({ ...cfg, enabled: v })} />
            Aktiv
          </label>
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          {num("headroom_percent", "Luft (%)", "Zusammenfassen ab 100 − Luft % des Budgets (1–50).")}
          {num("keep_percent", "Bleibt wörtlich (%)", "Anteil des Budgets für den jüngsten Verlauf (10–80).")}
          {num("output_reserve_percent", "Ausgabe-Reserve (%)", "Nur wenn das Modell keine max. Tokens setzt (5–60).")}
        </div>
        <div className="space-y-1">
          <div className="flex items-center justify-between">
            <Label className="text-xs">Anweisung für die Zusammenfassung ({"{messages}"} = Verlauf)</Label>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setCfg({ ...cfg, prompt: cfg.default_prompt })}
              disabled={cfg.prompt === cfg.default_prompt}
            >
              <RotateCcw className="size-3.5" />
              Auf Standard zurücksetzen
            </Button>
          </div>
          <Textarea rows={8} value={cfg.prompt} onChange={(e) => setCfg({ ...cfg, prompt: e.target.value })} />
        </div>
        <Button size="sm" onClick={save} disabled={saving}>
          {saving ? <Loader2 className="size-4 animate-spin" /> : null}
          Speichern
        </Button>
      </CardContent>
    </Card>
  );
}
