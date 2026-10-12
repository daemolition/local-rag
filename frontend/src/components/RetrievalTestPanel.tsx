import { useMemo, useState } from "react";
import { Check, FlaskConical, Loader2 } from "lucide-react";
import { toast } from "sonner";
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
import { api, errorMessage } from "@/lib/api";
import type {
  Knowledge,
  RetrievalProfile,
  RetrievalTestResult,
  TraceStage,
} from "@/lib/types";

const OWN_PROFILE = "__own__";

const STAGE_LABEL: Record<string, string> = {
  query_enhancement: "Query-Enhancement",
  search: "Suche",
  fusion: "Zusammenführen",
  rerank: "Reranking",
  mmr: "MMR",
  neighbors: "Nachbar-Chunks",
  final: "Ergebnis",
};

interface Brief {
  filename: string;
  collection: string;
  chunk_index: number | null;
  score: number;
  snippet: string;
}

function BriefList({ items }: { items: Brief[] }) {
  return (
    <ol className="mt-1 space-y-1">
      {items.map((b, i) => (
        <li key={i} className="flex gap-2 text-xs">
          <span className="w-5 shrink-0 text-right text-muted-foreground">{i + 1}.</span>
          <span className="w-14 shrink-0 font-mono">{b.score}</span>
          <span className="min-w-0">
            <span className="font-medium">{b.filename}</span>
            {b.chunk_index !== null ? ` #${b.chunk_index + 1}` : ""}
            <span className="block truncate text-muted-foreground">{b.snippet}</span>
          </span>
        </li>
      ))}
    </ol>
  );
}

function StageView({ stage }: { stage: TraceStage }) {
  const s = stage as Record<string, unknown>;
  const lists = (["candidates", "result", "results"] as const).filter(
    (k) => Array.isArray(s[k]) && (s[k] as unknown[]).length > 0,
  );
  const error = (s.error ?? s.errors) as string | string[] | undefined;
  const warnings = s.warnings as string[] | undefined;
  const queries = s.queries as string[] | undefined;

  return (
    <details className="rounded-lg border border-border-base px-3 py-2" open={stage.stage === "final"}>
      <summary className="flex cursor-pointer items-center gap-2 text-sm font-medium">
        {STAGE_LABEL[stage.stage] ?? stage.stage}
        {stage.ms !== undefined ? (
          <span className="text-xs font-normal text-muted-foreground">{stage.ms} ms</span>
        ) : null}
        {error ? <span className="text-xs font-normal text-destructive">Fehler</span> : null}
      </summary>
      <div className="mt-2 space-y-2 text-xs">
        {queries ? (
          <div>
            <p className="font-medium">Suchfragen</p>
            <ul className="list-disc pl-5">
              {queries.map((q, i) => (
                <li key={i}>{q}</li>
              ))}
            </ul>
          </div>
        ) : null}
        {s.per_collection ? (
          <p>
            Treffer je Collection:{" "}
            {Object.entries(s.per_collection as Record<string, number>)
              .map(([c, n]) => `${c}: ${n}`)
              .join(", ")}
          </p>
        ) : null}
        {typeof s.skipped === "string" ? <p className="text-muted-foreground">Übersprungen: {s.skipped}</p> : null}
        {typeof s.fallback === "string" ? <p className="text-amber-600">{s.fallback}</p> : null}
        {typeof s.without_chunk_index === "number" && s.without_chunk_index > 0 ? (
          <p className="text-amber-600">
            {s.without_chunk_index} Treffer ohne Chunk-Reihenfolge (Dokument neu einlesen, damit
            Nachbarn greifen).
          </p>
        ) : null}
        {warnings?.map((w, i) => (
          <p key={i} className="text-amber-600">{w}</p>
        ))}
        {error ? (
          <p className="text-destructive">{Array.isArray(error) ? error.join("; ") : error}</p>
        ) : null}
        {lists.map((k) => (
          <BriefList key={k} items={s[k] as Brief[]} />
        ))}
      </div>
    </details>
  );
}

interface RetrievalTestPanelProps {
  knowledge: Knowledge[];
  profiles: RetrievalProfile[];
  // Wird nach "Auf Knowledge anwenden" aufgerufen.
  onApplied?: () => void;
}

