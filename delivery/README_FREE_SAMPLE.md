# RealityDB Financial Cases — Free Sample Pack

Thank you for downloading the RealityDB
Financial Cases free sample pack.

## What Is Inside

This pack contains 5 complete synthetic
underwriting cases:

  2 approved borrowers
  2 flagged borrowers (manual review)
  1 rejected borrower

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
    income.json              Wages + withholding
    liabilities.json         Debts + assets
    case_manifest.json       Complete case metadata

  evaluation/   Evaluation layer
    expected_extractions.json  What to extract
    alignment_matrix.json      Cross-doc checks
    expected_decision.json     Correct outcome

  README.md     Case summary

30 PDFs, 41 JSON files, 5 case READMEs.

## Core Principle

A financial document is not the financial world.
It is an observation of the financial world.

Every document in this pack derives from a
single BorrowerProfile — one source of truth.
Same name, same employer, same income appears
across all documents in every case.

## Using This Pack

Test your document AI:
  Feed the PDFs to your extraction pipeline.
  Compare against expected_extractions.json.

Test your underwriting AI:
  Run the full packet through your system.
  Compare your decision against
  expected_decision.json.

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

Comparing pay stub YTD *gross* against W-2 Box 1
differs by the deferral rate. That is the most
common mistake we see, and
evaluation/alignment_matrix.json states each
document's basis explicitly.

## Alignment Class

Every case in this pack is A0 — perfectly aligned.
Every material value reconciles across every
document that states it. Use it for OCR baselines,
field-extraction accuracy and happy-path workflow
testing.

Controlled misalignment — fraud cases where the
loan application overstates income against the
W-2 and the bank deposits — is in the
Professional Pack.

## All Documents Are Synthetic

Every document is watermarked SYNTHETIC — NOT VALID.
SSNs use the reserved 900-xx-xxxx range, which the
SSA has never issued.
No real borrower data. No PII.

Safe to share across your team.
No compliance review needed.

## Reproducibility

Every case is generated from a seed. The same seed
and the same generator version always reproduce the
same case exactly. Seeds are recorded in each
case's truth/case_manifest.json.

## Licence

Permitted: software development, QA, model training,
internal evaluation, demonstrations, research.

Prohibited: representing these documents as
authentic, submitting them to real lenders,
identity fraud, removing synthetic markings, resale
of the raw dataset.

## Upgrade

Starter Pack (20 cases): $299
Professional Pack (50 cases + timeline fraud cases): $799

realitydb.dev/financial-cases/

## Contact

eddy@mpingo.ai
Mpingo Systems LLC
4030 Wake Forest Road Suite 349
Raleigh, NC 27609
