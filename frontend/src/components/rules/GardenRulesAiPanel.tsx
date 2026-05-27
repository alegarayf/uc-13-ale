import { forwardRef, useCallback, useEffect, useImperativeHandle, useState } from "react";
import { fetchRules } from "../../api/rules.js";
import { DeleteNlRuleDialog } from "./DeleteNlRuleDialog.js";
import { NlRuleFormModal } from "./NlRuleFormModal.js";
import type { Rule } from "../../types/rule.js";
import { formatRuleStatusLabel, formatRuleSummary } from "../../utils/formatRule.js";
import { isAiRule, ruleMatchesSearch } from "../../utils/ruleSearch.js";

export interface GardenRulesAiPanelHandle {
  openAddModal: () => void;
}

export interface GardenRulesAiPanelProps {
  searchQuery?: string;
}

export const GardenRulesAiPanel = forwardRef<GardenRulesAiPanelHandle, GardenRulesAiPanelProps>(
  function GardenRulesAiPanel({ searchQuery = "" }, ref) {
    const [rules, setRules] = useState<Rule[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [modalOpen, setModalOpen] = useState(false);
    const [modalMode, setModalMode] = useState<"add" | "edit">("add");
    const [editingRule, setEditingRule] = useState<Rule | null>(null);
    const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
    const [deletingRule, setDeletingRule] = useState<Rule | null>(null);

    const loadRules = useCallback(async () => {
      const data = await fetchRules();
      setRules(data.filter(isAiRule));
    }, []);

    useEffect(() => {
      let cancelled = false;

      async function load() {
        try {
          setLoading(true);
          setError(null);
          const aiRules = (await fetchRules()).filter(isAiRule);
          if (!cancelled) setRules(aiRules);
        } catch (err: unknown) {
          if (!cancelled) {
            const message = err instanceof Error ? err.message : "Failed to load";
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

    function openAddModal() {
      setModalMode("add");
      setEditingRule(null);
      setModalOpen(true);
    }

    useImperativeHandle(ref, () => ({ openAddModal }), []);

    function openEditModal(rule: Rule) {
      setModalMode("edit");
      setEditingRule(rule);
      setModalOpen(true);
    }

    const handleConfirmed = useCallback(async () => {
      try {
        await loadRules();
      } catch {
        /* best-effort refresh */
      }
    }, [loadRules]);

    function openDeleteDialog(rule: Rule) {
      setDeletingRule(rule);
      setDeleteDialogOpen(true);
    }

    const handleDeleted = useCallback((id: number) => {
      setRules((prev) => prev.filter((r) => r.id !== id));
    }, []);

    const filteredRules = rules.filter((row) => ruleMatchesSearch(row, searchQuery));

    return (
      <>
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

        {!loading && !error && rules.length > 0 && (
          <div className="rules-table-wrap">
            <table className="rules-table" aria-labelledby="rules-heading">
              <thead>
                <tr>
                  <th scope="col">Name</th>
                  <th scope="col">Summary</th>
                  <th scope="col">Status</th>
                  <th scope="col">Updated</th>
                  <th scope="col">
                    <span className="visually-hidden">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {filteredRules.length === 0 ? (
                  <tr className="rules-table__empty-row">
                    <td colSpan={5}>No rules match your search.</td>
                  </tr>
                ) : (
                  filteredRules.map((row) => (
                    <tr key={row.id}>
                      <td>
                        <span className="rules-table__name">{row.name}</span>
                        <span className="rules-table__id">#{row.id}</span>
                      </td>
                      <td className="rules-table__summary-cell">
                        <span className="rules-table__summary-text">{formatRuleSummary(row)}</span>
                      </td>
                      <td>
                        <span
                          className={`rules-table__status rules-table__status--${row.status}`}
                        >
                          {formatRuleStatusLabel(row.status)}
                        </span>
                      </td>
                      <td>{new Date(row.updated_at).toLocaleString()}</td>
                      <td className="rules-table__actions">
                        <button
                          type="button"
                          className="btn btn--text"
                          onClick={() => openEditModal(row)}
                        >
                          Edit
                        </button>
                        <button
                          type="button"
                          className="btn btn--text btn--text-danger"
                          onClick={() => openDeleteDialog(row)}
                        >
                          Delete
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        )}

        {!loading && !error && rules.length === 0 && (
          <p className="content-card__note">No rules yet. Add a rule to get started.</p>
        )}

        <NlRuleFormModal
          open={modalOpen}
          mode={modalMode}
          initialPrompt={editingRule?.nl_prompt ?? ""}
          existingRuleId={editingRule?.id}
          existingStatus={editingRule?.status}
          onClose={() => setModalOpen(false)}
          onConfirmed={handleConfirmed}
        />

        <DeleteNlRuleDialog
          open={deleteDialogOpen}
          rule={deletingRule}
          onClose={() => setDeleteDialogOpen(false)}
          onDeleted={handleDeleted}
        />
      </>
    );
  },
);