// Pipeline-Test: gleiche Frage mit verschiedenen Profilen vergleichen und das
// beste direkt dem Knowledge zuweisen.
export function RetrievalTestPanel({ knowledge, profiles, onApplied }: RetrievalTestPanelProps) {
  const [question, setQuestion] = useState("");
  const [knowledgeId, setKnowledgeId] = useState<string>(knowledge[0] ? String(knowledge[0].id) : "");
  const [profileId, setProfileId] = useState<string>(OWN_PROFILE);
  const [running, setRunning] = useState(false);
  const [results, setResults] = useState<RetrievalTestResult[] | null>(null);
  const [helper, setHelper] = useState<string | null>(null);
  const [testedProfile, setTestedProfile] = useState<number | null>(null);
  const [applied, setApplied] = useState(false);

  const current = useMemo(
    () => knowledge.find((k) => String(k.id) === knowledgeId),
    [knowledge, knowledgeId],
  );
  const ownName =
    profiles.find((p) => p.id === (current?.retrieval_profile_id ?? profiles.find((x) => x.is_default)?.id))
      ?.name ?? "Standard";

  const run = async () => {
    if (!question.trim() || !current) return;
    setRunning(true);
    setApplied(false);
    try {
      const res = await api.post<{
        results: RetrievalTestResult[];
        helper_model: string | null;
      }>("/api/retrieval/test", {
        question,
        knowledge_ids: [current.id],
        ...(profileId !== OWN_PROFILE ? { profile_id: Number(profileId) } : {}),
      });
      setResults(res.results);
      setHelper(res.helper_model);
      setTestedProfile(profileId === OWN_PROFILE ? null : Number(profileId));
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setRunning(false);
    }
  };

  const apply = async () => {
    if (!current || testedProfile === null) return;
    try {
      await api.put(`/api/knowledge/${current.id}/retrieval-profile`, {
        profile_id: testedProfile,
      });
      setApplied(true);
      toast.success(`Profil für „${current.name}“ gesetzt`);
      onApplied?.();
    } catch (e) {
      toast.error(errorMessage(e));
    }
  };

  return (
    <section className="space-y-4">
      <div>
        <h2 className="flex items-center gap-2 text-lg font-semibold">
          <FlaskConical className="size-5" />
          Profil testen
        </h2>
        <p className="text-sm text-muted-foreground">
          Stelle eine Frage an ein Knowledge und sieh, was jede Stufe der Pipeline daraus macht.
          Vergleiche Profile und übernimm das beste.
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1">
          <Label className="text-xs">Knowledge</Label>
          <Select value={knowledgeId} onValueChange={setKnowledgeId}>
            <SelectTrigger>
              <SelectValue placeholder="Knowledge wählen" />
            </SelectTrigger>
            <SelectContent>
              {knowledge.map((k) => (
                <SelectItem key={k.id} value={String(k.id)}>
                  {k.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1">
          <Label className="text-xs">Profil</Label>
          <Select value={profileId} onValueChange={setProfileId}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={OWN_PROFILE}>Aktuell am Knowledge ({ownName})</SelectItem>
              {profiles.map((p) => (
                <SelectItem key={p.id} value={String(p.id)}>
                  {p.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          void run();
        }}
      >
        <Input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Testfrage, z. B. „Wie lange ist die Kündigungsfrist?“"
        />
        <Button type="submit" disabled={running || !question.trim() || !current}>
          {running ? <Loader2 className="size-4 animate-spin" /> : null}
          Testen
        </Button>
      </form>

      {results?.map((r) => (
        <Card key={r.knowledge_id}>
          <CardContent className="space-y-4 p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-sm font-semibold">
                {r.knowledge} · {r.documents.length} Treffer · {r.trace.total_ms} ms
                {helper ? (
                  <span className="ml-2 font-normal text-muted-foreground">Helfer: {helper}</span>
                ) : null}
              </p>
              {testedProfile !== null && current?.can_write ? (
                <Button size="sm" variant="secondary" onClick={apply} disabled={applied}>
                  {applied ? <Check className="size-4" /> : null}
                  {applied ? "Übernommen" : "Auf dieses Knowledge anwenden"}
                </Button>
              ) : null}
            </div>

            <div className="space-y-2">
              {r.trace.stages
                .filter((s) => s.stage !== "final")
                .map((s, i) => (
                  <StageView key={i} stage={s} />
                ))}
            </div>

            <div>
              <h3 className="mb-2 text-sm font-semibold">Das bekäme das LLM</h3>
              {r.documents.length === 0 ? (
                <p className="text-sm text-muted-foreground">Keine Treffer.</p>
              ) : (
                <div className="space-y-2">
                  {r.documents.map((d, i) => (
                    <details key={i} className="rounded-lg border border-border-base px-3 py-2" open={i === 0}>
                      <summary className="cursor-pointer text-sm">
                        <span className="font-medium">{d.filename}</span>
                        {d.chunks
                          ? ` · Abschnitte ${d.chunks[0] + 1}–${d.chunks[1] + 1}`
                          : d.chunk_index !== null
                            ? ` · Abschnitt ${d.chunk_index + 1}`
                            : ""}
                        <span className="ml-2 font-mono text-xs text-muted-foreground">{d.score}</span>
                      </summary>
                      <pre className="mt-2 whitespace-pre-wrap text-xs">{d.text}</pre>
                    </details>
                  ))}
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      ))}
    </section>
  );
}
