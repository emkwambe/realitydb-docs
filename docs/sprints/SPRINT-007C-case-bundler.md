# Sprint 7C — Case bundler

**Date:** 2026-07-30
**Repo:** realitydb-docs
**Type:** commercial deliverable assembly
**Follows:** [Sprint 6 — pay stub](SPRINT-006-paystub.md)

---

## What was built

`realitydb_docs/packet.py` — the component that turns four renderers into a
sellable product.

- **`CaseBundler.generate_case(seed, scenario, ...)`** → one complete case
  folder: six PDFs, five ground-truth JSON files, three evaluation JSON files,
  and a README. 15 files.
- **`CaseBundler.generate_case_with_profile(...)`** → the same, plus the
  profile, so pack generation does not have to regenerate it.
- **`generate_case_pack(count, ...)`** → a ZIP of N cases plus
  `PACK_MANIFEST.json` and a pack-level README.
- **`cli.py packet`** subcommand.

Everything remains deterministic: same seed plus same generator version
reproduces the same case exactly. Verified, not asserted — see below.

---

## Case folder structure

```
case-000042/
├── documents/
│   ├── w2_2024.pdf
│   ├── bank_oct_2024.pdf
│   ├── bank_nov_2024.pdf
│   ├── loan_app_1003.pdf
│   ├── paystub_period22.pdf
│   └── paystub_period21.pdf
├── truth/
│   ├── borrower.json
│   ├── employment.json
│   ├── income.json
│   ├── liabilities.json
│   └── case_manifest.json
├── evaluation/
│   ├── expected_extractions.json
│   ├── alignment_matrix.json
│   └── expected_decision.json
└── README.md
```

Case IDs are `case-{seed:06d}`.

---

## Truth layer — world truth

| File | Contents |
|------|----------|
| `borrower.json` | Name, SSN, DOB, phone, email, structured address |
| `employment.json` | Employer, EIN, title, type, tenure, payroll descriptor |
| `income.json` | Annual/monthly gross, **every W-2 box**, withholding rates, FICA constants, and an explicit `reconciliation` block |
| `liabilities.json` | Five monthly obligations, total, DTI, and the three asset balances |
| `case_manifest.json` | Master record: IDs, version, seed, borrower, employment, financials, ground truth, document index, data sources, legal terms |

---

## Evaluation layer — document truth

| File | Contents |
|------|----------|
| `expected_extractions.json` | Per document, every field an extractor should return, **as printed** |
| `alignment_matrix.json` | 9 cross-document field checks with per-document values and comparison mode |
| `expected_decision.json` | Expected outcome, decision factors, three rules with thresholds and pass/fail |

### The two layers are genuinely different, and that is the point

Product spec §9 calls for **world truth** and **document truth** as separate
layers. This sprint is where that distinction stopped being theoretical.
`truth/` holds exact underlying values; `expected_extractions.json` holds what
is actually on the page. They differ in three ways, and stating world truth in
the evaluation layer makes the expectation unreachable:

| Document | Formatting reality |
|----------|-------------------|
| Form 1003 | Money prints to **whole dollars** (`${v:,.0f}`) — 8,654.60 appears as `$8,655` |
| Bank statement | Payroll deposit carries **±3% jitter** — exact monthly gross never appears |
| Pay stub | Employer prints **upper-cased**; SSN masked to `***-**-1234`; the 401(k) row is **omitted entirely** at a 0% deferral |

`expected_extractions.json` carries a `_formatting` block naming the rule per
document, plus `*_as_printed` variants for ratios and
`employer_name_normalized` for entity resolution.

---

## Verification

### Truth layer agrees with the documents

The layer a customer buys is the one that has to be right. A truth file that
disagrees with the PDF beside it is worse than a missing one: a model scored
against it is marked wrong for being right.

`test_expected_extractions_appear_on_documents` asserts every numeric and name
value in `expected_extractions.json` is literally present in the text extracted
from its own PDF. **73 values per case, 8 seeds.**

That test was written before the implementation was finished and caught **46
failures** on the first run — every one of them a real defect in the truth
layer, not a test artifact. All three formatting realities above were found
this way rather than reasoned about.

### Determinism

Two runs at seed 42 produce identical document *text*, identical truth JSON,
identical evaluation JSON and an identical README. `generated_at` is excluded —
it is a wall-clock stamp by design. Document text is compared rather than PDF
bytes because reportlab stamps a creation timestamp into every file, so byte
equality was never the right claim to make.

### Test suite

**419 passing**, up from 400. Runs clean on both interpreters in use here
(Python 3.13 / reportlab 5.0.0 and the PacketWise venv / reportlab 4.2.5).

| New test | Gates |
|----------|-------|
| `test_packet_generates_all_files` | all 15 files present and non-empty |
| `test_manifest_name_matches_documents` | manifest name is the name on the PDFs |
| `test_manifest_decision_correct` | all three scenarios record the right decision |
| `test_expected_extractions_appear_on_documents` (×8 seeds) | truth ↔ document agreement |
| `test_paystub_ytd_ties_to_w2_in_truth_layer` (×8 seeds) | the truth layer's own numbers reconcile |

---

## Pack generation results

`generate_case_pack(count=9, pack_name="test_pack")`:

```
Distribution: {'approved': 3, 'flagged': 3, 'rejected': 3}
ZIP: output/test_pack_9cases.zip
```

