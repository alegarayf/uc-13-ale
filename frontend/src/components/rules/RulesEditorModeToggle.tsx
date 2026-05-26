import type { RulesEditorMode } from "../../hooks/useRulesEditorMode.js";

export interface RulesEditorModeToggleProps {
  mode: RulesEditorMode;
  onChange: (mode: RulesEditorMode) => void;
  disabled?: boolean;
}

export function RulesEditorModeToggle({ mode, onChange, disabled }: RulesEditorModeToggleProps) {
  return (
    <div className="rules-editor-toggle" role="group" aria-label="Rule editor mode">
      <button
        type="button"
        className={`rules-editor-toggle__btn${mode === "form" ? " rules-editor-toggle__btn--active" : ""}`}
        aria-pressed={mode === "form"}
        disabled={disabled}
        onClick={() => onChange("form")}
      >
        Form
      </button>
      <button
        type="button"
        className={`rules-editor-toggle__btn${mode === "ai" ? " rules-editor-toggle__btn--active" : ""}`}
        aria-pressed={mode === "ai"}
        disabled={disabled}
        onClick={() => onChange("ai")}
      >
        AI
      </button>
    </div>
  );
}
