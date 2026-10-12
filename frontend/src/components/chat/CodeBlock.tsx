import { useState, type ReactNode } from "react";
import { Check, ChevronDown, ChevronRight, Copy, WrapText } from "lucide-react";
import { toast } from "sonner";
import { copyText, cn } from "@/lib/utils";

const FOLD_LINES = 25;

interface CodeBlockProps {
  language: string;
  text: string;
  streaming?: boolean;
  children: ReactNode;
}

// Codeblock mit Kopfzeile (Sprache, Umbrechen, Falten, Kopieren). Der Kopf bleibt beim Scrollen
// durch lange Bloecke (z. B. grosse SQL-Abfragen) sichtbar.
export function CodeBlock({ language, text, streaming, children }: CodeBlockProps) {
  const lines = text.replace(/\n$/, "").split("\n").length;
  const foldable = !streaming && lines > FOLD_LINES;
  const [folded, setFolded] = useState(foldable);
  const [wrap, setWrap] = useState(false);
  const [copied, setCopied] = useState(false);
  // Die Faltung gilt erst, wenn der Block fertig ist (waehrend des Streamens waechst er noch).
  const isFolded = foldable && folded;

  const copy = async () => {
    try {
      await copyText(text.replace(/\n$/, ""));
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      toast.error("Kopieren nicht möglich");
    }
  };

  return (
    <div className="rag-code">
      <div className="rag-code-head">
        <span className="truncate font-mono text-xs">{language || "text"}</span>
        <div className="flex shrink-0 items-center gap-0.5">
          <button
            type="button"
            className={cn("rag-code-btn", wrap && "bg-hover")}
            onClick={() => setWrap((w) => !w)}
            title="Zeilen umbrechen"
            aria-pressed={wrap}
          >
            <WrapText className="size-3.5" />
          </button>
          {foldable ? (
            <button type="button" className="rag-code-btn" onClick={() => setFolded((f) => !f)}>
              {isFolded ? <ChevronRight className="size-3.5" /> : <ChevronDown className="size-3.5" />}
              {isFolded ? "Ausklappen" : "Einklappen"}
            </button>
          ) : null}
          <button type="button" className="rag-code-btn" onClick={copy}>
            {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
            {copied ? "Kopiert" : "Kopieren"}
          </button>
        </div>
      </div>
      {isFolded ? (
        <button type="button" className="rag-code-folded" onClick={() => setFolded(false)}>
          {lines} Zeilen eingeklappt
        </button>
      ) : (
        <pre className={cn(wrap && "rag-code-wrap")}>{children}</pre>
      )}
    </div>
  );
}
