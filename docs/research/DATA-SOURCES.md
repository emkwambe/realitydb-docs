# Data sources and methodology

**What informs the financial parameters in a RealityDB Financial Case, and
what does not.**

This file exists because the case manifest points at it. It is deliberately
written to be checkable against the code.

---

## Summary

**No case in this generator is sampled from, or calibrated against, any
published dataset.**

Parameters are chosen to produce specific, reproducible underwriting outcomes.
That is the right design for the current product — a test fixture whose
expected decision is known in advance — but it is not the same thing as
statistical realism, and it should not be described as such.

---

## What was previously claimed, and why it was removed

Through Sprint 7C, `case_manifest.json` and `PACK_MANIFEST.json` both carried:

```json
"data_sources": [
  "IRS SOI 2022",
  "HMDA 2023",
  "CFPB Credit Score Trends 2023",
  "Census ACS 2022"
]
```

Nothing in the generator reads, derives a distribution from, or validates
against any of those. The list asserted a provenance the code does not have, in
a file shipped to customers. It was replaced in Sprint 7D with a `methodology`
block that describes what the generator actually does.

---

## What the parameters actually are

Defined in `realitydb_docs/packet.py::SCENARIOS` and
`realitydb_docs/profile.py`. The manifest's `methodology` block computes its
stated ranges from `SCENARIOS` directly, so the two cannot drift.

| Parameter | Source | Range in a case pack |
|-----------|--------|----------------------|
| Annual gross income | Fixed per scenario tier, ±2% per-case variation | $57,600 – $102,000 |
| DTI | `dti_target` per tier; liabilities sized so realised DTI **equals** the target | 36% – 55% |
| LTV | Fixed loan and property amounts per tier | 76.2% – 90.0% |
| Housing payment | 24–32% of monthly gross (the "28% rule" as a band) | derived |
| Car / student loan | The remaining DTI budget, split 60/40 | derived |
| Credit card minimum | $25 – $150 | uniform |
| Other monthly debt | $0 – $100 | uniform |
| Checking balance | 1.5–3.0 × monthly gross | uniform |
| Savings balance | 2.0–8.0 × monthly gross | uniform |
| Retirement balance | 0.5–3.0 × annual income | uniform |
| Federal withholding | 12% – 22% of Box 1 wages | uniform |
| State withholding | 3% – 7% of Box 1 wages | uniform |
| 401(k) deferral | One of 0%, 3%, 5%, 6%, 8% | discrete |
| Credit score | **Not modelled.** Optional on `BorrowerProfile`; case packs do not set it | n/a |

Names, employers, job titles, cities and street names are drawn from fixed
pools in `profile.py`. The employer pool is the Microsoft sample-company set
(Northwind Traders, Contoso, Fabrikam, …), chosen precisely because those names
are recognisably fictional.

---

## What *is* grounded in real rules

The tax arithmetic is real, and is the one part of the model that follows
published rules rather than chosen ranges:

| Rule | Value | Source |
|------|-------|--------|
| Social Security wage base | $160,200 | IRS, tax year 2024 |
| Social Security rate | 6.2% | IRS |
| Medicare rate | 1.45% | IRS |
| Pre-tax 401(k) treatment | Exempt from income tax, **not** from FICA — so W-2 boxes 3 and 5 exceed box 1 by the deferral | IRS W-2 instructions |
| SSN range | 900-xx-xxxx, never issued by the SSA | SSA |

The underwriting thresholds restated in `expected_decision.json` (43% QM DTI,
50% absolute DTI, 80% LTV, 620 minimum credit score) are conventional industry
figures and mirror PacketWise's `config/rules.yaml`. They are not drawn from a
specific published rule set.

---

## What would make a distributional claim true

If a future version needs to claim real-world calibration, these are the steps
that would earn it — none of which have been done:

1. Pull an actual dataset (IRS SOI tables for income by bracket; HMDA loan
   application records for loan/property/LTV distributions; CFPB or FRB data
   for credit score distributions).
2. Fit or bin the parameter distributions to it, and store the derived
   parameters in the repo with the extraction script.
3. Add a test that compares generated aggregates against the reference
   distribution within a stated tolerance.
4. Record the dataset name, vintage, retrieval date and licence.

Until then, the honest description is the one in the manifest: synthetic
parameters chosen to produce known outcomes.

---

© 2026 Mpingo Systems LLC
