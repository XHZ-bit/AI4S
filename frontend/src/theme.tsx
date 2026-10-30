import { createContext, useContext } from "react";

export type AtlasTheme = "light" | "dark";

export const THEME_STORAGE_KEY = "research-atlas-theme";

export function getInitialTheme(): AtlasTheme {
  if (typeof window === "undefined") return "light";
  try {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
    if (stored === "light" || stored === "dark") return stored;
  } catch { /* Browsers can disable local storage. */ }
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function applyTheme(mode: AtlasTheme): void {
  if (typeof document !== "undefined") document.documentElement.dataset.theme = mode;
  try { window.localStorage.setItem(THEME_STORAGE_KEY, mode); }
  catch { /* Theme still works for this session. */ }
}

export const ThemeContext = createContext<{ mode: AtlasTheme; toggle: () => void }>({
  mode: "light",
  toggle: () => undefined,
});

export function useAtlasTheme() { return useContext(ThemeContext); }
