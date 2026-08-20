# Normative reference (eval program)

Distilled excerpt of the (now largely executed) [eval-consolidation-program spec](../../.dev/specs/eval-consolidation-program/spec.md). Kept here because the schema contracts and controlled vocabularies below are not fully captured elsewhere — generated artifacts and validators encode them, but this is the human-readable contract map.

---

## Schema contracts

Authoritative shapes live in code and committed data; this section names fields and meaning only where prose adds context.

### Registry row (`registry.yaml`)

Top-level `schema_version: 1` plus an `items` list. Each item tracks one eval-program work item.

| Field | Meaning |
|---|---|
| `id` | Stable id (`<stage>-<seq>`, `EXT-<seq>`, `ACC-<slug>`, etc.). |
| `title` | Human label. |
| `source_refs` | Provenance anchors (briefing, OPEN_ITEMS, audits). |
| `source_id` | Join key to `source_manifest.yaml` (`manifest.id`); required on import-created rows, `null` on post-import rows. |
| `disposition` | `staged` \| `deferred` \| `rejected` \| `accepted`. |
| `stage` | Stage id when `disposition: staged`; otherwise `null`. |
| `status` | Lifecycle status; must match disposition per §7.1 matrix (`n/a` when not staged). |
| `trigger` | Required when `deferred` — what must become true to revisit. |
| `rationale` | Required when `rejected` or `accepted`; may record a ratification on staged rows. |
| `tshirt` | Gate-time estimate (`S` \| `M` \| `L`). |
| `evidence_refs` | Run ids, SHAs, paths; required non-empty when `status: closed`. |
| `rung_assignments` | Map `surface → rung` from S2 pre-plan (items 23/23a/26a). |
| `assessment_metrics` | Map `surface → {figure: float}` calibration outcomes for judge/human gates. |

**Authoritative sources:** [`eval/program/registry.yaml`](registry.yaml) (instance), [`validate_registry_manifest()`](../../eval/retrieval/tests/test_eval_program_registry.py) (spec §17 item 2a validator), [`eval/program/source_manifest.yaml`](source_manifest.yaml) (import-time join partner).

### Trust-statement row (generated)

One row per `(company, layer, surface)` cross-product. Regenerated — never hand-edited.

| Field | Meaning |
|---|---|
| `company` | Canonical slug from the four-step fold (see [`canonical_company_slug()`](../../eval/retrieval/companies.py)). |
| `layer` | Trust layer (`ingest_completeness`, `retrieval`, `agent_fields`, `e2e`, `content_correctness`). |
| `surface` | Content surface when `layer == content_correctness`; otherwise `null`. |
| `attestation` | Overall attestation for that cell (§16 vocabulary). |
| `reason` | Why not fully attested; required iff `attestation != attested`. |
| `method` | Ingest probe backend when a §8.4 probe was obtained; otherwise `null`. |
| `rung` | Evidence class behind attestation on content rows; required for `attested`/`partial` content rows. |
| `evidence_refs` | Pointers to runs, baselines, signoffs, score tables. |
| `known_gaps` | Human-readable gap notes (ingest fraction may appear here as prose). |
| `manual_check` | Where to double-check when attestation is below `attested`. |

**Authoritative sources:** [`TrustStatementRow`](../../eval/retrieval/trust_statement.py) and [`validate_row()`](../../eval/retrieval/trust_statement.py) (generation contract), [`eval/program/trust_statement.md`](trust_statement.md) (generated instance).

### S2 score row (`uc13_ale.eval.s2_scores`)

Append-only Delta table; two row classes share run grain (`run_id`, `run_ts`).

**Claim row (`row_type: claim`):** `company`, `surface`, `claim_id`, `verdict`, optional `rationale`, numeric fields (`asserted_*`, `extracted_*`, `cited_*`) when surface is numeric at rung 2, optional `judge_verdict_advisory`. Claim columns null on marker rows.

**Completion marker (`row_type: completion_marker`):** same run keys plus `writer`; all claim columns null. Marker presence is the run-completion predicate.

