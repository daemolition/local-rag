// Kleine Helfer fuer Markdown-Bausteine: Text und Tabellen aus dem hast-Baum lesen.
export interface HastNode {
  type: string;
  tagName?: string;
  value?: string;
  properties?: { className?: string[] | string };
  children?: HastNode[];
}

/** Gesamter Text eines Knotens (ohne Markup). */
export function nodeText(node: HastNode | undefined): string {
  if (!node) return "";
  if (node.type === "text") return node.value ?? "";
  return (node.children ?? []).map(nodeText).join("");
}

/** Sprache eines Codeblocks aus der Klasse ``language-xyz`` (leer, wenn keine). */
export function codeLanguage(code: HastNode | undefined): string {
  const raw = code?.properties?.className;
  const classes = Array.isArray(raw) ? raw : raw ? String(raw).split(/\s+/) : [];
  const hit = classes.find((c) => c.startsWith("language-"));
  return hit ? hit.slice("language-".length) : "";
}

/** Zeilen einer Tabelle als Zellentexte (Kopf zuerst). */
export function tableRows(table: HastNode | undefined): string[][] {
  const rows: string[][] = [];
  const walk = (n: HastNode) => {
    if (n.type !== "element") return;
    if (n.tagName === "tr") {
      rows.push(
        (n.children ?? [])
          .filter((c) => c.type === "element" && (c.tagName === "th" || c.tagName === "td"))
          .map((c) => nodeText(c).replace(/\s+/g, " ").trim()),
      );
      return;
    }
    (n.children ?? []).forEach(walk);
  };
  if (table) walk(table);
  return rows;
}

/** CSV (Semikolon-frei, RFC 4180) mit Anfuehrungszeichen-Maskierung. */
export function toCsv(rows: string[][]): string {
  const cell = (v: string) => (/[",\r\n]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v);
  return rows.map((r) => r.map(cell).join(",")).join("\r\n");
}

/** Markdown-Tabelle fuer die Zwischenablage. */
export function toMarkdownTable(rows: string[][]): string {
  if (rows.length === 0) return "";
  const esc = (v: string) => v.replace(/\|/g, "\\|");
  const line = (r: string[]) => `| ${r.map(esc).join(" | ")} |`;
  const [head, ...body] = rows;
  return [line(head), line(head.map(() => "---")), ...body.map(line)].join("\n");
}

/** Laedt Text als Datei herunter (UTF-8 mit BOM, damit Excel Umlaute richtig liest). */
export function downloadText(filename: string, text: string, mime = "text/csv"): void {
  const blob = new Blob(["﻿", text], { type: `${mime};charset=utf-8` });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
