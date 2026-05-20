import { RULE_COMPARISON_OPTIONS, type RuleFormState } from "./ruleForm.js";
import type { RuleStatus } from "../../types/rule.js";

export interface RuleFormFieldsProps {
  idPrefix: string;
  form: RuleFormState;
  onChange: (next: RuleFormState) => void;
  disabled?: boolean;
  autoFocusName?: boolean;
}

export function RuleFormFields({
  idPrefix,
  form,
  onChange,
  disabled = false,
  autoFocusName = false,
}: RuleFormFieldsProps) {
  const set = (patch: Partial<RuleFormState>) => onChange({ ...form, ...patch });

  return (
    <>
      <div className="form-field">
        <label className="form-field__label" htmlFor={`${idPrefix}-name`}>
          Name <span className="form-field__required">*</span>
        </label>
        <input
          id={`${idPrefix}-name`}
          className="form-field__input"
          type="text"
          value={form.name}
          onChange={(e) => set({ name: e.target.value })}
          required
          autoFocus={autoFocusName}
          disabled={disabled}
        />
      </div>

      <div className="form-field">
        <label className="form-field__label" htmlFor={`${idPrefix}-description`}>
          Description
        </label>
        <textarea
          id={`${idPrefix}-description`}
          className="form-field__input form-field__textarea"
          rows={3}
          value={form.description}
          onChange={(e) => set({ description: e.target.value })}
          disabled={disabled}
        />
      </div>

      <div className="form-field">
        <label className="form-field__label" htmlFor={`${idPrefix}-comparison`}>
          Comparison
        </label>
        <select
          id={`${idPrefix}-comparison`}
          className="form-field__input"
          value={form.comparison}
          onChange={(e) => set({ comparison: e.target.value })}
          disabled={disabled}
        >
          <option value="">None</option>
          {RULE_COMPARISON_OPTIONS.map((c) => (
            <option key={c.value} value={c.value}>
              {c.label}
            </option>
          ))}
        </select>
      </div>

      <div className="form-field-row">
        <div className="form-field">
          <label className="form-field__label" htmlFor={`${idPrefix}-minimum`}>
            Minimum
          </label>
          <input
            id={`${idPrefix}-minimum`}
            className="form-field__input"
            type="number"
            step={1}
            value={form.minimum}
            onChange={(e) => set({ minimum: e.target.value })}
            disabled={disabled}
          />
        </div>
        <div className="form-field">
          <label className="form-field__label" htmlFor={`${idPrefix}-maximum`}>
            Maximum
          </label>
          <input
            id={`${idPrefix}-maximum`}
            className="form-field__input"
            type="number"
            step={1}
            value={form.maximum}
            onChange={(e) => set({ maximum: e.target.value })}
            disabled={disabled}
          />
        </div>
      </div>

      <div className="form-field">
        <label className="form-field__label" htmlFor={`${idPrefix}-uom`}>
          Unit of measure
        </label>
        <input
          id={`${idPrefix}-uom`}
          className="form-field__input"
          type="text"
          value={form.uom}
          onChange={(e) => set({ uom: e.target.value })}
          disabled={disabled}
          placeholder="e.g. USD, score, employees"
        />
      </div>

      <div className="form-field">
        <label className="form-field__label" htmlFor={`${idPrefix}-status`}>
          Status
        </label>
        <select
          id={`${idPrefix}-status`}
          className="form-field__input"
          value={form.status}
          onChange={(e) => set({ status: e.target.value as RuleStatus })}
          disabled={disabled}
        >
          <option value="active">Active</option>
          <option value="inactive">Inactive</option>
        </select>
      </div>
    </>
  );
}
