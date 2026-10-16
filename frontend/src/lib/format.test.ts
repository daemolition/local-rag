import { describe, expect, it } from "vitest";
import { formatBytes, formatCount, formatDate, formatDateTime } from "@/lib/format";

describe("formatBytes", () => {
  it("laesst kleine Werte in Byte", () => {
    expect(formatBytes(1023)).toBe("1023 B");
  });
  it("teilt auf KB und MB", () => {
    expect(formatBytes(1024)).toBe("1.0 KB");
    expect(formatBytes(1024 * 1024 * 2.5)).toBe("2.5 MB");
  });
});

describe("formatCount", () => {
  it("formatiert deutsch mit Tausendertrenner", () => {
    expect(formatCount(1234)).toBe("1.234");
  });
});

describe("Leerstrings", () => {
  it("gibt leeren String bei fehlendem Datum", () => {
    expect(formatDateTime(null)).toBe("");
    expect(formatDate(undefined)).toBe("");
  });
});