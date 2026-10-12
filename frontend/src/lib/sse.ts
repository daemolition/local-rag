export interface ChatStreamEvent {
  token?: string;
  reasoning?: string;
  reasoning_done?: boolean;
  tool_start?: string;
  tool_end?: string;
  tool_result?: { name: string; output: string };
  sources?: string;
  source_list?: import("@/components/chat/Message").SourceInfo[];
  warning?: string;
  compaction?: { before: number; after: number; summarized?: number; clipped?: boolean };
  done?: boolean;
  session_id?: string;
  error?: string;
}

// Parses the SSE stream from POST /chat. Buffers across chunk boundaries so a
// "data: {...}" line split between reads is not lost.
export async function consumeChatStream(
  response: Response,
  onEvent: (event: ChatStreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  if (!response.body) throw new Error("Keine Antwort vom Server");

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    if (signal?.aborted) {
      await reader.cancel().catch(() => {});
      return;
    }
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    let sepIndex: number;
    while ((sepIndex = buffer.indexOf("\n")) !== -1) {
      const line = buffer.slice(0, sepIndex);
      buffer = buffer.slice(sepIndex + 1);

      if (!line.startsWith("data:")) continue;
      const data = line.slice(5).trim();
      if (!data) continue;

      try {
        onEvent(JSON.parse(data) as ChatStreamEvent);
      } catch {
        // Ignore malformed frames.
      }
    }
  }
}
