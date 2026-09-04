# Tasks — UC13 Final Report + progress signal

Execute in numeric order. **T08 is independent** of T01-T07 and may be done at any
point. **T06 is blocked** until decision D-01 (plan §5) has an explicit answer.

| # | File | Depends on | Closes |
|---|---|---|---|
| T01 | [T01_land_inputs.md](T01_land_inputs.md) | — | DoD-8 |
| T02 | [T02_bundle_field_audit.md](T02_bundle_field_audit.md) | T01 | DoD-11 |
| T03 | [T03_view_numeric_tests.md](T03_view_numeric_tests.md) | T02 | — |
| T04 | [T04_render_final_report.md](T04_render_final_report.md) | T01 | — |
| T05 | [T05_final_report_entry.md](T05_final_report_entry.md) | T04 | DoD-2 / DoD-12 (part) |
| T06 | [T06_mps_parity.md](T06_mps_parity.md) | T04, **D-01** | DoD-9 |
| T07 | [T07_render_tests.md](T07_render_tests.md) | T05, T06, T11 | DoD-2, DoD-3 |
| T08 | [T08_vdr_progress.md](T08_vdr_progress.md) | — | DoD-6 (part), DoD-10 (part) |
| T09 | [T09_runner_stage_two.md](T09_runner_stage_two.md) | T05, T08 | DoD-2, DoD-5, DoD-6, DoD-10, DoD-12 |
| T11 | [T11_final_report_narrative.md](T11_final_report_narrative.md) | T02, T05 | DoD-13 |
| T10 | [T10_docs_and_closeout.md](T10_docs_and_closeout.md) | all | DoD-1, DoD-4, DoD-7 |

## Rules that apply to every task

1. **Read [`../final_report_plan.md`](../final_report_plan.md) first.** It is the
   contract; this task file is the instruction set.
2. **Read `databricks/CLAUDE.md`** before touching anything under `databricks/`.
   Several of its statements are warnings earned from real outages.
3. **Read-only files** (plan §7): `rainmaker_view.py` (except the one additive
   `_MPS_RUN_MODE_LABELS` entry), `rainmaker_narrative.py`, `mps_agent.py`,
   `mps_rubric.py`, `bundle_builder.py`, `validate.py`, `absence_check.py`,
   `rainmaker_opportunity_summary.html.j2` (except D-01). If you believe one must
   change, **stop** and write the reason into plan §9 instead of changing it.
4. **Never touch the `uc13` catalog.** Everything is `uc13_preview`.
5. **Never add job or task parameters** to the VDR job YAML. Fixed parameters
   block the UI's `run-now` trigger. This was a real outage.
6. **The template does no arithmetic.** If you find yourself adding a calculation
   to a `.j2`, it belongs in `final_report_view.py`.
7. **Nothing is fabricated.** A figure the agents did not extract stays `None` all
   the way to the page, where it renders "not extracted". Never draw a `None` bar
   at zero. Caps are constants at the top of the view module — do not raise them
   to fit more content in.
8. **Repo style:** `from __future__ import annotations`, type hints, module
   docstrings that explain *why*, comments that record decisions rather than
   restate the code.
9. **Tests:** pytest, in `tests/`, following the conventions already in
   `tests/test_rainmaker_render.py` and `tests/test_run_vdr_rainmaker.py` (heavy
   dependencies mocked, no cluster needed). Do not introduce a new framework.
10. **Every task ends by ticking its DoD lines** in `../final_report_plan.md` §10
    and appending a short evidence note. A box without evidence stays unticked.
11. **One atomic Conventional Commit per task, then push.** Every task ends with
    the same sequence, on the feature branch and nowhere else:

    ```bash
    git branch --show-current    # must be feature/uc13-final-report-and-progress
    pytest tests/ -q             # green before the commit, not after
    git add <only the files this task touched>
    git commit -m "<the message at the end of the task file>"
    git push -u origin feature/uc13-final-report-and-progress
    ```

    Rules that matter more than they look:

    - **`git add` the files you touched, never `git add -A`.** This repo has a
      large gitignore surface and untracked local workspaces; a blanket add sweeps
      in things that must not ship.
    - **Never commit on `main` or on `feature/anthropic-sdk-migration`.** Check the
      branch before every commit — the plan branch was cut from the latter and it
      is easy to end up back on it after a `git checkout`.
    - **Do not commit unrelated changes alongside.** One task, one commit. If you
      fixed something incidental, either revert it or commit it separately with its
      own message.
    - **Tests green before committing.** A red commit on this branch makes the
      `git diff --stat` read-only proof in T10 much harder to interpret.
    - Pushing this branch is safe with respect to the Databricks jobs: they run
      whatever branch the shared Git folder is checked out to, and **nothing points
      at this branch**. Do not run `databricks repos update` — one Git folder feeds
      both VDR jobs and it can swap code mid-run (`databricks/CLAUDE.md`).
    - **Never force-push**, and never rebase a commit that is already on the
      remote.

12. **If a task cannot be completed as written, stop and say so.** Write the reason
    into `../final_report_plan.md` §9 and leave its DoD box unticked. A task that
    half-lands silently is worse than one that reports a blocker — the DoD is the
    only record of what actually shipped.
