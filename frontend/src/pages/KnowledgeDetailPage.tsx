import { useCallback, useEffect, useRef, useState, type DragEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  ArrowLeft,
  Database,
  Download,
  FileSpreadsheet,
  FileText,
  FileCode,
  ListChecks,
  Loader2,
  Pencil,
  Share2,
  Trash2,
  Upload,
} from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { AccessDialog } from "@/components/AccessDialog";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { KnowledgeDialog } from "@/components/KnowledgeDialog";
import { DataFileDialog } from "@/components/DataFileDialog";
import { ExternalSourceDialog } from "@/components/ExternalSourceDialog";
import { SqlSourceDialog } from "@/components/SqlSourceDialog";
import { SqlValuesCard } from "@/components/SqlValuesCard";
import { KnowledgeIndexCard } from "@/components/KnowledgeIndexCard";
import type { ExternalSource, SqlSource } from "@/lib/types";
import { MarkdownDialog } from "@/components/MarkdownDialog";
import { ReindexProgress } from "@/components/ReindexProgress";
import { useAuth } from "@/context/AuthContext";
import { useIngestion } from "@/context/IngestionContext";
import { api, errorMessage } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { useReindex } from "@/lib/useReindex";
import { cn } from "@/lib/utils";
import type {
  AccessInfo,
  DataFile,
  Knowledge,
  RetrievalProfile,
  UserDocument,
} from "@/lib/types";

const ACCEPT = ".pdf,.docx,.doc,.odt,.md,.xlsx,.xls,.csv";

