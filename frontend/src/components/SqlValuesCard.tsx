import { useCallback, useEffect, useRef, useState } from "react";
import { Loader2, Search, Sparkles } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { api, errorMessage } from "@/lib/api";

interface Overview {
  status: "idle" | "building" | "ready" | "error";
  built_at: string | null;
  value_count: number;
  column_count: number;
  error: string;
  columns: Record<string, string[]>;
  max_distinct: number;
}

interface Suggestion {
  table: string;
  column: string;
  rows: number;
  distinct: number;
  include: boolean;
  reason: string;
}

interface Hit {
  table: string;
  column: string;
  value: string;
  count: number;
  score: number;
}

const keyOf = (t: string, c: string) => `${t}\u0000${c}`;

// Wertverzeichnis: die verschiedenen Werte ausgewählter Textspalten, damit das Modell „Stühle“ zu
// „Stuhl“, „Bürostuhl“ usw. findet. Gespeichert werden Werte mit Häufigkeit, keine Zeilen.
export function SqlValuesCard({ knowledgeId }: { knowledgeId: number }) {
  const [info, setInfo] = useState<Overview | null>(null);
  const [rows, setRows] = useState<Suggestion[] | null>(null);
  const [chosen, setChosen] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [term, setTerm] = useState("");
  const [hits, setHits] = useState<Hit[] | null>(null);
  const timer = useRef<number | null>(null);

  const load = useCallback(async () => {
    try {
      const o = await api.get<Overview>(`/api/knowledge/${knowledgeId}/sql-values`);
      setInfo(o);
      return o;
    } catch (e) {
      toast.error(errorMessage(e));
      return null;
    }
  }, [knowledgeId]);

  useEffect(() => {
    void load();
    return () => {
      if (timer.current) window.clearTimeout(timer.current);
    };
  }, [load]);

  // Während des Aufbaus alle 2 s nachsehen
  useEffect(() => {
    if (info?.status !== "building") return;
    timer.current = window.setTimeout(() => void load(), 2000);
    return () => {
      if (timer.current) window.clearTimeout(timer.current);
    };
  }, [info, load]);

  if (!info) return null;

  const suggest = async () => {
    setBusy(true);
    try {
      const r = await api.post<{ columns: Suggestion[] }>(`/api/knowledge/${knowledgeId}/sql-values/suggest`);
      setRows(r.columns);
      const saved = new Set(Object.entries(info.columns).flatMap(([t, cs]) => cs.map((c) => keyOf(t, c))));
      setChosen(saved.size ? saved : new Set(r.columns.filter((c) => c.include).map((c) => keyOf(c.table, c.column))));
    } catch (e) {
      toast.error(errorMessage(e), { duration: 12000 });
    } finally {
      setBusy(false);
    }
  };

  const saveAndBuild = async () => {
    const columns: Record<string, string[]> = {};
    for (const k of chosen) {
      const [t, c] = k.split("\u0000");
      (columns[t] ??= []).push(c);
    }
    setBusy(true);
    try {
      await api.put(`/api/knowledge/${knowledgeId}/sql-values`, { columns });
      await api.post(`/api/knowledge/${knowledgeId}/sql-values/build`);
      toast.success("Wertverzeichnis wird aufgebaut");
      setRows(null);
      await load();
    } catch (e) {
      toast.error(errorMessage(e), { duration: 12000 });
    } finally {
      setBusy(false);
    }
  };

  const probe = async () => {
    try {
      const r = await api.post<{ results: Hit[] }>(`/api/knowledge/${knowledgeId}/sql-values/search`, { term });
      setHits(r.results);
    } catch (e) {
      toast.error(errorMessage(e));
    }
  };

  const statusText =
    info.status === "building"
      ? "Wird aufgebaut …"
      : info.status === "ready"
        ? `Bereit: ${info.value_count} Werte aus ${info.column_count} Spalten${info.built_at ? ` (Stand ${new Date(info.built_at).toLocaleString("de-DE")})` : ""}`
        : info.status === "error"
          ? "Aufbau fehlgeschlagen"
          : "Noch nicht aufgebaut";

  return (
    <Card>
      <CardContent className="space-y-3 p-4">
        <div>
          <h2 className="font-semibold">Wertverzeichnis</h2>
          <p className="text-sm text-muted-foreground">
            Damit das Modell „Stühle“ zu <em>Stuhl</em>, <em>Bürostuhl</em> und <em>Gartenstühle</em> findet, merkt sich die App
            die verschiedenen Werte ausgewählter Textspalten (nur Werte mit Häufigkeit, keine Zeilen). Die Antworten kommen
            weiterhin live aus der Datenbank.
          </p>
        </div>
        <p className="flex items-center gap-2 text-sm">
          {info.status === "building" ? <Loader2 className="size-4 animate-spin" /> : null}
          <span className={info.status === "error" ? "text-destructive" : ""}>{statusText}</span>
        </p>
        {info.error ? <p className="text-xs text-muted-foreground">{info.error}</p> : null}

        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="secondary" onClick={suggest} disabled={busy || info.status === "building"}>
            {busy && !rows ? <Loader2 className="size-4 animate-spin" /> : <Sparkles className="size-4" />}
            Spalten vorschlagen
          </Button>
        </div>

        {rows ? (
          <div className="space-y-2 rounded-lg border border-border-base p-3 text-sm">
            <div className="max-h-72 space-y-1 overflow-y-auto">
              {rows.length === 0 ? <p className="text-muted-foreground">Keine Textspalten gefunden.</p> : null}
              {rows.map((c) => {
                const k = keyOf(c.table, c.column);
                return (
                  <label key={k} className="flex items-start gap-2 rounded px-1 py-1 hover:bg-hover">
                    <input
                      type="checkbox"
                      className="mt-1"
                      checked={chosen.has(k)}
                      onChange={(e) =>
                        setChosen((s) => {
                          const n = new Set(s);
                          if (e.target.checked) n.add(k);
                          else n.delete(k);
                          return n;
                        })
                      }
                    />
                    <span className="min-w-0">
                      <span className="font-medium">
                        {c.table}.{c.column}
                      </span>{" "}
                      <span className="text-xs text-muted-foreground">
                        {c.distinct} verschiedene Werte in {c.rows} Zeilen · {c.reason}
                      </span>
                    </span>
                  </label>
                );
              })}
            </div>
            <Button size="sm" onClick={saveAndBuild} disabled={busy || chosen.size === 0}>
              {busy ? <Loader2 className="size-4 animate-spin" /> : null}
              Speichern und aufbauen
            </Button>
          </div>
        ) : null}

        {info.value_count > 0 ? (
          <div className="space-y-2">
            <div className="flex gap-2">
              <Input
                value={term}
                onChange={(e) => setTerm(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && term.trim() && void probe()}
                placeholder="Suche testen, z. B. Stühle"
              />
              <Button size="sm" variant="secondary" onClick={probe} disabled={!term.trim()}>
                <Search className="size-4" />
                Testen
              </Button>
            </div>
            {hits ? (
              hits.length === 0 ? (
                <p className="text-sm text-muted-foreground">Kein passender Wert.</p>
              ) : (
                <ul className="space-y-0.5 text-sm">
                  {hits.map((h) => (
                    <li key={`${h.table}.${h.column}.${h.value}`}>
                      <span className="text-muted-foreground">
                        {h.table}.{h.column}:
                      </span>{" "}
                      {h.value} <span className="text-xs text-muted-foreground">({h.count})</span>
                    </li>
                  ))}
                </ul>
              )
            ) : null}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
