import { useEffect, useId, useRef, useState } from "react";
import { AiApiError } from "../../api/aiClient.js";
import { confirmNlRule, denyNlRule, interpretNlRule } from "../../api/nlRules.js";
import type { NlRuleInterpretResponse } from "../../types/nlRule.js";
import { GenieLoadingRobot } from "./GenieLoadingRobot.js";

export type NlRuleFormModalMode = "add" | "edit";

export interface NlRuleFormModalProps {
  open: boolean;
  mode: NlRuleFormModalMode;
  /** Prefill for add/edit (edit loads from saved config). */
  initialPrompt?: string;
  /** When set, confirm updates this config file instead of creating a new one. */
  updateFilename?: string;
  onClose: () => void;
  onConfirmed: (result: { configFile: string; summary: string }) => void;
}

type Step = "prompt" | "review";

export function NlRuleFormModal({
  open,
  mode,
  initialPrompt = "",
  updateFilename,
  onClose,
  onConfirmed,
}: NlRuleFormModalProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const promptId = useId();

  const [step, setStep] = useState<Step>("prompt");
  const [prompt, setPrompt] = useState("");
  const [interpretation, setInterpretation] = useState<NlRuleInterpretResponse | null>(null);
  const [denyFeedback, setDenyFeedback] = useState("");
  const [showDenyFeedback, setShowDenyFeedback] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isEdit = mode === "edit";
  const showGenieLoader =
    busy && (step === "prompt" || (step === "review" && showDenyFeedback));

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open) {
      if (!dialog.open) dialog.showModal();
      setStep("prompt");
      setPrompt(initialPrompt);
      setInterpretation(null);
      setDenyFeedback("");
      setShowDenyFeedback(false);
      setError(null);
    } else if (dialog.open) {
      dialog.close();
    }
  }, [open, initialPrompt]);

  function handleClose() {
    if (busy) return;
    onClose();
  }

  function aiErrorMessage(err: unknown): string {
    if (err instanceof AiApiError) return err.message;
    if (err instanceof Error) return err.message;
    return "Something went wrong. Is the AI service running (npm run dev:ai)?";
  }

  async function handleSubmitPrompt() {
    const trimmed = prompt.trim();
    if (!trimmed) {
      setError("Describe how you want the rule to work.");
      return;
    }
    setError(null);
    setBusy(true);
    try {
      const result = await interpretNlRule(trimmed);
      setInterpretation(result);
      setStep("review");
    } catch (err: unknown) {
      setError(aiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleConfirm() {
    if (!interpretation) return;
    setError(null);
    setBusy(true);
    try {
      const result = await confirmNlRule(interpretation.sessionId, updateFilename);
      onConfirmed({ configFile: result.configFile, summary: interpretation.summary });
      onClose();
    } catch (err: unknown) {
      setError(aiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleDeny() {
    if (!interpretation) return;
    if (!interpretation.canDeny) {
      setError("No retries left for this session. Close and start a new rule.");
      return;
    }
    setError(null);
    setBusy(true);
    try {
      const result = await denyNlRule(interpretation.sessionId, denyFeedback || undefined);
      setInterpretation(result);
      setShowDenyFeedback(false);
      setDenyFeedback("");
    } catch (err: unknown) {
      setError(aiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <dialog
      ref={dialogRef}
      className="rd-modal rd-modal--nl-rule"
      aria-labelledby={titleId}
      onCancel={(e) => {
        e.preventDefault();
        handleClose();
      }}
    >
      <div className="rd-modal__panel">
        <header className="rd-modal__header">
          <h2 id={titleId} className="rd-modal__title">
            {isEdit ? "Edit rule with AI" : "Add rule with AI"}
          </h2>
          <button
            type="button"
            className="rd-modal__close"
            aria-label="Close"
            onClick={handleClose}
            disabled={busy}
          >
            ×
          </button>
        </header>

        <div className={`rd-modal__body${showGenieLoader ? " rd-modal__body--loading" : ""}`}>
          {showGenieLoader && (
            <div className="nl-rule-modal__genie-loading" role="status" aria-live="polite">
              <GenieLoadingRobot />
              <p className="nl-rule-modal__genie-loading-text">Genie is working on your rule…</p>
            </div>
          )}

          <div
            className={showGenieLoader ? "nl-rule-modal__content--hidden" : undefined}
            aria-hidden={showGenieLoader}
          >
          {error && !showGenieLoader && (
            <p className="rd-modal__error" role="alert">
              {error}
            </p>
          )}

          {step === "prompt" && (
            <>
              <p className="nl-rule-modal__hint">
                Describe the rule in your own words. We&apos;ll send your description to Databricks
                Genie and show you a summary of what it understood so you can confirm or refine it.
              </p>
              <label className="form-field" htmlFor={promptId}>
                <span className="form-field__label">Rule description</span>
                <textarea
                  id={promptId}
                  className="nl-rule-modal__prompt"
                  rows={12}
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  disabled={busy}
                  placeholder="Example: Reject opportunities where ARR is below $1M unless the sector is healthcare and the growth rate is above 40%."
                  autoFocus
                />
              </label>
            </>
          )}

          {step === "review" && interpretation && (
            <>
              <p className="nl-rule-modal__hint">
                Does this match what you meant? Confirm to save the rule, or deny to ask Genie to try
                once more.
                {interpretation.aiMode === "mock" && (
                  <>
                    {" "}
                    <span className="nl-rule-modal__badge">Mock mode</span> — set{" "}
                    <code>DATABRICKS_GENIE_SPACE_ID</code> to use live Genie.
                  </>
                )}
              </p>

              <section className="nl-rule-modal__review" aria-labelledby={`${titleId}-summary`}>
                <h3 id={`${titleId}-summary`} className="nl-rule-modal__review-title">
                  What we understood
                </h3>
                <p className="nl-rule-modal__summary">{interpretation.summary}</p>
              </section>

              {showDenyFeedback && interpretation.canDeny && (
                <label className="form-field" htmlFor={`${promptId}-deny`}>
                  <span className="form-field__label">What should change? (optional)</span>
                  <textarea
                    id={`${promptId}-deny`}
                    className="nl-rule-modal__prompt nl-rule-modal__prompt--compact"
                    rows={3}
                    value={denyFeedback}
                    onChange={(e) => setDenyFeedback(e.target.value)}
                    disabled={busy}
                    placeholder="Tell the AI what it misunderstood…"
                  />
                </label>
              )}
            </>
          )}
          </div>
        </div>

        <footer className="rd-modal__footer">
          {step === "prompt" && (
            <>
              <button
                type="button"
                className="btn btn--secondary"
                onClick={handleClose}
                disabled={busy}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn btn--primary"
                disabled={busy || !prompt.trim()}
                onClick={() => void handleSubmitPrompt()}
              >
                {busy ? "Sending…" : "Submit"}
              </button>
            </>
          )}

          {step === "review" && interpretation && (
            <>
              <button
                type="button"
                className="btn btn--secondary"
                onClick={() => {
                  setStep("prompt");
                  setInterpretation(null);
                  setShowDenyFeedback(false);
                  setError(null);
                }}
                disabled={busy}
              >
                Back
              </button>
              {interpretation.canDeny && (
                <button
                  type="button"
                  className="btn btn--secondary"
                  disabled={busy}
                  onClick={() => {
                    if (showDenyFeedback) {
                      void handleDeny();
                    } else {
                      setShowDenyFeedback(true);
                    }
                  }}
                >
                  {busy && showDenyFeedback
                    ? "Retrying…"
                    : showDenyFeedback
                      ? "Send deny"
                      : "Deny"}
                </button>
              )}
              <button
                type="button"
                className="btn btn--primary"
                disabled={busy}
                onClick={() => void handleConfirm()}
              >
                {busy ? "Saving…" : "Confirm"}
              </button>
            </>
          )}
        </footer>
      </div>
    </dialog>
  );
}
