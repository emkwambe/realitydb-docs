# Sprint 5 — BorrowerProfile

**Date:** 2026-07-29
**Repos touched:** `realitydb-docs`, `PacketWise`
**Type:** architectural refactor (no new document types)

---

## The problem this sprint exists to fix

`w2.py`, `bank_statement.py` and `loan_app.py` each drew identity, employer
and income from their own private name pools. Every generator was
deterministic on its own seed, so the suite *looked* reproducible — but
nothing tied the three documents to one person. A single loan packet named
three different borrowers.

### Reviewer finding

```
Loan application: Robert Miller
Bank statement:   Susan Johnson
W-2:              James Jones
```

This made every generated pack unusable for its stated purpose. Lenders do
not evaluate documents in isolation; they evaluate whether identity,
employment, income, assets and liabilities reconcile **across** sources. A
packet whose three documents describe three people cannot test that at all —
it only tests whether a field can be read off a page.

---

## What was built

`realitydb_docs/profile.py` — a single source of truth.

- **`BorrowerProfile`** (dataclass) — the canonical financial model:
  identity, address, employment, income model, monthly liabilities, assets,
  loan request, scenario. Computed properties derive everything a document
  needs: `full_name`, `full_address`, `monthly_gross_income`,
  `w2_box1_wages`, `total_monthly_debt`, `dti_ratio`, `ltv_ratio`,
  `down_payment`, `employer_payroll_description`.
- **`FinancialCaseGenerator.generate()`** — builds a profile from a seed plus
  scenario parameters (`annual_income`, `loan_amount`, `property_value`,
  `dti_target`, `credit_score`).
- **`_make_rngs()`** — eight independent random streams (`name`, `income`,
  `address`, `financial`, `dates`, `employer`, `misc`, `debt`), each seeded
  with a different prime multiplier. Fields cannot correlate with one
  another, so demographic proxy correlations are structurally prevented
  rather than merely unintended.

Every document is now a **view** of one profile.

---

## Architecture

```
                        seed + scenario params
                                 │
                                 ▼
                    FinancialCaseGenerator.generate()
                                 │
                     ┌───────────┴───────────┐
                     │    BorrowerProfile    │   ← single source of truth
                     │  identity · employer  │
                     │  income   · debts     │
                     │  assets   · loan      │
                     └───────────┬───────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              ▼                  ▼                  ▼
       W2Renderer      BankStatementRenderer   LoanAppRenderer
              │                  │                  │
              ▼                  ▼                  ▼
      _render_w2_pdf   _render_bank_statement  _render_loan_app_pdf
              │                _pdf │                  │
              ▼                  ▼                  ▼
          w2.pdf            bank.pdf          loan_app.pdf
              └──────────────────┴──────────────────┘
                                 │
                    one borrower, one story
```

No renderer draws a name, an employer or an income. A renderer that needed a
field the profile does not model (declarations, marital status, property
type) derives it from a generator seeded off `profile.seed`, so it stays
deterministic without competing with a profile value.

---

## Cross-document consistency test results

`W2Renderer` + `BankStatementRenderer` + `LoanAppRenderer` from one profile
(seed 42), text extracted with PyMuPDF:

```
CONSISTENCY TEST RESULTS
========================================
Borrower: Andrew Myers
Employer: Graphic Design Institute
SSN: 900-41-7435
City: Raleigh, NC

ALL CONSISTENCY CHECKS PASSED

Name appears in:      W-2 True | Bank True | Loan True
Employer appears in:  W-2 True | Bank True | Loan True
```

Extended sweep — **seeds 1–25, 11 assertions each (275 checks), all pass**:
name in all three, employer in all three (including the bank statement's
`DIRECT DEP …` payroll format), full SSN on the W-2, SSN last-4 on the 1003,
city on the W-2 and the 1003, state on the 1003.

---

## The nine alignment checks

