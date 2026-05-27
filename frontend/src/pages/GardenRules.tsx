import { useRef, useState } from "react";
import { GardenRulesAiPanel } from "../components/rules/GardenRulesAiPanel.js";
import { RulesSearchBar } from "../components/rules/RulesSearchBar.js";
import { normalizeRuleSearchQuery } from "../utils/ruleSearch.js";

export function GardenRules() {
  const aiPanelRef = useRef<{ openAddModal: () => void }>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const normalizedSearch = normalizeRuleSearchQuery(searchQuery);

  return (
    <div className="page">
      <header className="page__header">
        <h1 className="page__title">Garden rules</h1>
        <p className="page__subtitle">
          Describe rules in natural language. Genie interprets your intent, you review the summary,
          and confirmed rules are saved for evaluation against opportunities.
        </p>
      </header>

      <section className="content-card" aria-labelledby="rules-heading">
        <div className="content-card__toolbar content-card__toolbar--split">
          <div className="content-card__toolbar-start">
            <h2 id="rules-heading" className="content-card__title">
              Rules
            </h2>
          </div>
          <button
            type="button"
            className="btn btn--primary"
            onClick={() => aiPanelRef.current?.openAddModal()}
          >
            Add rule
          </button>
        </div>

        <RulesSearchBar value={searchQuery} onChange={setSearchQuery} />

        <GardenRulesAiPanel ref={aiPanelRef} searchQuery={normalizedSearch} />
      </section>
    </div>
  );
}