**Authoritative sources:** [`S2ScoreRow`](../../eval/content/s2_writer.py) and validators in [`eval/content/s2_writer.py`](../../eval/content/s2_writer.py) (`_validate_claim_row`, `_validate_marker_row`).

### Exemption store row (`eval_exemptions.yaml`)

Annotations for intent-level corpus gaps; keeps cross-company comparison honest without fabricating gold.

| Field | Meaning |
|---|---|
| `company` | Canonical slug at write time. |
| `intent_id` | Intent from the 57-intent registry. |
| `surface` | Content surface affected, or `null` if retrieval/gold only. |
| `coverage` | `eliminates` \| `narrows` \| `null` — required iff `surface` is non-null. |
| `reason` | `corpus_absent` \| `corpus_thin` \| `overlay_mismatch`. |
| `corpus_evidence` | Structured evidence backing the exemption. |
| `approved_by` | Approver id (e.g. `operator`). |

Three disjoint cases: `eliminates` → `known_gap`, no S2 run; `narrows` → S2 runs, failures become `partial` + `exempted_corpus_failures`; `surface: null` → no content-row effect.

**Authoritative sources:** [`IntentExemption`](../../eval/retrieval/exemptions.py) and [`_validate_exemption_fields()`](../../eval/retrieval/exemptions.py), [`eval/program/eval_exemptions.yaml`](eval_exemptions.yaml).

---

## Comparison principles

In the consolidation spec, **comparison rules are Principle 12** (spec §3), not spec §12 (which documents S2/C6 subsystems). Run these checks when adding or reviewing any comparator, threshold, or cross-artifact join.

### Principle 12 — five review clauses

1. **12.1 — State the predicate.** For every comparison, state the predicate, how its parts compose into a decision, and what makes each input a member of the comparison space.
2. **12.2 — No free half.** No half of a compound measure may be satisfiable without performing the task the measure exists to observe.
3. **12.3 — Representation and producible region.** State the representation the predicate uses; both producers must be able to populate the same region of that space (exact decimals for numeric magnitudes — no binary float; MVP locator kinds `page` and `section` only).
4. **12.4 — Producibility of inputs, outputs, and scopes.** Every required input must be producible by its assigned producer; every required output must exist on every path the predicate reaches; quantifiers must be evaluable over their stated scope.
5. **12.5 — Counterpart producer (diff-time).** Every obligation on one side of a comparison must appear on the other side or be explicitly exempted; for human vs machine pairs, state the human side first. Check *branches*, not just field names — both sides must split cases the same way.

**12.C — Standing charter check (Phase 3).** After a diff, look for rules that are individually correct but jointly wrong because a third predicate joins them. This class is not closed by adding more within-rule text.

### Operational comparison caveats

| Comparison | Valid when | Invalid or misleading when |
|---|---|---|
| **Harness baseline / retrieval metrics** | Same `gold_snapshot`, `registry_hash`, and `ingestion_snapshot` (inherited `compare()` pins). Forced re-baseline is the only override. | Different ingestion epoch, gold revision, or registry hash — `IngestionSnapshotMismatchError` is expected, not a harness bug. |
| **Cross-company trust rows** | Same layer and surface grain; exemption store documents corpus gaps (`known_gap`, `exempted_corpus_failures`). | Treating `partial` on Clearsulting Legal the same as Elder Care without reading exemptions; comparing companies outside the derived domain union (baseline-complete ∪ exemption companies). |
| **Cross-epoch trust / S2 scores** | Same company slug, same surface, latest **marker-complete** run per §9 dedup rules; note `run_id` time-sortability. | Mixing claim rows from different runs on one surface; comparing `rung` or attestation without checking writer/marker provenance. |
| **Ingest completeness over time** | Qualitative review of `known_gaps` prose and `method` backend marker. | Machine diff of completeness fraction in `known_gaps` alone — fraction is prose at MVP, not a typed field (DG-12). Rows with different `method` values (`sql_chunk_count` vs `doc_status`) measure different semantics. |
| **S2 numeric transcription** | Same surface class (`fta_numeric` is numeric; others are not); comparator uses §16 unit scale table; both halves of transcription agreement measured separately on numeric surfaces. | Comparing magnitudes across incompatible units without normalization; treating `unsupported` spans as equivalent across causes (a) no span vs (b)/(c) span without typable value. |
| **Calibration / gate metrics** | `assessment_metrics` figures match surface class (verdict agreement vs value/span/locator fractions). | Using numeric-surface figures on non-numeric surfaces or vice versa (forbidden figure sets in item 2a validator). |

