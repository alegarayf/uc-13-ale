import { forwardRef, useCallback, useEffect, useImperativeHandle, useState } from "react";
import { fetchNlRuleConfig, fetchNlRuleConfigs } from "../../api/nlRules.js";
import { NlRuleFormModal } from "./NlRuleFormModal.js";
import type { NlRuleConfigListItem } from "../../types/nlRule.js";

export interface GardenRulesAiPanelHandle {
  openAddModal: () => void;
}

export const GardenRulesAiPanel = forwardRef<GardenRulesAiPanelHandle>(
  function GardenRulesAiPanel(_, ref) {
    const [configs, setConfigs] = useState<NlRuleConfigListItem[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [modalOpen, setModalOpen] = useState(false);
    const [modalMode, setModalMode] = useState<"add" | "edit">("add");
    const [editingFilename, setEditingFilename] = useState<string | null>(null);
    const [initialPrompt, setInitialPrompt] = useState("");
    const [loadConfigError, setLoadConfigError] = useState<string | null>(null);

    const loadConfigs = useCallback(async () => {
      const data = await fetchNlRuleConfigs();
      setConfigs(data);
    }, []);

    useEffect(() => {
      let cancelled = false;

      async function load() {
        try {
          setLoading(true);
          setError(null);
          const configList = await fetchNlRuleConfigs();
          if (!cancelled) setConfigs(configList);
        } catch (err: unknown) {
          if (!cancelled) {
            const message = err instanceof Error ? err.message : "Failed to load";
            setError(
              message === "Failed to fetch"
                ? "Could not reach the AI API. Start it with npm run dev:ai and confirm VITE_AI_API_BASE_URL in .env."
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
      setEditingFilename(null);
      setInitialPrompt("");
      setLoadConfigError(null);
      setModalOpen(true);
    }

    useImperativeHandle(ref, () => ({ openAddModal }), []);

    async function openEditModal(row: NlRuleConfigListItem) {
      setLoadConfigError(null);
      setModalMode("edit");
      setEditingFilename(row.filename);
      try {
        const detail = await fetchNlRuleConfig(row.filename);
        setInitialPrompt(detail.prompt);
        setModalOpen(true);
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : "Failed to load rule config.";
        setLoadConfigError(message);
      }
    }

    const handleConfirmed = useCallback(async () => {
      try {
        await loadConfigs();
      } catch {
        /* best-effort refresh */
      }
    }, [loadConfigs]);

    return (
      <>
        {loadConfigError && (
          <p className="content-card__error" role="alert">
            {loadConfigError}
          </p>
        )}

        {loading && (
          <p className="content-card__note" role="status">
            Loading AI rules…
          </p>
        )}

        {error && (
          <p className="content-card__error" role="alert">
            {error}
          </p>
        )}

        {!loading && !error && configs.length > 0 && (
          <div className="rules-table-wrap">
            <table className="rules-table" aria-labelledby="rules-heading">
              <thead>
                <tr>
                  <th scope="col">Name</th>
                  <th scope="col">Summary</th>
                  <th scope="col">Updated</th>
                  <th scope="col">
                    <span className="visually-hidden">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {configs.map((row) => (
                  <tr key={row.filename}>
                    <td>
                      <span className="rules-table__name">{row.name ?? "—"}</span>
                    </td>
                    <td>{row.summary ?? "—"}</td>
                    <td>
                      {row.updatedAt
                        ? new Date(row.updatedAt).toLocaleString()
                        : row.createdAt
                          ? new Date(row.createdAt).toLocaleString()
                          : "—"}
                    </td>
                    <td className="rules-table__actions">
                      <button
                        type="button"
                        className="btn btn--text"
                        onClick={() => void openEditModal(row)}
                      >
                        Edit
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {!loading && !error && configs.length === 0 && (
          <p className="content-card__note">No AI rules yet. Add a rule to get started.</p>
        )}

        <NlRuleFormModal
          open={modalOpen}
          mode={modalMode}
          initialPrompt={initialPrompt}
          updateFilename={editingFilename ?? undefined}
          onClose={() => setModalOpen(false)}
          onConfirmed={handleConfirmed}
        />
      </>
    );
  },
);
