# Sprint 10 — Decision engine + end-to-end validation

**Date:** 2026-07-30
**Repos:** `realitydb-docs`, `PacketWise`
**Type:** correctness fix + cross-repo integration
**Follows:** [Sprint 9 — life event engine](SPRINT-009-timeline-engine.md)

---

## The two problems this sprint exists to fix

Sprint 9 closed with both written down.

**Issue 1 — the expected decision was a label, not a decision.**
`profile.expected_decision` is the scenario a timeline *started* from. Nothing
recomputed it after eighteen months of life events. A `career_growth` borrower
whose DTI improved 36.0% → 34.2% still shipped `approved` — right answer,
wrong reason. Worse in the other direction: a `financial_stress` borrower who
starts `flagged` at 45.0% and is pushed to 53.8% by a layoff and a medical bill
still shipped `flagged`, which is simply wrong. A customer scoring a model
against that file would mark a correct `rejected` as an error.

**Issue 2 — nothing had ever run a timeline case through PacketWise.**
realitydb-docs asserted its fraud cases were detectable by comparing its own
PDFs. Whether the engine built to do that comparison actually caught them was
untested. Both products' central claim rested on it.

---

## Part A — `derive_decision()`

```python
def derive_decision(profile: BorrowerProfile) -> str:
    dti, ltv = profile.dti_ratio, profile.ltv_ratio
    if dti > cfg.dti_threshold_max:                    # 0.50
        return "rejected"
    if dti > cfg.dti_threshold_qm or ltv > cfg.ltv_threshold:   # 0.43 / 0.80
        return "flagged"
    return "approved"
```

Thresholds come from `config/financial.yaml`, so a bank shipping its own
underwriting bands changes the ground truth without touching Python.

**Always called on the world state.** A borrower who overstates income is graded
on what is true, never on what they claimed. Grading the claim would let the
overstatement *buy a better expected decision*, which is backwards for a fraud
fixture. `test_fraud_decision_grades_world_not_claim` asserts the claimed DTI is
strictly better than the world DTI and that the file records the world one.

**No mutation.** `BorrowerProfile` is derived, never patched, so the decision is
computed where it is written — in the two evaluation files — and
`profile.expected_decision` stays the scenario label. Both files now carry:

```json
"expected_decision": "rejected",
"decision_basis": "derived_from_evolved_state",
"starting_scenario": "flagged",
"thresholds": { "dti_threshold_qm": 0.43, "dti_threshold_max": 0.50,
                "ltv_threshold": 0.8 }
```

`starting_scenario` keeps the label available as context without letting it be
mistaken for the answer.

### Observed, seed 42

| Preset | Start DTI → decision | Final DTI → decision | Moved |
|--------|---------------------|----------------------|-------|
| career_growth | 36.0% → approved | 34.2% → approved | no |
| financial_stress | 45.0% → flagged | **53.8% → rejected** | **yes** |
| income_inflation_fraud | 55.0% → rejected | 110.0% → rejected | no |

The middle row is the bug. Before this sprint that case shipped `flagged`.

Alignment class is untouched: still A4 when a fraud event is present, A0
otherwise. The decision changed; the alignment did not.

---

## Part B/C — `PacketWise/integrate_timeline.py`

541 lines. Generates timeline cases, posts all six documents of each to
`POST /api/v1/process`, scores the response against the case's own
`evaluation/expected_decision.json`.

### Two metrics, deliberately kept apart

They measure different things and must not be added together.

**Metric 1 — decision accuracy.** Ground truth grades DTI and LTV *bands*.
PacketWise grades *violation severity*: any critical → `rejected`, any warning →
`flagged`, else `approved`. Different functions. Divergence on a fraud case was
predicted, because an overstatement is a warning while the real DTI may already
be past the ceiling.

**Metric 2 — fraud detection.** Did `INCOME_VARIANCE` fire where an
overstatement exists and stay silent where none does. This is the one that
matters: the violation is the finding, the decision label is a downstream policy
choice.

### Results — 9 cases

