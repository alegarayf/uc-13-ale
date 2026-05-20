import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { ApiError } from "../../api/client.js";
import { createRule, replaceRule } from "../../api/rules.js";
import { CURRENT_USER } from "../../constants/user.js";
import type { Rule } from "../../types/rule.js";
import { RuleFormFields } from "./RuleFormFields.js";
import {
  EMPTY_RULE_FORM,
  formStateToCreateInput,
  formStateToReplaceInput,
  ruleToFormState,
} from "./ruleForm.js";

export type RuleFormModalMode = "add" | "edit";

export interface RuleFormModalProps {
  open: boolean;
  mode: RuleFormModalMode;
  /** Required when mode is `edit`. */
  rule?: Rule;
  onClose: () => void;
  onSaved: (rule: Rule) => void;
}

export function RuleFormModal({ open, mode, rule, onClose, onSaved }: RuleFormModalProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const [form, setForm] = useState(EMPTY_RULE_FORM);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isEdit = mode === "edit";

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open) {
      if (!dialog.open) dialog.showModal();
      setForm(isEdit && rule ? ruleToFormState(rule) : EMPTY_RULE_FORM);
      setError(null);
    } else if (dialog.open) {
      dialog.close();
    }
  }, [open, isEdit, rule]);

  function handleClose() {
    if (submitting) return;
    onClose();
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);

    const lastUpdatedBy = CURRENT_USER.displayName;

    if (isEdit) {
      if (!rule) return;
      const payload = formStateToReplaceInput(form, lastUpdatedBy);
      if ("error" in payload) {
        setError(payload.error);
        return;
      }
      setSubmitting(true);
      try {
        const updated = await replaceRule(rule.id, payload);
        onSaved(updated);
        onClose();
      } catch (err: unknown) {
        setError(err instanceof ApiError ? err.message : "Failed to update rule.");
      } finally {
        setSubmitting(false);
      }
      return;
    }

    const payload = formStateToCreateInput(form, lastUpdatedBy);
    if ("error" in payload) {
      setError(payload.error);
      return;
    }

    setSubmitting(true);
    try {
      const created = await createRule(payload);
      onSaved(created);
      onClose();
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : "Failed to create rule.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <dialog
      ref={dialogRef}
      className="rd-modal"
      aria-labelledby={titleId}
      onCancel={(e) => {
        e.preventDefault();
        handleClose();
      }}
    >
      <form className="rd-modal__panel" onSubmit={(e) => void handleSubmit(e)}>
        <header className="rd-modal__header">
          <h2 id={titleId} className="rd-modal__title">
            {isEdit ? "Edit rule" : "Add rule"}
          </h2>
          <button
            type="button"
            className="rd-modal__close"
            aria-label="Close"
            onClick={handleClose}
            disabled={submitting}
          >
            ×
          </button>
        </header>

        <div className="rd-modal__body">
          {error && (
            <p className="rd-modal__error" role="alert">
              {error}
            </p>
          )}

          <RuleFormFields
            idPrefix={titleId}
            form={form}
            onChange={setForm}
            disabled={submitting}
            autoFocusName
          />
        </div>

        <footer className="rd-modal__footer">
          <button
            type="button"
            className="btn btn--secondary"
            onClick={handleClose}
            disabled={submitting}
          >
            Cancel
          </button>
          <button type="submit" className="btn btn--primary" disabled={submitting}>
            {submitting ? "Saving…" : isEdit ? "Save changes" : "Save rule"}
          </button>
        </footer>
      </form>
    </dialog>
  );
}
