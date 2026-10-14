import { useCallback, useEffect, useState } from "react";
import { Loader2, RotateCcw } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { api, errorMessage } from "@/lib/api";

interface BehaviorSettings {
  prompt: string;
  default_prompt: string;
}

// Standard-Anweisungen für alle Modelle (Rolle, Sprache, Stil). Die Werkzeug- und Quellenregeln sind fest im Code.
export function BehaviorCard() {
  const [cfg, setCfg] = useState<BehaviorSettings | null>(null);
  const [saved, setSaved] = useState("");
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await api.get<BehaviorSettings>("/api/admin/agent-behavior");
      setCfg(data);
      setSaved(data.prompt);
    } catch (e) {
      toast.error(errorMessage(e));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (!cfg) return null;

  const save = async () => {
    setSaving(true);
    try {
      const data = await api.put<BehaviorSettings>("/api/admin/agent-behavior", { prompt: cfg.prompt });
      setCfg(data);
      setSaved(data.prompt);
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
        <div>
          <h2 className="font-semibold">Standard-Anweisungen für alle Modelle</h2>
          <p className="text-sm text-muted-foreground">
            Rolle, Sprache, Stil und wie Übersichts- oder Zusammenfassungsfragen beantwortet werden.
            Pro Modell kommt der Prompt aus der Modell-Konfiguration dazu (z. B. die Brand Voice).
            Die Regeln für Werkzeuge und Quellenangaben sind fest eingebaut und nicht änderbar,
            damit Aufrufe zuverlässig bleiben.
          </p>
        </div>
        <div className="space-y-1">
          <div className="flex items-center justify-between">
            <Label htmlFor="behavior-prompt" className="text-xs">Anweisungen</Label>
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
          <Textarea
            id="behavior-prompt"
            rows={10}
            value={cfg.prompt}
            onChange={(e) => setCfg({ ...cfg, prompt: e.target.value })}
          />
        </div>
        <Button size="sm" onClick={save} disabled={saving || cfg.prompt === saved}>
          {saving ? <Loader2 className="size-4 animate-spin" /> : null}
          Speichern
        </Button>
      </CardContent>
    </Card>
  );
}
