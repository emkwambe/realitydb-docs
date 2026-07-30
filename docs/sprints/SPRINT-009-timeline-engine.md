# Sprint 9 — Life Event Engine

**Date:** 2026-07-30
**Repo:** realitydb-docs
**Type:** new subsystem + config hardening
**Follows:** [Sprint 8 — config infrastructure](SPRINT-008-config.md)

---

## The problem this sprint exists to fix

A product consultant reviewing the case packs:

> Banks don't underwrite documents. They underwrite people over time. The cases
> appear static. January — promotion. February — salary increase. March — car
> purchase. April — new address. May — mortgage application. Now the PDFs become
> snapshots of a living financial world. That is significantly harder to copy.

`BorrowerProfile` is a point-in-time financial state. Every document in a case
was a view of the same instant. Nothing in the product could say *how the
borrower got here*, which is the thing an underwriter actually reasons about.

---

## What was built

### `realitydb_docs/timeline.py` — 1,819 lines

| Component | What it is |
|-----------|------------|
| `EventType` | 21 event types across 5 categories |
| `LifeEvent` | one event; a pure function `profile_before → profile_after` |
| `BorrowerTimeline` | ordered events + `state_at(month)` |
| `TimelineCaseBundler` | complete case folder with temporal evidence |
| `generate_timeline_pack()` | ZIP of N timeline cases |

**The 21 event types.** Career: `PROMOTION`, `RAISE`, `JOB_CHANGE`, `LAYOFF`,
`NEW_EMPLOYMENT`, `SELF_EMPLOYED`. Financial: `CAR_PURCHASE`, `CAR_PAYOFF`,
`STUDENT_PAYOFF`, `LARGE_DEPOSIT`, `MEDICAL_BILL`, `DEBT_PAYOFF`. Life: `MOVE`,
`MARRIAGE`, `BABY`, `DIVORCE`. Property: `HOME_PURCHASE`, `REFINANCE`. Fraud:
`INCOME_INFLATION`, `UNDISCLOSED_DEBT`, `EMPLOYER_MISMATCH`.

(The sprint plan said 22. There are 21 — `SELF_EMPLOYED` and `NEW_EMPLOYMENT`
share a handler, which is probably where the extra one came from.)

**Events are pure.** `LifeEvent.apply()` deep-copies before dispatching to its
handler, so a handler mutating its argument is mutating a copy. The starting
profile is never touched, and `state_at(18)` called twice returns the same
numbers. Both are asserted by tests rather than left as a claim.

**`state_at(month)` is a fold, not a cache.** Every call replays the event list
from the starting profile. Slower, and correct by construction: there is no
incremental state that can drift out of step with the event list.

### Three views of one timeline

A fraud case is only a fraud case if some document disagrees with the world.
One profile cannot express that, so there are three accessors:

| Accessor | Meaning |
|----------|---------|
| `state_at(month)` | every event applied |
| `world_state_at(month)` | what is actually true — claim-side fraud excluded |
| `claimed_state_at(month)` | what the application says — hidden debt excluded |

Fraud events are classified by which side of the divide they sit on:

- `INCOME_INFLATION`, `EMPLOYER_MISMATCH` — **claim-side.** The borrower asserts
  something the world does not support. Applied to the application only.
- `UNDISCLOSED_DEBT` — **world-side.** The debt is real and shows as a recurring
  debit on the bank statements; the application omits it.

Documents are rendered accordingly: the 1003 from the claimed state, the W-2,
pay stubs and bank statements from the world state. **Without a fraud event all
three views are identical and nothing changes**, which is asserted by
`test_clean_timeline_world_equals_claimed`.

This is what makes the inconsistency detectable by reading the PDFs, which is
the task a customer is buying. Verified at seed 42:

```
world annual income   28,553.18     (bank deposits and pay stubs follow this)
W-2 box 1             26,839.99     printed on w2_2024.pdf
1003 gross monthly     3,093.26  →  37,119.12/yr printed on loan_app_1003.pdf
overstatement          30.0%
```

`test_fraud_case_documents_actually_disagree` asserts the inflated figure is on
the 1003 and is **not** on the W-2.

### Three preset timelines

