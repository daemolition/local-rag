// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { downloadText } from "@/lib/hastText";
import { TableBlock } from "@/components/chat/TableBlock";
import type { HastNode } from "@/lib/hastText";

vi.mock("@/lib/hastText", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/hastText")>()),
  downloadText: vi.fn(),
}));

function tableNode(): HastNode {
  return {
    type: "element",
    tagName: "table",
    children: [
      {
        type: "element",
        tagName: "thead",
        children: [
          {
            type: "element",
            tagName: "tr",
            children: ["Name", "Wert"].map((c) => ({
              type: "element",
              tagName: "th" as const,
              children: [{ type: "text", value: c }],
            })),
          },
        ],
      },
      {
        type: "element",
        tagName: "tbody",
        children: [["a,b", '3"'], ["c", "2"]].map((row) => ({
          type: "element",
          tagName: "tr",
          children: row.map((c) => ({
            type: "element",
            tagName: "td" as const,
            children: [{ type: "text", value: c }],
          })),
        })),
      },
    ],
  };
}

function tableChildren() {
  return (
    <table>
      <thead>
        <tr>
          <th>Name</th>
          <th>Wert</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td>a,b</td>
          <td>3"</td>
        </tr>
        <tr>
          <td>c</td>
          <td>2</td>
        </tr>
      </tbody>
    </table>
  );
}

afterEach(cleanup);

describe("TableBlock", () => {
  it("rendert die übergebenen Tabellen-Children mit den Aktions-Buttons", () => {
    const { getByText, getByRole } = render(<TableBlock node={tableNode()}>{tableChildren()}</TableBlock>);
    expect(getByText("Name")).toBeTruthy();
    expect(getByText('a,b')).toBeTruthy();
    expect(getByRole("button", { name: "Kopieren" })).toBeTruthy();
    expect(getByRole("button", { name: "CSV" })).toBeTruthy();
  });

  it("kopiert die Markdown-Tabelle in die Zwischenablage", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { clipboard: { writeText } } as unknown as Navigator);
    const { getByRole } = render(<TableBlock node={tableNode()}>{tableChildren()}</TableBlock>);
    await userEvent.click(getByRole("button", { name: "Kopieren" }));
    expect(writeText).toHaveBeenCalledWith("| Name | Wert |\n| --- | --- |\n| a,b | 3\" |\n| c | 2 |");
  });

  it("exportiert das CSV unter tabelle.csv (Komma, Anfuehrungs-Maskierung)", async () => {
    const { getByRole } = render(<TableBlock node={tableNode()}>{tableChildren()}</TableBlock>);
    await userEvent.click(getByRole("button", { name: "CSV" }));
    expect(vi.mocked(downloadText)).toHaveBeenCalledWith(
      "tabelle.csv",
      'Name,Wert\r\n"a,b","3"""\r\nc,2',
    );
  });

  it("zeigt Kopiert voruebergehend an", async () => {
    vi.stubGlobal("navigator", {
      clipboard: { writeText: vi.fn().mockResolvedValue(undefined) },
    } as unknown as Navigator);
    const { getByRole } = render(<TableBlock node={tableNode()}>{tableChildren()}</TableBlock>);
    await userEvent.click(getByRole("button", { name: "Kopieren" }));
    expect(getByRole("button", { name: "Kopiert" })).toBeTruthy();
  });
});