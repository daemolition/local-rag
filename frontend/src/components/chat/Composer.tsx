import { useCallback, useEffect, useRef, useState, type DragEvent, type FormEvent } from "react";
import { ArrowUp, FileText, Loader2, Mic, Paperclip, Square, TriangleAlert, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { KnowledgePicker } from "@/components/chat/KnowledgePicker";
import { ModelPicker } from "@/components/chat/ModelPicker";
import { cn } from "@/lib/utils";
import type { ChatAttachment, Knowledge, ModelEntry } from "@/lib/types";

export const ATTACH_ACCEPT = ".pdf,.docx,.doc,.odt,.md";

interface ComposerProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  onStop: () => void;
  streaming: boolean;
  attachments: ChatAttachment[];
  onAttach: (files: File[]) => void;
  onRemoveAttachment: (id: string) => void;
  knowledge: Knowledge[];
  selectedKnowledge: number[] | null;
  onSelectKnowledge: (ids: number[] | null) => void;
  // Das gewählte Modell bringt eigenes Knowledge mit: Auswahl hier wirkungslos.
  knowledgeLocked: boolean;
  models: ModelEntry[];
  selectedModel: string;
  onSelectModel: (ref: string) => void;
  recording: boolean;
  onToggleMic: () => void;
  textareaRef: React.RefObject<HTMLTextAreaElement | null>;
  placeholder?: string;
}

function AttachmentChip({
  attachment,
  onRemove,
}: {
  attachment: ChatAttachment;
  onRemove: () => void;
}) {
  const busy =
    attachment.status === "uploading" || attachment.status === "processing";
  return (
    <div
      className={cn(
        "flex max-w-60 items-center gap-2 rounded-xl border bg-surface-subtle py-1.5 pl-2.5 pr-1.5 text-xs",
        attachment.status === "error"
          ? "border-destructive/50 text-destructive"
          : "border-border-base",
      )}
      title={attachment.error ?? attachment.filename}
    >
      {busy ? (
        <Loader2 className="size-4 shrink-0 animate-spin text-muted-foreground" />
      ) : attachment.status === "error" ? (
        <TriangleAlert className="size-4 shrink-0" />
      ) : (
        <FileText className="size-4 shrink-0 text-muted-foreground" />
      )}
      <span className="truncate">{attachment.filename}</span>
      <span className="shrink-0 text-muted-foreground">
        {attachment.status === "uploading"
          ? "lädt…"
          : attachment.status === "processing"
            ? "wird gelesen…"
            : null}
      </span>
      <button
        type="button"
        onClick={onRemove}
        className="shrink-0 rounded-full p-0.5 text-muted-foreground hover:bg-surface-muted hover:text-foreground"
        aria-label="Anhang entfernen"
      >
        <X className="size-3.5" />
      </button>
    </div>
  );
}

export function Composer({
  value,
  onChange,
  onSubmit,
  onStop,
  streaming,
  attachments,
  onAttach,
  onRemoveAttachment,
  knowledge,
  selectedKnowledge,
  onSelectKnowledge,
  knowledgeLocked,
  models,
  selectedModel,
  onSelectModel,
  recording,
  onToggleMic,
  textareaRef,
  placeholder = "Frag etwas zu deinem Wissen…",
}: ComposerProps) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  // Wächst mit dem Inhalt, aber höchstens 8 Zeilen; danach scrollt das Feld.
  const autoGrow = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    const cs = window.getComputedStyle(el);
    const lineHeight = parseFloat(cs.lineHeight) || 24;
    const padding = parseFloat(cs.paddingTop) + parseFloat(cs.paddingBottom);
    const maxHeight = lineHeight * 8 + padding;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, maxHeight)}px`;
    el.style.overflowY = el.scrollHeight > maxHeight ? "auto" : "hidden";
  }, [textareaRef]);

  useEffect(() => {
    autoGrow();
  }, [value, autoGrow]);

  const pending = attachments.some(
    (a) => a.status === "uploading" || a.status === "processing",
  );
  // Fragen sind auch waehrend des Einlesens moeglich: die Antwort startet danach.
  const canSend = value.trim().length > 0;

  const submit = (e?: FormEvent) => {
    e?.preventDefault();
    if (streaming) {
      onStop();
      return;
    }
    if (canSend) onSubmit();
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const files = Array.from(e.dataTransfer.files);
    if (files.length > 0) onAttach(files);
  };

  return (
    <form
      onSubmit={submit}
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
      className={cn(
        "w-full rounded-3xl border border-border-base bg-surface p-2 shadow-material-1 transition-colors focus-within:border-border-strong",
        dragging && "border-border-strong bg-surface-subtle",
      )}
    >
      {attachments.length > 0 ? (
        <div className="flex flex-wrap gap-2 px-2 pb-1 pt-1">
          {attachments.map((a) => (
            <AttachmentChip
              key={a.id}
              attachment={a}
              onRemove={() => onRemoveAttachment(a.id)}
            />
          ))}
        </div>
      ) : null}

      {pending ? (
        <p className="flex items-center gap-1.5 px-3 pb-1 text-xs text-muted-foreground">
          <Loader2 className="size-3.5 animate-spin" />
          Anhang wird gelesen. Du kannst schon fragen, die Antwort startet danach.
        </p>
      ) : null}

      <Textarea
        ref={textareaRef}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            submit();
          }
        }}
        placeholder={placeholder}
        rows={1}
        className="field-sizing-fixed min-h-0 w-full resize-none border-none bg-transparent px-3 py-2 leading-6 shadow-none focus-visible:ring-0"
      />

      <div className="flex items-center gap-1 pt-1">
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="size-8 rounded-full text-muted-foreground"
          title="Datei anhängen (PDF, DOCX, DOC, ODT, MD)"
          onClick={() => fileRef.current?.click()}
        >
          <Paperclip className="size-5" />
        </Button>
        <input
          ref={fileRef}
          type="file"
          multiple
          accept={ATTACH_ACCEPT}
          className="hidden"
          onChange={(e) => {
            const files = Array.from(e.target.files ?? []);
            if (files.length > 0) onAttach(files);
            e.target.value = "";
          }}
        />

        {models.length > 0 ? (
          <ModelPicker
            models={models}
            selected={selectedModel}
            onChange={onSelectModel}
          />
        ) : null}

        {knowledgeLocked ? (
          <span
            className="flex h-8 items-center gap-1.5 rounded-full px-3 text-sm text-muted-foreground"
            title="Dieses Modell hat festes Knowledge"
          >
            Knowledge vom Modell
          </span>
        ) : knowledge.length > 0 ? (
          <KnowledgePicker
            knowledge={knowledge}
            selectedIds={selectedKnowledge}
            onChange={onSelectKnowledge}
          />
        ) : null}

        <div className="ml-auto flex items-center gap-1">
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className={cn(
              "size-8 rounded-full text-muted-foreground",
              recording && "animate-pulse text-red-600",
            )}
            onClick={onToggleMic}
            title={recording ? "Aufnahme stoppen" : "Spracheingabe"}
          >
            <Mic className="size-5" />
          </Button>
          <Button
            type="submit"
            size="icon"
            disabled={!streaming && !canSend}
            className={cn("size-8 rounded-full", streaming && "bg-red-600 hover:bg-red-700")}
            title={streaming ? "Stopp" : pending ? "Senden – die Antwort startet, sobald der Anhang gelesen ist" : "Senden"}
          >
            {streaming ? <Square className="size-3.5" /> : <ArrowUp className="size-5" />}
          </Button>
        </div>
      </div>
    </form>
  );
}
