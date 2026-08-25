# UC-13: Status Update & Next Steps

**For:** stakeholders and leadership  
**Date:** August 21, 2026  
**Program stage:** Wave 4, **Milestone 4 of 8** (product fixes — in progress)

---

## In one minute

We built a **quality measurement system** that works well on four reference companies. We opened a **stakeholder beta**, but **real beta usage is not yet feeding that system**.

- **Production environment:** no new activity since **August 3**
- **Internal lab:** active work **today** (fixes, testing, measurement)
- **CIM preview (lighter demo):** some recent use (August 20)

**Bottom line:** we can measure and improve quality internally. We are **not yet learning from stakeholder runs**. Closing that gap is the most important next step — **after** we finish the current milestone (M4).

---

## The loop we need

| Stage | What happens | Why it matters |
|-------|----------------|----------------|
| **1. Use** | Someone runs UC-13 on a real deal | Creates real-world signal |
| **2. Capture** | Run is logged — company, date, outputs | Can't improve what we don't record |
| **3. Measure** | Score retrieval + report accuracy | Turns opinion into facts |
| **4. Feedback** | People flag what's wrong; we triage | Connects user pain to fixes |
| **5. Improve** | Fix, re-run, prove it worked | Trustworthy "we fixed it" |
| **6. Iterate** | Next run is better; we show the delta | Beta becomes a learning product |

**Today:** stages 3–5 work in our **internal lab**. Stages 1–2 are **not connected** for beta users.

---

## Where we are in the program

| Stage | Status | Result so far |
|-------|--------|---------------|
| M1 — Retrieval testing | ✅ Done | Proved we can measure search quality changes |
| M2 — Issue tracking cleanup | ✅ Done | Clear backlog; nothing stale blocking work |
| M3 — Calibration honesty | ✅ Done | Quality scores mean what they say |
| **M4 — Fix 10 known product issues** | **🔄 In progress** | Each fix proven by re-run, not guesswork |
| M5–M7 — Sign-off on 3 companies | ⏳ Next | Clearsulting, GKF, SPG reach "ready" bar |
| M8 — Legal/KPI root causes | ⏳ Later | Fixes that apply across companies |

**What M4 means for you:** we're fixing known problems on our reference deals **with evidence**. That helps quality — but **does not** by itself hook up beta usage.

---

## What's working vs. what's missing

**Working**

- We know how to score quality on four companies
- We track known defects and close them with proof
- The team is actively improving the product in the lab

**Missing**

- A simple answer to: *"Did anyone use beta this week?"*
- Beta runs flowing into the measurement system
- A standard way to turn stakeholder feedback into tracked fixes
- Proof that fixes reach the environment beta users actually hit

**Why that matters:** without the loop, beta feedback stays **anecdotal** ("I think it got worse") and our measurement investment **doesn't compound** from real usage.

---

## Four phases to close the gap

### Phase A — Are people using it? *(~1 week)*

**Rationale:** We can't improve beta if we don't know whether it's running or where.

**What we do:** Confirm which button/path beta uses; weekly usage check (last run, company, success/fail).

**Result:** Clear answer — live or not — instead of guessing from old data.

---

### Phase B — Connect usage to measurement *(~2 weeks)*

**Rationale:** Every beta run should automatically enter our quality system.

**What we do:** Log each run in one place; score it against our baselines after it completes.

**Result:** "Company X, run on date Y — these areas passed, these need work" — backed by data.

---

### Phase C — Feedback becomes fixes *(ongoing)*

**Rationale:** Stakeholder reports should land in the same backlog we already use for M4.

**What we do:** Simple feedback form (company + date + what's wrong); weekly triage; re-run before saying "fixed."

**Result:** Issues don't disappear in Slack — they're tracked, fixed, and verified.

---

### Phase D — New companies get the same bar *(after M5–M7)*

**Rationale:** Beta will add deals beyond our four reference companies.

**What we do:** Repeat onboarding + quality sign-off for each new company (human review where required).

**Result:** New beta deals aren't second-class — they get the same quality path.

---

## What we gain if we invest

| Timeframe | What we'd earn |
|-----------|----------------|
| **Week 1** | Know if beta is alive; stop debating from stale assumptions |
| **Month 1** | First beta run fully scored end-to-end |
| **Quarter 1** | Visible trend: fewer open issues, measurable improvements per company |
| **Steady state** | Every beta cycle makes the next report more trustworthy |

**What we won't promise yet**

- Fully automated review of every sentence in every report (human review still required on key sections)
- That beta is already teaching the system (data says **no** since August 3 in production)

---

## Is this worth doing?

| Question | Answer |
|----------|--------|
| Do we have a real quality system? | **Yes** — M1–M3 done, M4 in flight |
| Is beta feeding it today? | **No** |
| Would wiring usage multiply what we already built? | **Yes** |
| Should we pause M4 to do this? | **No** — finish known fixes first |
| How to approach it? | **Small phases** — prove usage, then connect, then scale |

**Verdict:** **Warranted**, phased, starting with Phase A in parallel with M5–M7 if cheap.

---

## How we'll know it's working

**Weekly**

- New production activity matches beta submissions (or we document zero usage)

**Per beta run**

- Run is logged, scored, and failures enter the backlog

**Quarterly (what we'd tell stakeholders)**

- "Since your last run: X issues fixed, Y quality checks improved" — with dates and evidence

**Red flags**

- UI says "done" but production shows nothing → wiring problem
- We say "fixed" without re-running → same mistake as before M4
- Preview demo mixed up with full diligence scores → misleading story

---

## What we need from stakeholders

1. **Which path are you using?** Full diligence vs. CIM preview (different scope)
2. **Report issues with company + approximate date** (run ID coming in Phase B)
3. **Expect human review** on narrative-heavy sections for now — not fully automated yet

**What you get back**

- Honest quality trends per company
- Fixes with proof, not "we shipped an update"
- Clear line between preview demo and full diligence

---

## Decisions to align on

1. Is **production** the official home for stakeholder beta?
2. Should **CIM preview** be marketed separately (lighter product, separate expectations)?
3. Where does feedback go (form, Slack, etc.) so it ties to a run?
4. After M4–M8: formal **Phase 9** in the program, or a new wave?

---

## Snapshot (August 21, 2026)

| Environment | Role | Last activity |
|-------------|------|---------------|
| Production (full diligence) | Stakeholder beta target | **August 3** — quiet since |
| Internal lab | Team measurement & fixes | **Today** |
| CIM preview | Lighter one-pager demo | **August 20** |

*Numbers should be refreshed before any steering meeting.*

---

## Suggested order

1. **Now:** Finish M4 (known fixes with proof)
2. **In parallel (cheap):** Phase A — is beta alive?
3. **M5–M7:** Three companies reach sign-off bar
4. **When first confirmed beta run lands:** Phase B — connect to measurement
5. **Then:** Phase C feedback loop; Phase D for new companies

**The story to tell:** We've built the engine to measure quality. The next win is plugging beta into it so every run makes the product smarter.
