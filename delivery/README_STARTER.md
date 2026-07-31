# RealityDB Financial Cases — Starter Pack

20 complete synthetic underwriting cases.
Thank you for your purchase.

## What Is Inside

  8 approved borrowers
  6 flagged borrowers (manual review)
  6 rejected borrowers

120 PDFs, 161 JSON files, 20 case READMEs, plus a
PACK_MANIFEST.json indexing every case with its
borrower, income, DTI, LTV and expected decision.

Each case folder contains:

  documents/    6 synthetic PDFs
    w2_2024.pdf              IRS W-2 form
    bank_oct_2024.pdf        Bank statement (Oct)
    bank_nov_2024.pdf        Bank statement (Nov)
    loan_app_1003.pdf        Fannie Mae 1003
    paystub_period22.pdf     Pay stub (recent)
    paystub_period21.pdf     Pay stub (prior)

  truth/        Ground truth JSON
    borrower.json            Identity + address
    employment.json          Employer + job
    income.json              Wages + withholding,
                             every W-2 box
    liabilities.json         Debts + assets
    case_manifest.json       Complete case metadata

  evaluation/   Evaluation layer
    expected_extractions.json  What to extract
    alignment_matrix.json      Cross-doc checks
    expected_decision.json     Correct outcome

  README.md     Case summary

## Core Principle

A financial document is not the financial world.
It is an observation of the financial world.

Every document in a case derives from a single
BorrowerProfile — one source of truth. Same name,
same employer, same income across all six
documents.

## The Three Decision Tiers

Each tier is built to land on a specific side of
the underwriting thresholds, so the expected
decision is known in advance:

  approved   DTI 36%, LTV 76.2%
             Within the QM threshold (43%) and the
             conventional LTV limit (80%).

  flagged    DTI 45%, LTV 82.6%
             Between the QM threshold and the 50%
             ceiling. Also above the LTV limit.
             Manual review.

  rejected   DTI 55%, LTV 90.0%
             Past the 50% ceiling.

Realised DTI equals the tier's target exactly on
every seed — liabilities are sized backwards from
it rather than drawn at random.

## Using This Pack

Test your document AI:
  Feed the PDFs to your extraction pipeline.
  Compare against expected_extractions.json.

Test your underwriting AI:
  Run the full packet through your system.
  Compare against expected_decision.json, which
  states the thresholds it was evaluated on.

Test cross-document reasoning:
  alignment_matrix.json lists every field that
  appears on more than one document, the expected
  value, and how it should be compared — exact,
  case-insensitive, last-four, or derived.

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
on three different bases. They reconcile exactly;
they are not equal:

  W-2 Box 1                 = annual gross less the
                              pre-tax 401(k) deferral
  Pay stub YTD taxable,
    annualized              = W-2 Box 1, to the cent
  Pay stub YTD gross,
    annualized              = annual gross

FICA is computed on gross, not on Box 1 — a
pre-tax deferral is exempt from income tax but not
from Social Security or Medicare, so Boxes 3 and 5
exceed Box 1 by the deferral. Comparing pay stub
YTD *gross* against Box 1 differs by the deferral
rate and is the most common mistake we see.

## Alignment Class

Every case in this pack is A0 — perfectly aligned.
Every material value reconciles across every
document that states it.

Controlled misalignment — fraud cases where the
loan application overstates income against the W-2
and the bank deposits — is in the Professional
Pack.

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
the same case exactly. This pack uses seeds
100-119, recorded in PACK_MANIFEST.json and in each
case's truth/case_manifest.json.

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

## Licence

Permitted: software development, QA, model
training, internal evaluation, demonstrations,
research.

Prohibited: representing these documents as
authentic, submitting them to real lenders,
identity fraud, removing synthetic markings, resale
of the raw dataset.

Perpetual-download licence for internal
development and testing.

## Upgrade

Professional Pack (50 cases + 10 timeline cases
including A4 fraud): $799

realitydb.dev/financial-cases/

## Contact

eddy@mpingo.ai
Mpingo Systems LLC
4030 Wake Forest Road Suite 349
Raleigh, NC 27609
