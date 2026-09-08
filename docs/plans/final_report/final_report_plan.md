# UC13 — Final Diligence Report + full-VDR MPS + UI progress signal · Plan

> **Step 0 deliverable** for `CLAUDE_CODE_PROMPT_final_report_and_progress.md`.
> Branch: `feature/uc13-final-report-and-progress` (cut from `feature/anthropic-sdk-migration`).
> Working catalog: **`uc13_preview`**. `uc13` is not touched.
>
> **Status: awaiting review.** No production code has been written yet. The
> executable task files live in [`tasks/`](tasks/) and are meant to be run in
> order; each one closes its own line in §10 (Definition of Done).
>
> **Merged with `feature/anthropic-sdk-migration` on 2026-09-07.** This branch was
> cut from `31878cc` (Sep 3), one day before the 2026-09-04 executive-review format
> work landed (`b0998c9` sale process / key partners / core business / numeric
> fixes, `ad6d009` page-1 pagination). Those two commits are now merged in, and the
> findings below were **re-verified against the merged tree** — suite green,
> 1205 passed / 38 skipped. Three findings changed; they are marked
> *(re-verified 2026-09-07)*.

---

## 1. What was read, and what the code actually says

Everything in §8 of the task prompt was read before this plan was written. Four
findings changed the design, so they are recorded here rather than in a task file.

### 1.1 `_mps_table` is genuinely column-generic — verified, not assumed

`rainmaker_view.py:743` `_mps_table(mps_runs)` iterates `mps_runs`, appending one
`{"header": …}` per run to `columns`, one `mps_total(scores)` per run to
`total_cells`, and one cell per run to each row's `score_cells`. Threshold,
verdict, `mps_status`, `degraded_reason` and the commentary bullets all come from
`mps_runs[-1]` (`rainmaker_view.py:786-789`, `:805`). The ER template loops
`mps.columns` / `row.score_cells` / `mps.total_cells`
(`rainmaker_opportunity_summary.html.j2:338, :348, :364`), so **two runs render as
two score columns and two total cells with no template change.**

Consequence for ordering: pass `[cim_run, full_run]`, never the reverse. The
*last* run owns the verdict, the threshold, and the commentary — and the verdict
we want on the page is the one scored over the whole data room.

### 1.2 The CIM-stage MPS run must be read back from Delta, not held in memory

`build_rainmaker_summary` returns only `{"html", "pdf", "synthesis_status",
"mps_status"}` (`rainmaker_entry.py:76-80`) — the MPS run dict itself is discarded.
`rainmaker_entry.py` is read-only for this task, so there is no in-memory route to
the CIM run.

The Delta route works. `mps_agent.py:454-488` persists `run_mode`, `generated_at`,
`total`, `threshold`, `verdict`, `mps_status`, `categories_json`, `cim_detected`,
`retrieval_used` to `{catalog}.analysis.mps_score`, append-only, one row per
generation. Rehydrating `{"run_mode", "generated_at", "categories":
json.loads(categories_json), "threshold", "mps_status"}` is exactly the shape
`_mps_table` consumes for a non-last column.

**Answer to §8 question 2: yes.** One caveat, and it is harmless: `degraded_reason`
is *not* a persisted column, so a rehydrated run carries `degraded_reason=None`.
That value is only read off `mps_runs[-1]`, and the CIM run is never last.

### 1.3 Stage-2 ingestion really does skip what the CIM pass already parsed

`parse_manifest.py:350-370`: a doc is re-queued only when `force_all`, or its
`doc_id` is in `force_ids`, or its `source_mtime`/`source_size` differ from
`doc_status`; a doc whose `status == COMPLETE` and whose stat is unchanged is
skipped. Stage 2 passes **no** `force`, so the CIM documents parsed in stage 1
(which ran with `force="company"`) are skipped rather than re-parsed.

**Answer to §8 question 1: yes**, for the parse step. Two costs that are *not*
skipped and should be expected in stage-2 wall-clock: `download_upload` re-lists
and re-downloads the whole room, and `document_classifier` re-classifies it.
Neither is avoidable without touching `run_ingestion_pipeline` (out of scope).

**The CIM stays in scope for stage 2 — "skipped" means "not re-parsed", not
"excluded".** Its chunks and embeddings from stage 1 are never deleted (the
per-doc clean only runs when a doc is actually re-parsed), stage 2 passes no
`file_whitelist`, and so the agents retrieve over the CIM *plus* everything else.
The final report and its MPS are scored over the whole room, CIM included — which
is what makes the two MPS columns comparable.

One dependency worth knowing, because it is not obvious: `retrieval.py` takes
`priority_tier` from `classification.doc_relevance` via a JOIN, and one of its
query paths also filters `r.should_parse = true` (`retrieval.py:168-208`). So the
CIM's presence in stage-2 retrieval depends on the row the **stage-2** classifier
wrote for it, not on stage-1 state. A CIM classified as tier 1 with
`should_parse=true` — the normal and expected outcome, and exactly what already
happens on Branch B today for any CIM-bearing room — is fully in scope. T10's
operator checklist verifies it on the first real run rather than assuming it.

### 1.4 None of the eight bundle fields the view layer wants exist today

Grepped against `field_mapping.py`, `bundle_builder.py` and `populate.py`:

| Field the view reads | Exists? | Nearest thing that does exist |
|---|---|---|
| `financials.segment_performance` | ✗ | `revenue_by_segment` (field_mapping.py:223) |
| `financials.forecast_rows` | ✗ | — |
| `financials.forecast_assumptions` | ✗ | — |
| `financials.growth_bridge` | ✗ | — |
| `revenue_quality.revenue_type_mix` | ✗ | — |
| `revenue_quality.client_distribution` | ✗ | `clients` (field_mapping.py:523) |
| `qoe.addbacks` | ✗ | `addback_schedule` (field_mapping.py:586) |
| `diligence_questions[].why_it_matters` | ✗ | — |

Per §4.1 of the prompt: where the difference is a **rename with a compatible
shape**, the view layer reads the existing name; where the field genuinely does
not exist, the section renders its "not extracted" state and the field goes on the
follow-up list in §9. **T02 does that audit shape-by-shape and is the only task
allowed to touch those reads.** Nothing is invented in the view layer.

**The gap is wider than the eight fields the prompt named.** A spot-check of other
fields the view reads found more with no producer anywhere in the bundle layer —
`revenue_quality.top_customers` (the top-customer table on p.5),
`revenue_quality.client_count` (a customer tile), `legal.coc_consent_count` (a
legal tile). So T02's audit is scoped to **every** bundle path
`final_report_view.py` reads, not just the eight; the eight are a starting list,
not the boundary.

*(Re-verified 2026-09-07, post-merge: the eight are still all absent under those
names.)*

**`customer_tenure` is a shape problem, not an absence** *(re-verified
2026-09-07)*. The CQA agent does emit `customer_tenure.average_tenure_years` and
`tenure_distribution_note`, but `field_mapping._retention_note_from_cqa`
(`field_mapping.py:532-554`) folds them into a single flattened **note string**
rather than carrying the dict onto the bundle. `final_report_view` reads
`(rq.get("customer_tenure") or {}).get("average_tenure_years")` — a dict. So the
figure exists one layer below and never arrives in a usable form. Same class of
problem as D-03: not a rename T02 can fix inside the view.

**Opportunity the 2026-09-04 work opened.** That commit added
`company_framing.business_description`, `sale_process`, `key_partners` and
`key_dependencies` to the bundle (`field_mapping.py`, +67 lines), and the
executive review now names the sale process and the partners on its cover. **The
final report template reads none of them.** Naming how the business is being sold,
and who it depends on, belongs on the final report's business page at least as much
as on the ER's cover. Not in scope for the tasks as written — recorded as F-6.

**T02 close-out (2026-09-07) — full audit, RENAME/RESHAPE/ABSENT.** Every
`bundle.get(...)` path `final_report_view.py` reads was traced through
`field_mapping.py`, `populate.py` and `bundle_builder.py` back to the
workstream agent that would produce it. Result: **zero RENAME, zero RESHAPE —
every field is ABSENT.** The "candidate existing names" T02's task file
suggested as leads (`revenue_by_segment` at a stated `field_mapping.py:223`,
`clients` at a stated `field_mapping.py:523`) do not exist in the current
tree under those names or at those lines — verified by direct grep, not
assumed from the task file's leads.

