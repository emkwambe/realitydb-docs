# RealityDB Financial Cases — Professional Pack

50 standard underwriting cases plus 10 timeline
cases, including fraud injection.
Thank you for your purchase.

## What Is Inside

Standard cases (50):

  20 approved borrowers
  15 flagged borrowers (manual review)
  15 rejected borrowers

Timeline cases (10, in `timeline_cases/`):

   4 career growth      A0
   3 financial stress   A0
   3 income inflation   A4 — fraud

360 PDFs, 452 JSON files. Every case has its own
README.md; the pack has a PACK_MANIFEST.json
indexing the standard cases, and the timeline
cases have their own manifest.

## Two Kinds of Case

**Standard cases** are point-in-time. All six
documents describe one borrower at one moment,
and every material value reconciles. Use them for
OCR baselines, extraction accuracy and happy-path
workflow testing.

**Timeline cases** are 18-month borrower journeys.
The documents are snapshots of a financial world
that evolved — a promotion at month 3, a car
purchase at month 6, a layoff at month 12 — and
each case ships the causal chain that produced its
final state.

Each timeline case contains:

  documents/    6 PDFs at the application month
  truth/
    world_truth.json      what is actually true,
                          plus the causal chain
    document_truth.json   what each document
                          claims, plus the
                          discrepancies between them
    timeline.json         every event, with the
                          financial state after each
  evaluation/
    causal_evidence.json      which events drove the
                              outcome
    expected_decision.json    decision + thresholds
  README.md

## The Fraud Cases

Three timeline cases carry a deliberate income
overstatement. This is the part that a standard
pack cannot contain.

In a fraud case the borrower's world and their
application diverge. The W-2, the pay stubs and
the bank statements are rendered from the **world
state** — what is actually true. The Fannie Mae
1003 is rendered from the **claimed state** — what
the borrower asserted.

The result is a document set that genuinely
disagrees with itself:

  world annual income     28,553.18
  W-2 Box 1 (on the PDF)  26,839.99
  1003 gross monthly       3,093.26  -> 37,119.12/yr
  overstatement            30.0%

The inflated figure appears on the loan
application and appears nowhere on the W-2. Bank
payroll deposits follow the world state, so they
corroborate the W-2 rather than the application.

`truth/document_truth.json` carries a
`discrepancies` array computed by diffing the two
states — so a discrepancy is never claimed unless
the documents actually carry it.
`evaluation/causal_evidence.json` states what a
detector should find, and when.

**Verified end to end.** These cases were run
through an independent underwriting engine
(PacketWise, FastAPI + regex extraction). It
raised INCOME_VARIANCE on 3 of 3 fraud cases —
variances of 25.4%, 27.7% and 29.2% against a 10%
tolerance — and on 0 of 6 clean cases. The clean
cases sit under tolerance because their only
income gap is the pre-tax 401(k) deferral, capped
at 8%.

## Alignment Classes

  A0   Perfectly aligned. Every material value
       reconciles. All 50 standard cases and 7 of
       the 10 timeline cases.

  A4   Probable manipulation. 3 timeline cases.

A1 (benign variation), A2 (explainable
discrepancy), A3 (material inconsistency without
manipulation) and A5 (coordinated synthetic fraud)
are defined in the case taxonomy but are not
present in this pack.

## A Note on the Expected Decision

For standard cases, the expected decision is the
scenario tier the case was built for.

For timeline cases it is **derived** from the
borrower's world state at the application month —
DTI and LTV against the published thresholds —
never from the scenario the timeline started from.
A borrower who overstates income is graded on what
is true, so the overstatement cannot buy a better
expected decision.

Each timeline case's `expected_decision.json`
carries `decision_basis: derived_from_evolved_state`
alongside `starting_scenario`, so the two are never
confused.

## Read expected_extractions.json Carefully

It states what is PRINTED on each page, not the
underlying value. Three documents reformat:

  loan_app_1003.pdf  rounds money to whole dollars,
                     so 8,654.60 appears as $8,655
  bank statements    payroll deposit carries +/-3%
                     jitter around monthly gross
  pay stubs          employer is upper-cased, SSN
                     is masked to the last four

The exact values are in truth/. Scoring against
truth/ instead of evaluation/ will mark a correct
extraction wrong.

## The Three Income Bases

W-2 Box 1, the 1003, and the pay stub state income
on three different bases. On a clean case they
reconcile exactly; they are not equal:

  W-2 Box 1                 = annual gross less the
                              pre-tax 401(k) deferral
  Pay stub YTD taxable,
    annualized              = W-2 Box 1, to the cent
  Pay stub YTD gross,
    annualized              = annual gross

FICA is computed on gross, not on Box 1 — a
pre-tax deferral is exempt from income tax but not
from Social Security or Medicare, so Boxes 3 and 5
exceed Box 1 by the deferral.

A fraud detector must not confuse the deferral gap
with an overstatement. That is exactly what these
cases test: the deferral gap is at most 8%, the
injected overstatement is 30%.

## All Documents Are Synthetic

Every document is watermarked SYNTHETIC — NOT VALID.
SSNs use the reserved 900-xx-xxxx range, which the
SSA has never issued.
No real borrower data. No PII.

Safe to share across your team.
No compliance review needed.

## Reproducibility

Every case is generated from a seed. The same seed
and the same generator version always reproduce
the same case exactly. Standard cases use seeds
200-249; timeline cases use seeds 250-259.

## Methodology

PACK_MANIFEST.json carries a `methodology` block
describing how the financial parameters were
chosen. Read it. The short version: parameters are
synthetic and selected to produce specific,
reproducible underwriting outcomes. They are not
sampled from, or calibrated against, any published
dataset.

The tax arithmetic is real — FICA rates, the Social
Security wage base, the pre-tax deferral treatment
and the reserved SSN range all follow published
rules.

One limitation worth stating plainly: the fraud
preset applies a layoff before the overstatement,
so the borrower's real DTI is already past the
ceiling. INCOME_VARIANCE therefore fires alongside
a DTI violation rather than deciding the outcome
alone. A preset that isolates the overstatement on
an otherwise-qualifying borrower is planned.

## Licence

Permitted: software development, QA, model
training, internal evaluation, demonstrations,
research.

Prohibited: representing these documents as
authentic, submitting them to real lenders,
identity fraud, removing synthetic markings,
resale of the raw dataset.

Perpetual-download licence for internal
development and testing.

## Need Something Specific

Custom scenarios, your own document templates,
your own underwriting thresholds, or a larger
volume — the generator is config-driven and the
thresholds ship as YAML.

eddy@mpingo.ai

## Contact

eddy@mpingo.ai
Mpingo Systems LLC
4030 Wake Forest Road Suite 349
Raleigh, NC 27609
