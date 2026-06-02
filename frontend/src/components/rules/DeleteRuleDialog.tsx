import { useEffect, useId, useRef, useState } from "react";
import { ApiError } from "../../api/client.js";
import { deleteRule } from "../../api/rules.js";
import type { Rule } from "../../types/rule.js";

export interface DeleteRuleDialogProps {
  open: boolean;
  rule: Rule | null;
  onClose: () => void;
  onDeleted: (id: number) => void;
}

export function DeleteRuleDialog({ open, rule, onClose, onDeleted }: DeleteRuleDialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open && rule) {
      if (!dialog.open) dialog.showModal();
      setError(null);
    } else if (dialog.open) {
      dialog.close();
    }
  }, [open, rule]);

  function handleClose() {
    if (deleting) return;
    onClose();
  }

  async function handleConfirm() {
    if (!rule) return;
    setDeleting(true);
    setError(null);
    try {
      await deleteRule(rule.id);
      onDeleted(rule.id);
      onClose();
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : "Failed to delete rule.");
    } finally {
      setDeleting(false);
    }
  }

  if (!rule) return null;

  return (
    <dialog
      ref={dialogRef}
      className="rd-modal rd-modal--compact"
      aria-labelledby={titleId}
      onCancel={(e) => {
        e.preventDefault();
        handleClose();
      }}
    >
      <div className="rd-modal__panel">
        <header className="rd-modal__header">
          <h2 id={titleId} className="rd-modal__title">
            Delete rule
          </h2>
          <button
            type="button"
            className="rd-modal__close"
            aria-label="Close"
            onClick={handleClose}
            disabled={deleting}
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
          <p className="rd-modal__message">
            Delete <strong>{rule.name}</strong> (#{rule.id})? This cannot be undone.
          </p>
        </div>

        <footer className="rd-modal__footer">
          <button
            type="button"
            className="btn btn--secondary"
            onClick={handleClose}
            disabled={deleting}
          >
            Cancel
          </button>
          <button
            type="button"
            className="btn btn--danger"
            onClick={() => void handleConfirm()}
            disabled={deleting}
          >
            {deleting ? "Deleting…" : "Delete"}
          </button>
        </footer>
      </div>
    </dialog>
  );
}
