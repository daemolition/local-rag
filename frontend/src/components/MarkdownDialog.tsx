import { useEffect, useState } from "react";
import { Download, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { api, errorMessage } from "@/lib/api";
import type { UserDocument } from "@/lib/types";

// Zeigt das Markdown, aus dem ein Dokument indexiert wurde: macht sichtbar, was der
// Parser aus PDF/Word gemacht hat (Überschriften, Tabellen, Bildbeschreibungen).
export function MarkdownDialog({
  document,
  source,
  onOpenChange,
}: {
  document?: UserDocument | null;
  // Alternativ zu ``document``: beliebige Markdown-Quelle (z. B. "Meine Uploads")
  source?: { title: string; url: string } | null;
  onOpenChange: (open: boolean) => void;
}) {
  const target = source ?? (document ? { title: document.filename, url: `/api/documents/${document.id}/markdown` } : null);
  const [text, setText] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!target) return;
    setText(null);
    setError(null);
    let active = true;
    api
      .get<{ markdown: string }>(target.url)
      .then((r) => active && setText(r.markdown))
      .catch((e) => active && setError(errorMessage(e)));
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target?.url]);

  return (
    <Dialog open={target !== null} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[90vh] flex-col sm:max-w-4xl">
        <DialogHeader>
          <DialogTitle>Markdown: {target?.title}</DialogTitle>
          <DialogDescription>
            So sieht die Suche das Dokument. Überschriften bestimmen die Abschnitte,
            Tabellen stehen als Markdown oder als Verweis auf eine CSV-Datei.
          </DialogDescription>
        </DialogHeader>

        <div className="min-h-0 flex-1 overflow-auto rounded-lg border border-border-base bg-surface-subtle p-3">
          {error ? (
            <p className="text-sm text-muted-foreground">{error}</p>
          ) : text === null ? (
            <p className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin" />
              Lade…
            </p>
          ) : (
            <pre className="whitespace-pre-wrap break-words font-mono text-xs">{text}</pre>
          )}
        </div>

        {target && text !== null ? (
          <div className="flex justify-end">
            <Button variant="secondary" size="sm" asChild>
              <a href={`${target.url}?download=1`}>
                <Download className="size-4" />
                Herunterladen
              </a>
            </Button>
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
