import type { RuleFormState } from "./ruleForm.js";

export interface RuleFormFieldsProps {
  idPrefix: string;
  form: RuleFormState;
  set: (patch: Partial<RuleFormState>) => void;
  disabled?: boolean;
}

export function RuleFormFields({ idPrefix, form, set, disabled }: RuleFormFieldsProps) {
  return (
    <>
      <label className="form-field" htmlFor={`${idPrefix}-name`}>
        <span className="form-field__label">Name</span>
        <input
          id={`${idPrefix}-name`}
          type="text"
          className="form-field__input"
          value={form.name}
          onChange={(e) => set({ name: e.target.value })}
          disabled={disabled}
          required
        />
      </label>

      <label className="form-field" htmlFor={`${idPrefix}-description`}>
        <span className="form-field__label">Description</span>
        <textarea
          id={`${idPrefix}-description`}
          className="form-field__input"
          rows={3}
          value={form.description}
          onChange={(e) => set({ description: e.target.value })}
          disabled={disabled}
        />
      </label>

      <label className="form-field" htmlFor={`${idPrefix}-status`}>
        <span className="form-field__label">Status</span>
        <select
          id={`${idPrefix}-status`}
          className="form-field__input"
          value={form.status}
          onChange={(e) => set({ status: e.target.value as RuleFormState["status"] })}
          disabled={disabled}
        >
          <option value="active">Active</option>
          <option value="inactive">Inactive</option>
        </select>
      </label>
    </>
  );
}
