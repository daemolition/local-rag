import {
  BarChart3,
  ChevronRight,
  Check,
  Copy,
  Database,
  FileSearch,
  FileText,
  Globe,
  List,
  Loader2,
  Search,
  Table,
  Wrench,
} from "lucide-react";
import { useState, type ReactNode } from "react";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Markdown } from "@/components/Markdown";
import { toast } from "sonner";
import { cn, copyText } from "@/lib/utils";

export interface ToolCall {
  name: string;
  status: "running" | "done";
}

const TOOL_META: Record<string, { label: string; icon: ReactNode }> = {
  web_search_tool: { label: "Internet-Suche", icon: <Globe className="size-4" /> },
  document_search_tool: {
    label: "Dokumentensuche",
    icon: <Search className="size-4" />,
  },
  list_files: { label: "Dateiauflistung", icon: <FileText className="size-4" /> },
  preview_data: { label: "Datenvorschau", icon: <FileSearch className="size-4" /> },
  run_pandas: { label: "Datenanalyse", icon: <BarChart3 className="size-4" /> },
  sql_schema: { label: "Datenbank-Schema", icon: <Database className="size-4" /> },
  sql_query: { label: "Datenbankabfrage", icon: <Database className="size-4" /> },
  sql_find_values: { label: "Wertesuche", icon: <Search className="size-4" /> },
  list_summaries: { label: "Ablagen auflisten", icon: <List className="size-4" /> },
  read_summary: { label: "Ablage lesen", icon: <Table className="size-4" /> },
  write_summary: { label: "Ablage speichern", icon: <FileText className="size-4" /> },
  edit_summary: { label: "Ablage bearbeiten", icon: <FileText className="size-4" /> },
};

function toolMeta(name: string) {
  return TOOL_META[name] ?? { label: name, icon: <Wrench className="size-4" /> };
}

export interface ToolResult {
  name: string;
  output: string;
}

interface MessageProps {
  role: "user" | "assistant";
  content: string;
  reasoning?: string;
  tools?: ToolCall[];
  toolResults?: ToolResult[];
  sources?: SourceInfo[];
  streaming?: boolean;
  dimmed?: boolean;
  attachments?: string[];
  waiting?: string;
}

export interface SourceInfo {
  n?: number;
  filename: string;
  score: number | null;
  section: string | number | null;
  page?: string | null;
  headers?: Record<string, string> | null;
  snippet?: string;
}

// Historie speichert die Quellen als <sources>[json]</sources> am Ende der Antwort.
function splitSources(content: string): { body: string; sources: SourceInfo[] } {
  const match = content.match(/\n*<sources>([\s\S]*?)<\/sources>\s*$/);
  if (!match) return { body: content, sources: [] };
  try {
    return { body: content.slice(0, match.index), sources: JSON.parse(match[1]) };
  } catch {
    return { body: content.slice(0, match.index), sources: [] };
  }
}

function SourcesBlock({ sources }: { sources: SourceInfo[] }) {
  return (
    <Collapsible className="mt-3 rounded-lg border border-border-base bg-surface-muted/60">
      <CollapsibleTrigger className="flex w-full items-center gap-2 px-3 py-2 text-xs font-medium text-muted-foreground">
        <ChevronRight className="size-3.5 transition-transform data-[state=open]:rotate-90" />
        Quellen ({sources.length})
      </CollapsibleTrigger>
      <CollapsibleContent>
        <ol className="space-y-1.5 px-3 pb-3 text-xs">
          {sources.map((src, i) => {
            const path = src.headers ? Object.values(src.headers).join(" › ") : "";
            return (
              <li key={i} id={`source-${src.n ?? i + 1}`} className="flex items-start gap-2">
                <span className="text-muted-foreground">[{src.n ?? i + 1}]</span>
                <div className="min-w-0 flex-1">
                  <span className="font-medium">{src.filename}</span>
                  {src.page ? (
                    <span className="text-muted-foreground"> · {src.page}</span>
                  ) : null}
                  {src.section != null ? (
                    <span className="text-muted-foreground"> · Abschnitt {src.section}</span>
                  ) : null}
                  {path ? <span className="text-muted-foreground"> · {path}</span> : null}
                  {src.snippet ? (
                    <p className="truncate text-muted-foreground" title={src.snippet}>
                      {src.snippet}
                    </p>
                  ) : null}
                </div>
                <span
                  className="shrink-0 rounded bg-background px-1.5 py-0.5 font-mono"
                  title="Score aus Suche und Neusortierung (höher = relevanter)"
                >
                  {src.score != null ? src.score.toFixed(3) : "–"}
                </span>
              </li>
            );
          })}
        </ol>
      </CollapsibleContent>
    </Collapsible>
  );
}

// Splits assistant content on  thinking...</think> blocks (history persists
// reasoning that way), returning reasoning text + remaining markdown.
function splitThink(content: string): { reasoning: string; body: string } {
  const match = content.match(/^<think>([\s\S]*?)<\/think>\s*/);
  if (match) {
    return { reasoning: match[1].trim(), body: content.slice(match[0].length) };
  }
  const unclosed = content.match(/^<think>([\s\S]*)$/);
  if (unclosed) {
    return { reasoning: unclosed[1].trim(), body: "" };
  }
  return { reasoning: "", body: content };
}