```
  [01] tc-01000 | career_growth          | GT:approved PW:approved MATCH
  [02] tc-01037 | career_growth          | GT:approved PW:approved MATCH
  [03] tc-01074 | career_growth          | GT:approved PW:approved MATCH
  [04] tc-01111 | financial_stress       | GT:rejected PW:rejected MATCH
  [05] tc-01148 | financial_stress       | GT:rejected PW:rejected MATCH
  [06] tc-01185 | financial_stress       | GT:rejected PW:rejected MATCH
  [07] tc-01222 | income_inflation_fraud | GT:rejected PW:rejected MATCH  [FRAUD DETECTED]
  [08] tc-01259 | income_inflation_fraud | GT:rejected PW:rejected MATCH  [FRAUD DETECTED]
  [09] tc-01296 | income_inflation_fraud | GT:rejected PW:rejected MATCH  [FRAUD DETECTED]
```

| Metric | Result |
|--------|--------|
| Decision accuracy | **9/9 (100%)** |
| `INCOME_VARIANCE` on fraud cases | **3/3 (100%)** |
| False positives on clean cases | **0/6** |
| Errors | 0 |
| Avg processing time | 0.571s (~105 cases/min) |

Income as the engine read it:

```
tc-01222: 1003 states $37,164/yr vs W-2 box 1 $27,727 = 25.4% variance
tc-01259: 1003 states $36,864/yr vs W-2 box 1 $26,659 = 27.7% variance
tc-01296: 1003 states $37,428/yr vs W-2 box 1 $26,489 = 29.2% variance
```

Against a 10% tolerance, all three fire. Violations by case:

| Case type | Violations |
|-----------|-----------|
| career_growth ×3 | *none* |
| financial_stress ×3 | `DTI_EXCEEDS_MAX`, `LTV_EXCEEDS_MAX` |
| income_inflation_fraud ×3 | `INCOME_VARIANCE`, `DTI_EXCEEDS_MAX`, `LTV_EXCEEDS_MAX` |

Clean cases show a variance equal to the 401(k) deferral rate, capped at 8%
since Sprint 5, so none crossed the 10% threshold. That cap is what makes this
test meaningful — see PacketWise ISSUE-002 for the era when `INCOME_VARIANCE`
fired on everything.

### The pipeline is closed

```
realitydb-docs                    PacketWise                ground truth
──────────────                    ──────────                ────────────
world state    → W-2, stubs, banks →  extract  →
claimed state  → 1003              →  compare  → INCOME_VARIANCE
                                                            ↑
                    derive_decision(world) ───────────────── matches
```

A synthetic borrower's real income reaches one set of documents, an inflated
figure reaches another, an independent engine reads the PDFs and reports the
gap, and the case's own truth layer confirms the gap was deliberate. That loop
is what neither product could demonstrate before this sprint.

### The predicted divergence did not happen — and why that matters

Decision accuracy was expected to be below 100%. It wasn't, because the fraud
preset stacks a 50% layoff *before* the 30% inflation, so the world DTI reaches
110% and `DTI_EXCEEDS_MAX` — a critical — fires alongside `INCOME_VARIANCE` and
decides the label.

So this fixture proves `INCOME_VARIANCE` **detects**, and cannot show it
**deciding**. A preset with a healthy DTI and an inflated income would isolate
it: `INCOME_VARIANCE` alone, moving `approved` → `flagged`. Filed as PacketWise
ISSUE-014.

---

## Tests

**439 passing**, up from 431. Eight new, not the five planned:

| Test | Asserts |
|------|---------|
| `test_derive_decision_approved` | 36% DTI, 76% LTV → approved |
| `test_derive_decision_flagged` | 45% DTI → flagged |
| `test_derive_decision_rejected` | 55% DTI → rejected |
| `test_derive_decision_uses_config_thresholds` | boundary walks with `financial.yaml`, ±1bp either side of QM and the ceiling |
| `test_career_growth_final_decision_from_state` | growth case approved on merit |
| `test_stress_timeline_decision_moves_off_its_label` | **flagged → rejected; profile label untouched** |
| `test_fraud_decision_grades_world_not_claim` | claimed DTI is better than world DTI, and the file records world |
| `test_fraud_timeline_decision_reflects_real_state` | `decision_basis`, `fraud_present`, `starting_scenario` |

