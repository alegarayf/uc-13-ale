import { useId } from "react";

export interface RulesSearchBarProps {
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}

export function RulesSearchBar({ value, onChange, disabled }: RulesSearchBarProps) {
  const inputId = useId();

  return (
    <div className="rules-search">
      <label className="rules-search__label" htmlFor={inputId}>
        Search rules
      </label>
      <div className="rules-search__control">
        <input
          id={inputId}
          type="search"
          className="rules-search__input"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          disabled={disabled}
          placeholder="Search by name, description, criteria, status, or other text…"
          autoComplete="off"
        />
        {value && !disabled && (
          <button
            type="button"
            className="rules-search__clear"
            aria-label="Clear search"
            onClick={() => onChange("")}
          >
            ×
          </button>
        )}
      </div>
    </div>
  );
}
