# T11 — `final_report_narrative.py`: the six analyst takes and the recommendation

**Depends on:** T02 (the view's field reads), T05 (the entry point that calls this) · **Closes:** DoD-13 · **Est. size:** large

Read [`../final_report_plan.md`](../final_report_plan.md) §3.5 and
[`tasks/README.md`](README.md) before starting. Read `databricks/CLAUDE.md`'s
**"The LLM gateway"** section before writing a single model call — a static test
fails the build if you bypass it.

## Why this task exists

`final_report.html.j2` was designed with nine prose slots. The existing
`rainmaker_narrative.py` — read-only for this task — produces exactly eight keys
(`_FRAMING_RESULT_KEYS` + `_REVQUAL_RESULT_KEYS`,
`rainmaker_narrative.py:300-308`) and **none of them are the ones the section
pages need**:

| Slot | Template | Fed by the ER narrative? |
|---|---|---|
| `business_model` bullets | `final_report.html.j2` p.3 | ✅ yes |
| `key_watchouts` | cover | ✅ yes |
| `thesis_bullets` | cover | ⚠️ no — falls back to `bundle.executive.thesis_bullets` |
| `recommendation.verdict/rationale/conditions/tone` | cover, `j2:389-400` | ⚠️ shape mismatch — the ER returns a **sentence**, the template reads a **dict** |
| `business_take` | p.3, `j2:521` | ❌ |
| `financial_take` | p.4, `j2:591` | ❌ |
| `customer_take` | p.5, `j2:649` | ❌ |
| `kpis.take` | p.6, `j2:696` | ❌ hardcoded `None` at `final_report_view.py:399` |
| `quality_take` | p.7, `j2:745` | ❌ |
| `forecast_take` | p.8, `j2:788` | ❌ |

Left alone, the final report ships with six empty "Analyst take" boxes and a cover
that prints *"Not yet concluded"* while a perfectly good recommendation sentence
sits unused in the narrative dict. It would read **thinner in prose than the
executive review** — the opposite of the point. Hector chose to build the module.

## The contract

Create `databricks/agents/exec_summary/final_report_narrative.py`.

```python
def synthesize_final_report_narrative(
    bundle: dict[str, Any],
    llm_endpoint: str,
    spark: "SparkSession",
) -> dict[str, Any]:
    """The final report's section-level prose: one analyst take per section page
    plus a structured recommendation. Never raises."""
```

Returns:

```python
{
    "business_take": str | None,
    "financial_take": str | None,
    "customer_take": str | None,
    "kpi_take": str | None,
    "quality_take": str | None,
    "forecast_take": str | None,
    "recommendation": {"verdict": str|None, "rationale": str|None,
                       "conditions": list[str], "tone": str|None} | None,
    "final_narrative_status": "success" | "degraded",
}
```

`final_narrative_status` is a **distinct key** from the ER's `synthesis_status`, so
that merging the two dicts never lets one silently overwrite the other's status.

## Steps

### 1. Model it on `rainmaker_narrative.py`, do not import its privates

Same architecture: a deterministic digest builder, one bounded LLM call, a strict
result-key allowlist, a degraded-fields constant, and a public function that never
raises. Read that file end to end first — it is the pattern this must match.

**Do not import `rainmaker_narrative`'s private helpers** (`_build_digest`,
`_string_list`, …). It is read-only, and importing its privates couples the two
documents' prose layers so that a future edit to the ER changes the final report.
Write this module's own digest. Duplicating ~40 lines of digest plumbing is the
cheaper mistake.

### 2. The digest comes from the bundle, not from the view

Tempting and wrong: "let the takes comment on what is actually on the page" by
digesting `final_report_view(...)`'s output. That is circular — the view takes
`narrative` as an input (`final_report_view(bundle, narrative=…)`), so the
narrative cannot be derived from the view. Build the digest from the **bundle**.

Keep it small and bounded. One compact section per take, with only the figures
that take is supposed to comment on:

- business — `company_framing.overview_bullets`, `revenue_quality.revenue_model`,
  the revenue mix fields T02 resolved;
- financial — the P&L periods, revenue/EBITDA/margins, `financials.observations`;
- customer — concentration summary, retention, top customers;
- kpi — `kpi_dashboard` plus which screens the sector applies (read `_SCREENS`
  from `final_report_view`, do not restate the thresholds in a prompt string);
- quality — `qoe` addbacks/flags;
- forecast — forecast rows and assumptions if T02 found them, `financials`
  history otherwise.

Cap every list and truncate every string in the digest. A digest that grows with
the data room is how this call starts timing out.

### 3. The LLM call — the rules that cost real incidents

- **Route through the gateway.** `from agents.shared import llm_client`, then
  `llm_client.chat(system_prompt=…, user_content=…, endpoint=llm_endpoint,
  max_tokens=…, temperature=0.0)`. Nothing else may construct a deploy client
  (AD-001; `tests/test_llm_gateway_convention.py` fails the build otherwise).
- **Set `max_tokens` explicitly at the call site**, per `databricks/CLAUDE.md`.
  This output is six short paragraphs plus a recommendation — **3,000 is ample**.
  Do not copy the 8-12K figures from the extraction agents; the serving read
  timeout is ~120s and there is no reason to go near it.
- `temperature=0.0`, like every other call site in this repo.
- **One call, not six.** Six calls would be six times the latency and six chances
  to fail for one page of prose. The takes are correlated — the model should see
  the whole company at once.

### 4. The prompt — what to demand, and what to forbid

Mirror `rainmaker_narrative`'s prompt discipline: a JSON-only response, an exact
schema echoed in the prompt, a hard character budget per field.

