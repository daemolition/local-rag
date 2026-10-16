import { describe, expect, it, vi } from "vitest";
import { consumeChatStream, type ChatStreamEvent } from "@/lib/sse";

// SSE-Stream-Parser: Frames muessen auch ueber Chunk-Grenzen (Teil-JSON in
// zwei TCP-Paketen) unversehrt ankommen.
function responseOf(chunks: string[]): Response {
  const encoder = new TextEncoder();
  const body = new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
  return new Response(body, { status: 200 });
}

async function collect(response: Response, signal?: AbortSignal): Promise<ChatStreamEvent[]> {
  const events: ChatStreamEvent[] = [];
  await consumeChatStream(response, (e) => events.push(e), signal);
  return events;
}

describe("consumeChatStream", () => {
  it("fasst einen ueber Chunk-Grenzen gesplitteten Frame zusammen", async () => {
    const events = await collect(responseOf(['data: {"token":"hal', 'lo"}\n']));
    expect(events).toEqual([{ token: "hallo" }]);
  });

  it("verarbeitet mehrere Events je Chunk in Reihenfolge", async () => {
    const lines = 'data: {"token":"a"}\ndata: {"reasoning":"b"}\ndata: {"done":true}\n'.split("\n\n");
    const events = await collect(responseOf(lines));
    expect(events).toEqual([{ token: "a" }, { reasoning: "b" }, { done: true }]);
  });

  it("ignoriert Nicht-data-Zeilen, leere data-Zeilen und Kommentare", async () => {
    const events = await collect(responseOf([": keepalive\nevent: x\ndata:\ndata: {\"done\":true}\n"]));
    expect(events).toEqual([{ done: true }]);
  });

  it("ueberspringt kaputte Frames und liest weiter", async () => {
    const events = await collect(responseOf(['data: {broken\ndata: {"token":"ok"}\n']));
    expect(events).toEqual([{ token: "ok" }]);
  });

  it("bricht bei bereits abgebrochenem Signal sofort ab (cancel statt lesen)", async () => {
    const cancel = vi.fn();
    const read = vi.fn(async () => ({ done: true, value: undefined }));
    const response = {
      body: { getReader: () => ({ cancel: async () => cancel(), read }) },
    } as unknown as Response;
    const onEvent = vi.fn();

    await consumeChatStream(response, onEvent, AbortSignal.abort());

    expect(onEvent).not.toHaveBeenCalled();
    expect(read).not.toHaveBeenCalled();
    expect(cancel).toHaveBeenCalled();
  });

  it("wirft ohne Stream-Body", async () => {
    const response = new Response(null, { status: 200 });
    await expect(collect(response)).rejects.toThrow("Keine Antwort vom Server");
  });
});