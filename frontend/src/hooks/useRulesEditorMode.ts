import { useCallback, useEffect, useState } from "react";

export type RulesEditorMode = "form" | "ai";

const STORAGE_KEY = "garden-rules-editor-mode";

function readStoredMode(): RulesEditorMode {
  try {
    return localStorage.getItem(STORAGE_KEY) === "ai" ? "ai" : "form";
  } catch {
    return "form";
  }
}

export function useRulesEditorMode(initialMode?: RulesEditorMode) {
  const [mode, setModeState] = useState<RulesEditorMode>(() => initialMode ?? readStoredMode());

  useEffect(() => {
    if (initialMode) setModeState(initialMode);
  }, [initialMode]);

  const setMode = useCallback((next: RulesEditorMode) => {
    setModeState(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      /* private browsing */
    }
  }, []);

  return [mode, setMode] as const;
}
