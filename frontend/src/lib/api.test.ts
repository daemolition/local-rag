// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, csrfHeaders, errorMessage } from "@/lib/api";

function jsonResponse(status: number, body: unknown, contentType?: string): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: { get: (name: string) => (name.toLowerCase() === "content-type" ? (contentType ?? "application/json") : null) },
    text: async () => (body === null ? "" : typeof body === "string" ? body : JSON.stringify(body)),
  } as unknown as Response;
}

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "csrf_token=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/";
});

describe("csrfHeaders", () => {
  it("liest das Token aus dem Cookie", () => {
    document.cookie = "csrf_token=abc123; path=/";
    expect(csrfHeaders()).toEqual({ "X-CSRF-Token": "abc123" });
  });

  it("decodiert URL-kodierte Werte", () => {
    document.cookie = "csrf_token=a%2Bb; path=/";
    expect(csrfHeaders()).toEqual({ "X-CSRF-Token": "a+b" });
  });

  it("liefert ein leeres Objekt ohne Cookie", () => {
    expect(csrfHeaders()).toEqual({});
  });
});

describe("api.request", () => {
  it("parst JSON-Antworten", async () => {
    const fetchMock = vi.fn(async () => jsonResponse(200, { ok: true, value: 5 }));
    vi.stubGlobal("fetch", fetchMock);
    expect(await api.get<{ ok: boolean }>("/api/x")).toEqual({ ok: true, value: 5 });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/x",
      expect.objectContaining({ credentials: "same-origin" }),
    );
  });

  it("setzt Content-Type bei JSON-Body und schickt das CSRF-Header", async () => {
    document.cookie = "csrf_token=tok1; path=/";
    const fetchMock = vi.fn(async (_url: string, _init?: RequestInit) => jsonResponse(200, { success: true }));
    vi.stubGlobal("fetch", fetchMock);
    await api.post("/api/y", { a: 1 });
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.method).toBe("POST");
    expect(init.body).toBe(JSON.stringify({ a: 1 }));
    expect(init.headers).toMatchObject({
      "Content-Type": "application/json",
      "X-CSRF-Token": "tok1",
    });
  });

  it("ruft POST ohne Daten mit leerem JSON-Body auf", async () => {
    const fetchMock = vi.fn(async (_url: string, _init?: RequestInit) => jsonResponse(200, { success: true }));
    vi.stubGlobal("fetch", fetchMock);
    await api.post("/api/z");
    expect(fetchMock.mock.calls[0]?.[1]?.body).toBe(JSON.stringify({}));
  });

  it("wirft ApiError mit Server-Meldung bei 400", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(400, { error: "Feld fehlt" })));
    const err = (await api.post("/api/nope").catch((e) => e)) as unknown;
    expect(err).toBeInstanceOf(ApiError);
    const apiError = err as ApiError;
    expect(apiError.status).toBe(400);
    expect(apiError.message).toBe("Feld fehlt");
    expect(errorMessage(err)).toBe("Feld fehlt");
  });

  it("faellt auf die generische HTTP-Meldung ohne parsebare Server-Ausnahme (HTML-Body)", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(500, "<html>kaputt</html>", "text/html")));
    const err = (await api.get("/api/boom").catch((e) => e)) as ApiError;
    expect(err.status).toBe(500);
    expect(err.message).toBe("HTTP 500");
    expect(err.payload).toBe("<html>kaputt</html>");
  });

  it("nimmt kein error-Feld aus Listen-Payloads", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(404, { fehler: "kein error-schluessel" })));
    const err = (await api.get("/api/404").catch((e) => e)) as ApiError;
    expect(err.message).toBe("HTTP 404");
  });

  it("gibt null bei leerem Body", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(200, null)));
    expect(await api.del("/api/weg")).toBeNull();
  });
});