function ReasoningBlock({ text }: { text: string }) {
  const clean = text
    .replace(/\r\n/g, "\n")
    .replace(/\n{2,}/g, "\n")
    .replace(/^\n+|\n+$/g, "");
  return (
    <Collapsible className="mb-2 rounded-lg border border-border-base bg-surface-muted/60">
      <CollapsibleTrigger className="flex w-full items-center gap-2 px-3 py-2 text-xs font-medium text-muted-foreground">
        <ChevronRight className="size-3.5 transition-transform data-[state=open]:rotate-90" />
        Denken
      </CollapsibleTrigger>
      <CollapsibleContent>
        <pre className="mx-2 mb-2 whitespace-pre-wrap rounded bg-background p-3 text-xs text-foreground">
          {clean}
        </pre>
      </CollapsibleContent>
    </Collapsible>
  );
}

function ToolIndicator({ tool }: { tool: ToolCall }) {
  const meta = toolMeta(tool.name);
  const running = tool.status === "running";
  return (
    <div
      className={cn(
        "my-1 inline-flex w-fit items-center gap-2 rounded-full border px-3 py-1.5 text-xs",
        running
          ? "animate-pulse border-primary/50 text-foreground"
          : "border-green-500/50 text-green-600 dark:text-green-400",
      )}
    >
      {running ? meta.icon : <Check className="size-4" />}
      {meta.label} {running ? "läuft…" : "abgeschlossen"}
    </div>
  );
}

function CopyAnswer({ text }: { text: string }) {
  const [done, setDone] = useState(false);
  const copy = async () => {
    try {
      await copyText(text);
      setDone(true);
      setTimeout(() => setDone(false), 1500);
    } catch {
      toast.error("Kopieren nicht möglich");
    }
  };
  return (
    <button
      type="button"
      onClick={copy}
      className="mt-2 inline-flex items-center gap-1 rounded-md px-1.5 py-1 text-xs text-muted-foreground hover:bg-hover"
    >
      {done ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
      {done ? "Kopiert" : "Antwort kopieren"}
    </button>
  );
}

export function Message({
  role,
  content,
  reasoning,
  tools,
  toolResults,
  sources,
  streaming,
  dimmed,
  attachments,
  waiting,
}: MessageProps) {
  const [resultsOpen, setResultsOpen] = useState(false);
  const split = role === "assistant" ? splitSources(content) : { body: content, sources: [] };
  const parsed = role === "assistant" ? splitThink(split.body) : { reasoning: "", body: content };
  const shownSources = sources && sources.length > 0 ? sources : split.sources;
  const reasoningText = reasoning || parsed.reasoning;

  return (
    <div
      className={cn(
        // OpenAI-Stil: Nutzer als dezente Bubble rechts, Antworten als
        // Fließtext in voller Breite ohne Rahmen.
        role === "user"
          ? "max-w-[85%] self-end rounded-3xl bg-surface-muted px-4 py-2.5 text-foreground"
          : "w-full min-w-0 self-start rounded-2xl border border-border-base bg-surface px-4 py-3 text-foreground",
        dimmed && "opacity-70",
      )}
    >
      {attachments && attachments.length > 0 ? (
        <div className="mb-2 flex flex-wrap gap-1.5">
          {attachments.map((name) => (
            <span
              key={name}
              className="inline-flex max-w-60 items-center gap-1.5 rounded-lg border border-border-base bg-surface px-2 py-1 text-xs"
            >
              <FileText className="size-3.5 shrink-0 text-muted-foreground" />
              <span className="truncate">{name}</span>
            </span>
          ))}
        </div>
      ) : null}

      {reasoningText ? <ReasoningBlock text={reasoningText} /> : null}

      {tools?.map((tool, i) => <ToolIndicator key={i} tool={tool} />)}

      {toolResults && toolResults.length > 0 ? (
        <div className="my-2 text-sm">
          <button
            className="text-xs font-medium text-muted-foreground underline-offset-2 hover:underline"
            onClick={() => setResultsOpen((o) => !o)}
          >
            {resultsOpen ? "Tool-Ergebnisse ausblenden" : "Tool-Ergebnisse anzeigen"}
          </button>
          {resultsOpen
            ? toolResults.map((r, i) => (
                <pre
                  key={i}
                  className="mt-1 overflow-x-auto rounded bg-background p-2 text-xs"
                >
                  {`[${r.name}]\n${r.output}`}
                </pre>
              ))
            : null}
        </div>
      ) : null}

      {role === "assistant" ? (
        parsed.body ? (
          <Markdown content={parsed.body} sources={shownSources} streaming={streaming} />
        ) : waiting ? (
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" />
            {waiting}
          </p>
        ) : streaming ? (
          <div className="loading-dots">
            <span />
            <span />
            <span />
          </div>
        ) : null
      ) : (
        <p className="whitespace-pre-wrap">{content}</p>
      )}

      {role === "assistant" && shownSources.length > 0 ? (
        <SourcesBlock sources={shownSources} />
      ) : null}

      {role === "assistant" && parsed.body && !streaming ? (
        <CopyAnswer text={parsed.body} />
      ) : null}
    </div>
  );
}