| | Count |
|--|-------|
| Files in ZIP | 137 |
| PDFs | 54 (9 × 6) |
| JSON | 73 (9 × 8 + PACK_MANIFEST) |
| READMEs | 10 (9 cases + pack) |
| ZIP size | 206.8 KB (0.20 MB) |
| `testzip()` integrity | OK |

Roughly **23 KB per case**, so the 100-case Starter Pack in the product spec is
about 2.3 MB and a 2,500-case Team Pack about 57 MB — comfortably deliverable
as a single download.

Scenario distribution defaults to an even three-way split with the remainder to
the front, and can be set explicitly:

```
python -m realitydb_docs.cli packet --count 9 --output output/ \
  --seed-start 100 --pack-name cli_test \
  --distribution approved:3,flagged:3,rejected:3
```

Validated: a distribution that does not sum to `--count`, or that names an
unknown scenario, is rejected with a message rather than producing a
half-correct pack.

---

## Phase 1 capability statement

**realitydb-docs can now generate complete synthetic underwriting cases ready
for commercial delivery.**

A 100-case Starter Pack is one command and produces 600 PDFs, 500 ground-truth
files, 300 evaluation files, 100 case READMEs, a pack manifest and a pack
README, as a single ~2.3 MB ZIP — every case internally consistent, every
expected value verified present on its document, and every case reproducible
from its seed.

What this is **not** yet: every case is alignment class **A0 — perfectly
aligned**. That is the right first product (OCR baselines, field-extraction
accuracy, happy-path workflow testing) but it is one of six classes in the
product spec, and the controlled-misalignment classes are where the
differentiation actually lives. Nothing here can yet test whether a system
*detects* an inconsistency.

---

## Issues found

1. **Three of the plan's ground-truth values were wrong**, all in the
   evaluation layer. `ss_wages_box_3` and `medicare_wages_box_5` were specified
   as box-1-based, but Sprint 6 moved FICA onto gross, so they would have
   contradicted the rendered W-2. The pay stub `net_pay` formula applied federal
   and state rates to gross where the renderer applies them to box 1 — wrong
   for any non-zero deferral. And the `annual_income` alignment check asserted
   three documents agree within 5% on annual gross, which is false by the
   deferral rate for anyone deferring more than about 5%.
   Fixed by reading every value from the profile or from the renderer that
   produces the document, never from a formula restated alongside it.
2. **`datetime.utcnow()` is deprecated** from Python 3.12 and returns a naive
   datetime. Replaced with a timezone-aware helper.
3. **`open(path, "w")` without an encoding** defaults to the locale encoding —
   cp1252 on this host, which cannot represent `≤`. It survived only because
   `json.dump` escapes non-ASCII by default. All writes are now explicitly
   UTF-8, and JSON is written with `ensure_ascii=False` now that the encoding
   is pinned.
4. **The staging directory was created with `exist_ok=True` and later
   `rmtree`d.** Pre-existing content would have been packed into a customer
   deliverable and then deleted. Now refused with a message; verified against a
   directory holding a file, which survived.
5. **`total_checks` was hardcoded to 7** beside a 7-item list. Counted now; the
   list has since grown to 9.
6. **The `alignment` parameter was accepted and ignored** — the manifest
   hardcoded `A0`. It is now threaded through, and any value other than `A0`
   raises rather than silently producing a mislabelled case.
7. **`generate_case_pack` regenerated every profile a second time** purely to
   build its summary rows — two code paths that would have to agree forever.
   Removed via `generate_case_with_profile`.

---

## Known remaining issues

1. **A0 only.** `alignment` rejects anything else. Classes A1–A5 are the
   product's actual differentiator and the whole evaluation layer is shaped to
   carry them (`fraud_flags`, `misaligned_checks`, `aligned` per check are all
   present and all trivially empty).
2. **No negative tests anywhere in the repo.** Every one of the 419 checks
   confirms consistency; none confirms an inconsistency is *detectable*. Same
   gap flagged in Sprint 6; A1–A5 is what closes it.
3. **The case is a mortgage case, but the product spec's Phase 1 offer is an
   auto-loan pack.** Six documents are present; the spec's auto-loan case also
   lists a vehicle buyer's order, proof of insurance, an identity document and
   a credit-report summary. `documents_per_case` is hardcoded to 6 in the pack
   manifest.
4. **`_payroll_deposit` reaches into `renderer._build_transactions()`**, a
   private method. It is the only way to learn the jittered deposit without
   re-deriving it; a public accessor on the renderer would be cleaner.
5. **Thresholds are duplicated.** `DTI_QM_THRESHOLD` and friends restate
   PacketWise's `config/rules.yaml` so a shipped pack is self-describing. Two
   copies that must agree.
6. **`data_sources` is a static list** naming IRS SOI 2022, HMDA 2023, CFPB and
   Census ACS. Nothing in the generator actually derives distributions from
   those sources yet, so the claim is aspirational and should either be made
   true or removed before the pack is sold.

---

## Next

1. **Alignment classes A1–A5.** Everything else is secondary; this is the
   product boundary the spec identifies.
2. **Remove or substantiate `data_sources`.** It is a factual claim in a
   customer-facing manifest.
3. **Auto-loan document set** to match the Phase 1 offer in the spec.
