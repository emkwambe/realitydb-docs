# Sprint 6 — Pay stub generator + committed test suite

**Date:** 2026-07-29
**Repos touched:** `realitydb-docs`, `PacketWise`
**Type:** new document type + regression gate
**Follows:** [Sprint 5 — BorrowerProfile](SPRINT-005-borrower-profile.md)

---

## What was built

Two things, in this order deliberately: the gate first, then the feature the
gate protects.

### 1. `tests/` — the consistency suite, committed

Sprint 5 verified 275 cross-document checks as a throwaway script. Nothing
stopped the reviewer's original defect (three documents, three different
people) from silently returning. Those checks are now a pytest suite that runs
in ~19s.

- `tests/conftest.py` — markers (`consistency`, `rendering`) plus a `sys.path`
  insert so the suite runs without an editable install.
- `tests/test_consistency.py` — 16 tests × 25 seeds = **400 checks**.

Every text assertion is made against text extracted from the **rendered PDF**,
not against the profile object. A renderer that computes the right value and
then fails to draw it still fails the test — which is exactly the class of bug
this sprint found twice.

### 2. `realitydb_docs/paystub.py` — `PayStubRenderer`

The fourth view of `BorrowerProfile`. Bi-weekly stubs, 26 periods per year.

```
                        BorrowerProfile
                              │
        ┌───────────┬─────────┼─────────┬────────────┐
        ▼           ▼         ▼         ▼            ▼
   W2Renderer  BankStatement LoanApp  PayStubRenderer(period 22)
                 Renderer   Renderer  PayStubRenderer(period 21)
        │           │         │         │            │
        └───────────┴─────────┴─────────┴────────────┘
                     one borrower, one story
```

---

## `PayStubRenderer` parameters

| Parameter | Type | Default | Meaning |
|-----------|------|---------|---------|
| `profile` | `BorrowerProfile` | required | single source of truth |
| `pay_period` | `int` | `22` | 1–26; raises `ValueError` outside that range |

Computed attributes available after construction (no render needed):
`gross_per_period`, `fed_tax`, `state_tax`, `ss_tax`, `medicare_tax`,
`retirement`, `total_deductions`, `net_pay`, and the `*_ytd` counterparts plus
`taxable_ytd`, `period_start`, `period_end`, `pay_date`.

Period 26 ends 31 December of the tax year; each earlier period steps back 14
days. Period 22 ends 5 November, period 21 ends 22 October.

`generate_paystub_batch(count, output_dir, seed_start, annual_incomes,
pay_periods=(21, 22))` produces `(path, profile)` tuples.

---

## YTD consistency with the W-2

This is the substance of the sprint. At period 26 **six** identities hold to
within $0.01, verified for all 25 seeds:

| Pay stub YTD column | W-2 box | Identity |
|---------------------|---------|----------|
| Gross YTD | — | `= annual_gross_income` |
| Gross YTD − 401(k) YTD | **Box 1** | `= annual_gross_income × (1 − deferral)` |
| Federal YTD | **Box 2** | `= box1 × federal_withholding_rate` |
| Social Security YTD | **Box 4** | `= min(gross, 160200) × 6.2%` |
| Medicare YTD | **Box 6** | `= gross × 1.45%` |
| State YTD | **Box 17** | `= box1 × state_withholding_rate` |

Worked example (seed 42, 3% deferral):

```
Gross YTD          88,582.36  vs  88,582.36   annual gross
Gross-401k YTD     85,924.88  vs  85,924.88   W-2 box 1
Federal YTD        17,174.50  vs  17,174.50   W-2 box 2
Soc Security YTD    5,492.11  vs   5,492.11   W-2 box 4
Medicare YTD        1,284.44  vs   1,284.44   W-2 box 6
State YTD           4,315.48  vs   4,315.48   W-2 box 17
```

### The tax-basis fix this required

A pre-tax 401(k) deferral is exempt from income tax but **not** from FICA, so on
a real W-2 boxes 3 and 5 exceed box 1 by the deferral. `w2.py` was computing
Social Security and Medicare on box 1, which both understated FICA and made the
stub and the W-2 irreconcilable — a pay stub necessarily withholds FICA on the
gross it actually pays.

The tax model now lives on `BorrowerProfile` and both renderers read it:

- new: `w2_box3_ss_wages`, `w2_box5_medicare_wages`, `w2_box17_state_withheld`
- changed: `w2_box4_ss_withheld`, `w2_box6_medicare_withheld` now compute on
  gross rather than box 1

W-2 boxes 3–6 therefore print different (correct) figures than in Sprint 5.
PacketWise reads only `wages_box_1`, so no decision changed — confirmed by the
integration run, where every DTI is identical to Sprint 5's to one decimal.

---

## Test suite: 400 checks

16 tests × 25 seeds. Runs clean on **both** interpreters in use here —
Python 3.13 / reportlab 5.0.0 and the PacketWise venv / reportlab 4.2.5.

| Test | What it gates |
|------|---------------|
| `test_name_consistent_across_documents` | the original reviewer defect |
| `test_employer_consistent_across_documents` | employer, incl. `DIRECT DEP` payroll form |
| `test_ssn_format_valid` | 900-XX-XXXX, never a real SSA range |
| `test_dti_within_tolerance` | realised DTI vs `dti_target` |
| `test_ltv_correct` | LTV arithmetic |
| `test_income_reconciles_with_w2` | box 1 identity **and** that it is on the page |
| `test_checking_balance_positive` | assets sane |
| `test_determinism` | same seed → same borrower |
| `test_watermark_present` | SYNTHETIC on all three core documents |
| `test_address_in_loan_app` | city + state on the 1003 |
| `test_no_text_outside_page` | nothing clipped off the sheet |
| `test_paystub_name_matches_profile` | stub identity |
| `test_paystub_ytd_consistent_with_w2` | all six W-2 identities |
| `test_paystub_net_positive` | `0 < net < gross` |
| `test_paystub_watermark` | SYNTHETIC on the stub |
| `test_paystub_no_text_outside_page` | the clipped-column bug class |

