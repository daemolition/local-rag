import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { applyTheme, getStoredTheme, toggleTheme, type ThemePref } from "@/lib/theme";

interface ThemeContextValue {
  pref: ThemePref;
  dark: boolean;
  setPref: (pref: ThemePref) => void;
  toggle: () => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [pref, setPrefState] = useState<ThemePref>(() => getStoredTheme());
  const [dark, setDark] = useState(() =>
    document.documentElement.classList.contains("dark"),
  );

  const setPref = useCallback((next: ThemePref) => {
    setPrefState(next);
    setDark(applyTheme(next));
  }, []);

  const toggle = useCallback(() => {
    setDark(toggleTheme());
    setPrefState(getStoredTheme());
  }, []);

  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const handler = () => {
      if (getStoredTheme() === "system") setDark(applyTheme("system"));
    };
    media.addEventListener("change", handler);
    return () => media.removeEventListener("change", handler);
  }, []);

  return (
    <ThemeContext.Provider value={{ pref, dark, setPref, toggle }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme muss innerhalb von ThemeProvider laufen");
  return ctx;
}
