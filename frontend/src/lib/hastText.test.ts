import { describe, expect, it } from "vitest";
import { codeLanguage, nodeText, toCsv, tableRows, toMarkdownTable, type HastNode } from "@/lib/hastText";

function text(value: string): HastNode {
  return { type: "text", value };
}

describe("nodeText", () => {
  it("sammelt Text ueber Kinder", () => {
    const node: HastNode = {
      type: "element",
      tagName: "p",
      children: [text("Hallo "), { type: "element", tagName: "b", children: [text("Welt")] }],
    };
    expect(nodeText(node)).toBe("Hallo Welt");
  });
  it("ist tolerant gegen fehlende Knoten", () => {
    expect(nodeText(undefined)).toBe("");
    expect(nodeText({ type: "element" })).toBe("");
  });
});

describe("codeLanguage", () => {
  it("liest language-* aus Klassenlisten", () => {
    expect(codeLanguage({ type: "element", properties: { className: ["language-python", "hljs"] } })).toBe("python");
  });
  it("akzeptiert String-Klassen und fehlende Klassen", () => {
    expect(codeLanguage({ type: "element", properties: { className: "language-dockerfile extra" } })).toBe(
      "dockerfile",
    );
    expect(codeLanguage({ type: "element", properties: {} })).toBe("");
    expect(codeLanguage(undefined)).toBe("");
  });
});

describe("tableRows", () => {
  it("liefert Zellen kopfzuerst und normalisiert Whitespace", () => {
    const table: HastNode = {
      type: "element",
      tagName: "table",
      children: [
        {
          type: "element",
          tagName: "thead",
          children: [
            { type: "element", tagName: "tr", children: [
              { type: "element", tagName: "th", children: [text("Name")] },
              { type: "element", tagName: "th", children: [text("Wert")] },
            ]},
          ],
        },
        {
          type: "element",
          tagName: "tbody",
          children: [
            { type: "element", tagName: "tr", children: [
              { type: "element", tagName: "td", children: [text("a\n  b")] },
              { type: "element", tagName: "td", children: [text("3")] },
            ]},
          ],
        },
      ],
    };
    expect(tableRows(table)).toEqual([["Name", "Wert"], ["a b", "3"]]);
  });
});

describe("toCsv", () => {
  it("maskiert Komma, Anfuehrungsstriche und Zeilenumbrueche", () => {
    expect(toCsv([["a,b", 'ein "Wort"']])).toBe('"a,b","ein ""Wort"""');
  });
  it("trennt Zeilen mit CRLF", () => {
    expect(toCsv([["a", "b"], ["c", "d"]])).toBe("a,b\r\nc,d");
  });
});

describe("toMarkdownTable", () => {
  it("escaped Pipes und setzt Trennzeile", () => {
    expect(toMarkdownTable([["Spalte|1", "x"], ["a", "b"]])).toBe(
      "| Spalte\\|1 | x |\n| --- | --- |\n| a | b |",
    );
  });
  it("gibt leeren String fuer keine Zeilen", () => {
    expect(toMarkdownTable([])).toBe("");
  });
});