| # | Check | Status |
|---|-------|--------|
| 1 | Same borrower name on all documents | ✅ |
| 2 | Same employer on all documents | ✅ |
| 3 | Same SSN on all documents | ✅ |
| 4 | Same address on all documents | ✅ |
| 5 | W-2 wages reconcile with stated gross income | ✅ (gross − 401k deferral) |
| 6 | Bank payroll deposits reconcile with monthly income | ✅ (± 3%) |
| 7 | Statement recurring debits equal declared liabilities | ✅ (exact profile values) |
| 8 | Statement ending balance equals declared checking assets | ✅ (derived, exact) |
| 9 | Realised DTI equals the requested `dti_target` | ✅ (exact, all seeds) |

Checks 7–9 were not achievable before this sprint at all: the amounts were
drawn independently per document.

---

## Rendering defects fixed

Two were named in the sprint brief; three more were found by geometry
assertions written to verify the fixes.

**W-2 (`w2.py`)**

1. **Boxes ran off the page.** Four 145pt boxes with 15pt gaps from `x=50`
   ended at `x=675` — past the 612pt page and past the form border at
   `x=572`. Box 4 (*Social security tax withheld*) and box 17 (*State income
   tax*) were clipped off the sheet entirely. Boxes are now sized from
   `CONTENT_LEFT`/`CONTENT_RIGHT` so all four close inside the border.
2. **Border cut through text.** The employer/employee boxes straddled the
   horizontal rule under the header, so `_draw_box` drew its label directly
   on the line. Both boxes now start `BOX_CLEARANCE` below the rule.
3. **Wage-box labels overlapped the names.** The box row was positioned by
   its bottom edge, putting the box-1 and box-3 labels on top of the employer
   and employee names — which share a left edge with them. The row is now
   positioned by its top edge, `BLOCK_CLEARANCE` below the address baseline.
4. **Header lines overlapped.** A 14pt title followed 12pt later by an 8pt
   line left the title's descenders inside the next line's glyph box.
   Baselines are now stepped by more than the leading of the larger font.
5. Padding is explicit (`BOX_PADDING_LEFT`, `BOX_PADDING_TOP`,
   `BOX_TEXT_CLEARANCE`, `MIN_LABEL_VALUE_GAP`), label/value separation is
   asserted at draw time, and long labels are truncated to the box width
   instead of running into the border.

Verified: across four seeds, **zero words outside the form border** and
**zero overlapping text spans** (pairwise span-bbox intersection > 1pt²).

**Bank statement (`bank_statement.py`)**

6. **Column misalignment.** Header labels were drawn left-aligned at
   `column_left + 4` while the three money values were drawn right-aligned at
   `column_right - 6`. Header and value sat at opposite ends of the same
   column, so the table read as misaligned on every statement. Shared column
   constants are now the single source of truth for both rows: text columns
   share a left edge, money columns share a **right** edge.

   Verified: header right edges land on 425 / 495 / 568, and the only money
   right-edges in the table body are those same three values.

   *Deviation from the brief:* it specified left-aligning the money headers.
   Left-aligning a header over right-aligned values is precisely the reported
   misalignment, so the headers are right-aligned to meet the brief's stated
   goal ("guarantees header and values always align"). `COL_BALANCE_W` is 72
   rather than 70 so the table closes on the right margin.

---

## PacketWise integration

`integrate_realitydb.py` builds one profile per packet and renders all three
documents from it. Result at `--count 9`:

```
approved: 3   flagged: 3   rejected: 3   errors: 0
```

Stable at `--count 18 --seed 500` → 6 / 6 / 6 / 0. Every packet's decision
matched its scenario.

Two profile defects were found by this run and fixed in `profile.py`:

- **`dti_target` was not honoured.** The budget formula sized car and student
  loans as `dti_target * monthly − housing`, then added the credit-card
  minimum and other-debt lines *on top*. Realised DTI always exceeded the
  target by 1.5–3.5%. With `dti_target = 0.45` that straddled the engine's
  50% absolute ceiling and two `flagged` packets came out `rejected`. All
  obligations now count against the budget; realised DTI equals `dti_target`
  exactly on every seed tested.