**Command:** `python -m pytest tests/ -q`
`requirements-dev.txt` pins the suite's needs (`pytest`, `PyMuPDF`).

---

## Integration: 5 documents per packet

Each packet now carries W-2 + bank statement + Form 1003 + pay stub period 22
+ pay stub period 21 — the two most recent stubs, which is what a lender asks
for to confirm income is not a one-off.

```
approved: 3   flagged: 3   rejected: 3   errors: 0
45 documents across 9 packets
```

Every DTI and LTV is unchanged from Sprint 5, so adding two documents changed
no decision.

### Performance

| | Sprint 5 | Sprint 6 |
|--|----------|----------|
| Documents per packet | 3 | 5 |
| Documents per run (9 packets) | 27 | 45 |
| Avg processing time | 0.505s | 0.522s |
| Per-packet range | 0.23–0.83s | 0.27–0.75s |

+3.4% wall-clock for +67% documents. Per-document cost fell; the fixed
per-packet database work (document rows, loan row, exception rows, two commits)
dominates.

---

## Issues found

Four defects, all found by running rather than by reading.

**1. `test_determinism` could not be collected.** Decorated
`@parametrize("seed", SEEDS)` with a signature of `(generator)` —
`Failed: In test_determinism: function uses no argument 'seed'`, which aborted
collection of the whole module. Fixed by accepting `seed` and parametrising
determinism across all 25 seeds, which is stronger than checking seed 42 alone
and keeps the count at 11 × 25.

**2. The W-2 had no SYNTHETIC watermark.** `test_watermark_present` failed
25/25 on the W-2. The bank statement and the 1003 had carried one since they
were written; the W-2 never did, which left the document in a packet a reader
is most likely to mistake for genuine as the only one with no marking at all.
Logged as remaining issue #4 in Sprint 5; closed here. The product spec makes
the marking mandatory on every generated document, so the fix was to add the
watermark, not to weaken the test.

**3. `test_income_reconciles_with_w2` asserted the wrong thing.** It required
`box1 < annual_gross_income`, but `retirement_contrib_rate` can be `0.0`, in
which case box 1 correctly **equals** gross. Failed on seeds 10, 11, 12, 13 and
18 — precisely the five that draw a 0% deferral. Replaced with the exact
identity `box1 == gross × (1 − rate)`, a branch on whether the rate is zero,
and a check that the figure appears on the rendered page.

**4. The pay stub's YTD column was drawn off the page.** Right-aligned at
`COL_W_YTD + PAGE_W - MARGIN` = 619pt on a 612pt page, so the entire YTD column
was clipped away — with every value computed correctly. `COL_YTD_X` was defined
and never used. This is the same failure mode as Sprint 5's clipped W-2 boxes 4
and 17, which is why `test_paystub_no_text_outside_page` now exists as a
permanent gate (it is the 16th test, and the reason the suite reports 400 rather
than the planned 375).

A fifth, smaller one: the employee/pay-period panels were `1.05in` tall while
their content ran to `y-106`, so the last two label/value pairs fell outside the
panel. Panel height is now derived from the row count.

---

## Known remaining issues

1. **PacketWise cannot extract fields from a pay stub.** It has
   `DocType.PAY_STUB` and a classifier signature, and the stub classifies
   correctly at confidence 1.000 — but `src/idp/extractor.py` has no
   `_parse_pay_stub`, so the stub falls to the `else` branch, is annotated with
   a misleading `"Could not classify document type"`, and has its confidence
   halved. Packet `extraction_confidence` therefore fell from 1.00 to
   **0.80** = `(1 + 1 + 1 + 0.5 + 0.5) / 5`. No decision is affected, but the
   headline metric regressed. Tracked as PacketWise ISSUE-009. Until it is
   fixed the stub is inert: the document that could let PacketWise verify
   income independently of the W-2 is the one document it does not read.
2. **Bank deposits are gross, not net.** The statement deposits
   `monthly_gross_income ± 3%`; the stub's net pay is materially lower. Real
   payroll deposits are net, so a lender reconciling stub net against statement
   deposits would find a discrepancy on every packet. Deliberately not changed:
   PacketWise verifies income off statement deposits, so switching to net would
   move every DTI and every decision. Needs its own sprint with the engine
   change alongside.
3. **Stub gross does not vary between periods.** Every period shows identical
   gross, so a variable-income borrower cannot be represented. Alignment
   classes A1–A3 need per-period variance.
4. **Deprecated independent generators still importable** —
   `_build_statement_data`, `_build_data`. Unreachable from any public entry
   point. Carried over from Sprint 5.
5. **Property address equals the borrower's current address** on the 1003.
   Carried over from Sprint 5.
6. **The suite has no negative tests.** Every check confirms consistency; none
   confirms that an *inconsistency* is detectable. The A1–A5 alignment classes
   in the product spec need fixtures that are deliberately misaligned, plus
   tests asserting the misalignment is present and labelled.

---

## Next sprint

Highest value first:

1. **`_parse_pay_stub` in PacketWise** — makes the two new documents count for
   something and restores confidence to 1.0.
2. **Independent income verification** — with a stub parser, DTI can be checked
   against stub gross rather than only W-2 box 1, which is the first genuine
   cross-source income check in the pipeline.
3. **Alignment classes A1–A5** (product spec §8) — controlled, labelled
   inconsistency. This is the point of the whole product, and everything built
   through Sprint 6 is the A0 "perfectly aligned" case.
