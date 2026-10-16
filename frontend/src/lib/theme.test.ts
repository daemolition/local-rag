// @vitest-environment jsdom
import { describe, expect, it } from "vitest";

// jsdom stellt kein matchMedia; theme.ts liest es beim Import (Listener) und in "system".
const stub = (query: string): MediaQueryList =>
  ({
    matches: query.includes("prefers-color-scheme: dark"),
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
  }) as unknown as MediaQueryList;
window.matchMedia = stub as unknown as typeof window.matchMedia;

const { applyTheme, getStoredTheme, isDarkMode, toggleTheme } = await import("@/lib/theme");

const KEY = "ui_theme";

describe("applyTheme", () => {
  it("setzt die dark-Klasse und speichert die Wahl", () => {
    const dark = applyTheme("dark");
    expect(dark).toBe(true);
    expect(isDarkMode()).toBe(true);
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(localStorage.getItem(KEY)).toBe("dark");

    applyTheme("light");
    expect(isDarkMode()).toBe(false);
    expect(document.documentElement.classList.contains("dark")).toBe(false);
    expect(localStorage.getItem(KEY)).toBe("light");
  });

  it("loest die System-Einstellung per prefers-color-scheme auf", () => {
    expect(applyTheme("system")).toBe(true);
    expect(isDarkMode()).toBe(true);
    expect(localStorage.getItem(KEY)).toBe("system");
  });
});

describe("getStoredTheme", () => {
  it("liest gueltige Werte", () => {
    for (const value of ["light", "dark", "system"] as const) {
      localStorage.setItem(KEY, value);
      expect(getStoredTheme()).toBe(value);
    }
  });

  it("faellt bei ungültigem Wert auf system", () => {
    localStorage.setItem(KEY, "blue");
    expect(getStoredTheme()).toBe("system");
    localStorage.removeItem(KEY);
    expect(getStoredTheme()).toBe("system");
  });
});

describe("toggleTheme", () => {
  it("wechselt dunkel ⇄ hell und gibt den neuen Zustand", () => {
    applyTheme("dark");
    expect(toggleTheme()).toBe(false);
    expect(isDarkMode()).toBe(false);
    expect(toggleTheme()).toBe(true);
    expect(isDarkMode()).toBe(true);
  });
});