The sixth is the regression gate on Issue 1; the seventh on the world/claim
split. Neither was in the plan and both guard behaviour the plan introduced.

---

## PacketWise issues

| ID | Title | Status |
|----|-------|--------|
| ISSUE-012 | Timeline cases never tested against PacketWise | **Fixed** |
| ISSUE-013 | Only the first bank statement is read | Open, Sprint 11 |
| ISSUE-014 | Fraud preset cannot isolate `INCOME_VARIANCE` | Open, unassigned |

ISSUE-013 is the one to watch. `UnderwritingEngine.evaluate()` selects documents
with `next(...)`, which takes the first match and discards the rest. A case ships
two bank statements; November is uploaded, classified, extracted, charged against
`extraction_confidence` — and never read. Harmless today because both months are
rendered from the same profile and carry identical debts. It stops being harmless
the moment they legitimately differ, which is exactly what timeline cases are
for: a `CAR_PURCHASE` at month 17 shows in November and not October, and the
engine reads the month that does not show it.

The planned conditional ISSUE-013 ("INCOME_VARIANCE threshold too wide") was not
filed. The rule fired on all three cases; there was nothing to report.

---

## Deviations from the plan

1. **`derive_decision` takes the world state, not `final_profile`.** Sprint 9
   left no single final profile — there are `world_state_at()` and
   `claimed_state_at()`. Confirmed before implementing.
2. **No write-back onto the profile.** The plan set
   `final_profile.expected_decision = derive_decision(...)`. Every
   `BorrowerProfile` in this codebase is derived, never patched. The decision is
   computed where it is written instead; same output, no mutation. Confirmed
   before implementing.
3. **Eight tests, not five.** The three extras are the config-threshold boundary
   walk and the two regression gates named above.
4. **`ltv_threshold` read via `cfg.ltv_threshold`**, not
   `cfg.financial["underwriting"]["ltv_threshold"]`. Same value, and the typed
   accessor already exists.
5. **Console output is ASCII.** The plan used `✅ ❌ 🚩 ⚠️ ✓`; piping those
   through a cp1252 console mangles them, which is how the first run printed
   `METRIC 1 �`. Same information, `MATCH`/`DIFFER` and `[FRAUD DETECTED]`.
6. **`API_KEY` reads `PACKETWISE_API_KEY` from the environment** before falling
   back to the literal, so the key is not pinned in a second file.
7. **Metrics are split three ways, not two** — overall, clean-only and
   fraud-only decision accuracy — plus an explicit false-positive count on clean
   cases. Without the last one, "3/3 fraud detected" says nothing about whether
   the rule fires indiscriminately.
8. **Ground truth is read from the case file**, not from the hardcoded
   `expected_decision` in `TIMELINE_SCENARIOS`. Those hardcoded labels would now
   be wrong for `financial_stress` — its ground truth is `rejected`, not
   `flagged` — which is exactly the bug Part A fixed.

---

## Open items for Sprint 11

1. **Reconcile multiple bank statements** (ISSUE-013). The `next(...)` selection
   is the blocker on per-document months.
2. **A fraud preset that isolates `INCOME_VARIANCE`** (ISSUE-014) — healthy DTI,
   inflated income, one violation, decision moved by that violation alone.
3. **Per-document application months.** `application_month` picks one state for
   all six PDFs. The consultant's framing — a statement from month 3 beside one
   from month 17 — needs the bundler to accept a month per document. ISSUE-013
   must land first or the second statement is discarded anyway.
4. **`expected_extractions.json` for timeline cases.** `packet.py` builds one by
   reading values back off each renderer; the timeline bundler does not, so
   timeline cases sit outside the extraction-accuracy gate that covers standard
   cases.
5. **Debts do not rescale when income collapses.** `LAYOFF` multiplies income and
   leaves every obligation untouched, which is how the fraud preset reaches 110%
   DTI. Directionally right, numerically extreme.
6. **A1/A2 alignment classes** remain unimplemented from Sprint 8.

---

© 2026 Mpingo Systems LLC | eddy@mpingo.ai
