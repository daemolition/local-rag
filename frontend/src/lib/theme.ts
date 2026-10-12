export type ThemePref = "light" | "dark" | "system";

const STORAGE_KEY = "ui_theme";

export function getStoredTheme(): ThemePref {
  const pref = localStorage.getItem(STORAGE_KEY);
  if (pref === "light" || pref === "dark" || pref === "system") return pref;
  return "system";
}

function isDark(pref: ThemePref): boolean {
  return (
    pref === "dark" ||
    (pref === "system" &&
      window.matchMedia("(prefers-color-scheme: dark)").matches)
  );
}

export function applyTheme(pref: ThemePref): boolean {
  localStorage.setItem(STORAGE_KEY, pref);
  const dark = isDark(pref);
  document.documentElement.classList.toggle("dark", dark);
  return dark;
}

export function toggleTheme(): boolean {
  const isCurrentlyDark = document.documentElement.classList.contains("dark");
  return applyTheme(isCurrentlyDark ? "light" : "dark");
}

export function isDarkMode(): boolean {
  return document.documentElement.classList.contains("dark");
}

// Re-apply on OS preference change while in "system" mode.
window
  .matchMedia("(prefers-color-scheme: dark)")
  .addEventListener("change", () => {
    if (getStoredTheme() === "system") applyTheme("system");
  });
