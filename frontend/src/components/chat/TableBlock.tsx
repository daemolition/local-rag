import { useState, type ReactNode } from "react";
import { Check, Copy, Download } from "lucide-react";
import { toast } from "sonner";
import { downloadText, tableRows, toCsv, toMarkdownTable, type HastNode } from "@/lib/hastText";
import { copyText } from "@/lib/utils";

// Tabelle in einem Scroll-Container mit fixiertem Kopf. Kopieren (Markdown) und CSV-Export
// erscheinen beim Ueberfahren.
export function TableBlock({ node, children }: { node?: HastNode; children: ReactNode }) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await copyText(toMarkdownTable(tableRows(node)));
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      toast.error("Kopieren nicht möglich");
    }
  };

  return (
    <div className="rag-table group">
      <div className="rag-table-actions">
        <button type="button" className="rag-code-btn" onClick={copy}>
          {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
          {copied ? "Kopiert" : "Kopieren"}
        </button>
        <button
          type="button"
          className="rag-code-btn"
          onClick={() => downloadText("tabelle.csv", toCsv(tableRows(node)))}
        >
          <Download className="size-3.5" />
          CSV
        </button>
      </div>
      <div className="rag-table-scroll">
        <table>{children}</table>
      </div>
    </div>
  );
}