export function KnowledgeDetailPage() {
  const { id = "" } = useParams();
  const kb = `knowledge_id=${encodeURIComponent(id)}`;
  const navigate = useNavigate();
  const { isIngesting } = useIngestion();
  const { hasRole } = useAuth();

  const [knowledge, setKnowledge] = useState<Knowledge | null>(null);
  const [documents, setDocuments] = useState<UserDocument[]>([]);
  const [dataFiles, setDataFiles] = useState<DataFile[]>([]);
  const [pending, setPending] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [dragging, setDragging] = useState(false);
  const [ingesting, setIngesting] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [accessOpen, setAccessOpen] = useState(false);
  const [markdownDoc, setMarkdownDoc] = useState<UserDocument | null>(null);
  const [viewData, setViewData] = useState<string | null>(null);
  const [sourceOpen, setSourceOpen] = useState(false);
  const [profiles, setProfiles] = useState<RetrievalProfile[]>([]);
  const [deleteKb, setDeleteKb] = useState(false);
  const [deleteDoc, setDeleteDoc] = useState<UserDocument | null>(null);
  const [deleteData, setDeleteData] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    try {
      const [k, docs, data] = await Promise.all([
        api.get<Knowledge>(`/api/knowledge/${id}`),
        api.get<UserDocument[]>(`/api/documents?${kb}`),
        api.get<DataFile[]>(`/api/data-files?${kb}`),
      ]);
      setKnowledge(k);
      setDocuments(docs);
      setDataFiles(data);
    } catch (e) {
      toast.error(errorMessage(e));
      navigate("/knowledge", { replace: true });
    } finally {
      setLoading(false);
    }
  }, [id, kb, navigate]);

  const { status: reindex, refresh: refreshReindex } = useReindex(() => void load());
  const reindexing = reindex.running && (reindex.current?.id === Number(id) || reindex.queue.includes(Number(id)));

  const startReindex = async () => {
    try {
      await api.post(`/api/knowledge/${id}/reindex`);
      await refreshReindex();
    } catch (e) {
      toast.error(errorMessage(e));
    }
  };

  useEffect(() => {
    setLoading(true);
    setPending([]);
    void load();
  }, [load]);

  useEffect(() => {
    api
      .get<RetrievalProfile[]>("/api/retrieval/profiles")
      .then(setProfiles)
      .catch(() => setProfiles([]));
  }, []);

  const changeProfile = async (value: string) => {
    const profileId = value === "default" ? null : Number(value);
    try {
      await api.put(`/api/knowledge/${id}/retrieval-profile`, { profile_id: profileId });
      setKnowledge((k) => (k ? { ...k, retrieval_profile_id: profileId } : k));
      toast.success("Profil gewechselt, wirkt sofort");
    } catch (e) {
      toast.error(errorMessage(e));
    }
  };

  const upload = async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    const form = new FormData();
    for (let i = 0; i < files.length; i++) form.append("files", files[i]);
    try {
      const data = await api.post<{
        success: boolean;
        documents?: string[];
        data_files?: string[];
        skipped?: string[];
        message?: string;
        error?: string;
      }>(`/api/documents/upload?${kb}`, form);
      if (!data.success) {
        toast.error(data.error || "Fehler beim Hochladen");
        return;
      }
      setPending((prev) => [...prev, ...(data.documents || [])]);
      if (data.data_files?.length) await load();
      if (data.message) toast.success(data.message);
      if (data.skipped?.length) {
        toast.warning(`Übersprungen (nicht unterstützt): ${data.skipped.join(", ")}`);
      }
    } catch (e) {
      toast.error(errorMessage(e));
    }
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    void upload(e.dataTransfer.files);
  };

  const ingest = async () => {
    setIngesting(true);
    try {
      const res = await api.post<{
        processed: number;
        errors: { file: string; error: string }[];
        warnings: string[];
      }>(`/api/documents/ingest?${kb}`);
      if (res.errors.length === 0) {
        toast.success(`${res.processed} Dokument(e) verarbeitet`);
      } else {
        toast.warning(`${res.processed} verarbeitet, ${res.errors.length} fehlgeschlagen`);
      }
      // Fehler pro Datei sichtbar machen (Datei bleibt im Eingang und kann erneut eingelesen werden)
      for (const err of res.errors) toast.error(`${err.file}: ${err.error}`, { duration: 15000 });
      for (const w of res.warnings) toast.warning(w, { duration: 12000 });
      setPending([]);
      await load();
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setIngesting(false);
    }
  };

  const rename = async (values: { name: string; description: string }) => {
    try {
      setKnowledge(await api.patch<Knowledge>(`/api/knowledge/${id}`, values));
    } catch (e) {
      toast.error(errorMessage(e));
      throw e;
    }
  };

  const removeKnowledge = async () => {
    try {
      await api.del(`/api/knowledge/${id}`);
      toast.success("Knowledge gelöscht");
      navigate("/knowledge", { replace: true });
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setDeleteKb(false);
    }
  };

  const removeDocument = async () => {
    if (!deleteDoc) return;
    try {
      await api.del(`/api/documents/${deleteDoc.id}`);
      setDocuments((d) => d.filter((x) => x.id !== deleteDoc.id));
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setDeleteDoc(null);
    }
  };

  const removeDataFile = async () => {
    if (!deleteData) return;
    try {
      await api.del(`/api/data-files/${encodeURIComponent(deleteData)}?${kb}`);
      setDataFiles((d) => d.filter((x) => x.filename !== deleteData));
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setDeleteData(null);
    }
  };

  if (loading || !knowledge) {
    return <p className="p-6 text-muted-foreground">Lade…</p>;
  }

  const busy = ingesting || isIngesting;
  const external = knowledge.kind === "external";
  const sql = knowledge.kind === "sql";
  // Fremde Quellen (Vektorspeicher, SQL) sind schreibgeschützt und haben keine eigenen Dokumente
  const remote = external || sql;
  const sqlSource = sql ? (knowledge.source_config as SqlSource | undefined) : undefined;
  const extSource = external ? (knowledge.source_config as ExternalSource | undefined) : undefined;
  const isAdmin = hasRole("admin");
  // Externe Quellen sind schreibgeschützt: kein Upload, Einlesen, Löschen oder Neu-Indexieren
  const canWrite = knowledge.can_write && !remote;
  const activeProfile = profiles.find(
    (p) => p.id === (knowledge.retrieval_profile_id ?? profiles.find((x) => x.is_default)?.id),
  );

  return (
    <div className="h-full overflow-y-auto">
      <div className="w-full space-y-6 p-6">
        <div className="space-y-3 border-b border-border-base pb-4">
          <Button variant="ghost" size="sm" asChild className="-ml-3">
            <Link to="/knowledge">
              <ArrowLeft className="size-4" />
              Alle Knowledge
            </Link>
          </Button>
          {knowledge.stale && !reindexing ? (
            <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-amber-500/50 bg-amber-500/10 px-3 py-2 text-sm">
              <span>
                Index veraltet: Modell oder Zerlege-Einstellungen wurden geändert. Die Suche
                funktioniert weiter, nutzt aber noch den alten Index.
                {knowledge.last_reindex_error ? (
                  <span className="block text-destructive">
                    Letzter Fehler: {knowledge.last_reindex_error}
                  </span>
                ) : null}
              </span>
              {knowledge.can_write ? (
                <Button size="sm" onClick={() => void startReindex()} disabled={reindex.running}>
                  Neu indexieren
                </Button>
              ) : null}
            </div>
          ) : null}
          {reindexing ? <ReindexProgress status={reindex} /> : null}
          <div className="flex flex-col items-start justify-between gap-3 sm:flex-row sm:items-center">
            <div className="min-w-0">
              <h1 className="truncate text-2xl font-semibold">{knowledge.name}</h1>
              <p className="text-sm text-muted-foreground">
                {knowledge.description || "Keine Beschreibung"}
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                Collection <code>{knowledge.collection_name}</code>
                {knowledge.embedding_model
                  ? ` · ${knowledge.embedding_model}`
                  : ""}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              {remote ? null : (
                <Button variant="secondary" size="sm" asChild>
                  <Link to={`/vectordb?kb=${knowledge.id}`}>
                    <Database className="size-4" />
                    Vektoren ansehen
                  </Link>
                </Button>
              )}
              {remote && isAdmin ? (
                <Button variant="secondary" size="sm" onClick={() => setSourceOpen(true)}>
                  <Pencil className="size-4" />
                  Quelle bearbeiten
                </Button>
              ) : null}
              {knowledge.can_write && hasRole("editor") ? (
                <Button variant="secondary" size="sm" onClick={() => setAccessOpen(true)}>
                  <Share2 className="size-4" />
                  Freigaben
                </Button>
              ) : null}
              {knowledge.can_write && !knowledge.is_default ? (
                <>
                  <Button variant="secondary" size="sm" onClick={() => setEditOpen(true)}>
                    <Pencil className="size-4" />
                    Bearbeiten
                  </Button>
                  <Button variant="destructive" size="sm" onClick={() => setDeleteKb(true)}>
                    <Trash2 className="size-4" />
                    Löschen
                  </Button>
                </>
              ) : null}
            </div>
          </div>
        </div>

        {/* Standardmäßig eingeklappt: Der Standard ist die empfohlene Strategie und
            funktioniert ohne Zutun. Wechseln ist nur für Sonderfälle gedacht. */}
        <details className="rounded-xl border border-border-base px-4 py-3">
          <summary className="cursor-pointer text-sm font-medium">
            Erweitert: Suchstrategie
            <span className="ml-2 font-normal text-muted-foreground">
              {activeProfile?.name ?? "Standard"}
            </span>
          </summary>
          <div className="mt-3 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-xs text-muted-foreground">
              {activeProfile?.description || "Wie die passenden Textstellen gesucht werden."} Ein
              Wechsel wirkt sofort, ein erneutes Einlesen ist nicht nötig.
            </p>
            <Select
              value={
                knowledge.retrieval_profile_id === null
                  ? "default"
                  : String(knowledge.retrieval_profile_id)
              }
              onValueChange={(v) => void changeProfile(v)}
              disabled={!canWrite || profiles.length === 0}
            >
              <SelectTrigger className="w-full sm:w-64">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="default">
                  {profiles.find((p) => p.is_default)?.name ?? "Standard"} (empfohlen)
                </SelectItem>
                {profiles
                  .filter((p) => !p.is_default)
                  .map((p) => (
                    <SelectItem key={p.id} value={String(p.id)}>
                      {p.name}
                    </SelectItem>
                  ))}
              </SelectContent>
            </Select>
          </div>
        </details>

        {canWrite ? (
          <>
        <div
          onClick={() => inputRef.current?.click()}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          className={cn(
            "cursor-pointer rounded-2xl border-2 border-dashed border-border-base p-8 text-center transition-colors",
            dragging && "border-border-strong bg-surface-subtle",
          )}
        >
          <Upload className="mx-auto mb-3 size-8 text-muted-foreground" />
          <p className="mb-1 text-muted-foreground">
            Dateien hierher ziehen oder klicken zum Auswählen
          </p>
          <p className="text-sm text-muted-foreground">
            PDF, DOCX, DOC, ODT, MD (Vektoren) | XLSX, XLS, CSV (Pandas-Referenz)
          </p>
          <input
            ref={inputRef}
            type="file"
            multiple
            accept={ACCEPT}
            className="hidden"
            onChange={(e) => {
              void upload(e.target.files);
              e.target.value = "";
            }}
          />
        </div>

        {pending.length > 0 ? (
          <Card>
            <CardContent className="space-y-3 p-4">
              <h2 className="flex items-center gap-2 text-sm font-semibold">
                <ListChecks className="size-4" />
                Warten auf Verarbeitung ({pending.length})
              </h2>
              <ul className="space-y-1 text-sm text-muted-foreground">
                {pending.map((f) => (
                  <li key={f} className="truncate">
                    {f}
                  </li>
                ))}
              </ul>
              <Button onClick={ingest} disabled={busy}>
                {busy ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  <ListChecks className="size-4" />
                )}
                {busy ? "Verarbeitung läuft…" : "Jetzt verarbeiten"}
              </Button>
            </CardContent>
          </Card>
        ) : null}

          </>
        ) : (
          <p className="rounded-lg border border-border-base bg-surface-subtle px-4 py-3 text-sm text-muted-foreground">
            {external
              ? `Externe Quelle (nur lesen): ${extSource?.url ?? ""} · Collection „${extSource?.collection ?? ""}“. Sie wird bei jeder Frage live abgefragt und nie verändert.`
              : sql
                ? `SQL-Datenbank (nur lesen): ${sqlSource?.dialect === "sqlite" ? sqlSource.database : `${sqlSource?.host ?? ""}${sqlSource?.instance ? `\\${sqlSource.instance}` : ""} · ${sqlSource?.database ?? ""}`}. Das Modell fragt sie bei jeder Frage live ab; es werden keine Daten kopiert.`
                : "Du hast nur Leserechte auf dieses Knowledge."}
          </p>
        )}

        {sql && isAdmin ? <SqlValuesCard knowledgeId={knowledge.id} /> : null}

        {remote ? null : (
          <>
        <KnowledgeIndexCard knowledgeId={knowledge.id} canWrite={canWrite} refreshKey={documents} />

        <section className="space-y-3">
          <h2 className="flex items-center gap-2 text-lg font-semibold">
            <FileText className="size-5" />
            Dokumente
            <span className="rounded-full bg-surface-muted px-2 py-0.5 text-xs font-normal text-muted-foreground">
              {documents.length}
            </span>
          </h2>
          {documents.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Noch keine verarbeiteten Dokumente.
            </p>
          ) : (
            <Card>
              <CardContent className="p-0">
                {documents.map((doc) => (
                  <div
                    key={doc.id}
                    className="flex items-center gap-3 border-b border-border-base px-4 py-3 transition-colors last:border-0 hover:bg-hover/40"
                  >
                    <FileText className="size-4 shrink-0 text-muted-foreground" />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium">{doc.filename}</p>
                      <p className="line-clamp-1 text-xs text-muted-foreground">
                        {formatDateTime(doc.uploaded_at)} · {doc.content_preview}
                      </p>
                    </div>
                    {doc.has_markdown ? (
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        title="Markdown ansehen"
                        onClick={() => setMarkdownDoc(doc)}
                      >
                        <FileCode className="size-4" />
                      </Button>
                    ) : null}
                    {canWrite ? (
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        title="Dokument löschen"
                        onClick={() => setDeleteDoc(doc)}
                      >
                        <Trash2 className="size-4" />
                      </Button>
                    ) : null}
                  </div>
                ))}
              </CardContent>
            </Card>
          )}
        </section>

        <section className="space-y-3">
          <h2 className="flex items-center gap-2 text-lg font-semibold">
            <FileSpreadsheet className="size-5" />
            Strukturierte Daten
            <span className="rounded-full bg-surface-muted px-2 py-0.5 text-xs font-normal text-muted-foreground">
              {dataFiles.length}
            </span>
          </h2>
          {dataFiles.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Excel/CSV liegen als Referenz für die Pandas-Analyse bereit, nicht
              als Vektoren.
            </p>
          ) : (
            <Card>
              <CardContent className="p-0">
                {dataFiles.map((f) => (
                  <div
                    key={f.filename}
                    className="flex items-center gap-3 border-b border-border-base px-4 py-3 transition-colors last:border-0 hover:bg-hover/40"
                  >
                    <FileSpreadsheet className="size-4 shrink-0 text-muted-foreground" />
                    <span className="min-w-0 flex-1 truncate text-sm">{f.filename}</span>
                    <span className="shrink-0 text-xs text-muted-foreground">
                      {f.size_human}
                    </span>
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => setViewData(f.filename)}
                    >
                      Ansehen
                    </Button>
                    <Button variant="ghost" size="icon-sm" title="Herunterladen" asChild>
                      <a href={`/api/data-files/${encodeURIComponent(f.filename)}?download=1&${kb}`}>
                        <Download className="size-4" />
                      </a>
                    </Button>
                    {canWrite ? (
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        title="Datei löschen"
                        onClick={() => setDeleteData(f.filename)}
                      >
                        <Trash2 className="size-4" />
                      </Button>
                    ) : null}
                  </div>
                ))}
              </CardContent>
            </Card>
          )}
        </section>
          </>
        )}
      </div>

      <ExternalSourceDialog
        open={sourceOpen && external}
        onOpenChange={setSourceOpen}
        existing={external ? knowledge : null}
        onSaved={() => void load()}
      />
      <SqlSourceDialog
        open={sourceOpen && sql}
        onOpenChange={setSourceOpen}
        existing={sql ? knowledge : null}
        onSaved={() => void load()}
      />
      <DataFileDialog
        filename={viewData}
        knowledgeQuery={kb}
        onOpenChange={(o) => !o && setViewData(null)}
      />
      <MarkdownDialog document={markdownDoc} onOpenChange={(o) => !o && setMarkdownDoc(null)} />
      <AccessDialog
        open={accessOpen}
        onOpenChange={setAccessOpen}
        title="Freigaben"
        description={`Wer darf „${knowledge.name}“ nutzen oder verwalten?`}
        publicLabel="Für alle angemeldeten Nutzer lesbar"
        readLabel="Nutzen"
        allowWrite
        load={() => api.get<AccessInfo>(`/api/knowledge/${id}/access`)}
        save={async (info) => {
          const saved = await api.put<AccessInfo>(`/api/knowledge/${id}/access`, info);
          setKnowledge((k) => (k ? { ...k, is_public: saved.is_public } : k));
          return saved;
        }}
      />
      <KnowledgeDialog
        open={editOpen}
        onOpenChange={setEditOpen}
        title="Knowledge bearbeiten"
        confirmLabel="Speichern"
        initial={{ name: knowledge.name, description: knowledge.description }}
        onSubmit={rename}
      />
      <ConfirmDialog
        open={deleteKb}
        onOpenChange={setDeleteKb}
        title="Knowledge löschen?"
        description={`„${knowledge.name}“ samt Vektoren und Dateien wird endgültig gelöscht.`}
        confirmLabel="Löschen"
        destructive
        onConfirm={removeKnowledge}
      />
      <ConfirmDialog
        open={deleteDoc !== null}
        onOpenChange={(o) => !o && setDeleteDoc(null)}
        title="Dokument löschen?"
        description={deleteDoc?.filename}
        confirmLabel="Löschen"
        destructive
        onConfirm={removeDocument}
      />
      <ConfirmDialog
        open={deleteData !== null}
        onOpenChange={(o) => !o && setDeleteData(null)}
        title="Datei löschen?"
        description={deleteData ?? undefined}
        confirmLabel="Löschen"
        destructive
        onConfirm={removeDataFile}
      />
    </div>
  );
}
