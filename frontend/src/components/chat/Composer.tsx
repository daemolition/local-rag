import { useCallback, useEffect, useRef, type FormEvent, type KeyboardEvent } from "react";
import { ArrowUp, FileText, Loader2, Mic, Paperclip, Square, TriangleAlert, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { KnowledgePicker } from "@/components/chat/KnowledgePicker";
import { ModelPicker } from "@/components/chat/ModelPicker";
import { cn } from "@/lib/utils";
import type { ChatAttachment, Knowledge, ModelEntry } from "@/lib/types";

export const ATTACH_ACCEPT = ".pdf,.docx,.doc,.odt,.md,.png,.jpg,.jpeg,.webp,.gif,.bmp";

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
  baseKnowledge?: { id: number; name: string }[];
  models: ModelEntry[];
  selectedModel: string;
  onSelectModel: (ref: string) => void;
  recording: boolean;
  transcribing?: boolean;
  onToggleMic: () => void;
  textareaRef: React.RefObject<HTMLTextAreaElement | null>;
  placeholder?: string;
  // Eigene Nachrichten dieser Unterhaltung, älteste zuerst (Pfeil hoch holt sie zurück).
  history?: string[];
  // Das gewählte Modell versteht Bilder: Bild-Anhänge gehen direkt an das Modell
  seesImages?: boolean;
}

const IMAGE_NAME = /\.(png|jpe?g|webp|gif|bmp)$/i;

function AttachmentChip({
  attachment,
  onRemove,
  seesImages,
}: {
  attachment: ChatAttachment;
  onRemove: () => void;
  seesImages: boolean;
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
      title={
        attachment.error ??
        (IMAGE_NAME.test(attachment.filename)
          ? `${attachment.filename} – ${seesImages ? "das Modell sieht das Bild selbst, der gelesene Text macht es zusätzlich durchsuchbar" : "das Bild wird zu Text gelesen und durchsucht"}`
          : attachment.filename)
      }
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
        className="shrink-0 rounded-full p-0.5 text-muted-foreground hover:bg-hover hover:text-foreground"
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
  baseKnowledge,
  models,
  selectedModel,
  onSelectModel,
  recording,
  transcribing = false,
  onToggleMic,
  textareaRef,
  placeholder = "Frag etwas zu deinem Wissen…",
  history = [],
  seesImages = false,
}: ComposerProps) {
  const fileRef = useRef<HTMLInputElement>(null);
  // Position im Verlauf (null = es wird nicht geblättert) und der zuvor getippte Entwurf.
  const histIndex = useRef<number | null>(null);
  const histDraft = useRef("");

  const recall = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.shiftKey || e.altKey || e.ctrlKey || e.metaKey || e.nativeEvent.isComposing) return;
    const el = e.currentTarget;
    const atStart = el.selectionStart === 0 && el.selectionEnd === 0;
    const atEnd = el.selectionStart === el.value.length && el.selectionEnd === el.value.length;
    let next: number | null = null;
    if (e.key === "ArrowUp" && history.length > 0 && (atStart || el.value === "")) {
      const from = histIndex.current ?? history.length;
      if (from === 0) return;
      if (histIndex.current === null) histDraft.current = el.value;
      next = from - 1;
    } else if (e.key === "ArrowDown" && histIndex.current !== null && atEnd) {
      next = histIndex.current + 1;
    } else {
      return;
    }
    e.preventDefault();
    const text = next >= history.length ? histDraft.current : history[next];
    histIndex.current = next >= history.length ? null : next;
    onChange(text);
    // Cursor ans Ende, sonst bliebe er am Anfang und blockierte das nächste Blättern
    requestAnimationFrame(() => el.setSelectionRange(text.length, text.length));
  };

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

  return (
    <form
      onSubmit={submit}
      className="w-full rounded-3xl border border-border-base bg-surface p-2 shadow-material-1 transition-colors focus-within:border-border-strong"
    >
      {attachments.length > 0 ? (
        <div className="flex flex-wrap gap-2 px-2 pb-1 pt-1">
          {attachments.map((a) => (
            <AttachmentChip
              key={a.id}
              attachment={a}
              onRemove={() => onRemoveAttachment(a.id)}
              seesImages={seesImages}
            />
          ))}
        </div>
      ) : null}

      {pending ? (
        <p className="px-3 pb-1 text-xs text-muted-foreground">
          Du kannst schon fragen, die Antwort startet, sobald der Anhang gelesen ist.
        </p>
      ) : null}

      <Textarea
        ref={textareaRef}
        value={value}
        onChange={(e) => {
          histIndex.current = null;
          onChange(e.target.value);
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            histIndex.current = null;
            submit();
            return;
          }
          recall(e);
        }}
        onPaste={(e) => {
          // Eingefügte Bilder (Screenshot aus der Zwischenablage) werden wie Anhänge behandelt
          const images = Array.from(e.clipboardData.files).filter((f) => f.type.startsWith("image/"));
          if (images.length > 0) {
            e.preventDefault();
            onAttach(images);
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
          title="Datei oder Bild anhängen (PDF, DOCX, DOC, ODT, MD, PNG, JPG, WebP)"
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
        ) : knowledge.length > 0 || (baseKnowledge?.length ?? 0) > 0 ? (
          <KnowledgePicker
            knowledge={knowledge}
            selectedIds={selectedKnowledge}
            onChange={onSelectKnowledge}
            base={baseKnowledge}
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
            disabled={transcribing}
            title={transcribing ? "Wird transkribiert …" : recording ? "Aufnahme stoppen" : "Spracheingabe"}
          >
            {transcribing ? <Loader2 className="size-5 animate-spin" /> : <Mic className="size-5" />}
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
