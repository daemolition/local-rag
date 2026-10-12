import type { ChatAttachment } from "@/lib/types";

// Entwurf pro Chat (angehaengte Dateien, getippter Text). Ueberlebt den Wechsel zwischen
// Seiten und das Neuladen; liegt nur im Browser-Tab (sessionStorage).
const PREFIX = "rag.draft.";

export interface ChatDraft {
  attachments: ChatAttachment[];
  input: string;
}

export function loadDraft(key: string): ChatDraft {
  try {
    const raw = sessionStorage.getItem(PREFIX + key);
    if (raw) {
      const data = JSON.parse(raw) as Partial<ChatDraft>;
      return { attachments: data.attachments ?? [], input: data.input ?? "" };
    }
  } catch {
    // Speicher nicht verfuegbar oder defekt: leerer Entwurf
  }
  return { attachments: [], input: "" };
}

export function saveDraft(key: string, draft: ChatDraft): void {
  try {
    // Hochladende Dateien (noch ohne Server-ID) lassen sich nicht fortsetzen.
    const attachments = draft.attachments.filter((a) => !a.id.startsWith("local-"));
    if (attachments.length === 0 && !draft.input) sessionStorage.removeItem(PREFIX + key);
    else sessionStorage.setItem(PREFIX + key, JSON.stringify({ attachments, input: draft.input }));
  } catch {
    // ohne Speicher gilt der Entwurf nur, solange die Seite offen ist
  }
}

/** Haengt eine Datei an den gespeicherten Entwurf an (Upload endete, nachdem die Seite verlassen wurde). */
export function addToStoredDraft(key: string, attachment: ChatAttachment): void {
  const draft = loadDraft(key);
  if (draft.attachments.some((a) => a.id === attachment.id)) return;
  saveDraft(key, { ...draft, attachments: [...draft.attachments, attachment] });
}