| Preset | Events | Class |
|--------|--------|-------|
| `career_growth_timeline` | promotion m3 (+18%), car purchase m6 ($389/mo), raise m12 (+5%) | A0 |
| `financial_stress_timeline` | layoff m2 (42% replacement), new employment m5 (88% of prior), medical bill m9 | A0 |
| `income_inflation_fraud_timeline` | layoff m12 (50%), income inflation m17 (×1.30) | A4 |

Observed progression, `career_growth_timeline`, seed 42, $72k start:

```
Month  0: income=    73,310 | debt=   2,199/mo | DTI=36.0%
Month  3: income=    86,505 | debt=   2,199/mo | DTI=30.5%
Month  6: income=    86,505 | debt=   2,588/mo | DTI=35.9%
Month 12: income=    90,831 | debt=   2,588/mo | DTI=34.2%
Month 18: income=    90,831 | debt=   2,588/mo | DTI=34.2%
```

### Case folder

```
timeline-NNNNNN/
├── documents/            6 PDFs at the application month
├── truth/
│   ├── world_truth.json      actual state + causal_chain
│   ├── document_truth.json   what each document claims + discrepancies
│   └── timeline.json         events, narrative, serialized timeline
├── evaluation/
│   ├── causal_evidence.json  which events drove the outcome
│   └── expected_decision.json
└── README.md
```

`document_truth.json → discrepancies` is **computed by diffing the world and
claimed profiles**, not restated from the event list. A discrepancy cannot be
claimed unless the two profiles actually carry it.

---

## Part A — config hardening (the Sprint 8 gap)

Sprint 8 closed with: *"No test asserts config wiring. If someone reverts a
`cfg.` reference to a literal, all 419 tests still pass."*

**Schema validation.** `REQUIRED_KEYS` in `config.py` names the top-level keys
each file must define; `_load()` checks them after parsing and raises naming the
file, the keys and the path it loaded from. A typo in a key was previously a
`KeyError` deep inside a renderer that named neither.

**Four tests, closing the gap from both directions:**

| Test | Catches |
|------|---------|
| `test_config_ss_rate_is_consulted` | a literal that has drifted from the YAML |
| `test_config_scenario_drives_dti` | scenario params not reaching the generator |
| `test_config_override_actually_propagates` | a literal that has **not** drifted — the only form that proves the file is read |
| `test_config_missing_required_key_is_rejected` | an incomplete config loading silently |

The third one is the one that actually closes the gap. It writes a modified
`financial.yaml` to a temp dir, points `REALITYDB_CONFIG_DIR` at it, and runs a
subprocess — subprocess because `profile.SS_WAGE_BASE` is snapshotted at import
and `cfg.reload()` deliberately does not move it, so an in-process override
would prove nothing.

---

## Tests

**431 passing**, up from 419.

| Group | Count |
|-------|-------|
| Pre-existing | 419 |
| Config wiring (Part A) | 4 |
| Timeline engine (Part F) | 8 |

The eight timeline tests: determinism of `state_at`, non-mutation of the
starting profile, event ordering, promotion raises income by the stated
percentage, car purchase raises debt by exactly the payment, fraud timeline
carries flags and grades A4, fraud documents actually disagree, clean timeline
has world == claimed and reports no discrepancies.

---

## CLI

```
$ python -m realitydb_docs.cli timeline --count 3 --output output/ \
    --seed-start 200 --months 18

  [01/3] timeline-000200 | career_growth        | Janet Morris    | DTI 34.4% | A0
  [02/3] timeline-000201 | fraud                | Gary Scott      | DTI 110.0% | A4
  [03/3] timeline-000202 | fraud                | Anna Jimenez    | DTI 110.0% | A4

ZIP: output/timeline_pack_3cases.zip (0.06 MB)
```

A 6-case pack: 73 files, 36 PDFs, 31 JSON, 6 READMEs, 120.4 KB.

---

## Deviations from the plan

1. **The plan's `_load()` rewrite would have deleted the config search path.**
   It read `path = CONFIG_DIR / filename` against a constant that does not
   exist; the real loader searches `REALITYDB_CONFIG_DIR`, then the bundled
   directory, then `cwd/config`. Validation was added *inside* the existing
   loader instead. Taking the snippet literally would have removed the
   enterprise override feature Sprint 8 shipped.

