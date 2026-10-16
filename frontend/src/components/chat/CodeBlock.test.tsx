// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CodeBlock } from "@/components/chat/CodeBlock";

function lines(n: number): string {
  return Array.from({ length: n }, (_, i) => `Zeile ${i + 1}`).join("\n");
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("CodeBlock Falten", () => {
  it("faelt lange Bloecke erst nach dem Streamen; Ausklappen zeigt den Inhalt", async () => {
    const { container, getByRole, queryByRole } = render(
      <CodeBlock language="sql" text={lines(30)} streaming={false}>
        <code>inhalt</code>
      </CodeBlock>,
    );
    expect(getByRole("button", { name: "30 Zeilen eingeklappt" })).toBeTruthy();
    expect(container.querySelector("pre")).toBeNull();
    expect(queryByRole("button", { name: "Einklappen" })).toBeNull();

    await userEvent.click(getByRole("button", { name: "Ausklappen" }));
    expect(container.querySelector("pre")).not.toBeNull();
    expect(queryByRole("button", { name: "30 Zeilen eingeklappt" })).toBeNull();
    expect(getByRole("button", { name: "Einklappen" })).toBeTruthy();
  });

  it("faelt nicht waehrend des Streamings", () => {
    const { getByText, queryByRole } = render(
      <CodeBlock language="sql" text={lines(30)} streaming>
        <code>inhalt</code>
      </CodeBlock>,
    );
    expect(getByText("inhalt")).toBeTruthy();
    expect(queryByRole("button", { name: /eingeklappt/ })).toBeNull();
  });

  it("faelt kurze Bloecke nicht", () => {
    const { getByText, queryByRole } = render(
      <CodeBlock language="sql" text={lines(5)} streaming={false}>
        <code>inhalt</code>
      </CodeBlock>,
    );
    expect(getByText("inhalt")).toBeTruthy();
    expect(queryByRole("button", { name: /eingeklappt/ })).toBeNull();
  });
});

describe("CodeBlock Kopieren", () => {
  it("schreibt den Text ohne Schlusszeilenumbruch in die Zwischenablage", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { clipboard: { writeText } } as unknown as Navigator);
    const { getByRole } = render(
      <CodeBlock language="python" text={"print(1)\n"}>
        <code />
      </CodeBlock>,
    );
    await userEvent.click(getByRole("button", { name: "Kopieren" }));
    expect(writeText).toHaveBeenCalledWith("print(1)");
    expect(getByRole("button", { name: "Kopiert" })).toBeTruthy();
  });
});