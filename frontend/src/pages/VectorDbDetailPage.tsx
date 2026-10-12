import { useEffect, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { ArrowLeft, Copy, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { Markdown } from "@/components/Markdown";
import { api, errorMessage } from "@/lib/api";
import { copyText } from "@/lib/utils";
import type { VectorDocumentDetail } from "@/lib/types";

export function VectorDbDetailPage() {
  const { docId = "" } = useParams();
  const navigate = useNavigate();
  const kb = useSearchParams()[0].get("kb") ?? "";
  const kbQuery = kb ? `knowledge_id=${encodeURIComponent(kb)}` : "";
  const listPath = `/vectordb${kb ? `?kb=${kb}` : ""}`;
  const [document, setDocument] = useState<VectorDocumentDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [deleteOpen, setDeleteOpen] = useState(false);

  useEffect(() => {
    api
      .get<VectorDocumentDetail>(`/api/vectordb/${docId}${kbQuery ? `?${kbQuery}` : ""}`)
      .then(setDocument)
      .catch((e) => setError(errorMessage(e)));
  }, [docId, kbQuery]);

  const copy = async (text: string) => {
    try {
      await copyText(text);
      toast.success("Inhalt kopiert");
    } catch {
      toast.error("Kopieren fehlgeschlagen");
    }
  };

  const confirmDelete = async () => {
    try {
      await api.del(`/api/vectordb/${docId}${kbQuery ? `?${kbQuery}` : ""}`);
      toast.success("Dokument gelöscht");
      navigate(listPath);
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setDeleteOpen(false);
    }
  };

  if (error) {
    return (
      <div className="space-y-6 p-6">
        <p className="text-muted-foreground">{error}</p>
        <Button variant="secondary" className="mt-4" asChild>
          <Link to={listPath}>Zurück zur Liste</Link>
        </Button>
      </div>
    );
  }

  if (!document) {
    return <div className="p-6 text-muted-foreground">Lade…</div>;
  }

  return (
    <div className="space-y-6 p-6">
      <Button variant="ghost" size="sm" asChild className="-ml-3">
        <Link to={listPath}>
          <ArrowLeft className="size-4" />
          Zurück zur Liste
        </Link>
      </Button>
      <Card>
        <CardHeader className="flex flex-row items-center justify-between gap-4">
          <CardTitle>Dokument-Informationen</CardTitle>
          <span className="rounded-lg bg-surface-muted px-3 py-1.5 font-mono text-xs">
            {document.id.slice(0, 8)}…
          </span>
        </CardHeader>
        <CardContent>
          <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {Object.entries(document.metadata).map(([key, value]) => (
              <div key={key} className="rounded-xl bg-surface-subtle p-4">
                <div className="mb-1 text-xs uppercase tracking-wider text-muted-foreground">
                  {key}
                </div>
                <div className="break-all text-sm">{String(value)}</div>
              </div>
            ))}
          </div>
          <div className="flex flex-wrap gap-3">
            <Button variant="secondary" asChild>
              <Link to={listPath}>
                <ArrowLeft className="size-4" />
                Zurück
              </Link>
            </Button>
            <Button variant="destructive" onClick={() => setDeleteOpen(true)}>
              <Trash2 className="size-4" />
              Dokument löschen
            </Button>
          </div>
        </CardContent>
      </Card>

      {document.page_content ? (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>Kontext-angereicherter Inhalt</CardTitle>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => copy(document.page_content)}
            >
              <Copy className="size-3.5" />
              Kopieren
            </Button>
          </CardHeader>
          <CardContent>
            <div className="max-h-96 overflow-y-auto rounded-xl border border-border-base bg-surface-subtle p-4">
              <Markdown content={document.page_content} />
            </div>
          </CardContent>
        </Card>
      ) : null}

      {document.original_content ? (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>Original-Inhalt</CardTitle>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => copy(document.original_content)}
            >
              <Copy className="size-3.5" />
              Kopieren
            </Button>
          </CardHeader>
          <CardContent>
            <div className="max-h-96 overflow-y-auto rounded-xl border border-border-base bg-surface-subtle p-4">
              <Markdown content={document.original_content} />
            </div>
          </CardContent>
        </Card>
      ) : null}

      <ConfirmDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        title="Dokument löschen?"
        description="Dieses Dokument wird endgültig aus der Vektordatenbank gelöscht. Diese Aktion kann nicht rückgängig gemacht werden."
        confirmLabel="Löschen"
        destructive
        onConfirm={confirmDelete}
      />
    </div>
  );
}