- **401k deferral sat on the income-variance tolerance.** W-2 box 1 is gross
  minus the pre-tax deferral, so the deferral rate *is* the variance a lender
  sees between the 1003's stated gross and the W-2's documented wages. A 10%
  rate landed exactly on PacketWise's 10% tolerance, where `$`-rounding on
  the printed form decided whether `INCOME_VARIANCE` fired — a 1-in-6 chance
  of flipping an `approved` packet to `flagged`. The deferral now caps at 8%.

---

## Backward compatibility

Both profile-driven renderer names collided with existing classes. The names
were repurposed as the brief specifies; the pre-Sprint-5 low-level renderers
are preserved under new names.

| Before | After | Interface |
|--------|-------|-----------|
| `w2.W2Renderer(output_dir)` | `w2.W2FormRenderer(output_dir)` | `.render(W2Data, filename, add_noise)` |
| — | `w2.W2Renderer(profile)` | `.render(output_path)` |
| `bank_statement.BankStatementRenderer(style)` | `bank_statement.BankStatementStyleRenderer(style)` | `.render(BankStatementData, output_path)` |
| — | `bank_statement.BankStatementRenderer(profile, month, style)` | `.render(output_path)` |
| `loan_app.LoanApplicationRenderer()` | unchanged | `.render(LoanApplicationData, output_path)` |
| — | `loan_app.LoanAppRenderer(profile)` | `.render(output_path)` |

All public batch/entry functions keep their signatures and now build profiles
internally: `generate_synthetic_w2_batch`,
`generate_synthetic_bank_statement`,
`generate_synthetic_bank_statement_batch`, `generate_loan_application`,
`generate_loan_application_batch`. Both CLI interfaces (subcommand and legacy
flat-flag) were re-run and produce documents unchanged in shape.

---

## Known remaining issues

1. **The legacy independent generators still exist.** `_build_statement_data`
   and `_build_data` draw identity independently of any profile — the exact
   defect this sprint fixes. They are marked DEPRECATED and are no longer
   reachable from any public entry point, but they are still importable. They
   should be deleted once no caller passes explicit field values.
2. **Property address equals the borrower's current address.** For a
   `Purchase` loan these should differ. The profile models one address; the
   1003 prints it in both Section 2 and Section 3.
3. **One month per statement PDF.** `BankStatementRenderer.render()` emits a
   single month; the pre-Sprint-5 generator emitted two months in one file.
   PacketWise infers the period count from the document and handles either,
   but a two-month bundle now requires two renders. A `render_range()` helper
   would restore the single-file form.
4. **The W-2 carries no `SYNTHETIC — NOT VALID` watermark.** The bank
   statement and the 1003 both do. The product spec makes the marking
   mandatory on every generated document. Out of scope for this sprint.
5. **`loan_purpose` is hard-coded to `"Purchase"`** in the generator, though
   `BorrowerProfile` models Refinance too.
6. **No automated test suite.** The consistency and geometry checks above
   were run as scripts, not committed as tests. They should become
   `tests/test_consistency.py` so the reviewer's defect cannot regress
   silently.
7. **`realitydb_docs/profile.py` shadows the stdlib `profile` module name**
   within the package. Absolute imports make this safe on Python 3, but the
   name is unfortunate.

---

## Next sprint: pay stub generator

A pay stub is the fourth view of `BorrowerProfile` and closes the income
triangle (1003 states gross, W-2 documents annual wages, statement shows net
deposits, stub shows the gross-to-net bridge).

It should render from the existing profile with no new identity fields:

- gross pay for the period, derived from `monthly_gross_income`
- federal / state withholding at `federal_withholding_rate` /
  `state_withholding_rate`
- FICA at the same rates the W-2 uses (`SS_RATE`, `MEDICARE_RATE`)
- 401k deferral at `retirement_contrib_rate`
- net pay that must equal the statement's payroll deposit, so check 6 becomes
  exact rather than ± 3%
- year-to-date columns that must reconcile with `w2_box1_wages`

That last point is the real value: a pay stub whose YTD does not tie to the
W-2 is the single most common real-world document inconsistency, and it
becomes a first-class alignment class (A1–A3) once the stub exists.