2. **The plan's `test_config_ss_rate_is_consulted` asserts the wrong tax
   basis and fails.** It computes `min(w2_box1_wages, ss_wage_base) * ss_rate`.
   Social Security wages are **gross**, not box 1 — a pre-tax 401(k) deferral is
   exempt from income tax but not from FICA, which is precisely the accounting
   Sprint 6 fixed. At seed 42 the two differ by $164.76 and the test as written
   fails. Corrected to gross, with the reason recorded in the docstring so it is
   not "fixed" back.

3. **`_write_json` and the README writer needed explicit UTF-8.** The plan used
   bare `open(path, "w")`. Windows defaults to cp1252; the README carries em
   dashes and `©`, and `narrative()` originally emitted `↑`/`↓`. Every write is
   now `encoding="utf-8"`, matching `packet.py`. The arrows were also replaced
   with `up`/`down` — a JSON consumer should not have to handle them.

4. **World/claim split (largest deviation).** As planned, every document rendered
   from one profile, so `INCOME_INFLATION` inflated the W-2 and the bank
   deposits too — and `world_truth.json` and `document_truth.json` were written
   from the same object and could never differ. The fraud case would have
   carried a fraud *label* with no detectable fraud, contradicting the preset's
   own docstring ("W-2 and bank deposits tell the true story"). The three-view
   split above is the fix.

5. **Two extra tests beyond the plan's six** (items 7 and 8 above), guarding
   deviation 4 in both directions. The plan's arithmetic said "421 + 8 = 429";
   there were six tests listed. Actual: 419 + 4 + 8 = 431.

6. **Staging-directory guard on `generate_timeline_pack`.** It `rmtree`s
   `{pack_name}_cases` after zipping. Without a guard, pointing it at an
   existing directory packs unrelated files into a customer deliverable and then
   deletes them. Same guard, same wording, as `packet.generate_case_pack`.

7. **ZIP entries are walked in sorted order**, as in `packet.py`, so the same
   pack produces a comparable archive listing.

8. **21 event types, not 22.** See above.

---

## Known remaining issues

1. **`expected_decision` is not recomputed.** It is the scenario label the
   timeline started from. A `career_growth` timeline that improves DTI from
   36.0% to 34.2% still reports `approved` because it started that way — not
   because the evolved state was evaluated. Every file this module writes
   carries an `expected_decision_basis` line saying so rather than implying a
   derivation. Deriving the decision from `world_state_at(month)` against the
   thresholds already in `financial.yaml` is the obvious next sprint.

2. **Debts do not rescale when income collapses.** `LAYOFF` multiplies income
   and leaves every obligation untouched, so the fraud preset lands at 110% DTI.
   Directionally right, numerically extreme — a real borrower would default or
   restructure. The event model has no notion of that.

3. **The pack mix is only approximately 40/30/30.** `int(count * share)` per
   tier with the remainder to the last one. At `count=6` that is 2/1/3, at
   `count=3` it is 1/0/2 — no `financial_stress` case at all. Exact at
   `count=10`. Inherited from the plan's formula; worth replacing with the
   largest-remainder split `packet._default_distribution` already uses.

4. **Only A0 and A4 are graded.** `alignment_class` returns A4 if any fraud event
   is present and A0 otherwise. A3 (material inconsistency without manipulation)
   is not distinguished, because nothing in the event model separates an
   omission from an alteration. Claiming A3 would be a label the data does not
   support. A1/A2 remain unimplemented from Sprint 8.

5. **Timeline documents are still rendered at one month.** `application_month`
   selects *which* state the six PDFs describe, but a case ships one set. The
   consultant's framing — statements from month 3 and month 17 in the same
   case — needs per-document months, which the bundler does not yet take.

6. **Timeline cases carry no `expected_extractions.json`.** `packet.py` builds
   one by reading values back off each renderer; the timeline bundler does not,
   so timeline cases are not covered by the extraction-accuracy gate that
   `test_expected_extractions_appear_on_documents` applies to standard cases.

---

## The product shift

Sprint 8 and earlier: a case is a set of documents that agree with each other.

Sprint 9: a case is a **borrower with a history**, and the documents are
snapshots of that history at a chosen moment. The evaluation target moves from
*did the system extract the field* to *did the system understand what happened
to this person, and why the answer is what it is*.

That is the difference between a document generator and a decision simulation
engine, and it is the part that is hard to copy.

---

© 2026 Mpingo Systems LLC | eddy@mpingo.ai
