// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Markdown } from "@/components/Markdown";

afterEach(cleanup);

describe("Markdown Sanitizer-Regressionen", () => {
  it("entfernt Skripte (Sanitizer zuerst), laesst Text weiterlaufen", () => {
    const { container, getByText } = render(
      <Markdown content={"Vorher\n\n<script>alert(1)</script>\n\nNachher"} />,
    );
    expect(container.querySelector("script")).toBeNull();
    expect(getByText("Vorher")).toBeTruthy();
    expect(getByText("Nachher")).toBeTruthy();
  });

  it("behält hljs-Sprachklassen am Code-Element (Highlighting nach Sanitize)", () => {
    const { container } = render(<Markdown content={"```python\nprint('hi')\n```"} />);
    const code = container.querySelector("pre code");
    expect(code).not.toBeNull();
    expect((code as HTMLElement).className).toContain("language-python");
    expect((code as HTMLElement).className).toContain("hljs");
  });

  it("fasst GFM-Tabellen in den TableBlock (.rag-table) ein", () => {
    const table = "| Name | Wert |\n| --- | --- |\n| a | 1 |\n";
    const { container } = render(<Markdown content={table} />);
    expect(container.querySelector(".rag-table table")).not.toBeNull();
  });

  it("laesst Bilder aus Fremdquellen zu (CSP img-src https: bewusst offen)", () => {
    const { container } = render(<Markdown content={"![X](https://beispiel.example/x.png)"} />);
    const img = container.querySelector("img");
    expect(img?.getAttribute("src")).toBe("https://beispiel.example/x.png");
  });

  it("externalisiert normale Links (target=_blank, rel noreferrer)", () => {
    const { container } = render(<Markdown content={"[Doku](https://beispiel.example)"} />);
    const a = container.querySelector("a");
    expect(a?.getAttribute("target")).toBe("_blank");
    expect(a?.getAttribute("rel")).toContain("noreferrer");
  });
});

describe("Quellennummern", () => {
  it("verlinkt [2] nur, wenn Quelle 2 bekannt ist", () => {
    const { container } = render(<Markdown content={"Siehe [2] und [7]."} />);
    expect(container.querySelector("a[href='#src-2']")).toBeNull();
  });

  it("macht aus bekannten [n] Klick-Links und ruft onCite", async () => {
    const onCite = vi.fn();
    const { container, getByText } = render(
      <Markdown
        content={"Siehe [2]."}
        sources={[{ n: 2, filename: "handbuch.pdf", score: 0.87, section: 3 }]}
        onCite={onCite}
      />,
    );
    const link = container.querySelector("a[href='#src-2']");
    expect(link).not.toBeNull();
    expect((link as HTMLElement).title).toContain("handbuch.pdf");
    await userEvent.click(getByText("2"));
    expect(onCite).toHaveBeenCalledWith(2);
  });
});