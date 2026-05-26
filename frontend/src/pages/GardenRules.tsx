import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { fetchApiConfig } from "../api/config.js";
import { fetchRules } from "../api/rules.js";
import { GardenRulesAiPanel } from "../components/rules/GardenRulesAiPanel.js";
import { DeleteRuleDialog } from "../components/rules/DeleteRuleDialog.js";
import { RuleFormModal } from "../components/rules/RuleFormModal.js";
import { RulesEditorModeToggle } from "../components/rules/RulesEditorModeToggle.js";
import { useRulesEditorMode, type RulesEditorMode } from "../hooks/useRulesEditorMode.js";
import type { Rule } from "../types/rule.js";
import { formatRuleCriteria, formatRuleStatusLabel } from "../utils/formatRule.js";

export function GardenRules() {
  const [searchParams] = useSearchParams();
  const urlMode = searchParams.get("mode");
  const initialMode: RulesEditorMode | undefined =
    urlMode === "ai" ? "ai" : urlMode === "form" ? "form" : undefined;
  const [editorMode, setEditorMode] = useRulesEditorMode(initialMode);

  const [rules, setRules] = useState<Rule[]>([]);
  const [dataStore, setDataStore] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [formModalOpen, setFormModalOpen] = useState(false);
  const [formModalMode, setFormModalMode] = useState<"add" | "edit">("add");
  const [editingRule, setEditingRule] = useState<Rule | null>(null);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [deletingRule, setDeletingRule] = useState<Rule | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        setLoading(true);
        setError(null);
        const [config, data] = await Promise.all([fetchApiConfig(), fetchRules()]);
        if (!cancelled) {
          setDataStore(config.dataStore);
          setRules(data);
        }
      } catch (err: unknown) {
        if (!cancelled) {
          const message = err instanceof Error ? err.message : "Failed to load rules";
          setError(
            message === "Failed to fetch"
              ? "Could not reach the API. Start it with npm run dev (or npm run dev:api) and confirm VITE_API_BASE_URL in .env."
              : message,
          );
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  const handleRuleSaved = useCallback((rule: Rule) => {
    setRules((prev) => {
      const idx = prev.findIndex((r) => r.id === rule.id);
      if (idx === -1) return [...prev, rule].sort((a, b) => a.id - b.id);
      const next = [...prev];
      next[idx] = rule;
      return next;
    });
  }, []);

  const handleRuleDeleted = useCallback((id: number) => {
    setRules((prev) => prev.filter((r) => r.id !== id));
  }, []);

  function openAddModal() {
    setFormModalMode("add");
    setEditingRule(null);
    setFormModalOpen(true);
  }

  function openEditModal(rule: Rule) {
    setFormModalMode("edit");
    setEditingRule(rule);
    setFormModalOpen(true);
  }

  function openDeleteDialog(rule: Rule) {
    setDeletingRule(rule);
    setDeleteDialogOpen(true);
  }

  const isFormMode = editorMode === "form";
  const aiPanelRef = useRef<{ openAddModal: () => void }>(null);

  return (
    <div className="page">
      <header className="page__header">
        <h1 className="page__title">Garden rules</h1>
        <p className="page__subtitle">
          Define and manage criteria that shape how opportunities are evaluated. Use the form editor
          for classic rules, or AI to describe rules in natural language.
        </p>
      </header>

      <section className="content-card" aria-labelledby="rules-heading">
        <div className="content-card__toolbar content-card__toolbar--split">
          <div className="content-card__toolbar-start">
            <h2 id="rules-heading" className="content-card__title">
              Rules
            </h2>
            <RulesEditorModeToggle mode={editorMode} onChange={setEditorMode} disabled={loading} />
          </div>
          {isFormMode ? (
            <button type="button" className="btn btn--primary" onClick={openAddModal}>
              Add rule
            </button>
          ) : (
            <button
              type="button"
              className="btn btn--primary"
              onClick={() => aiPanelRef.current?.openAddModal()}
            >
              Add rule with AI
            </button>
          )}
        </div>

        {loading && (
          <p className="content-card__note" role="status">
            Loading rules…
          </p>
        )}

        {error && (
          <p className="content-card__error" role="alert">
            {error}
          </p>
        )}

        {isFormMode ? (
          <>
            {!loading && !error && rules.length > 0 && (
              <div className="rules-table-wrap">
                <table className="rules-table">
                  <thead>
                    <tr>
                      <th scope="col">Rule</th>
                      <th scope="col">Description</th>
                      <th scope="col">Criteria</th>
                      <th scope="col">Status</th>
                      <th scope="col">
                        <span className="visually-hidden">Actions</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {rules.map((rule) => (
                      <tr key={rule.id}>
                        <td>
                          <span className="rules-table__name">{rule.name}</span>
                          <span className="rules-table__id">#{rule.id}</span>
                        </td>
                        <td>{rule.description ?? "—"}</td>
                        <td>{formatRuleCriteria(rule)}</td>
                        <td>
                          <span
                            className={`rules-table__status rules-table__status--${rule.status}`}
                          >
                            {formatRuleStatusLabel(rule.status)}
                          </span>
                        </td>
                        <td className="rules-table__actions">
                          <button
                            type="button"
                            className="btn btn--text"
                            onClick={() => openEditModal(rule)}
                          >
                            Edit
                          </button>
                          <button
                            type="button"
                            className="btn btn--text btn--text-danger"
                            onClick={() => openDeleteDialog(rule)}
                          >
                            Delete
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {!loading && !error && rules.length === 0 && (
              <p className="content-card__note">
                No rules returned from the API
                {dataStore ? ` (data store: ${dataStore})` : ""}.{" "}
                {dataStore === "memory"
                  ? "The in-memory store should include seed rules — try restarting the API."
                  : dataStore === "databricks"
                    ? "The Databricks table may be empty. Add rows in the warehouse, or set DATA_STORE=memory in .env for local seed data."
                    : "Check that the rules table exists and contains rows."}
              </p>
            )}
          </>
        ) : (
          !loading && !error && <GardenRulesAiPanel ref={aiPanelRef} />
        )}
      </section>

      <RuleFormModal
        open={formModalOpen}
        mode={formModalMode}
        rule={editingRule ?? undefined}
        onClose={() => setFormModalOpen(false)}
        onSaved={handleRuleSaved}
      />

      <DeleteRuleDialog
        open={deleteDialogOpen}
        rule={deletingRule}
        onClose={() => setDeleteDialogOpen(false)}
        onDeleted={handleRuleDeleted}
      />
    </div>
  );
}
