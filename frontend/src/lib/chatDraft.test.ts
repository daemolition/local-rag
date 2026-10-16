// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from "vitest";
import { addToStoredDraft, loadDraft, saveDraft, type ChatDraft } from "@/lib/chatDraft";
import type { ChatAttachment } from "@/lib/types";

const KEY = "chat-1";

function attachment(id: string): ChatAttachment {
  return {
    id,
    filename: `${id}.pdf`,
    status: "ready",
    error: null,
    markdown: "",
  } as ChatAttachment;
}

beforeEach(() => {
  sessionStorage.clear();
});

describe("loadDraft", () => {
  it("liefert einen leeren Entwurf ohne Speicherinhalt", () => {
    expect(loadDraft(KEY)).toEqual({ attachments: [], input: "" });
  });

  it("rundet gespeicherte Entwürfe", () => {
    const draft: ChatDraft = { attachments: [attachment("id-1")], input: "Frage?" };
    saveDraft(KEY, draft);
    expect(loadDraft(KEY)).toEqual(draft);
  });

  it("erholt sich von defektem JSON", () => {
    sessionStorage.setItem("rag.draft." + KEY, "{kaputt");
    expect(loadDraft(KEY)).toEqual({ attachments: [], input: "" });
  });

  it("fuellt fehlende Felder mit Defaults", () => {
    sessionStorage.setItem("rag.draft." + KEY, JSON.stringify({ input: "nur text" }));
    const draft = loadDraft(KEY);
    expect(draft.input).toBe("nur text");
    expect(draft.attachments).toEqual([]);
  });
});

describe("saveDraft", () => {
  it("entfernt den Schluessel bei leerem Entwurf", () => {
    saveDraft(KEY, { attachments: [attachment("id-2")], input: "hi" });
    expect(sessionStorage.getItem("rag.draft." + KEY)).not.toBeNull();
    saveDraft(KEY, { attachments: [], input: "" });
    expect(sessionStorage.getItem("rag.draft." + KEY)).toBeNull();
  });

  it("filtert lokale Anhänge (kein Server-Id) heraus", () => {
    saveDraft(KEY, { attachments: [attachment("local-1"), attachment("server-9")], input: "" });
    expect(loadDraft(KEY).attachments.map((a) => a.id)).toEqual(["server-9"]);
  });
});

describe("addToStoredDraft", () => {
  it("haengt an und vermeidet Doppelte", () => {
    addToStoredDraft(KEY, attachment("a-1"));
    addToStoredDraft(KEY, attachment("a-2"));
    addToStoredDraft(KEY, attachment("a-1"));
    expect(loadDraft(KEY).attachments.map((a) => a.id)).toEqual(["a-1", "a-2"]);
  });
});