---

## Attestation vocabulary

Closed sets unless marked *scaffolded*. Generation and write paths fail closed on unknown values (Principle 7).

### Trust-statement `attestation`

| Value | Definition |
|---|---|
| `attested` | Layer/surface meets its attestation bar; `reason` must be `null`. |
| `partial` | Evidence exists but some claims or corpus completeness fell short; `reason` required. |
| `not_attested` | No qualifying evidence (no run, probe failed, etc.); `reason` required. |
| `known_gap` | The gap itself is the attested fact (e.g. exempted surface with no S2 run). |

### Trust-statement `reason`

| Value | Definition |
|---|---|
| `no_completed_run` | No marker-complete S2 or layer run exists. |
| `zero_claim_run` | Marker-complete run with zero claim rows. |
| `claim_failures` | `partial` due to per-claim `contradicted` or `unsupported` verdicts. |
| `exempted_corpus_failures` | `partial` on a surface with §8.3 `coverage: narrows` exemption. |
| `incomplete_corpus` | Ingest completeness below full (non-1.0 measured). |
| `probe_unavailable` | Ingest probe failed (`status: probe_failed`). |
| `denominator_undefined` | Expected document count undefined. |
| `unnormalizable_company` | Display name folds to empty on read path (`__unnormalizable__` sentinel). |
| `corpus_absent` / `corpus_thin` / `overlay_mismatch` | Also used on `known_gap` rows from exemption store (severity: absent > thin > overlay). |

### Trust-statement `rung` and ingest `method`

| Vocabulary | Values | Definition |
|---|---|---|
| `rung` | `deterministic`, `judge`, `human`, `null` | Evidence ladder step behind a content attestation; `null` when no evidence class applies. |
| `method` / preflight `backend` | `sql_chunk_count`, `doc_status`, `null` | Which ingest backend produced the row; required only when a probe record was obtained. |

### S2 and exemption vocabularies (selected)

| Vocabulary | Values | Definition |
|---|---|---|
| Claim `verdict` | `supported`, `contradicted`, `unsupported` | Pass/fail partition uniform across rungs; numeric rung 2 comparator writes `verdict`. |
| S2 `writer` | `deterministic_verifier`, `judge_harness`, `human_spot_check` | Run provenance on completion marker; maps to trust `rung`. |
| Exemption `coverage` | `eliminates`, `narrows`, `null` | Whether exemption removes a surface from S2 scope or relabels failures. |
| Trust `layer` | five layers (see schema) | *Scaffolded* — unrecognized values halt generation. |
| Trust `surface` | `fta_numeric`, `legal_register`, `exec_summary`, `null` | Content correctness sub-key; only `fta_numeric` is classed numeric. |

Full enumeration table (dispositions, statuses, numeric units, locator kinds, row types, etc.): spec §16. Runtime constants mirror it in [`eval/retrieval/trust_statement.py`](../../eval/retrieval/trust_statement.py) (`ATTESTATIONS`, `REASONS`, `RUNGS`, `METHODS`), [`eval/content/s2_writer.py`](../../eval/content/s2_writer.py) (`CLAIM_VERDICTS`, `WRITERS`, `NUMERIC_UNITS`, `LOCATOR_KINDS`), and [`eval/retrieval/exemptions.py`](../../eval/retrieval/exemptions.py).

---

Source: `.dev/specs/eval-consolidation-program/spec.md` (excerpt)
