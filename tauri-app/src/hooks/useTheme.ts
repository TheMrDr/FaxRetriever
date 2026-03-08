import { useState, useEffect, useCallback } from "react";

type Theme = "light" | "dark";

function getStoredTheme(): Theme {
  // On first load, try to read from localStorage
  const stored = localStorage.getItem("faxretriever-theme");
  if (stored === "dark" || stored === "light") return stored;
  // Default to system preference
  if (window.matchMedia("(prefers-color-scheme: dark)").matches) return "dark";
  return "light";
}

function applyTheme(theme: Theme) {
  document.documentElement.setAttribute("data-theme", theme);
  localStorage.setItem("faxretriever-theme", theme);
}

export function useTheme() {
  const [theme, setThemeState] = useState<Theme>(getStoredTheme);

  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  const toggleTheme = useCallback(() => {
    setThemeState((prev) => (prev === "light" ? "dark" : "light"));
  }, []);

  const setTheme = useCallback((t: Theme) => {
    setThemeState(t);
  }, []);

  return { theme, toggleTheme, setTheme };
}
