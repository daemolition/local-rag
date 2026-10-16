import { describe, expect, it } from "vitest";
import { splitSources, splitTools, type SourceInfo, type ToolResult } from "@/components/chat/Message";

// Historie speichert Werkzeuge/Quellen als JSON-Block am Ende der Nachricht.
// Parser muessen bei kaputtem JSON die Blöcke trotzdem vom Text abtrennen.
describe("splitTools", () => {
  it("laesst Text ohne Block unveraendert", () => {
    const r = splitTools("Einfache Antwort");
    expect(r.body).toBe("Einfache Antwort");
    expect(r.tools).toEqual([]);
  });

  it("extrahiert den Tools-Block und trennt ihn vom Text", () => {
    const tools: ToolResult[] = [{ name: "run_pandas", output: "…", input: "df.head()" }];
    const text = `Analyse fertig\n<tools>${JSON.stringify(tools)}</tools>`;
    const r = splitTools(text);
    expect(r.body).toBe("Analyse fertig");
    expect(r.tools).toEqual(tools);
  });

  it("entfernt Block mit kaputtem JSON trotzdem (leere Tools)", () => {
    const r = splitTools("Hier die Antwort\n<tools>{kein json}</tools>");
    expect(r.body).toBe("Hier die Antwort");
    expect(r.tools).toEqual([]);
  });

  it("trennt mehrfache Zeilenumbrueche vor dem Block ab", () => {
    const r = splitTools("Text\n\n\n<tools>[]</tools>");
    expect(r.body).toBe("Text");
    expect(r.tools).toEqual([]);
  });

  it("matcht nur den Block am Ende (Text mit tools-Begriff im Fliesstext bleibt unverändert)", () => {
    const text = "Ich nutze <tools> nie fuer andere Zwecke.\n<tools>[{\"name\":\"list_files\"}]</tools>";
    const r = splitTools(text);
    expect(r.body).toBe("Ich nutze <tools> nie fuer andere Zwecke.");
    expect(r.tools).toEqual([{ name: "list_files" }]);
  });
});

describe("splitSources", () => {
  it("laesst Text ohne Block unveraendert", () => {
    const r = splitSources("Antwort ohne Quellen");
    expect(r.body).toBe("Antwort ohne Quellen");
    expect(r.sources).toEqual([]);
  });

  it("extrahiert Quellen mit Titel und ID", () => {
    const sources: SourceInfo[] = [{ n: 1, filename: "Handbuch", score: 0.9, section: null, snippet: "…" }];
    const text = `Nennen wir es so\n<sources>${JSON.stringify(sources)}</sources>`;
    const r = splitSources(text);
    expect(r.body).toBe("Nennen wir es so");
    expect(r.sources).toEqual(sources);
  });

  it("entfernt Block mit kaputtem JSON trotzdem (leere Quellen)", () => {
    const r = splitSources("Antwort\n<sources>[broken]</sources>");
    expect(r.body).toBe("Antwort");
    expect(r.sources).toEqual([]);
  });
});