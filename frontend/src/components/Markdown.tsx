import { memo, useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeSanitize from "rehype-sanitize";
import rehypeHighlight from "rehype-highlight";
import { common } from "lowlight";
import dockerfile from "highlight.js/lib/languages/dockerfile";
import { CodeBlock } from "@/components/chat/CodeBlock";
import { TableBlock } from "@/components/chat/TableBlock";
import { codeLanguage, nodeText, type HastNode } from "@/lib/hastText";

// Sanitizer zuerst, Highlighting danach: sonst entfernt der Sanitizer die hljs-Klassen.
// Unbekannte Sprachen bleiben ohne Farben (kein Raten).
const HIGHLIGHT = { detect: false, plainText: ["text", "txt", "plaintext"], languages: { ...common, dockerfile } };

export interface CitationSource {
  n?: number;
  filename: string;
  score: number | null;
  section: string | number | null;
  page?: string | null;
}

// "[2]" im Antworttext wird zum Link #src-2 (ausser in Codebloecken und echten Links).
function linkCitations(content: string, known: Set<number>): string {
  return content
    .split(/(```[\s\S]*?```)/g)
    .map((part, i) =>
      i % 2 === 1
        ? part
        : part.replace(/\[(\d{1,3})\](?![(:\[])/g, (m, d) =>
            known.has(Number(d)) ? `[${d}](#src-${d})` : m,
          ),
    )
    .join("");
}

// Beim Streamen hoechstens einmal pro Bildwiederholung neu rendern (lange Antworten bleiben flüssig).
function useFrameThrottled(value: string, active: boolean): string {
  const [shown, setShown] = useState(value);
  const latest = useRef(value);
  latest.current = value;
  useEffect(() => {
    if (!active) {
      setShown(value);
      return;
    }
    const id = requestAnimationFrame(() => setShown(latest.current));
    return () => cancelAnimationFrame(id);
  }, [value, active]);
  return active ? shown : value;
}

// Renders assistant markdown safely (GFM tables/strikethrough, sanitized HTML).
// Mit ``sources`` werden Quellennummern wie [2] als Marker direkt im Satz gezeigt.
export const Markdown = memo(function Markdown({
  content: rawContent,
  sources,
  streaming = false,
}: {
  content: string;
  sources?: CitationSource[];
  streaming?: boolean;
}) {
  const content = useFrameThrottled(rawContent, streaming);
  const byNumber = useMemo(() => {
    const map = new Map<number, CitationSource>();
    (sources ?? []).forEach((src, i) => map.set(src.n ?? i + 1, src));
    return map;
  }, [sources]);
  const text = useMemo(
    () => (byNumber.size ? linkCitations(content, new Set(byNumber.keys())) : content),
    [content, byNumber],
  );

  return (
    <div className="rag-prose">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeSanitize, [rehypeHighlight, HIGHLIGHT]]}
        components={{
          pre: ({ node, children }) => {
            const code = (node as HastNode | undefined)?.children?.find((c) => c.tagName === "code");
            return (
              <CodeBlock language={codeLanguage(code)} text={nodeText(code)} streaming={streaming}>
                {children}
              </CodeBlock>
            );
          },
          table: ({ node, children }) => <TableBlock node={node as HastNode | undefined}>{children}</TableBlock>,
          a: ({ node: _node, href, children, ...props }) => {
            const match = href?.match(/^#src-(\d+)$/);
            if (match) {
              const src = byNumber.get(Number(match[1]));
              const where = [src?.page, src?.section != null ? `Abschnitt ${src.section}` : null]
                .filter(Boolean)
                .map((x) => `, ${x}`)
                .join("");
              const score = src?.score != null ? ` · Score ${src.score.toFixed(3)}` : "";
              return (
                <sup>
                  <a
                    href={href}
                    onClick={(e) => {
                      e.preventDefault();
                      document
                        .getElementById(`source-${match[1]}`)
                        ?.scrollIntoView({ behavior: "smooth", block: "center" });
                    }}
                    title={src ? `${src.filename}${where}${score}` : undefined}
                    className="mx-0.5 rounded bg-surface-muted px-1 text-[0.7rem] font-medium text-primary no-underline hover:bg-border-base"
                  >
                    {children}
                  </a>
                </sup>
              );
            }
            return <a {...props} href={href} target="_blank" rel="noreferrer noopener">{children}</a>;
          },
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
});
