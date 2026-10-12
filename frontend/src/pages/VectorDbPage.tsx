import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ArrowLeft, Eye, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { api, errorMessage } from "@/lib/api";
import type { VectorListResponse } from "@/lib/types";

export function VectorDbPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const filename = searchParams.get("filename") ?? "";
  const limit = Number(searchParams.get("limit") ?? "20");
  const offset = searchParams.get("offset") ?? "";
  // Knowledge-Bereich (Query-Parameter "kb"); ohne Angabe der Standard-Bereich.
  const kb = searchParams.get("kb") ?? "";
  const kbQuery = kb ? `knowledge_id=${encodeURIComponent(kb)}` : "";

  const [data, setData] = useState<VectorListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [batchDelete, setBatchDelete] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      params.set("limit", String(limit));
      if (offset) params.set("offset", offset);
      if (filename) params.set("filename", filename);
      if (kb) params.set("knowledge_id", kb);
      const res = await api.get<VectorListResponse>(
        `/api/vectordb?${params.toString()}`,
      );
      setData(res);
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setLoading(false);
    }
  }, [filename, limit, offset, kb]);

  const [limitInput, setLimitInput] = useState(String(limit));

  useEffect(() => {
    setLimitInput(String(limit));
  }, [limit]);

  useEffect(() => {
    void load();
  }, [load]);

  const updateParams = (changes: Record<string, string | null>) => {
    const next = new URLSearchParams(searchParams);
    for (const [key, value] of Object.entries(changes)) {
      if (value === null || value === "") next.delete(key);
      else next.set(key, value);
    }
    // Reset offset whenever filters change.
    if (!("offset" in changes)) next.delete("offset");
    setSearchParams(next);
  };

  const applyLimit = () => {
    const parsed = Number(limitInput);
    const safe = Number.isFinite(parsed)
      ? Math.min(100, Math.max(10, parsed))
      : 20;
    setLimitInput(String(safe));
    updateParams({ limit: String(safe) });
  };

  const confirmDelete = async () => {
    if (!deleteId) return;
    try {
      await api.del(`/api/vectordb/${deleteId}${kbQuery ? `?${kbQuery}` : ""}`);
      toast.success("Dokument gelöscht");
      void load();
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setDeleteId(null);
    }
  };

  const confirmBatchDelete = async () => {
    if (!batchDelete) return;
    try {
      await api.post("/api/vectordb/batch-delete", {
        filename: batchDelete,
        knowledge_id: kb ? Number(kb) : undefined,
      });
      toast.success("Dokumente gelöscht");
      updateParams({ filename: null });
      void load();
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setBatchDelete(null);
    }
  };

  const documents = data?.documents ?? [];
  const filenames = data?.filenames ?? [];

  return (
    <div className="space-y-6 p-6">
      <Button variant="ghost" size="sm" asChild className="-ml-3">
        <Link to={kb ? `/knowledge/${kb}` : "/knowledge"}>
          <ArrowLeft className="size-4" />
          Zurück zum Knowledge
        </Link>
      </Button>
      <Card>
        <CardHeader className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <CardTitle>Vektordatenbank Dokumente</CardTitle>
          <div className="flex gap-2">
            <Select
              value={filename || "__all__"}
              onValueChange={(v) =>
                updateParams({ filename: v === "__all__" ? null : v })
              }
            >
              <SelectTrigger className="w-52">
                <SelectValue placeholder="Alle Dateien" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__all__">Alle Dateien</SelectItem>
                {filenames.map((fn) => (
                  <SelectItem key={fn} value={fn}>
                    {fn}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Input
              type="number"
              min={10}
              max={100}
              value={limitInput}
              onChange={(e) => setLimitInput(e.target.value)}
              onBlur={applyLimit}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  applyLimit();
                }
              }}
              className="w-20"
            />
          </div>
        </CardHeader>
        <CardContent>
          {loading ? (
            <p className="py-8 text-center text-muted-foreground">Lade…</p>
          ) : documents.length === 0 ? (
            <p className="py-8 text-center text-muted-foreground">
              Keine Dokumente gefunden.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>ID</TableHead>
                    <TableHead>Dateiname</TableHead>
                    <TableHead>Datei</TableHead>
                    <TableHead>Quelle</TableHead>
                    <TableHead>Inhalt (Vorschau)</TableHead>
                    <TableHead>Aktionen</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {documents.map((doc) => (
                    <TableRow key={doc.id}>
                      <TableCell className="font-mono text-xs text-muted-foreground">
                        {doc.id.slice(0, 8)}…
                      </TableCell>
                      <TableCell>{doc.filename}</TableCell>
                      <TableCell>
                        <span className="rounded-full bg-surface-muted px-2.5 py-1 text-xs">
                          {doc.has_data_file ? "Vorhanden" : "Keine Datei"}
                        </span>
                      </TableCell>
                      <TableCell
                        className="max-w-[14rem] truncate text-muted-foreground"
                        title={doc.source}
                      >
                        {doc.source}
                      </TableCell>
                      <TableCell
                        className="max-w-lg truncate text-muted-foreground"
                        title={doc.content_preview}
                      >
                        {doc.content_preview}
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <Button variant="outline" size="sm" asChild>
                            <Link to={`/vectordb/${doc.id}${kbQuery ? `?kb=${kb}` : ""}`}>
                              <Eye className="size-3.5" />
                              Ansehen
                            </Link>
                          </Button>
                          <Button
                            variant="destructive"
                            size="sm"
                            onClick={() => setDeleteId(doc.id)}
                          >
                            <Trash2 className="size-3.5" />
                            Löschen
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}

          <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
            <div>
              {filename ? (
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={() => setBatchDelete(filename)}
                >
                  <Trash2 className="size-4" />
                  Alle „{filename}" löschen
                </Button>
              ) : null}
            </div>
            {data?.next_offset ? (
              <Button
                variant="secondary"
                onClick={() =>
                  updateParams({ offset: String(data.next_offset) })
                }
              >
                Nächste Seite
              </Button>
            ) : null}
          </div>
        </CardContent>
      </Card>

      <ConfirmDialog
        open={deleteId !== null}
        onOpenChange={(o) => !o && setDeleteId(null)}
        title="Dokument löschen?"
        description="Dieses Dokument wird endgültig aus der Vektordatenbank gelöscht."
        confirmLabel="Löschen"
        destructive
        onConfirm={confirmDelete}
      />
      <ConfirmDialog
        open={batchDelete !== null}
        onOpenChange={(o) => !o && setBatchDelete(null)}
        title="Alle Dokumente löschen?"
        description={batchDelete ?? undefined}
        confirmLabel="Alle löschen"
        destructive
        onConfirm={confirmBatchDelete}
      />
    </div>
  );
}