| # | View reads | Producer traced to | Verdict | Justifying line |
|---|---|---|---|---|
| 1 | `financials.segment_performance` / `segment_dimension` | `RevenueSubAgent` → `revenue_by_segment` (`revenue_sub_agent.py:71-79`) lands as `bundle.financials.geographic_mix` (`field_mapping.py:758`), a **different key**, with keys `segment/revenue_pct/revenue_dollars` — no `gross_margin_pct`, `growth_pct`, `read_label`, or `read` (severity) exist anywhere in the pipeline | ABSENT | `field_mapping.py:758`; zero hits for `segment_performance`/`segment_dimension` as a writer |
| 2 | `financials.forecast_rows` | `forecast_agent.py` writes `revenue_build_comparison` to `{catalog}.analysis.forecast`; `BundleBuilder` never reads that table (`constants.py:4-11` omits `forecast`) | ABSENT — **SUPPLIED-BY-T05** (D-03, §1.5) | zero hits in `field_mapping.py`/`bundle_builder.py`/`populate.py` |
| 3 | `financials.forecast_assumptions` | same as #2 | ABSENT — **SUPPLIED-BY-T05** | zero hits, same files |
| 4 | `financials.growth_bridge` | No producer anywhere names or shapes a revenue/EBITDA bridge for the bundle. (`quality_of_earnings_agent.py`'s `_tool_retrieve_ebitda_bridge` is a retrieval query, not an extraction field.) | ABSENT | zero hits outside the reader at `final_report_view.py` |
| 5 | `revenue_quality.revenue_type_mix` | `customer_quality_agent.py:211-213,295-300` extracts a **dict** (`recurring_pct`/`project_onetime_pct`/`retainer_pct`), not a list of mix segments; never copied into the bundle by `_revenue_quality_from_agents` (`field_mapping.py:617-640`) | ABSENT (would additionally need a RESHAPE — dict → list — if wired) | `field_mapping.py:617-640` |
| 6 | `revenue_quality.client_distribution` | No producer; `_revenue_quality_from_agents` returns only `scale_narrative`/`concentration`/`end_market_mix`/`retention_notes` | ABSENT | `field_mapping.py:617-642` |
| 7 | `qoe.addbacks` | `EbitdaSubAgent` → `addback_schedule.items` (`ebitda_sub_agent.py:56-65`, wrapped `financial_trends_agent.py:1651-1654`); `_qoe_from_snapshots` (`field_mapping.py:645-657`) copies only `addback_pct_of_ebitda`, never `items`. Even if wired: items carry `description`/`amount_stated`, not `label`/`amount`, and **no `tier` field exists anywhere in the schema** | ABSENT | `field_mapping.py:645-657` |
| 8 | `diligence_questions[].why_it_matters` | `GapAggregator.build_diligence_questions()` (`bundle_builder.py:553-588`) emits exactly `category`/`question`/`priority`/`source_agent`/`fill_state` — no rationale string exists upstream (legal's `recommended_diligence` carries only `doc_type`/`priority`/`item_id`) to even rename | ABSENT | `bundle_builder.py:553-588` |
| — | `revenue_quality.top_customers` | CQA extracts `top_customers` (`customer_quality_agent.py:228`) but `_revenue_quality_from_agents` never copies it into the bundle | ABSENT | `field_mapping.py:617-640` |
| — | `revenue_quality.client_count` | No producer anywhere | ABSENT | grep, zero writer hits |
| — | `revenue_quality.customer_tenure` | Shape problem, not absence — see above. CQA's `average_tenure_years`/`tenure_distribution_note` are flattened into the string `retention_notes` by `_retention_note_from_cqa` (`field_mapping.py:532-554`); the dict shape the view reads never reaches the bundle | ABSENT under this key | `field_mapping.py:532-554` |
| — | `legal.coc_consent_count` | Computed as a local variable inside `legal_contracts_agent.py` (~:1707-1922) for a narrative sentence only; never persisted to Delta or copied by `_build_legal_block` (`field_mapping.py:697-718`) | ABSENT | `field_mapping.py:697-718` |

Since every field is ABSENT, **no read in `final_report_view.py` changed** —
each section keeps rendering its "not extracted" state exactly as before (T02
step 4). What did change, all inside `final_report_view.py` only:

- Adopted `rainmaker_view._financial_periods` (chronological sort by
  `_period_sort_year`, unparseable labels kept in relative order after the
  parseable ones — never dropped, never guessed at) and
  `rainmaker_view._normalize_period_units` (rescales a period extracted in a
  different unit than its neighbours) inside `_pnl_table`, so the P&L
  column order and figures agree with the executive review's table built
  from the same bundle (§1.6, DoD-14).
- Adopted `rainmaker_view._unit_label` as the computed fallback behind the
  (currently never-populated) `bundle.financials.unit_label` read (A-3-style
  future-proofing — a future producer wins over the computed value).
- `parse_percent` now delegates to `rainmaker_view._parse_percent` — proven
  behaviourally equivalent on a 16-input comparison sweep
  (`tests/test_final_report_numeric_parity.py`). `parse_money` stays
  **inline**: it disagrees with `rainmaker_view._parse_money` on magnitude
  suffixes (`"2k"` → `0.002` here vs `2.0` there; `"1.5bn"`/`"1.5b"` →
  `1500.0` here vs `1.5` there — this module applies the suffix multiplier,
  `rainmaker_view`'s does not). Per the task's rule, a disagreement means
  keep the inline copy and record the divergence here rather than silently
  changing behaviour; the divergence is pinned as a test, not just asserted
  in prose.
- Added `_ASSUMPTION_SUPPORT_CLASS`/`_ASSUMPTION_SUPPORT_LABEL` (module
  constants next to `_SEVERITY_CLASS`) translating the forecast agent's
  `Supported`/`Plausible`/`Stretch` rubric onto the template's
  `high`/`medium`/`low` severity classes, for when T05's injected
  `forecast_assumptions` start arriving. An unrecognised value degrades to
  `neutral`, never `high`.
- `final_report_view()` gained the additive `run_mode: str | None = None`
  parameter (A-3): the cover's `mode_label` now reads the caller-supplied
  branch fact first, falling back to `meta.get("run_mode")` (which
  `bundle_builder.py` never populates) only when the parameter is omitted —
  so the function stays usable standalone.

**Evidence:** `git diff --stat` shows only `final_report_view.py` modified
(plus the new `tests/test_final_report_numeric_parity.py`); every read-only
file in §7 shows zero diff; `pytest tests/ -q`: 1241 passed / 38 skipped
(1205 passed baseline + 36 new parametrized parity tests, no regressions, no
skips added or removed).

### 1.5 The forecast page has no data path at all — bigger than a rename

`forecast_agent.py` genuinely extracts what page 8 wants: `forecast_assumptions`,
`revenue_build`, `haircut_revenue_by_period`, assumption credibility, downside
sensitivities. It writes them to `{catalog}.analysis.forecast`.

But **`BundleBuilder` never reads that table.** `AGENT_DELTA_TABLE_SUFFIXES`
(`constants.py:4-11`) lists six agents — business_model, financial_trends,
customer_quality, kpi, legal, quality_of_earnings — and `forecast` is not among
them; `field_mapping.py` does not mention forecast anywhere (zero hits). So the
data exists in Delta and never reaches the bundle. This is not a rename T02 can
resolve.

Three ways out, in increasing order of blast radius:

1. **Read it in `build_final_report` and inject.** That function has `spark`, and
   the bundle it holds is a plain dict. It can read `{catalog}.analysis.forecast`
   and add `financials.forecast_rows` / `forecast_assumptions` to *its own* copy
   before rendering. Additive, contained in a module we own, touches nothing
   read-only, and leaves the ER's bundle exactly as it is. **Recommended.**
2. Extend `constants.py` + `field_mapping.py` so every consumer gets it. Wider
   reach, and it changes the bundle the ER is built from — `bundle_builder.py` is
   read-only and `validate_bundle` runs over the result, so this needs care.
3. Leave page 8 rendering "not extracted" and list it as follow-up.

**DECIDED (Hector, 2026-09-07): option 1 — read it in `build_final_report`.**
Owned by [T05](tasks/T05_final_report_entry.md).

The mapping was verified against the agent before deciding, and it is mostly
renames:

| The view wants | `analysis.forecast` already has |
|---|---|
| `forecast_rows[].year` / `.revenue` | `revenue_build_comparison[].period` / `.forecast_revenue` |
| `forecast_rows[].ebitda_margin_pct` | — nothing projects margin anywhere in the pipeline (verified: `forecast_agent` only touches EBITDA in downside sensitivities, and `OpexSubAgent` *queries* for projected P&L pages but its extraction schema keeps only opex/cost-structure fields). Stays `None`; see §1.7 |
| `forecast_assumptions[].assumption` | `forecast_assumptions[].description` (fall back to `.stated_value`) |
| `forecast_assumptions[].support` | `.credibility_rating` — **Supported / Plausible / Stretch** |
| `forecast_assumptions[].test` | `management_validation_items_json` |

The only thing to build is the translation from `Supported/Plausible/Stretch` to
the template's severity classes, which speak `high/medium/low`. That mapping lives
in `final_report_view.py` (ours), stated once, as a module constant — not inline
at a call site.

### 1.6 The Sep 4 numeric fixes are in the ER's view and **not** in the final report's *(added 2026-09-07)*

`b0998c9` did not only add prose fields. It put ~220 lines of numeric hardening
into `rainmaker_view.py` that `final_report_view.py` does not have, and the two
modules render **the same bundle**. Verified function by function:

| Fix, in `rainmaker_view.py` | In `final_report_view.py`? | Consequence for the final report |
|---|---|---|
| `_period_sort_year` (FY/CY/'23 parsing) | ✗ | `_pnl_table` takes periods in **emission order** (`final_report_view.py:160-168`) — the P&L columns can be ordered differently than the ER's, from the same rows |
| `_normalize_period_units` + `_nearest_power_of_1000` (`_UNIT_OUTLIER_FACTOR = 500.0`) | ✗ | A period an agent emitted in units while its siblings are in thousands stays an outlier — the exact defect Sep 4 fixed for the ER |
| `_unit_label` | ✗ (reads `bundle.financials.unit_label`, which **no producer populates** — 0 hits in `field_mapping`/`bundle_builder`/`populate`) | The P&L header always falls back to `"as reported"` while the ER states the real unit |
| `_headline_absolute_dollars` (parses `"$23.0mm"`) | ✗ | Headline tiles are not cross-checked against the table |
| `_format_money` | ✗ (has its own `_short()`) | Money can format differently in the two documents |

`rainmaker_view._unit_label`'s own docstring names the bug it closed: *"the
hardcoded 'in millions' that mislabelled every table extracted in thousands"*.
Shipping the final report without these reintroduces it in a second document.

**This is a correctness requirement, not an enhancement.** Two documents built
from one bundle, disagreeing on column order and on what unit the figures are
stated in, is worse than either document alone — the reader has no way to know
which is right. **T02 owns it**, under the same equivalence-proof discipline as
the `parse_money`/`parse_percent` de-duplication it already carries.

Note the direction of reuse: `rainmaker_view.py` stays read-only. The final
report's view **imports** its helpers; nothing moves the other way.

### 1.7 Projected EBITDA margin does not exist — say so, don't infer it *(decided 2026-09-07)*

`_forecast` builds its chart series over `hist + plan` rows, so the margin line
**renders across the historical periods and stops where the plan begins**. That is
not a hole; it is a correct edge. Nothing in the pipeline projects margin:
`forecast_agent` mentions EBITDA only in downside sensitivities
(`approx_ebitda_impact_dollars`, a one-off on customer loss), and `OpexSubAgent`
*retrieves* the plan's P&L pages — its query literally asks for *"projected EBITDA
summary P&L income statement forward projections"*
(`opex_sub_agent.py:174-177`) — but its extraction schema keeps only
`opex_breakdown`, `cost_structure`, `executive_summary`, `extraction_notes`. The
projected P&L is read and discarded.

**Decision (Hector, 2026-09-07): make the absence explicit, do not infer the
value.** When the plan periods carry no margin, the forecast chart's `footnote`
gains a clause saying the plan does not state a projected EBITDA margin. One line
in `final_report_view.py`, inside the footnote that chart already has. **T05**
owns it, alongside the D-03 injection.

Why it matters more than it looks: a line that simply stops reads as *"a figure is
missing"*. A footnote turns it into *"the plan does not commit to a margin"* —
which is a finding about the plan, and one a deal team should notice. Extending
the historical margin across the plan periods to draw a continuous line would be
the opposite: inventing a management commitment that was never made.

Follow-up **F-7** covers extracting the real figure.

### 1.8 How to measure pagination — neither obvious method works *(added 2026-09-08)*

The eleven-page figure is a property of the HTML under a layout engine that
honours the template's `@page { size: A4 portrait }`. Two engines are in play and
**neither can be used for this**:

- **WeasyPrint** honours `@page`, but it is not usable here: it imports and then
  dies on `write_pdf` with `OSError: cannot load library 'libgobject-2.0-0'`.
  This is the same missing system library behind the repo's 38 pre-existing skips.
  Deferring the check to "a session where WeasyPrint works" does not help — every
  session runs on this machine.
- **PyMuPDF Story**, the production fallback, honours neither `@page` nor flex, so
  its page count is unrelated to the document's. It reported **16 pages** for a
  document that is really 12. A before/after comparison through PyMuPDF is not
  evidence of anything.

And note the consequence for production: `renderers.py:133` records that Databricks
Serverless cannot install cairo/pango either, so **the shipped PDF comes from
PyMuPDF as well**. The eleven-page layout is real in a browser and never realised
in the PDF artifact. That is precisely what T04's `pdf_degraded` flag exists to
say, and it is why the HTML is the faithful deliverable.

**Use headless Chrome**, which honours `@page` and is installed on this machine:

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new \
  --disable-gpu --user-data-dir=<scratch>/prof --no-pdf-header-footer \
  --print-to-pdf=<out>.pdf "file://<rendered>.html"
```

Chrome writes the PDF and then does not exit — background it, poll for a non-empty
file, then kill it. Count and inspect with PyMuPDF (`fitz`), which is already a
dependency:

```python
d = fitz.open(out); d.page_count, [round(v) for v in (d[0].rect.width, d[0].rect.height)]
# A4 portrait == 595 x 842
```

Measured this way on the illustrative bundle (2026-09-08): **11 pages without
`core_business`, 12 with it**, and page 4 of the twelve carries 204 characters —
the business section's footer alone, against 1,935 on page 3. That orphan sheet,
not the count, is the defect DoD-16 now names.

---

## 2. Exact call sequence after the change

### Branch A — a CIM exists

```
run_vdr_rainmaker(table_name, record_id, special_folder, no_cim_mode)
├─ _get_spark / _read_vdr_record
├─ ensure_progress_columns(spark, table_name)                      # NEW, idempotent ALTER
├─ _update_vdr_record(processing_status="processing")              # unchanged
├─ progress = Progress(spark, table_name, record_id, _STAGES_CIM)  # NEW
│
│  ── STAGE 1 — the executive review. Byte-for-byte the flow that ships today. ──
├─ progress.start("cim_detection")
├─ cim_files = _detect_cim_files(...)                              # unchanged
├─ progress.complete("cim_detection", {"cim_files": cim_files})
├─ progress.start("cim_ingestion")
├─ run_ingestion_pipeline(file_whitelist=cim_files,
│                         parse_priority_tiers="all", force="company")   # unchanged
├─ strict parse guard → raises on != SUCCESS                       # unchanged (whole run fails)
├─ progress.complete("cim_ingestion")
├─ progress.start("cim_agents")
├─ run_pipeline(run_orchestrator=False)                            # unchanged
├─ progress.complete("cim_agents")
├─ progress.start("executive_review_ready")
├─ rendered = build_rainmaker_summary(run_mode="cim_only")         # unchanged
├─ output_dir = _build_output_dir(company_name); copy executive_summary.pdf
│               + rainmaker_opportunity_summary.html                # unchanged
├─ progress.complete("executive_review_ready", artifacts=[…])
├─ _update_vdr_record(results_location=output_dir + "/")           # NEW: published EARLY
│
│  ── STAGE 2 — the final report. New. Cannot fail the run. ──────────────────
├─ stage2 = _run_final_report_stage(
│       spark, table_name, record_id, company_name, output_dir, progress,
│       run_mode="full_vdr_after_cim", run_ingest=True, run_agents=True,
│       prior_run_modes=("cim_only",), rescore_mps=True,   # new evidence → new score
│       llm_endpoint=…, vision_endpoint=…)
│   ├─ progress.start("vdr_ingestion")
│   ├─ run_ingestion_pipeline(company_name, catalog=VDR_CATALOG,
│   │                         vision_endpoint=…, parse_priority_tiers="1,2")
│   │                         # NO file_whitelist, NO force → incremental (§1.3)
│   ├─ strict parse guard → on != SUCCESS: progress.fail("vdr_ingestion", …)
│   │                       and RETURN {"status": "failed", …}   (no raise)
│   ├─ progress.complete("vdr_ingestion")
│   ├─ progress.start("vdr_agents"); run_pipeline(run_orchestrator=False)
│   ├─ progress.complete("vdr_agents")
│   ├─ progress.start("final_report")
│   ├─ built = build_final_report(company_name, VDR_CATALOG, spark, llm_endpoint,
│   │                             run_mode="full_vdr_after_cim",
│   │                             prior_mps_runs=_load_prior_mps_runs(…, ("cim_only",)))
│   │          # never raises; returns {"status", "html"?, "pdf"?, "pdf_degraded"?, …}
│   ├─ copy final_report.pdf / final_report.html → output_dir
│   └─ progress.complete("final_report") ; progress.complete("final_report_ready", artifacts=[…])
│
└─ _update_vdr_record(processing_status="done",
                      completion_status="success" | "partial",
                      results_location=output_dir + "/",  error_message=… if partial,
                      token counters, updated_at)
```

### Branch B — no CIM

```
run_vdr_rainmaker(...) → _run_full_room_flow(...)
├─ progress = Progress(spark, table_name, record_id, _STAGES_FULL)
├─ progress.start("vdr_scan")      # the detect_cim call that returned []
├─ progress.complete("vdr_scan")
├─ progress.start("vdr_pipeline")                                  # see §4 for why one stage
├─ run_full_pipeline(company_name, catalog=VDR_CATALOG, …)         # unchanged
├─ strict parse guard + "no successful agents" guard → raise       # unchanged
├─ progress.complete("vdr_pipeline")
├─ progress.start("executive_review_ready")
├─ build_rainmaker_summary(run_mode="full_vdr_no_cim")             # unchanged
├─ copy executive_summary.pdf + rainmaker_opportunity_summary.html + full_report.docx
├─ progress.complete("executive_review_ready", artifacts=[…])
├─ _update_vdr_record(results_location=output_dir + "/")           # NEW: published EARLY
├─ stage2 = _run_final_report_stage(..., run_mode="full_vdr_no_cim",
│                                   run_ingest=False, run_agents=False,
│                                   prior_run_modes=(), rescore_mps=False)
│   │  # the room is already ingested, the agents have already run, and the ER's
│   │  # MPS already scored THIS bundle → reuse that run rather than re-scoring
│   │  # the same data (decision D-02, §3)
│   └─ stages: final_report → final_report_ready
└─ _update_vdr_record(done, success|partial, …)
```

The two branches share **one** stage-2 helper, `_run_final_report_stage()`. They
differ only in three arguments: `run_mode`, whether ingestion/agents still have
work (`run_ingest` / `run_agents`), and whether a prior MPS run exists
(`prior_run_modes`).

---

## 3. MPS — where the two runs are read and written

| | Branch A | Branch B |
|---|---|---|
| CIM run — written | `build_rainmaker_summary(run_mode="cim_only")` → `MPSAgent().score` → append row to `uc13_preview.analysis.mps_score` | n/a |
| ER run — written | (that same CIM run) | `build_rainmaker_summary(run_mode="full_vdr_no_cim")` → `MPSAgent().score` → append row |
| Final run | a **new** `MPSAgent().score` call over the complete bundle, `run_mode="full_vdr_after_cim"`, its own appended row | **no new call** — the ER's run is read back and reused (D-02 below) |
| Read for the page | `_load_prior_mps_runs()` reads back the newest `run_mode="cim_only"` row; passed as `prior_mps_runs` | `_load_prior_mps_runs()` reads back the newest `run_mode="full_vdr_no_cim"` row; passed as `reuse_mps_run` |
| Passed to the view | `_mps_table(mps_runs=[cim_run, full_run])` → 2 columns, 2 totals | `_mps_table(mps_runs=[er_run])` → 1 column |

Every scoring call goes through `MPSAgent().score(...)`, which never raises: a
failure degrades to `mps_status="degraded"` and the page still renders its
seven-row skeleton. Nothing about the MPS page is redesigned, re-laid-out or
re-summarised — it is `rainmaker_view._mps_table` rendered into the same markup
(§5).

### D-02 — Branch B reuses the ER's MPS run instead of re-scoring

**Decided by Hector, 2026-09-03. This is a deliberate deviation from §2.3 of the
task prompt**, which says the final report's MPS is *always* a new
`MPSAgent().score(...)` call and that Branch B simply keeps
`run_mode="full_vdr_no_cim"`.

The reason for the deviation: on Branch B there is **no new evidence between the
two documents**. The ER and the final report are built from the same bundle, over
the same catalog, with no ingestion and no agent run in between — `run_ingest` and
`run_agents` are both `False`. A second scoring call would therefore be an extra
LLM call over identical data, producing a second `full_vdr_no_cim` row per run and
a score that can differ from the one the deal team already downloaded, with
nothing on the page to explain why. Re-scoring is what makes Branch A's second
column meaningful; on Branch B it manufactures a discrepancy instead of measuring
one.

So on Branch B the final report's MPS page is, by construction, **the same page
with the same number as the executive review's** — which is also what the reader
expects when nothing new was read.

Mechanics: `build_final_report` gains `reuse_mps_run: dict | None = None`. When
supplied, it skips `MPSAgent().score` entirely and passes that run straight
through as the current run. `_load_prior_mps_runs` already does the read-back and
is reused unchanged.

**Failure path.** If the read-back returns nothing or a malformed row (a missing
table, an ER whose MPS itself failed to persist), `build_final_report` falls back
to a fresh `MPSAgent().score` call and prints why. An MPS page with a number is
worth more than an empty one; the fallback is a degraded path, not the norm, and
it is visible in stdout.

**The one edit permitted in `rainmaker_view.py`** is the additive dictionary entry:

```python
_MPS_RUN_MODE_LABELS = {
    "cim_only": "CIM-only preview",
    "full_vdr_no_cim": "Full data room",
    "full_vdr_after_cim": "Full data room",   # NEW
}
```

Label choice: **"Full data room"**, deliberately identical to `full_vdr_no_cim`.
The header already carries the date (`_mps_column_header`, `rainmaker_view.py:674`),
so the two columns read "CIM-only preview · 2026-09-03" and "Full data room ·
2026-09-03". The reader is being told *what was scored*, not which internal branch
produced it, and `full_vdr_after_cim` vs `full_vdr_no_cim` is not a distinction the
deal team has any use for.

**Score-movement explanation (FEAT-04) — gap, not built.** `MPSAgent.score()` scores
one bundle in isolation; it is never given a prior run and has no mechanism to
explain a delta. Nothing in `mps_rubric.py` or the rubric file carries a
"movement" concept either. Per §2.3 of the prompt this is **recorded as a gap
rather than invented here** — see §9, follow-up F-1. The two columns show the
movement; nothing in this change explains it in prose.

---

## 3.5 Prose: the template has nine slots and the existing narrative feeds two

The final report is not purely deterministic. `final_report.html.j2` carries a
cover recommendation block, thesis bullets, watchouts, business-model bullets, and
**six "Analyst take" boxes**, one per section page (`j2:521, 591, 649, 696, 745,
788`). The takes are the analyst's voice on each topic — what the number the
reader just saw actually means.

`rainmaker_narrative.py` produces nine keys — `_FRAMING_RESULT_KEYS` +
`_REVQUAL_RESULT_KEYS`, `rainmaker_narrative.py:368-377` *(re-verified
2026-09-07: `core_business` was added by the Sep 4 work, so it is nine, not the
eight this section originally said, and the line reference has been corrected)* —
and only two of them are what those slots need:

| Slot | Fed today? |
|---|---|
| `business_model` bullets, `key_watchouts` | ✅ |
| `thesis_bullets` | ⚠️ absent — the view falls back to `bundle.executive.thesis_bullets` |
| `recommendation` | ⚠️ shape mismatch — the ER returns a sentence, the template reads `rec.verdict`/`rec.rationale`/`rec.conditions`, so the cover silently prints "Not yet concluded" over a usable sentence |
| the six analyst takes | ❌ none; `kpis.take` is hardcoded `None` at `final_report_view.py:399` |

Left alone, the final report would ship six empty take boxes and read **thinner in
prose than the executive review** — the opposite of its purpose.
`rainmaker_narrative.py` is read-only, so the fix cannot live there.

One more key now exists and is unused: **`core_business`**, added Sep 4 — exactly
three lines (what the business does, how it operates, one high-impact KPI with its
figure). The ER template renders it; the final report template does not read it.
T11 should consider wiring it into the business page rather than asking a second
model call to re-say it. Folded into F-6.

**Decision (Hector, 2026-09-03):** build a new, additive
`final_report_narrative.py` — one bounded LLM call through the gateway producing
the six takes plus a structured recommendation, degrading to all-`None` exactly
the way the ER narrative degrades. `build_final_report` merges the two dicts, the
section layer winning on the single overlapping key (`recommendation`). Nothing
read-only is touched. Specified in [T11](tasks/T11_final_report_narrative.md).

Two rules that carry over from the deterministic layer and matter more here,
because a language model is involved: the prompt forbids introducing any figure
not present in the digest, and forbids producing a take for a section whose digest
is empty — a section where the agents extracted nothing renders **no** box. An
analyst take over absent data is fabrication in a confident voice, which is worse
than the blank the template already handles.

**T11 close-out (2026-09-08) — final key list and merge order shipped.**
`synthesize_final_report_narrative(bundle, llm_endpoint, spark)` returns
exactly:

```python
{
    "business_take": str | None, "financial_take": str | None,
    "customer_take": str | None, "kpi_take": str | None,
    "quality_take": str | None, "forecast_take": str | None,
    "recommendation": {"verdict": str|None, "rationale": str|None,
                       "conditions": list[str], "tone": str|None} | None,
    "final_narrative_status": "success" | "degraded",
}
```

`core_business` is **not** in this schema, per the task's own instruction —
it is already produced by the ER's `synthesize_rainmaker_narrative` and
survives the merge unchanged; this module only threads it through
`final_report_view`. `build_final_report` calls both narratives and merges
`narrative = {**er_narrative, **fr_narrative}` — the section layer's dict
wins the one overlapping key (`recommendation`), and every other key from
each layer passes straight through. Both statuses
(`synthesis_status`, `final_narrative_status`) are surfaced in
`build_final_report`'s return value so a job log shows which layer
degraded independently.

---

## 4. Progress-stage vocabulary, and the one place it deviates from the prompt

`processing_status` keeps its exact current vocabulary (`submitted` → `processing`
→ `done` | `error`) and stays `processing` until the whole run finishes. An
unmodified UI is unaffected. Progress lives in four **additive, nullable** columns
on `rallyday_partners_llc.default.companies_vdr_history`: `progress_stage`,
`progress_pct`, `progress_json`, `stage_updated_at`.

### Branch A (CIM) — as proposed

| key | label |
|---|---|
| `cim_detection` | Scanning the data room for a CIM |
| `cim_ingestion` | Ingesting the CIM |
| `cim_agents` | Running the diligence agents on the CIM |
| `executive_review_ready` | Executive review ready |
| `vdr_ingestion` | Ingesting the full data room |
| `vdr_agents` | Running the diligence agents on the full data room |
| `final_report` | Building the final diligence report |
| `final_report_ready` | Final report ready |

### Branch B (no CIM) — **deviates: `vdr_ingestion` + `vdr_agents` collapse to `vdr_pipeline`**

| key | label |
|---|---|
| `vdr_scan` | Scanning the data room |
| `vdr_pipeline` | Ingesting the data room and running the diligence agents |
| `executive_review_ready` | Executive review ready |
| `final_report` | Building the final diligence report |
| `final_report_ready` | Final report ready |

**Why.** §5 of the prompt says "the progress granularity is whatever the runner can
see from outside" and invites better boundaries if the code suggests them. On
Branch B the runner makes **one** call — `run_full_pipeline()` — which does Phase 1-2
*and* Phase 3-5 internally and returns only when both are finished. The runner
cannot observe the ingestion→agents boundary from outside. Emitting two stages
would mean either inventing a `finished_at` for `vdr_ingestion` (a fabricated
timestamp on a record the deal team reads) or back-filling both stages as `done` at
the same instant (a progress bar that sits at one stage for 40 minutes and then
jumps two). One honest stage beats two dishonest ones.

Rejected alternative: thread a progress callback into `run_full_pipeline()`. It is
not on the read-only list, so it is legal — but it puts progress plumbing inside a
shared Phase 1-5 entry point used by three other callers, for a cosmetic gain.
Revisit only if the UI asks for it.

`progress_json` payload, per stage: `key`, `label`, `status`
(`pending`/`processing`/`done`/`failed`/`skipped`), `started_at`, `finished_at`,
`artifacts`. The whole ordered list ships on every write, so the UI renders the bar
from that one field without knowing the branch in advance.

`progress_pct` is monotonic and never regresses: it is
`round(100 * terminal_stages / total_stages)`, clamped to its own previous value,
and is only forced to `100` when the run reaches its terminal update.

### Publishing the ER early

At `executive_review_ready`, **before stage 2 starts**, the runner writes
`results_location` (the timestamped VDR volume dir, with the trailing `/` the
existing code uses) onto the record. The ER filenames are unchanged
(`executive_summary.pdf`, `rainmaker_opportunity_summary.html`) — the UI resolves
them by name — and they are also listed in that stage's `artifacts`. The deal team
can download the executive review while stage 2 is still running.

### If the ALTER is refused

Preferred and assumed: the four columns. If `ALTER TABLE … ADD COLUMNS IF NOT
EXISTS` on the UI-owned table turns out not to be permitted (T08 checks this
against the warehouse before writing the emitter), fall back to
`uc13_preview.analysis.vdr_progress`, keyed by `record_id`, same payload — and
record the refusal here. The columns are preferred because they keep the UI to one
query.

**A-2 resolved (T08, 2026-09-08) — the columns path, not the fallback.**
Checked live against the warehouse (profile `rallyday`, `f8e7a8ed6dea21fd`) via
`databricks api post /api/2.0/sql/statements`:

- `ALTER TABLE rallyday_partners_llc.default.companies_vdr_history ADD COLUMNS
  (progress_stage STRING, progress_pct INT, progress_json STRING,
  stage_updated_at STRING)` **succeeded** — permission is granted on this
  UI-owned table. `DESCRIBE TABLE` before/after confirms the table went from
  15 columns to 19, all four new ones nullable, no existing column touched.
- The literal SQL the plan and T08 assumed — `ADD COLUMNS IF NOT EXISTS (...)`
  and the singular `ADD COLUMN IF NOT EXISTS col type` — both fail with
  `[PARSE_SYNTAX_ERROR] ... at or near 'EXISTS'` on this SQL engine,
  **unconditionally**, independent of whether the columns already exist. This
  is a syntax gap on this platform, not a permission refusal.
- Re-running the bare `ADD COLUMNS (progress_stage STRING)` a second time
  (columns already present) fails with `[FIELD_ALREADY_EXISTS]` /
  `SQLSTATE 42710` — the specific, catchable error `ensure_progress_columns`
  swallows to get idempotency without `IF NOT EXISTS` in the SQL text.

**Consequence for the emitter:** `ensure_progress_columns` issues the bare
`ADD COLUMNS (...)` (no `IF NOT EXISTS`) and wraps it in a blanket
`try/except`, same as any other refusal it must tolerate. The
`uc13_preview.analysis.vdr_progress` fallback table was **not needed** — the
columns already exist on the live table as of this check. No drop-and-recreate
was used anywhere near `companies_vdr_history`; this was four additive `ADD
COLUMNS` calls plus reads, nothing destructive.

---

## 5. MPS markup: one copy, not two — open decision D-01

The attached `final_report.html.j2` carries a faithful **replica** of the ER's
`mps-table` block and its CSS. Two copies of the same markup drift.

**Proposal (D-01):** extract the block into
`databricks/agents/exec_summary/templates/_mps_page.html.j2` and `{% include %}` it
from both templates. This requires a *mechanical* edit to
`rainmaker_opportunity_summary.html.j2` — which is otherwise read-only for this
task — swapping the block for an include, with byte-identical rendered output.

T06 produces the evidence before anything is swapped: it renders the ER from a
fixture bundle before and after the change and diffs the two HTML files, and only
proceeds if the diff is empty. **If D-01 is refused, T06's fallback path ships
instead:** the replica stays, and a parity test renders both documents from the
same bundle + MPS run and asserts the extracted MPS section markup is identical.
Either way the parity test ships — it is what stops the replica from drifting, and
it guards the include if the swap lands.

**DECIDED (Hector, 2026-09-07): approved — Path A, the shared partial.**

Recorded reasoning, including the part that argues *against* the urgency: the MPS
block has **not** been edited since it was created on 2026-08-25 (`374737f`), and
the 2026-09-04 work changed 30 other lines of that template without touching it.
So this is not a fire. It is the moment the second copy comes into existence —
`diff` over the two blocks today returns **35 identical lines each, zero
differences** — and the choice is whether the repo carries one copy or two from
here on. One.

T06's gate still stands and is not a formality: the three before/after render
diffs (normal run, degraded, two-column) must all be **empty**, and
`test_rainmaker_golden_render.py` must pass with no golden file regenerated. If
any diff is non-empty, abort the swap and fall back to Path B; do not "fix" the
template to make the diff empty.

**T06 close-out (2026-09-07) — Path A executed, gate passed.**

Step 1's gate (before extracting anything): a throwaway script under the
session scratchpad rendered `rainmaker_opportunity_summary.html.j2` from
`tests/fixtures/elder_care_bundle.yaml` + `tests/fixtures/mps_run_verbose.yaml`
(the seven-rubric-row fixture), once against the unmodified templates dir and
once against a scratch copy with the block→include extraction applied, for
three MPS shapes — a single run, `mps_runs=[]` (degraded, 7 unscored rows),
and two runs (CIM + full). All three `diff before.html after.html` came back
**empty**. Only then did the real swap land.

Extraction detail: the shared partial (`_mps_page.html.j2`) carries the exact
byte-identical span both templates already had —
`rainmaker_opportunity_summary.html.j2:341-388` and
`final_report.html.j2:869-916` before the swap, confirmed via `diff` to be
zero lines different — i.e. from `{% set mps_score_col_pct %}` through the
closing `{% endif %}` of the footer-note block. The surrounding chrome (the
`<section>`/`<div>` wrapper, running header, eyebrow, `<h2>` — whose class
differs, `section-header` vs `section` — and footer) stays in each template,
because that part is *not* identical between the two documents. Only the CSS
was left duplicated in each template's `<head>` (not moved into the
partial) — `final_report.html.j2`'s own `.mps-page` selector and margin
values already differ slightly from the ER's `.page.mps`, so moving the CSS
was out of scope for a byte-identical-output-only extraction.

Re-run of Step 1's three diffs against the **real, already-swapped**
templates (before = git `HEAD`'s pre-swap `rainmaker_opportunity_summary.html.j2`
materialized into a scratch dir alongside the rest of the real templates;
after = the real templates dir as committed) — all three still **empty**.

`git diff databricks/agents/exec_summary/templates/rainmaker_opportunity_summary.html.j2`
shows exactly the block→include swap and nothing else (49 lines removed, one
`{% include %}` line added). `pytest tests/test_rainmaker_render.py
tests/test_rainmaker_golden_render.py -q` — 72 passed / 20 skipped, unchanged
from before the swap; `tests/fixtures/rainmaker_golden_render.json` shows zero
diff (`git status --short` on that path is empty) — no golden file
regenerated.

The parity test (`tests/test_mps_parity.py`, new) renders both documents from
the same bundle and the same single MPS run, extracts
`<table class="mps-table">` through the closing `mps-footer-note` div from
each, normalises only whitespace runs that sit entirely between tags, and
asserts the two extracts are identical — plus a second case for the degraded
(`mps=None`) 7-row unscored skeleton. Confirmed the test can fail: temporarily
replaced `final_report.html.j2`'s `{% include %}` with an inlined copy of the
partial with one word changed (`Total` → `TOTAL-MUTATED`), reran
`pytest tests/test_mps_parity.py -q` → both cases **failed** as expected, then
restored the file (`git diff` back to the clean swap, verified byte-for-byte
against the pre-mutation version).

`pytest tests/ -q` — **1331 passed / 38 skipped** (2 new parity tests, no
regressions); `pytest tests/ --collect-only -q` — **1366 tests collected**.

---

## 6. How a stage-2 failure degrades

By the time stage 2 starts, the ER is on disk, copied to the VDR volume, and
`results_location` already points at it. Nothing in stage 2 may take that away.

- `_run_final_report_stage()` is wrapped end-to-end in `try/except`. It **never
  raises**; it returns `{"status": "success" | "failed", "stage": <key>, "error":
  str | None, "files": [...]}`.
- The **strict parse guard is kept** for stage-2 ingestion — a non-`SUCCESS`
  `ingestion_parser` still refuses to build on stale chunks — but instead of
  raising it marks that stage `failed` and returns early. The run does not die.
- `build_final_report()` never raises either (same contract as
  `build_rainmaker_summary`): internal failures degrade the affected section, and
  an MPS failure degrades to `mps_status="degraded"` with the seven-row skeleton
  still on the page.
- Terminal record state:

| Outcome | `processing_status` | `completion_status` | `results_location` | `progress_json` |
|---|---|---|---|---|
| Everything succeeded | `done` | `success` | ER + final report dir | all stages `done`, `progress_pct=100` |
| ER ok, stage 2 failed | `done` | `success` (see A-1) | still the ER dir | ER stages `done`, failing stage `failed`, later stages `pending`, `error_message` set |
| Stage 1 failed | `error` | `failure` | unset | stage that failed marked `failed` |

**A-1 resolved (T09, 2026-09-08) — `completion_status="success"` with
`error_message` set, not `"partial"`.** Checked live against the warehouse
(profile `rallyday`, `f8e7a8ed6dea21fd`):

- `SHOW CREATE TABLE rallyday_partners_llc.default.companies_vdr_history` has
  **no `CHECK` constraint clause** on `completion_status` (or anywhere else) —
  a write of `"partial"` would not be rejected at the database level.
- `rallyday_partners_llc.information_schema.table_constraints` returns zero
  rows for this table — confirms no constraint exists via a second, more
  direct check.
- The column's own DDL comment reads `'Values: success | failure'` — the
  vocabulary is explicitly documented as binary, independent of any
  constraint enforcing it.
- Live data: `SELECT completion_status, count(*) ... GROUP BY
  completion_status` returns exactly three groups — `success` (50),
  `failure` (5), `NULL` (10, pre-dating this column being populated on every
  path). No row has ever held any third value.
- The UI's own source is outside this repo, so its switch behavior on
  `completion_status` cannot be inspected directly. Given the column comment
  and a 100% historical success/failure split, introducing a third value the
  UI has never seen is a real regression risk for no proven benefit — the
  plan's own fallback (§9) already anticipated exactly this outcome.

**Consequence for the runner:** on a stage-2 failure, both branches write
`completion_status="success"` (not `"partial"`), `results_location` still
pointing at the ER directory, `error_message` set to the stage-2 failure
(truncated to `[:4000]` like the existing failure path), and `progress_json`
showing the failed stage as `"failed"` with later stages left `"pending"`.
An operator or an updated UI reading `progress_stage`/`progress_json`
gets the honest picture; an unmodified UI sees a normal `success` row with a
downloadable executive review, which is still true. See
`tests/test_run_vdr_rainmaker.py::test_branch_a_stage2_ingestion_failure_keeps_er_intact`
and `test_branch_a_stage2_build_final_report_failed_status`.

---

## 7. Files created and modified

### Created

| Path | Why |
|---|---|
| `databricks/agents/exec_summary/templates/final_report.html.j2` | The attached 11-page template, moved into the package unchanged. |
| `databricks/agents/exec_summary/templates/_mps_page.html.j2` | The shared MPS partial — **only if D-01 is approved**. |
| `databricks/agents/exec_summary/final_report_view.py` | The attached deterministic bundle→template projection. |
| `databricks/agents/exec_summary/final_report_entry.py` | The bridge: bundle → validate → verify → narrative → MPS → render. Sibling of `rainmaker_entry.py`. |
| `databricks/agents/exec_summary/final_report_narrative.py` | The section-level prose the template needs and the ER narrative does not produce — six analyst takes + a structured recommendation (§3.5). |
| `databricks/jobs/scripts/vdr_progress.py` | The thin progress emitter the runner calls between steps. |
| `tests/fixtures/final_report_sample_bundle.py` | The illustrative bundle — test fixture only, never shipped in the package. |
| `tests/test_final_report_view.py` | The numeric contract (`None` never becomes `0`, caps, screens, CAGR). |
| `tests/test_final_report_render.py` | Four render scenarios + the MPS parity assertion. |
| `tests/test_final_report_narrative.py` | One gateway call, pinned `max_tokens`/`temperature`, and three degradation paths. |
| `tests/test_vdr_progress.py` | Stage transitions, monotonic pct, emitter swallows a raising spark. |

### Modified

| Path | Why |
|---|---|
| `databricks/agents/exec_summary/renderers.py` | Add `render_final_report()`; add the optional `report=` kwarg to `ReportRenderer.render()`; give the PyMuPDF fallback an A4 **portrait** rect for this template. |
| `databricks/agents/exec_summary/rainmaker_view.py` | One additive entry in `_MPS_RUN_MODE_LABELS`. Nothing else. |
| `databricks/agents/exec_summary/templates/rainmaker_opportunity_summary.html.j2` | **Only if D-01 is approved** — mechanical block→include swap, byte-identical output. |
| `databricks/jobs/scripts/run_vdr_rainmaker.py` | Stage 2 on both branches via one shared `_run_final_report_stage()`; progress calls; early `results_location`; the partial-completion terminal state. |
| `databricks/workflows/vdr_rainmaker_poc.yml` | Description only — it now produces two deliverables. **No parameters added** (fixed params block the UI's `run-now`). |
| `databricks/CLAUDE.md` | Required: the two-stage flow, the new deliverables, the progress columns, the stage vocabulary. |
| `.gitignore` | One negation so `docs/plans/final_report/**` is tracked — `docs/*` is ignored, and this plan is a DoD artifact. |

**T04 close-out (2026-09-07).** `ReportRenderer.render()` gained the additive
`report: dict[str, Any] | None = None` kwarg, injected into the context exactly
like `tldr`/`rainmaker`/`narrative`/`mps`. `_html_to_pdf` gained an optional
`page_rect_spec: str = "a4-l"` parameter (default unchanged, so
`render_rainmaker` is untouched); `render_final_report` passes `"a4"` — the
final report template is portrait (`final_report.html.j2:46`). `render_final_report()`
landed mirroring `render_rainmaker`: builds `final_report_view(...)` for the
`report=` context key, builds the MPS projection via the same
`rainmaker_view(bundle, mps_runs=[*(prior_mps or []), mps] if mps else
(prior_mps or None))["mps"]` (prior runs first, current run last — the
function never builds its own MPS projection), writes `final_report.html` /
`final_report.pdf`, and returns `pdf_degraded: True` when the PyMuPDF fallback
engine was used. Evidence: `pytest tests/test_rainmaker_render.py
tests/test_rainmaker_golden_render.py -q` — 72 passed / 20 skipped, unchanged;
`pytest tests/ -q` — 1311 passed / 38 skipped (up from 1241/38 — T03b's mutant
tests plus this task's suite runs added no new failures, no regressions).

### Read-only — must show zero diff at the end (`git diff --stat`)

`rainmaker_view.py`\* · `rainmaker_narrative.py` · `mps_agent.py` · `mps_rubric.py` ·
`bundle_builder.py` · `validate.py` · `absence_check.py` ·
`rainmaker_opportunity_summary.html.j2`\*\*

\* except the one additive `_MPS_RUN_MODE_LABELS` entry (§3).
\*\* except the D-01 mechanical include swap (approved — §5).

**Use `git merge-base`, never the branch point, as the baseline.** The branch was
cut at `31878cc` and *later* merged `anthropic-sdk-migration` up to `ad6d009`
(§Status). Diffing from `31878cc` therefore attributes the whole 2026-09-04
executive-review commit to this branch, and `rainmaker_view.py` appears to have
gained 220 lines it did not. That misread happened once during the T01 review.
The correct, self-maintaining form is what T10 already uses:

```bash
git diff --stat $(git merge-base HEAD feature/anthropic-sdk-migration)..HEAD -- <files>
```

It resolves to `ad6d009` today and stays correct if that branch advances or is
merged again.

---

## 7.5 Stakeholder preview artifacts

[`preview/`](preview/) holds two documents built from the shipped template and the
illustrative bundle, plus the harness that regenerates them:

- `UC13_Final_Report_ANNOTATED_PREVIEW.html` — the delivered preview with a
  per-panel **Ready / Partial / Pending data** badge and a legend.
- `UC13_Final_Report_TODAY_PREVIEW.html` — the same template rendered with every
  field that has no producer stripped: what a real run produces today.
- `coverage.py` — the panel audit both are built from. **T02 owns re-running it**
  and must regenerate both files in the same commit, so an artifact a stakeholder
  was shown never drifts from what the pipeline does.

The harness reproduces the delivered preview **byte for byte**, which is worth
more than the preview itself: it proves the template and the view module integrate
through exactly the wiring T04 is implementing (`report=`, `mps=`, `narrative=`,
autoescape on for `*.html.j2`).

Current coverage: **20 ready · 3 partial · 11 pending**.

---

## 8. Tasks

Ordered. Each file in [`tasks/`](tasks/) is self-contained and closes its own DoD
line. T08 is independent of T01-T07 and can run at any point.

| # | Task | Gate |
|---|---|---|
| [T01](tasks/T01_land_inputs.md) | Land the template, the view module and the fixture in their final locations | imports clean |
| [T02](tasks/T02_bundle_field_audit.md) | Audit the 8 bundle fields; wire renames, record the genuinely-absent ones | no invented fields |
| [T03](tasks/T03_view_numeric_tests.md) | `test_final_report_view.py` — the numeric contract | green |
| [T03b](tasks/T03b_pin_format_policy.md) | Pin the caps and screens as policy — closes two surviving mutants | mutants fail |
| [T04](tasks/T04_render_final_report.md) | `render_final_report()` + `report=` kwarg + A4 portrait fallback | green |
| [T05](tasks/T05_final_report_entry.md) | `build_final_report()` + MPS read-back/reuse (D-02) + the run-mode label | green |
| [T06](tasks/T06_mps_parity.md) | D-01 evidence, the include swap or the replica, and the parity test | **needs D-01 answer** |
| [T07](tasks/T07_render_tests.md) | `test_final_report_render.py` — four scenarios | green |
| [T08](tasks/T08_vdr_progress.md) | `vdr_progress.py` + the ALTER + `test_vdr_progress.py` | green |
| [T09](tasks/T09_runner_stage_two.md) | `_run_final_report_stage()` wired into both branches | green |
| [T11](tasks/T11_final_report_narrative.md) | The six analyst takes + the structured recommendation (§3.5) | green |
| [T10](tasks/T10_docs_and_closeout.md) | `databricks/CLAUDE.md`, the YAML description, the read-only diff proof | DoD closed |

---

## 9. Assumptions and follow-ups

**Assumptions made because the repo did not answer the question.**

- **A-1.** `completion_status="partial"` is accepted by the UI. Unverified — see §6;
  T09 checks and substitutes if not.
- **A-2 — RESOLVED 2026-09-08 (T08).** `ALTER TABLE … ADD COLUMNS` (bare, not
  `IF NOT EXISTS` — that clause doesn't parse on this engine) is permitted on
  `rallyday_partners_llc.default.companies_vdr_history`; the four columns are
  live on the table. See §4 for the full evidence. The
  `uc13_preview.analysis.vdr_progress` fallback was not needed.
- **A-3.** `bundle["meta"]` carries no `run_mode` key (`bundle_builder.py:652-668`
  confirms it does not), yet `final_report_view` derives its cover `mode_label`
  from `meta.get("run_mode")` — so today every report would read "Full data room",
  including a CIM-first one. Resolution: `final_report_view()` takes an additive
  `run_mode: str | None = None` parameter supplied by `build_final_report`, which
  already knows the branch as a fact. This is an extension of a module we own, not
  a restructure, and it keeps the rule that `run_mode` is never re-derived from
  `bundle.meta`.
- **A-4.** Two files named in §0 of the prompt were not delivered with the others:
  `UC13_Final_Report_Template_Proposal.md` (design rationale, read-for-intent, not
  shipped) and `render_preview.py` (the throwaway preview harness). Neither is
  required to build anything here — the template and the view module are
  self-describing and the rendered preview HTML *was* delivered — so work proceeds
  without them. If the proposal document surfaces, re-read §5-§9 of it against
  T02's field audit.
- **A-5.** The stage-2 full-room ingestion uses `parse_priority_tiers="1,2"` (the
  runner default), not `"all"`. `"all"` is a CIM-scoping choice that only makes
  sense against a whitelist of a handful of files; running it over a whole data
  room is a large, unbudgeted parse.

**Follow-up work, deliberately not built here.**

- **F-1.** Score-movement explanation between the two MPS columns (FEAT-04). No
  agent produces it; see §3.
- **F-2 — CLOSED 2026-09-07 (T02).** Every field the final report reads that has
  no producer today, the section it degrades, and the agent that would have to
  change to populate it. Full trace and RENAME/RESHAPE/ABSENT classification
  is in §1.4's T02 close-out table; this is the flat follow-up list.

  | Field | Section renders "not extracted" | Agent that would need to change |
  |---|---|---|
  | `financials.segment_performance` / `segment_dimension` | Page 3 performance-by-segment table + chart | `RevenueSubAgent` (`revenue_sub_agent.py`) would need to extract gross margin and growth per segment, not just revenue |
  | `financials.forecast_rows` / `forecast_assumptions` | Page 8 plan-vs-history chart + assumptions table | **Not a gap** — SUPPLIED-BY-T05 (D-03); `forecast_agent.py` already extracts these, `build_final_report` reads them from Delta directly |
  | `financials.growth_bridge` | Page 4 growth bridge | No agent computes a revenue/EBITDA bridge today; would need a new extraction (or a deterministic build off `table_rows` + `addback_schedule`) |
  | `revenue_quality.revenue_type_mix` | Page 3 recurring-vs-project mix bar | `customer_quality_agent.py` extracts this as a dict already (`recurring_pct`/`project_onetime_pct`/`retainer_pct`) — needs `_revenue_quality_from_agents` (`field_mapping.py`) to copy it, reshaped into a list of `{label, pct}` |
  | `revenue_quality.client_distribution` | Page 3 clients-by-segment mix bar | No agent extracts a client-by-segment breakdown today |
  | `qoe.addbacks` | Page 7 addback stack | `EbitdaSubAgent` already extracts `addback_schedule.items` — needs `_qoe_from_snapshots` (`field_mapping.py`) to copy the list (renamed `description`→`label`, `amount_stated`→`amount`), and the schema would need a `tier` field, which does not exist anywhere today |
  | `diligence_questions[].why_it_matters` | Page 9 "why it matters" column | `GapAggregator.build_diligence_questions()` (`bundle_builder.py`) would need a rationale string; none of its upstream sources (legal's `recommended_diligence`, KPI's `missing_kpis`) carry one today |
  | `revenue_quality.top_customers` | Page 5 top-customer table | CQA already extracts `top_customers` — needs `_revenue_quality_from_agents` to copy it into the bundle |
  | `revenue_quality.client_count` | Customer tile | No agent computes a client count today |
  | `revenue_quality.customer_tenure` (structured) | Customer tile (avg tenure) | Data exists one layer down (`cqa_yaml.customer_tenure.average_tenure_years`) but `_retention_note_from_cqa` flattens it into a string; needs a second, structured path alongside the note |
  | `legal.coc_consent_count` | Legal tile | `legal_contracts_agent.py` already computes this as a local variable for a narrative sentence — needs a Delta column and `_build_legal_block` (`field_mapping.py`) to copy it |
- **F-9. `_retention_rows` ignores a screen's declared direction; `_kpi_scorecard`
  honours it.** Two functions in `final_report_view.py` read the same `_SCREENS`
  table and disagree about what it means:

  ```python
  # :671  _retention_rows — always "below the threshold"
  flag = bool(screen and num is not None and num < screen["threshold"])

  # :402  _kpi_scorecard — honours the declared direction
  and ((screen["dir"] == "min" and value_num < threshold)
       or (screen["dir"] == "max" and value_num > threshold))
  ```

  **Harmless today, and specifically primed to break.** The two retention metrics
  that have screens (`nrr_pct`, `grr_pct`) are both `min`, so `<` is the right
  comparison for them. But `_retention_rows` already reads
  `logo_churn_rate_annual_pct` (`:665`) and that metric has **no `_SCREENS`
  entry**, so it renders "No screen" — and churn is the archetypal
  `max`-direction metric. The moment a churn screen is added, this function will
  flag *low* churn as a problem and *high* churn as healthy, exactly inverted, in
  the one place a reader would never think to double-check.

  Found while reviewing T03b: the `dir`-flip mutant produced one failure instead
  of the expected two, because the behavioural test on `nrr_pct` correctly still
  passed — the code genuinely never consults `dir` there.

  **Fix:** make `_retention_rows` use the same direction-aware condition as
  `_kpi_scorecard`, ideally by extracting that condition into one small helper
  both call, so a third reader of `_SCREENS` cannot invent a fourth
  interpretation. Not done here: it is production behaviour, no task in flight
  owns that function, and the change wants its own test (a `max`-direction
  retention screen flagging the correct side). Worth doing before a churn screen
  is ever added, not after.

- **F-8. Money suffixes inside P&L cells are parsed differently by the two
  documents, and neither parser is right.** T02 proved the divergence and pinned
  it as a test (`tests/test_final_report_numeric_parity.py`) rather than picking a
  winner, which was the correct call — because there isn't one:

  - `final_report_view.parse_money` applies magnitude multipliers on an implicit
    **millions** base (`k → 0.001`, `bn/b → 1000`, no `m` branch).
    `rainmaker_view._parse_money` applies none — by design: it parses table cells,
    which the ER treats as bare numbers in a unit stated separately by
    `_unit_label`.
  - A cell `"1.5bn"` in a millions-based table: the final report reads `1500.0`
    (right); the ER reads `1.5`, and `_normalize_period_units` does **not** rescue
    it — the ratio to the median is ~30×, under `_UNIT_OUTLIER_FACTOR = 500` — so
    the ER **under-reports by 1000×**.
  - A cell `"2k"` in a thousands-based table: the ER reads `2.0`, which the
    normaliser rescales correctly; the final report reads `0.002` and needs a much
    larger correction to get back.

  Each is better in one scenario and worse in the other, so hardening either
  parser just moves the defect. **The real fix is upstream: a magnitude suffix
  should never reach a P&L table cell** — the extraction layer should normalise
  the table onto one unit and state it, which is what `_unit_label` already
  assumes happened. Until then the divergence is documented and tested, and it is
  only reachable when an agent emits a suffix inside `financials.table_rows`.

  Note that `parse_money`'s docstring claims to honour `m` suffixes; there is no
  such branch. Harmless while millions is the implicit base, but the docstring
  overstates what the code does — worth correcting next time someone is in that
  file.

- **F-7. Extract projected EBITDA / margin per period.** The figures are in the
  documents and the pipeline already retrieves the pages that hold them
  (`OpexSubAgent`'s third query), but no extraction schema keeps them — see §1.7.
  Closing this means extending `forecast_agent`'s schema and `_EXPECTED_COLS`, and
  **re-running the agents** for companies already processed. That is its own cycle
  with its own validation, not an appendix to this plan. Until then the forecast
  chart states the absence rather than inferring the value.

- **F-6 — DECIDED (Hector, 2026-09-07): wire all of it.** Owned by
  [T11](tasks/T11_final_report_narrative.md). Moved out of the follow-up list; it
  is scope now.

  **How the executive review actually uses these fields — checked, because it
  changes the work.** The ER does *not* render `sale_process`, `key_partners`,
  `key_dependencies` or `business_description` as blocks of their own. They go
  into the narrative **digest**, as input to the LLM, and the prompt requires the
  prose to use them (`rainmaker_narrative.py:186-187, :290` — *"when this field is
  non-empty, ONE company_overview bullet must state how the business is being
  sold"*). Only `core_business` is rendered directly, on the ER cover
  (`rainmaker_opportunity_summary.html.j2:139-141`).

  So F-6 is mostly **not** a template change:

  - `sale_process`, `key_partners`, `key_dependencies`, `business_description` →
    into T11's digest, with prompt instructions mirroring the ER's. No new markup,
    no pagination risk, and the prose is better grounded rather than longer.
  - `core_business` → three lines the model already produced. Render them on the
    business page instead of asking a second model call to re-say them.

  **The *numeric* half of that commit was never a follow-up** — see §1.6. Period
  ordering and unit normalisation are a correctness requirement and are part of
  T02.

- **F-5. The report's screening thresholds are Python constants, not config.**
  `_SCREENS` in `final_report_view.py` is, in substance, a first-pass screening
  rubric — 14 entries of `(metric, threshold, direction, sector)` covering
  `tech_services` and `healthcare_services` — and it decides what the KPI page
  flags. Unlike the MPS, whose rubric lives in `mps_rubric.yaml` and is editable
  without a deploy, changing a screen here needs a code change. The same applies
  to `_CONTENTS` (the 11-page table of contents) and the `CAP_*` format caps.

  Not changed here: §0 of the task prompt says integrate the view module, not
  restructure it, and the caps in particular are deliberately constants "at the
  top of the view module". But if Rallyday wants to tune screens without shipping
  code, the pattern already exists next door — a `report_screens.yaml` loaded the
  way `mps_rubric.load_rubric()` loads its file, with the current tuple as the
  default when the file is absent. Worth a decision once the first real reports
  have been read.

- **F-4. The early executive review needs a UI-side change to be *visible*
  early — this backend change alone does not deliver the time saving.** The
  backend does its part: on Branch A the ER lands in the usual timestamped VDR
  volume dir under its usual filenames, and `results_location` is written onto
  the record at the `executive_review_ready` stage, long before the run ends
  (§2, §4). But `processing_status` deliberately stays `processing` until the
  whole run finishes (§5 of the task prompt, so the existing UI keeps working).
  If the UI reveals the download only when the status reads `done`, the deal team
  still waits for stage 2 and the whole point of the two-stage split is lost in
  the presentation layer.

  The fix belongs to whoever owns the Project Lighthouse UI — it is not in this
  repo (`frontend/`, `backend-api/` and `backend-ai/` contain no reference to
  `companies_vdr_history`, `processing_status` or `results_location`), so it
  could not be verified from here. What that UI needs: surface `results_location`
  as soon as it is non-null, without gating on `processing_status`, and
  optionally render the stage list from `progress_json`. Everything it needs is
  already on the record.

  **Do not "solve" this by flipping `processing_status` to `done` after stage 1.**
  It is forbidden by §5, it is untrue — the run has not finished — and a second
  `done` at the end would break any consumer that treats the transition as
  terminal.

- **F-3.** `docs/*` is gitignored repo-wide. This plan and its tasks are tracked
  only because of the `.gitignore` negation listed in §7; if that negation is
  reverted, this plan disappears from a fresh clone.

---

## 10. Definition of done

Closed by the task that owns each line. Do not tick a box without the evidence
named next to it.

- [x] **DoD-1** — `docs/plans/final_report/final_report_plan.md` exists, is
      reviewed, and matches what was built. *(closed by T10, after every other box)*
      **Closed 2026-09-08 (T10).** Re-read §1-§9 against the shipped code
      (`run_vdr_rainmaker.py`, `vdr_progress.py`, `final_report_entry.py`,
      `final_report_view.py`, `final_report_narrative.py`, `renderers.py`,
      the templates) and found no discrepancy needing correction — every
      stage key, the `_run_final_report_stage()` argument set, D-01/D-02's
      mechanics, and A-1/A-2's resolutions in §4/§9 match the code as it
      stands today. Two boxes were found ticked-in-substance but left
      unticked and are closed below as part of this pass: **DoD-14**
      (`test_final_report_numeric_parity.py`'s P&L order/unit/cell-value
      tests already existed from T02) and **DoD-15** (the forecast
      chart/assumptions/footnote degrade tests already existed from T05).
      Nothing else in §10 was silently open.
- [x] **DoD-2** — Branch A produces, in one run: the existing ER PDF/HTML with its
      CIM-only MPS, **then** the final report PDF/HTML whose MPS page is the same
      page with a second score column for the full-data-room run.
      *(T05 + T09; evidence: `test_final_report_render.py` two-column case +
      `test_run_vdr_rainmaker.py` branch-A stage-2 case)*
      **T03 evidence (view-layer numeric contract, not the box-closing evidence —
      T07/T09 close this box).** `tests/test_final_report_view.py`: 55 tests
      covering `None`-never-`0` at every layer, `scale()`, `_calc_column()`,
      both `_SCREENS` sectors' min/max threshold direction and boundary, every
      cap constant (`CAP_TILES` … `CAP_GAPS`, each read from the module, not
      hardcoded), P&L row drop/keep semantics, and question dedup +
      `why_it_matters`. `tests/test_final_report_numeric_parity.py` gained the
      cell-value parity assertion for Revenue and EBITDA (§8 of T03), leaving
      the growth/CAGR column deliberately unchecked (documented presentation
      difference, not a defect). `pytest tests/test_final_report_view.py -q`:
      55 passed. `pytest tests/ -q`: 1297 passed / 38 skipped (1241 passed
      baseline + 55 new view tests + 1 new parity test, no regressions, no
      skips added or removed).
      **T05 evidence (entry point exists, threads `run_mode`, orders the MPS
      runs `[cim, full]` — not the box-closing evidence, T09 closes this box).**
      `databricks/agents/exec_summary/final_report_entry.py` added:
      `build_final_report()` (never raises — wrapped end-to-end in
      `try/except Exception`, `KeyboardInterrupt`/`SystemExit` excluded),
      `_load_prior_mps_runs()` (Delta read-back of
      `{catalog}.analysis.mps_score`, one row per requested `run_mode`,
      newest first then re-sorted oldest-first, `generated_at` converted to
      `str(...)` explicitly for `_mps_column_header`'s `[:10]` slice, never
      raises — a missing table/empty result/malformed `categories_json` all
      collapse to `[]`), and `_load_forecast()` (D-03: reads
      `{catalog}.analysis.forecast`, maps `revenue_build_comparison` →
      `forecast_rows`, `forecast_assumptions`/`management_validation_items`
      → `forecast_assumptions` with `.test` joined on `assumption_type`,
      `ebitda_margin_pct` never populated — see DoD-15/§1.7 — never raises,
      merged into a **copy** of `checked["financials"]` after
      `verify_bundle_claims` and before narrative/render). `run_mode` reaches
      both `MPSAgent().score(...)` and `render_final_report(...)` unchanged
      from the caller's argument (never re-derived from `bundle.meta`, A-3).
      `render_final_report` receives `mps=` (current run) and
      `prior_mps=prior_mps_runs` (caller-supplied, oldest-first) —
      `renderers.render_final_report` already builds
      `[*(prior_mps or []), mps]`, i.e. **`[cim, full]`**, current run last
      (T04). Evidence: `tests/test_final_report_entry.py` (30 tests) —
      happy-path call order (`validate → verify → narrative → mps → render`)
      and `run_mode` threading, three failure-path tests (raising
      `BundleBuilder`/narrative/renderer each produce `status="failed"` with
      no exception escaping — see DoD-12 note for the reuse-specific
      assertions), `_load_prior_mps_runs` degradation (raising spark, empty
      result, malformed JSON → `[]`) and oldest-first ordering, `_load_forecast`
      mapping + degradation (raising spark, empty table, malformed JSON →
      `{}`) + the merged-bundle-reaches-narrative-and-render assertion (and
      that `BundleBuilder`'s original bundle is left unmutated). The one
      permitted `rainmaker_view.py` edit (`"full_vdr_after_cim": "Full data
      room"`) is the entire diff — confirmed via `git diff
      databricks/agents/exec_summary/rainmaker_view.py`. `pytest tests/ -q`:
      1329 passed / 38 skipped (1311 passed baseline + 15 new
      `test_final_report_view.py` footnote tests (§1.7/DoD-15) + a new
      30-test `test_final_report_entry.py`, no regressions, no skips added or
      removed). `git diff --stat` against every other §7 read-only file
      (`rainmaker_entry.py`, `mps_agent.py`, `bundle_builder.py`,
      `validate.py`, `absence_check.py`, `rainmaker_narrative.py`) is empty.
      **T07 evidence (the two-column render case — T09 ticks this box).**
      `tests/test_final_report_render.py::test_final_report_render_two_mps_runs_orders_cim_first_full_room_last`
      builds a CIM-stage run (scores all 2, threshold 10, total 0.128) and a
      full-room run (the existing `mps_run_verbose.yaml` fixture — scores
      `[4,5,5,4,5,3,4]`, threshold 15, total 24.0), renders through
      `rainmaker_view._mps_table` with `mps_runs=[cim, full]`, and asserts:
      exactly two `<th class="mps-score-col">` headers, every one of the
      seven rubric `<tr>` carries exactly two `<td class="mps-score-col">`,
      the total row carries exactly two total cells (`"0.1"` and `"24.0"`,
      both present so the two runs are distinguishable), and the footer note
      reads `Threshold 15 · above threshold` (the full-room run's own
      threshold/verdict) with `Threshold 10` (the CIM run's) absent anywhere
      in the document — confirming `_mps_table` reads verdict/threshold from
      `mps_runs[-1]`, not `[0]`. Verified adversarially: swapping `[-1]` for
      `[0]` in `rainmaker_view._mps_table` (under `PYTHONDONTWRITEBYTECODE=1`,
      `__pycache__` cleared before and after) made this test fail on the
      `Threshold 15 · above threshold` assertion; reverted via `git checkout --`.
      **T09 evidence (closes this box) — the runner call sequence itself.**
      `run_vdr_rainmaker()` (Branch A) now continues past the ER into
      `_run_final_report_stage(run_mode="full_vdr_after_cim", run_ingest=True,
      run_agents=True, prior_run_modes=("cim_only",), rescore_mps=True)` —
      stage 2 re-ingests the rest of the room (`catalog=uc13_preview`, no
      `file_whitelist`, no `force`, `parse_priority_tiers="1,2"`), re-runs the
      agents, then calls `build_final_report(run_mode="full_vdr_after_cim",
      prior_mps_runs=[the cim_only run])`. Stage 1's own calls are
      byte-identical to before this task — the diff on those lines is
      progress-call insertions only (verified by reading the diff, not
      assumed). Evidence:
      `tests/test_run_vdr_rainmaker.py::test_branch_a_stage1_untouched_and_stage2_success`
      asserts `run_ingestion_pipeline` is called exactly twice (stage 1 with
      `file_whitelist`+`force="company"`, stage 2 without either), `run_pipeline`
      exactly twice, `build_final_report` once with `run_mode="full_vdr_after_cim"`
      and `prior_mps_runs=[{"run_mode": "cim_only"}]`, and both
      `final_report.{pdf,html}` land alongside the existing ER files in
      `results_location`. `pytest tests/test_run_vdr_rainmaker.py -q`: 20
      passed (11 baseline + 9 new). `pytest tests/ -q`: 1388 passed / 38
      skipped (1379 baseline + 9 new tests, no regressions, no skip count
      change — baseline and delta measured by temporarily restoring the
      pre-T09 versions of both changed files via `git show HEAD:...` and
      diffing `pytest --collect-only -q` / `pytest -q` counts, then restoring
      the T09 versions and confirming byte-identical restoration with `diff`).
- [x] **DoD-3** — Branch B produces the existing ER + MPS, then the final report
      with a one-column MPS. In both branches the MPS appears exactly once, on its
      own page. *(T07 + T09; evidence: the render test asserts a single
      `class="page mps"` section)*
      **Closed 2026-09-08.** `tests/test_final_report_render.py` covers all
      four render scenarios (illustrative bundle + full MPS run; a nearly
      empty bundle; no MPS run at all; two MPS runs) plus the T11 prose-layer
      additions (six take boxes / zero take boxes / a stray take for an
      empty section). Scenario (c) — `mps=None, prior_mps=None` — asserts
      the MPS page still renders (`class="page mps-page"` present), the
      seven-row unscored skeleton (`tbody.count("<tr>") == 7`, distinct from
      the total row's `<tr class="mps-total-row">`), the degraded footer
      note, and no score column header. Scenario (d) is the two-run case
      cited under DoD-2 above. Every one of the four scenarios (plus the
      T11 additions) calls a shared `_assert_single_mps_section()` helper
      that asserts exactly one `<table class="mps-table">` in the whole
      document and that no other top-level page div contains any MPS
      markup (`mps-table`/`mps-score-col`/`mps-total-row`) — checked
      structurally, not by searching for the phrase "Minimum Pursuit Score"
      (which legitimately also appears in the table-of-contents row naming
      the section). Verified adversarially: injecting a second
      `<table class="mps-table">` onto the cover page made all four core
      scenario tests fail on this helper; reverted via `git checkout --`.
      `pytest tests/test_final_report_render.py tests/test_final_report_pagination.py -q`:
      8 passed. `pytest tests/ -q`: 1369 passed / 38 skipped (1361 passed
      baseline + 8 new tests, no regressions, no skip count change).
- [x] **DoD-4** — No file listed read-only in §7 has changed, beyond the two
      documented exceptions. *(T10; evidence: `git diff --stat` against the branch
      point, pasted into T10's report)*
      **Closed 2026-09-08 (T10).** Baseline is
      `$(git merge-base HEAD feature/anthropic-sdk-migration)` = `ad6d009`, per
      §7's warning against using the branch-point SHA (`31878cc`, which would
      wrongly attribute the 2026-09-04 executive-review merge to this branch).
      ```
      $ git diff --stat $(git merge-base HEAD feature/anthropic-sdk-migration)..HEAD -- \
          databricks/agents/exec_summary/rainmaker_view.py \
          databricks/agents/exec_summary/rainmaker_narrative.py \
          databricks/agents/workstreams/mps_agent.py \
          databricks/agents/exec_summary/mps_rubric.py \
          databricks/agents/exec_summary/bundle_builder.py \
          databricks/agents/exec_summary/validate.py \
          databricks/agents/exec_summary/absence_check.py \
          databricks/agents/exec_summary/templates/rainmaker_opportunity_summary.html.j2

       databricks/agents/exec_summary/rainmaker_view.py           | 1 +
       .../templates/rainmaker_opportunity_summary.html.j2        | 49 +---------------------
       2 files changed, 2 insertions(+), 48 deletions(-)
      ```
      Exactly the two documented exceptions: `rainmaker_view.py`'s single
      `_MPS_RUN_MODE_LABELS` entry, and the D-01 block→include swap on the
      template (1 insertion, 48 deletions — the extracted markup moved into
      `_mps_page.html.j2`). `rainmaker_narrative.py`, `mps_agent.py`,
      `mps_rubric.py`, `bundle_builder.py`, `validate.py`, `absence_check.py`
      show zero diff.
- [x] **DoD-5** — A stage-2 failure leaves the ER downloadable and the record
      honest about what failed. *(T09; evidence: a test that fails stage-2
      ingestion and asserts `results_location` still points at the ER dir)*
      **Closed 2026-09-08.** `_run_final_report_stage()` wraps its entire
      body in `try/except Exception` and never raises; the strict parse
      guard on stage-2 ingestion calls `progress.fail(...)` and returns
      `{"status": "failed", ...}` instead of raising. Both branches check
      `stage2["status"]` and, on anything but `"success"`, still write
      `results_location` pointing at the (already-copied) ER directory,
      `processing_status="done"`, `completion_status="success"` (A-1, §6),
      and `error_message` set to the truncated stage-2 failure. Evidence:
      `tests/test_run_vdr_rainmaker.py::test_branch_a_stage2_ingestion_failure_keeps_er_intact`
      fails stage-2 ingestion (`ingestion_parser` status `FAILED`), asserts no
      exception escapes `run_vdr_rainmaker`, `build_final_report` is never
      called, `results_location` still ends in `/` and points at the ER-only
      files (`executive_summary.pdf` + `.html`, no `final_report.*`), and
      `error_message` names the failure.
      `test_branch_a_stage2_build_final_report_failed_status` covers the
      other stage-2 failure mode (`build_final_report` returns
      `status="failed"` without raising, per `databricks/CLAUDE.md`'s "Phase
      results are returned, not raised") with the same assertions.
      `pytest tests/test_run_vdr_rainmaker.py -q`: 20 passed.
- [x] **DoD-6** — The record exposes a progress stage list an unmodified UI can
      ignore and an updated UI can render. *(T08 + T09; evidence:
      `test_vdr_progress.py` + a runner test asserting `processing_status` never
      leaves its three legal values)*
      **T08 evidence (the emitter itself — T09 ticks this box once the
      runner is wired to it).** `databricks/jobs/scripts/vdr_progress.py`
      added: `ensure_progress_columns(spark, table_name)` (bare `ADD COLUMNS`,
      swallows `FIELD_ALREADY_EXISTS` and any other failure — see A-2 in §4),
      `STAGES_CIM`/`STAGES_FULL` module constants matching this section's
      tables exactly, and `class Progress` with `start`/`complete`/`fail`/
      `skip`/`publish`, each writing all four columns (`progress_stage`,
      `progress_pct`, `progress_json`, `stage_updated_at`) through one
      injectable `updater` call (defaults to
      `run_vdr_pipeline._update_vdr_record`). `progress_pct =
      round(100 * terminal_stages / total_stages)`, clamped to its own
      previous value, reaches exactly 100 when every stage is terminal.
      `publish(columns)` merges extra columns into the same single UPDATE
      call as the current progress write (asserted directly on the mock's
      call payload). An unknown stage key prints a warning and no-ops rather
      than raising. Nothing under `databricks/agents/` imports this module
      (`grep -rn vdr_progress databricks/agents/` returns nothing; also
      pinned as `test_nothing_under_agents_imports_vdr_progress`).
      Exception-proofness proved, not just asserted: `tests/test_vdr_progress.py`
      exercises every public method (`start`/`complete`/`fail`/`skip`/
      `publish`) plus `ensure_progress_columns` against an updater/spark that
      raises on every call, and confirms nothing propagates, alongside a
      normal sequence on a *different* instance completing to `progress_pct
      == 100` in the same test. Verified adversarially per rule 9b: mutated
      `_pct()`'s denominator (`total` → `total + 1`) under
      `PYTHONDONTWRITEBYTECODE=1`, confirmed 3 tests fail (`83 == 100`
      assertion, not a crash), then restored the file byte-for-byte (`diff`
      empty) and cleared `__pycache__`. `pytest tests/test_vdr_progress.py -q`:
      10 passed. `pytest tests/ -q`: 1379 passed / 38 skipped, no regressions,
      no skip count change. `pytest tests/ --collect-only -q`: 1414 tests
      collected.
      **T09 evidence (closes this box) — the runner wired to the emitter,
      `processing_status` proven never to leave its three legal values.**
      `run_vdr_rainmaker()` calls `ensure_progress_columns(spark, table_name)`
      once, right after reading the record and before the first
      `_update_vdr_record`, then constructs a `Progress(..., STAGES_CIM)` (or,
      inside `_run_full_room_flow`, a fresh `Progress(..., STAGES_FULL)` —
      Branch B's collapsed `vdr_pipeline` stage has no key in `STAGES_CIM`).
      Both are wrapped in a small `_SafeProgress` proxy in the runner itself
      (catches and prints on every method call) — belt-and-suspenders on top
      of `Progress`'s own exception-swallowing contract (T08), so a
      completely broken progress emitter still cannot change any outcome
      (README rule 7). Evidence:
      `tests/test_run_vdr_rainmaker.py::test_raising_progress_never_changes_the_outcome`
      replaces `vdr_progress.Progress` with a class whose every method raises
      and asserts the run still completes `done`/`success` with all four
      files copied. `_assert_processing_status_always_legal()` (a shared test
      helper) is threaded through every T09 test and asserts
      `processing_status` is one of `{processing, done, error}` on **every**
      recorded `_update_vdr_record` call, not just the terminal one — covering
      the CIM branch, the full-room branch, stage-2 failure, and the
      raising-Progress case. `pytest tests/test_run_vdr_rainmaker.py -q`: 20
      passed. `pytest tests/ -q`: 1388 passed / 38 skipped (1379 baseline + 9
      new tests, no regressions, no skip count change).
- [x] **DoD-7** — `databricks/CLAUDE.md` describes the new flow accurately. *(T10)*
      **Closed 2026-09-08 (T10).** Added/updated sections: the repo-layout
      block (new entries for `vdr_progress.py`, `final_report_view.py`,
      `final_report_narrative.py`, `final_report_entry.py`,
      `templates/final_report.html.j2`, `templates/_mps_page.html.j2`, and
      `renderers.py`'s description widened to both render functions); "VDR
      pipeline (UI-triggered)" gained "The run is now two stages" (stage
      1/stage 2 split, early `results_location` publish, the shared
      `_run_final_report_stage()` never-raises contract, the new
      `final_report.pdf`/`.html` deliverables), "Progress signal — four
      additive columns, `processing_status` unchanged" (the four columns,
      `ensure_progress_columns`'s bare-`ADD COLUMNS` mechanics, the
      three-value `processing_status` vocabulary staying exactly as-is, both
      branches' stage-key tables, and why Branch B collapses two stages into
      `vdr_pipeline`), and "MPS on the final report" (the fresh-score-vs-
      reused-run split by branch, D-02). Re-stated the two standing warnings
      (no job/task parameters; one Git folder feeds both VDR jobs) inline in
      the VDR pipeline section, since stage 2 makes both more load-bearing.
- [x] **DoD-8** — The illustrative `sample_bundle.py` is not in the shipped
      package — test fixtures only. *(T01; evidence: it lives under
      `tests/fixtures/` and nothing under `databricks/` imports it)*
      **Closed 2026-09-07.** Evidence: fixture landed at
      `tests/fixtures/final_report_sample_bundle.py`; `grep -rn "sample_bundle"
      databricks/` returns nothing (exit 1). Template and view module copied
      byte-identical (`diff` empty both ways); no `tests/fixtures/__init__.py`
      created (the directory is not a package — no existing `__init__.py`
      there). `.gitignore` negation was already in place;
      `git check-ignore docs/plans/final_report/final_report_plan.md` exits 1
      (not ignored). Smoke-check printed `ok`. `renderers._autoescape_html_templates`
      confirmed unchanged — it matches on `*.html.j2` suffix, which
      `final_report.html.j2` satisfies. `pytest tests/ -q`: 1205 passed / 38
      skipped before and after — no worse.

### Extra gates this plan adds

- [x] **DoD-9** — D-01 (§5) has an explicit answer from Hector, and the code
      matches it. *(T06)*
      **Closed 2026-09-07.** Path A executed: `_mps_page.html.j2` created,
      `{% include %}`d from both templates; Step 1's three before/after diffs
      (normal, degraded, two-run) empty both before and after the real swap;
      `rainmaker_opportunity_summary.html.j2`'s diff is only the block→include
      swap; `test_rainmaker_golden_render.py` passes with the golden fixture
      unchanged; `tests/test_mps_parity.py` (new) asserts markup identity
      between the two documents and was confirmed to fail on a deliberate
      mutation, then restored. Full evidence in §5.
- [x] **DoD-10** — A-1 and A-2 (§9) are resolved against the live warehouse, and
      §4/§6 of this plan record the actual answers. *(T08, T09)*
      **A-2 half closed 2026-09-08 (T08).** Resolved against the live
      warehouse — see §4 and §9.
      **A-1 half closed 2026-09-08 (T09).** Checked live against the same
      warehouse (profile `rallyday`, `f8e7a8ed6dea21fd`):
      `SHOW CREATE TABLE rallyday_partners_llc.default.companies_vdr_history`
      has no `CHECK` constraint on `completion_status`, and
      `information_schema.table_constraints` returns zero rows for the
      table — so nothing at the database level would reject `"partial"`. But
      the column's own DDL comment reads `'Values: success | failure'`, and a
      live `GROUP BY completion_status` shows exactly `success`/`failure`/
      `NULL` have ever been written (no third value, ever). The UI's own
      source is outside this repo and could not be inspected directly, so
      given the documented binary vocabulary and zero historical precedent,
      the runner does **not** write `"partial"` — it uses
      `completion_status="success"` with `error_message` set and the failed
      stage visible in `progress_json`, exactly the fallback the plan
      anticipated in §9. Recorded in full in §6.
- [x] **DoD-11** — F-2's final list of genuinely-absent bundle fields is written
      into §9. *(T02)*
      **Closed 2026-09-07.** Every `bundle.get(...)` path `final_report_view.py`
      reads was traced (§1.4 T02 close-out table): 0 RENAME, 0 RESHAPE, all 12
      fields ABSENT (the original 8 plus 4 the spot-check found). F-2 in §9
      replaced with the flat follow-up list (field → degraded section → agent
      that would need to change). No read in `final_report_view.py` changed.
      Also landed in the same commit: `_pnl_table` adopts
      `rainmaker_view._financial_periods` (chronological sort) and
      `_normalize_period_units` (unit-outlier correction); `parse_percent`
      delegates to `rainmaker_view._parse_percent` (proven equivalent);
      `parse_money` stays inline (proven divergent on magnitude suffixes,
      pinned as a test); `_ASSUMPTION_SUPPORT_CLASS`/`_LABEL` added for the
      Supported/Plausible/Stretch → high/medium/low translation; `run_mode`
      param added to `final_report_view()` (A-3). Evidence:
      `tests/test_final_report_numeric_parity.py` (36 new tests, all green);
      `pytest tests/ -q`: 1241 passed / 38 skipped (was 1205/38 — no
      regressions, no skip count change); `git diff --stat` against every
      §7 read-only file is empty; only `final_report_view.py` was modified.
- [x] **DoD-17** — The format caps and the screening thresholds are pinned as
      literal policy, and both mutants that survived T03 (raising a cap, flipping
      a screen's direction) now fail a test. *(T03b; evidence: the two mutant
      failure summaries below)*

      Mutant 1 — `CAP_QUESTIONS = 8` → `12`:

      ```
      FAILED tests/test_final_report_view.py::test_cap_constant_pinned_literally[CAP_QUESTIONS-8]
      AssertionError: assert 12 == 8
       +  where 12 = getattr(frv, 'CAP_QUESTIONS')
      1 failed, 68 passed in 0.08s
      ```

      Mutant 2 — `nrr_pct` screen `"dir": "min"` → `"max"`:

      ```
      FAILED tests/test_final_report_view.py::test_screens_table_pinned_literally
      AssertionError: assert {('healthcare..., 'max'), ...} == {('healthcare..., 'max'), ...}
      Extra items in the left set:
      ('tech_services', 'nrr_pct', 90, 'max')
      Extra items in the right set:
      ('tech_services', 'nrr_pct', 90, 'min')
      1 failed, 68 passed in 0.08s
      ```

      Both files restored via `git checkout --` after each mutant;
      `git status --porcelain` clean before commit. `pytest tests/ -q`:
      1311 passed / 38 skipped (14 new tests over the 1297 baseline — 10
      literal cap pins, 1 cap-coverage check, 1 screens-table pin, 2
      hardcoded-threshold behavioural tests), no regressions. `git diff
      --stat` under `databricks/` is empty — no production code changed.
- [x] **DoD-16** — The final report's business page carries the Sep 4 content
      (F-6): `core_business` renders, and the prose reflects `sale_process` /
      `key_partners` when those fields are non-empty.
      **Amended 2026-09-08 (Hector): the page *count* is not the criterion — the
      *format* is.** The report may run to twelve pages. What it may not do is
      spill a section so that a sheet carries only chrome — a running header and a
      footer with no content. Measured with the method in §1.8. *(T11 content
      ✓ landed; pagination verification deferred to T07)*
      **Pagination closed 2026-09-08 (T07).** Measured with headless Chrome
      per §1.8 (WeasyPrint dies on `libgobject` here; PyMuPDF Story ignores
      `@page` and is not evidence — both ruled out): the illustrative bundle
      renders 11 pages without `core_business` and 11 pages **with** it after
      the fix below (previously 12, with a page carrying only 199-204
      characters of running-footer chrome and nothing else). Fix: folded the
      three `core_business` lines into the existing "What The Business Does"
      card (`<p class="core-line">`) instead of a second bordered
      `.one-liner` box above it, plus a small amount of CSS tightening on the
      same page (`h3.block`, `.cols-2`, `.card .body`, `ul.b` margins/padding)
      — no cap raised, no font shrunk, `core_business` still renders after
      the fix (confirmed in the HTML). Per-page character counts (with
      `core_business`, 11 pages): `[2076, 1170, 2263, 1917, 1393, 1267, 1711,
      1607, 3773, 3006, 1765]` — no page under 250 characters, so no orphan
      sheet. Evidence: `tests/test_final_report_pagination.py`
      (`test_business_page_core_business_does_not_spill_an_orphan_sheet`),
      skippable only where headless Chrome is genuinely absent (not the case
      on this machine — the test ran for real, not skipped).
- [x] **DoD-15** — Page 8 renders the plan-vs-history chart and the assumptions
      table from `{catalog}.analysis.forecast` (D-03), and degrades to "not
      extracted" when that table is absent or empty. The chart's footnote states
      that the plan declares no projected EBITDA margin when the plan rows carry
      none (§1.7), and the historical margin is **never** extended across plan
      periods. *(T05 + T07)*
      **Closed 2026-09-08 (T10, marking T05's already-landed evidence).**
      `final_report_entry._load_forecast()` reads back
      `{catalog}.analysis.forecast`, maps `revenue_build_comparison` →
      `forecast_rows` and the assumption columns → `forecast_assumptions`,
      and never raises — a missing table, an empty result, or malformed JSON
      all collapse to `{}` (`tests/test_final_report_entry.py::
      test_load_forecast_returns_empty_dict_on_raising_spark` /
      `_on_empty_table` / `_on_malformed_json`), which
      `final_report_view._forecast()` then renders through the same "not
      extracted" fallback as every other absent section
      (`tests/test_final_report_render.py`'s near-empty-bundle scenario
      asserts the literal string "Forecast assumptions — not extracted from
      the data room."). `test_forecast_reaches_narrative_and_render` confirms
      a present forecast reaches both the narrative digest and the render
      bundle unmodified, and that the raw bundle `BundleBuilder` returned is
      left unmutated. The footnote clause is pinned by three tests in
      `tests/test_final_report_view.py`
      (`test_forecast_footnote_gains_clause_when_plan_rows_carry_no_margin`,
      `..._omits_clause_when_plan_rows_state_a_margin`,
      `..._omits_clause_when_there_are_no_plan_rows`) — `_forecast()` only
      ever reads `margins[len(hist):]` (the plan-period slice) for the
      clause decision and never substitutes the historical margin into a
      plan-period `line_pct`/`line_value`, so a plan with no stated margin
      renders `None` all the way to the chart rather than an inferred value.
      `pytest tests/test_final_report_view.py -k forecast -q`: 3 passed.
      `pytest tests/test_final_report_entry.py -k forecast -q`: 5 passed.
      `pytest tests/test_final_report_render.py -q`: 7 passed (pagination
      re-confirmed separately under DoD-16 — this box is about content and
      degrade, not page count).
- [x] **DoD-14** — The final report and the executive review, built from the same
      bundle, agree on the P&L column order and on the stated unit (§1.6). *(T02;
      evidence: a test that renders both and asserts both are identical)*
      **Closed 2026-09-08 (T10, marking T02's already-landed evidence).**
      `tests/test_final_report_numeric_parity.py::test_pnl_period_order_and_unit_label_match_executive_review`
      builds a bundle with periods out of emission order and one period
      extracted in a different unit than its neighbours, renders both
      `rainmaker_view._financial_table` and `final_report_view._pnl_table`,
      and asserts identical `periods` ordering and identical `unit_label`
      (`"in millions"`) on both.
      `test_pnl_cell_values_match_executive_review_for_revenue_and_ebitda`
      extends this to the cell values themselves (Revenue, EBITDA), through
      the same `_normalize_period_units(_financial_periods(bundle))`
      pipeline both documents share — the growth/CAGR column is deliberately
      excluded (documented presentation difference, not a defect; see the
      DoD-2 T03 evidence note). `pytest
      tests/test_final_report_numeric_parity.py -q`: 37 passed.
- [x] **DoD-13** — The final report's six analyst takes and its cover
      recommendation render from `final_report_narrative`, and a degraded
      narrative renders zero take boxes with no page missing (§3.5). *(T11)*

      **T11 close-out (2026-09-08).** `final_report_narrative.py` (new,
      additive) builds a six-section digest from the bundle (business,
      financial, customer, kpi, quality, forecast — the last falling back to
      historical P&L when no forecast data path exists) and makes exactly
      **one** bounded call through the gateway
      (`agents.shared.llm_client.chat`, `max_tokens=3_000`,
      `temperature=0.0`, both pinned at the call site and asserted on the
      mock's kwargs, not the result) producing the six takes plus a
      structured recommendation. Never raises: a raising gateway, malformed
      JSON, and valid-JSON-wrong-schema all degrade to
      `final_narrative_status="degraded"` with every field `None` — three
      dedicated tests confirm no exception escapes any of the three paths.
      The prompt forbids fabrication and empty-section takes verbatim:
      *"Never invent a figure, name, date or fact that is not in the
      input"* and *"Do NOT produce a take for a section whose digest is
      empty"* (also: *"Never mention the Minimum Pursuit Score..."*, per
      task prompt §2.3). `rainmaker_narrative.py` is untouched
      (`git diff --stat` empty) and none of its private helpers are
      imported — this module writes its own ~40-line digest, per the task's
      instruction that duplicating it is the cheaper mistake.

      `build_final_report` now calls both narrative layers and merges
      `{**er_narrative, **fr_narrative}` (T11's dict wins the one
      overlapping key, `recommendation`), surfacing both
      `synthesis_status` and `final_narrative_status` in its return value.
      Two view-layer edits close the loop in `final_report_view.py` (ours,
      not read-only): `_kpi_scorecard` takes `narrative` and reads
      `kpi_take` instead of the old hardcoded `None`; a new `_recommendation()`
      adapter wraps a bare-string recommendation (a degraded T11 call
      alongside a successful ER one) as `{"verdict": None, "rationale":
      <string>, "conditions": [], "tone": None}` instead of silently
      printing "Not yet concluded" over a usable sentence. F-6's
      `core_business` (already produced by the ER narrative, not by this
      module) is threaded into `business.core_business` and rendered on
      `final_report.html.j2`'s business page (new markup, 3 lines, reusing
      the existing `.one-liner` CSS class).

      Evidence: `tests/test_final_report_narrative.py` (19 tests — digest
      shape, the pinned-kwargs single-call assertion, the three
      never-raises paths, unknown-key dropping, dict/list-to-`None`
      coercion, the empty-digest/`None`-preserved case, and the two
      prompt-text assertions above) plus 11 new tests in
      `tests/test_final_report_view.py` covering the two view edits and a
      six-boxes-populated / zero-boxes-degraded assertion on
      `final_report_view()`'s six take sites (the render-level HTML
      assertion belongs to T07, not yet run). `pytest
      tests/test_llm_gateway_convention.py -q` — 13 passed (this module
      routes through the gateway with no raw deploy-client construction).
      `pytest tests/ --collect-only -q` — **1394 tests collected** (up from
      1366); `pytest tests/ -q` — **1359 passed / 38 skipped** (up from
      1331/38, no regressions, no skips added or removed).

      **Pagination gate — partially verified, environment-limited.**
      WeasyPrint is unavailable in this sandbox (`libgobject-2.0-0` cannot
      load; this is also why 38 tests are already skipped repo-wide), so the
      true WeasyPrint-rendered page count could not be measured here — the
      same limitation `test_rainmaker_render.py` already works around with
      `pytest.importorskip`/try-except-skip. Rendered
      `final_report_sample_bundle.py` through the real
      `render_final_report()` path (PyMuPDF Story fallback) twice — once
      with the pre-T11 narrative, once with `core_business` (3 lines) and
      `kpi_take` added — and both produced **16 pages** under that fallback
      engine: zero page-count regression from wiring core_business. The
      fallback engine is known to paginate differently from WeasyPrint
      (`test_rainmaker_render.py`'s own comment), so 16 is not the
      production figure; T07 (which runs where WeasyPrint is available)
      should re-confirm the true count is still eleven.
- [x] **DoD-12** — On Branch B, the final report's MPS page carries the *same*
      run as the executive review's — one column, same total, same verdict — with
      no second `MPSAgent().score` call (D-02, §3). *(T05 + T09; evidence: a test
      asserting `MPSAgent.score` is not called when `reuse_mps_run` is supplied,
      and a runner test asserting Branch B passes the read-back run)*
      **T05 evidence (the `reuse_mps_run` path never calls `MPSAgent.score` —
      not the box-closing evidence, T09 closes this box).**
      `build_final_report()` checks `reuse_mps_run is not None and
      reuse_mps_run` (not `reuse_mps_run or score(...)`, so a falsy-but-valid
      degraded run dict — which is truthy in practice — is never swallowed):
      when true, the supplied run is used as-is (`mps_source="reused"`) and
      `MPSAgent().score` is never invoked. When `reuse_mps_run` is supplied
      but empty/malformed (the read-back found nothing), `build_final_report`
      falls back to a fresh `MPSAgent().score` call and reports
      `mps_source="scored_fallback"` — an MPS page with a number beats an
      empty one, and the fallback is visible in stdout
      (`[final_report] reuse_mps_run was requested but the read-back was
      empty/malformed; falling back to a fresh MPSAgent().score call`).
      Evidence:
      `tests/test_final_report_entry.py::test_reuse_mps_run_skips_scoring_and_reaches_render_as_mps`
      uses a mock that raises `AssertionError` if `MPSAgent.score` is called
      at all (not just an inspection of the code) and asserts the supplied
      run reaches `render_final_report` as `mps` with `mps_source="reused"`;
      `test_reuse_mps_run_fallback_scores_when_readback_was_empty` passes
      `reuse_mps_run={}` and asserts `MPSAgent.score` **is** called once with
      `mps_source="scored_fallback"`. `pytest tests/ -q`: 1329 passed / 38
      skipped — see the DoD-2 T05 note for the full run.
      **T09 evidence (closes this box) — the runner passes the ER's own
      read-back run through, unmodified.** Branch B's
      `_run_final_report_stage(..., run_mode="full_vdr_no_cim",
      run_ingest=False, run_agents=False, prior_run_modes=(),
      rescore_mps=False)` reads back `_load_prior_mps_runs(spark,
      VDR_CATALOG, company_name, ("full_vdr_no_cim",))` — the ER's own run
      mode, since the ER already scored this exact bundle (D-02) — and passes
      `existing[-1]` straight through to `build_final_report(...,
      reuse_mps_run=reuse)` by object identity, never re-shaping it. Evidence:
      `tests/test_run_vdr_rainmaker.py::test_branch_b_d02_reuses_the_ers_mps_run_and_never_rescopes`
      patches `agents.workstreams.mps_agent.MPSAgent.score` with a mock that
      raises `AssertionError` if called at all, asserts it is never called,
      and asserts `build_final_report`'s `reuse_mps_run` kwarg `is` (identity,
      not just equality) the exact dict `_load_prior_mps_runs` returned.
      `test_branch_b_readback_empty_falls_back_to_scoring` covers the
      empty-read-back case: `reuse_mps_run=None` reaches `build_final_report`,
      and the run still completes `done`/`success` (the fallback-to-scoring
      behavior itself is T05's, already proven in `test_final_report_entry.py`).
      `test_branch_b_stage2_reuses_ingestion_and_agents_not_rerun` confirms
      `run_ingestion_pipeline`/`run_pipeline` are not called a second time on
      Branch B (they'd raise `AssertionError` if they were). `pytest
      tests/test_run_vdr_rainmaker.py -q`: 20 passed.
- [x] **DoD-18** — `_run_final_report_stage`'s generic `try/except` — the net
      for a stage-2 failure nobody wrote a specific branch for — is proven to
      actually catch, not just present. *(T09b; evidence: two new tests, each
      with a different stage-2 collaborator raising a plain `RuntimeError`,
      plus an adversarial mutation of the `except` block that fails without
      them)*
      **Closed 2026-09-08.** T09's stage-2 failure tests (DoD-2/DoD-5) only
      exercised **handled** paths — an early `return` on a non-`SUCCESS`
      parse phase, or on `build_final_report` reporting `status="failed"`.
      Neither ever reached the helper's own `except Exception`. Added to
      `tests/test_run_vdr_rainmaker.py`:
      `test_branch_a_stage2_unanticipated_exception_keeps_er_intact` (the
      stage-2 `run_pipeline` call itself raises `RuntimeError("agent DAG
      boom")`, via a `side_effect` list so stage 1's own agent call still
      succeeds) and
      `test_branch_a_stage2_copy_final_report_raises_keeps_er_intact`
      (`shutil.copy2` raises `RuntimeError("disk quota exceeded")` only when
      copying `final_report.pdf`, real `copy2` otherwise — modeling a
      permission/quota error). Both assert: `run_vdr_rainmaker()` returns
      normally (`status="success"`, no exception escapes); `results_location`
      and the two ER files (`executive_summary.pdf`,
      `rainmaker_opportunity_summary.html`) are untouched;
      `processing_status == "done"` and `completion_status == "success"`;
      `error_message` contains the failure text; and the last
      `progress_json` write (found by scanning `updates` in reverse for the
      entry that carries that key, since the terminal record update is a
      separate, later write without it) marks the failing stage — `vdr_agents`
      / `final_report` respectively — as `"failed"`. Both raise a plain
      `RuntimeError`, not `AssertionError` (that class means "this path must
      not run" everywhere else in this file, and would have confused which
      contract each test proves).

      Adversarial verification (the acceptance evidence): inserted a bare
      `raise` as the first statement of `_run_final_report_stage`'s
      `except Exception as exc:` block (`databricks/jobs/scripts/run_vdr_rainmaker.py`),
      ran under `PYTHONDONTWRITEBYTECODE=1`:

      ```
      FAILED tests/test_run_vdr_rainmaker.py::test_branch_a_stage2_unanticipated_exception_keeps_er_intact
      FAILED tests/test_run_vdr_rainmaker.py::test_branch_a_stage2_copy_final_report_raises_keeps_er_intact
      2 failed, 20 passed, 1 warning in 3.97s
      ```

      Both new tests failed on the mutation (the other 20, including all of
      T09's handled-path tests, stayed green — confirming they don't already
      cover this). Restored the file from a pre-mutation copy, cleared every
      `__pycache__` under `databricks/`, and confirmed `git status --porcelain`
      was clean before starting and after restoring.
      `git diff --stat -- databricks/`: empty — this task is tests-only.
      `pytest --collect-only -q`: 2134 tests collected. `pytest tests/ -q`:
      1390 passed / 38 skipped (1388 baseline + 2 new tests, no regressions,
      no skip count change).

---

## 11. What shipped (T10 close-out, 2026-09-08)

**Two deliverables per run, in one `results_location`.** Both branches now
produce, in `/Volumes/rallyday_partners_llc/default/vdr/{company}/{ts}/`:
the existing executive review (`executive_summary.pdf` +
`rainmaker_opportunity_summary.html`, plus `full_report.docx` on the no-CIM
branch — all unchanged filenames), published to the record as soon as stage 1
finishes, and `final_report.pdf` + `final_report.html` from stage 2. Stage 2
cannot fail the run: any failure (ingestion, agents, or
`build_final_report` itself) leaves the ER intact, `results_location`
already pointing at it, and the failure recorded in `error_message` and
`progress_json`.

**Stage vocabulary actually implemented** — Branch A (CIM): `cim_detection` →
`cim_ingestion` → `cim_agents` → `executive_review_ready` → `vdr_ingestion` →
`vdr_agents` → `final_report` → `final_report_ready`. Branch B (no CIM):
`vdr_scan` → `vdr_pipeline` (the collapsed ingestion+agents stage, §4) →
`executive_review_ready` → `final_report` → `final_report_ready`.
`processing_status` never left `{processing, done, error}` in any test that
checked every intermediate write, not just the terminal one.

**A-1 (§9) — answer: `completion_status` stays binary.** No `CHECK`
constraint exists on the live column, but its DDL comment and every row ever
written say `success | failure`, and the UI's own source could not be
inspected. The runner writes `completion_status="success"` even on a
stage-2 failure, with the failure visible in `error_message` and
`progress_json` instead of a third status value.

**A-2 (§9) — answer: the four columns, not the fallback table.** Live
`ALTER TABLE … ADD COLUMNS (progress_stage STRING, progress_pct INT,
progress_json STRING, stage_updated_at STRING)` succeeded on
`companies_vdr_history` (profile `rallyday`, warehouse `f8e7a8ed6dea21fd`).
`ensure_progress_columns()` issues the bare form (no `IF NOT EXISTS` — that
syntax does not parse on this engine) and swallows `FIELD_ALREADY_EXISTS` for
idempotency. `uc13_preview.analysis.vdr_progress` was never needed.

**D-01 (§5) — answer: one shared partial, Path A.** The MPS markup lives in
`templates/_mps_page.html.j2`, `{% include %}`d from both templates.
`rainmaker_opportunity_summary.html.j2`'s only diff against
`feature/anthropic-sdk-migration`'s merge base is that block→include swap
(1 insertion, 48 deletions); a golden-render test and a new markup-parity
test (`tests/test_mps_parity.py`) both guard it.

**Follow-up list, as it finally stands (§9):**

- **F-1.** Score-movement explanation between the two MPS columns — no agent
  produces it; still a gap, not built.
- **F-2 — CLOSED (T02).** Every bundle field the final report reads with no
  producer today is traced to its degrading section and the agent that would
  need to change; see §9's flat list.
- **F-3.** `docs/*` is gitignored repo-wide; this plan is tracked only via the
  `.gitignore` negation in §7. Still true — nothing in T10 changed that.
- **F-4 — F-9** are unchanged from §9 above (UI-side visibility for the early
  ER, the `_SCREENS`/`_CONTENTS`/caps-as-code tradeoff, the P&L
  magnitude-suffix parser divergence, F-6's resolution (wired, owned by
  T11), and `_retention_rows`'s direction bug) — none of them were in scope
  for T10 and none were touched by it.

**What T10 itself found and closed, beyond its own three boxes.** DoD-14 and
DoD-15 had their evidence already landed (T02 and T05 respectively) but were
never ticked; both are closed above with that evidence, so §10 now has no
silently-open box.

---

## 12. End-to-end verification is an operator step, not a test

**Nothing in this plan's test suite proves the two-stage flow works on a real
data room.** Every DoD box above closes on `pytest`, which runs against a
stubbed Spark session, mocked agents, and mocked renderers — no real
ingestion, no real LLM call, no real WeasyPrint/PyMuPDF render, and no real
`ALTER TABLE` beyond the one live check T08 already ran. A green suite here
means the *code paths* behave as designed under the inputs the tests
construct; it says nothing about a live CIM-bearing or CIM-less data room,
live Databricks serving latency, or the live `companies_vdr_history` record
shape.

**Operator checklist for the first real run (Hector):**

- [ ] Trigger the VDR job (`617196299594076`) for a CIM-bearing company and
      confirm both `final_report.{pdf,html}` land in the timestamped volume
      dir alongside the ER files.
- [ ] Confirm `results_location` is populated **before** the run finishes
      (i.e. while stage 2 is still running, not just at the terminal
      update), then check what the Project Lighthouse UI actually does with
      it at that moment. Per §9 F-4: if the UI only reveals the download once
      `processing_status == "done"`, the early ER is invisible and the
      two-stage split's time saving is lost in the presentation layer.
      Report that finding to whoever owns that UI — **do not** work around
      it by flipping `processing_status` to `done` after stage 1; that is
      forbidden (README rule 5 / §9 F-4) and untrue (the run has not
      finished).
- [ ] Confirm the final report's MPS page shows **two** score columns on
      this run (CIM-stage + full-room).
- [ ] **Confirm the CIM is still in scope for stage 2** (§1.3): after the
      run, check that `classification.doc_relevance` holds the CIM with
      `should_parse=true` and a tier inside the agents' `tier_filter`, and
      that `ingestion.chunks` still holds its stage-1 chunks. A CIM
      misclassified by the stage-2 classifier would quietly drop out of the
      final report's evidence.
- [ ] Trigger a no-CIM company and confirm **one** score column on the final
      report and **five** progress stages (`vdr_scan`, `vdr_pipeline`,
      `executive_review_ready`, `final_report`, `final_report_ready`).
- [ ] Check `progress_json` renders a sensible, monotonically-advancing stage
      list at a few points mid-run, on both a CIM and a no-CIM run.

**Do not tick any DoD box on the strength of a run that was not actually
observed.** None of the boxes in §10 are closed on the strength of this
checklist — they are closed on the mocked-suite evidence named next to each,
which is a different and narrower claim than "this works on a live data
room."