Demands:

- Each take: **one or two sentences, ≤ 240 characters**, leading with the specific
  figure or fact, saying what it *means* for the deal — not restating the table
  above it. A take that paraphrases the chart is worse than no take, because it
  costs the reader a second look for nothing.
- `recommendation.verdict`: a short call. `rationale`: one sentence.
  `conditions`: at most 3 short bullets — the template slices `[:3]`
  (`j2:397`). `tone`: `"pass"` when the read is positive (the template uses it for
  the verdict block's styling, `j2:390`), otherwise omit or `null`.

Forbid, explicitly, in the prompt:

- **inventing any figure.** The model comments on the digest; it never introduces
  a number that is not in it. This is the same "nothing is fabricated" rule the
  view layer obeys, one layer up, and it is the whole risk of this task.
- commenting on a section whose digest is empty — return `null` for that take.
  A section where the agents extracted nothing must produce **no** take, so the
  template omits the box (`{%- if report.business.take %}`). An analyst take over
  absent data is fabrication with a confident voice.
- mentioning the MPS, a score, or a threshold verdict. The MPS appears once, on
  its own page, and is not previewed or restated anywhere (task prompt §2.3).

### 5. Never raises

Same shape as `rainmaker_narrative:378`: on any failure — the call, the JSON
parse, a schema mismatch — return the degraded constant (all take fields `None`,
`recommendation` `None`, `final_narrative_status="degraded"`) and print why. The
template already omits every box whose value is falsy, so a degraded narrative
renders a slightly quieter report, never a broken one.

Validate the parsed JSON against the key allowlist before returning: drop unknown
keys, coerce each take to `str | None`, coerce `conditions` to a list of strings.
A model that returns a dict where a string was asked for must not reach Jinja.

### 6. Wire it in `final_report_entry.build_final_report` (T05's module)

The final report needs **both** narratives: the ER's for the cover bullets, this
one for the sections and the recommendation.

```python
er_narrative = synthesize_rainmaker_narrative(checked, llm_endpoint, spark)
fr_narrative = synthesize_final_report_narrative(checked, llm_endpoint, spark)
narrative = {**er_narrative, **fr_narrative}   # the section layer wins on overlap
```

The overlap is exactly one key — `recommendation` — and the merge order is
deliberate: the structured dict must win over the ER's sentence, because that is
the shape the template reads. Comment that at the merge site; a future reader will
otherwise "fix" the order.

Surface both statuses in `build_final_report`'s return value
(`synthesis_status`, `final_narrative_status`) so a job log shows which layer
degraded.

### 7. Two view edits this task owns

In `final_report_view.py` (ours to extend; `rainmaker_view.py` stays untouched):

1. **`kpis.take`** is hardcoded `None` at `final_report_view.py:399`. Change it to
   `narrative.get("kpi_take")` and thread `narrative` into `_kpi_scorecard`, which
   does not currently receive it. Keep the signature change minimal.
2. **The recommendation adapter.** `final_report_view.py:497` does
   `narrative.get("recommendation") or {...}`. With the merge above it now
   receives a dict, which is correct — but make the read defensive: if a
   `recommendation` arrives as a **string** (a degraded final narrative plus a
   successful ER one), wrap it as `{"verdict": None, "rationale": <the string>,
   "conditions": [], "tone": None}` rather than handing a `str` to a template that
   does `rec.verdict`. Today that mismatch silently prints "Not yet concluded"
   over a usable sentence; the adapter is what stops that.

### 8. Tests — `tests/test_final_report_narrative.py`

Model on `tests/test_rainmaker_narrative.py` (mock the gateway; no network).

- the happy path returns all six takes and a structured recommendation, and calls
  `llm_client.chat` **exactly once**;
- `max_tokens` and `temperature=0.0` are what the call site passes — assert on the
  kwargs, since these are the values `databricks/CLAUDE.md` says to pin at the
  call site;
- a raising gateway, malformed JSON, and a valid-JSON-wrong-schema each return the
  degraded dict with `final_narrative_status="degraded"` and **no exception
  escapes**;
- unknown keys in the model's response are dropped;
- a take returned as a dict/list instead of a string is coerced to `None`, not
  passed through;
- `conditions` longer than 3 still renders (the template slices) but is a list of
  strings;
- an empty digest section yields a `None` take — build a bundle with no `qoe` and
  assert the prompt's digest for that section is empty **and** that a `None`
  come back through is preserved rather than defaulted to a string.

In `tests/test_final_report_render.py` (T07), add: with a full final narrative,
**six** `class="take"` boxes render; with a degraded one, **zero** render and no
page is missing.

## Acceptance criteria

- [ ] `pytest tests/test_llm_gateway_convention.py -q` passes — the new module
      routes through the gateway.
- [ ] Exactly one LLM call per report, `max_tokens` and `temperature` explicit at
      the call site.
- [ ] `synthesize_final_report_narrative` never raises, proven by three failure
      tests.
- [ ] `rainmaker_narrative.py` has zero diff, and none of its private helpers are
      imported.
- [ ] The prompt forbids inventing figures and forbids a take over an empty
      section — quote both lines in your close-out.
- [ ] `pytest tests/ -q` passes.

## Close out

In [`../final_report_plan.md`](../final_report_plan.md):

- Tick **DoD-13** in §10 with the render assertion (six boxes / zero boxes) as
  evidence.
- Update §3.5 with the final key list and the merge order actually shipped.

Commit:

```
feat(final-report): add the section-level narrative and structured recommendation
```
