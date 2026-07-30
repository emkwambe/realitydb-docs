# Sprint 8 — Config infrastructure

**Date:** 2026-07-30
**Repo:** realitydb-docs
**Type:** refactor, no behaviour change
**Follows:** [Sprint 7C — case bundler](SPRINT-007C-case-bundler.md)

---

## The problem

Financial constants were scattered. `160200` appeared in `profile.py` and was
re-imported by three modules. `TOTAL_PERIODS = 26` sat in `paystub.py`. The
scenario table lived in `packet.py`. DTI thresholds were duplicated between
`packet.py` and PacketWise's `config/rules.yaml`.

Two concrete costs:

- The IRS raises the Social Security wage base every year. Updating it meant
  touching source, and missing a site meant a W-2 and a pay stub that disagreed.
- A bank wanting its own DTI thresholds or its own borrower tiers had to edit
  Python. Nothing could be shipped as configuration.

---

## What was built

### `config/` — four YAML files

| File | Holds | Bytes |
|------|-------|-------|
| `financial.yaml` | Tax year, FICA rates and wage base, withholding ranges, 401(k) options and cap, pay-period counts, DTI/LTV/credit thresholds, reserved SSN range | 2,776 |
| `distributions.yaml` | Income fallback range, asset multiples, liability ranges and split, loan/employment/borrower ranges, transaction counts, payroll and income variation | 1,881 |
| `scenarios.yaml` | 3 active scenarios, 3 commented future ones, 6 alignment class definitions (A0–A5) | 3,891 |
| `documents.yaml` | Watermark, colours, fonts, margins, footer, legal terms | 2,533 |

### `realitydb_docs/config.py` — the loader

456 lines. Lazy per-file loading with a cache, ~60 typed accessor properties,
`get_scenario()`, `scenario_params()`, `list_scenarios()`, `get_alignment()`,
`list_alignments()`, `describe()`, `reload()`. Singleton: `from
realitydb_docs.config import cfg`.

---

## What moved to config

| Constant | Was | Now |
|----------|-----|-----|
| SS wage base / rate, Medicare rate | `profile.py` literals | `financial.yaml` → `profile.SS_WAGE_BASE` etc., which `w2.py`, `paystub.py` and `packet.py` already import |
| `TOTAL_PERIODS = 26` | `paystub.py` | `financial.yaml: pay_periods.bi_weekly` |
| Withholding rate ranges | `profile.py` | `financial.yaml: withholding` |
| 401(k) options and 8% cap | `profile.py` | `financial.yaml: retirement` |
| SSN prefix and digit ranges | `profile.py` | `financial.yaml: ssn` |
| DTI / LTV / credit thresholds | `packet.py` | `financial.yaml: underwriting` |
| Housing band 0.24–0.32 | `profile.py` | `financial.yaml: underwriting` |
| Age, tenure, address tenure | `profile.py` | `distributions.yaml: borrower`, `employment` |
| Asset multiples, credit-card and other-debt ranges, car/student split | `profile.py` | `distributions.yaml: assets`, `liabilities` |
| Loan type/term tables and weights | `profile.py`, `loan_app.py` | `distributions.yaml: loan` |
| ±2% income variation | `profile.py` | `distributions.yaml: transactions` |
| ±3% payroll variation, 8–16 variable txns | `bank_statement.py` | `distributions.yaml: transactions` |
| $35k–$180k income fallback | `w2.py`, `bank_statement.py`, `loan_app.py`, `paystub.py` | `distributions.yaml: income` |
| Scenario table | `packet.py` | `scenarios.yaml` |
| Watermark text | four separate literals | `documents.yaml: watermark.text` |
| Palette, fonts, page margin | `paystub.py` | `documents.yaml` |
| Footer text | `paystub.py`, `loan_app.py` | `documents.yaml: footer.text` |

### Files refactored

`profile.py`, `paystub.py`, `w2.py`, `bank_statement.py`, `loan_app.py`,
`packet.py`, `cli.py`, plus `setup.py` and `requirements.txt`.

`w2.py` needed no change to its tax arithmetic — it already imported the three
FICA constants from `profile.py`, so sourcing them from YAML in that one place
propagated to every renderer for free. Only its watermark string and income
fallback moved.

---

## Verified: no behaviour change

The refactor's whole claim is that nothing moved. Checked against sixteen values
recorded earlier in the project, not re-derived:

```
name             Andrew Myers      w2 box 1     85924.88     SS_WAGE_BASE  160200
ssn              900-41-7435       401k rate    0.03         SS_RATE       0.062
employer         Graphic Design…   dti          0.3600       MEDICARE_RATE 0.0145
annual income    88582.36          ltv          0.7619       TOTAL_PERIODS 26
stub gross/per   3407.01           stub net     2217.63
stub ytd gross   74954.30          taxable ytd  72705.67
```

All sixteen identical. **419 tests pass** on both interpreters (Python 3.13 /
reportlab 5.0.0 / PyYAML 6.0.3, and the PacketWise venv / reportlab 4.2.5 /
PyYAML 6.0.2). All five CLI subcommands and the legacy flat-flag form
re-checked.

One near-miss worth recording: `housing_ratio_target: 0.28` minus
`housing_ratio_spread: 0.04` evaluates to `0.24000000000000002`, which would
have shifted every generated housing payment in its last bits. The band is
stated as explicit `housing_ratio_min`/`max` endpoints instead.

---

## Verified: config actually propagates

A refactor that centralises constants but does not thread them through is worse
than none — the YAML would read as authoritative while the code ignored it. So
propagation was tested rather than assumed. Four lines changed in
`financial.yaml` and one scenario uncommented:

| Observed | Before | After |
|----------|--------|-------|
| `cfg.tax_year` | 2024 | **2025** |
| `profile.SS_WAGE_BASE` | 160200 | **168600** |
| `truth/income.json → ss_wage_base` | 160200 | **168600** |
| `truth/case_manifest.json → tax_year` | 2024 | **2025** |
| `expected_decision.json → DTI_THRESHOLD_QM` | 0.43 | **0.40** |
| `expected_decision.json → LTV_RATIO` | 0.80 | **0.75** |
| `cfg.list_scenarios()` | 3 scenarios | **4, including `thin_file`** |

One edit reaches the module constants, the renderers, the truth layer and the
evaluation layer. `config/` was restored from a backup afterwards.

---

## How to update for the 2025 tax year

One line in `config/financial.yaml`:

```yaml
tax_year: 2025
fica:
  ss_wage_base: 168600     # 2025 IRS value
```

No code change. Restart the process — `SS_WAGE_BASE` and `TOTAL_PERIODS` are
read once at import, so `cfg.reload()` does not move them. An annual IRS update
is a deploy, not a hot reload.

## How to add a new scenario

Five lines in `config/scenarios.yaml`:

```yaml
  jumbo_prime:
    annual_income: 350000
    loan_amount: 900000
    property_value: 1200000
    dti_target: 0.31
```

Immediately visible in `cli scenarios`, usable via
`generate_case(scenario="jumbo_prime")` and `--distribution jumbo_prime:5`.
Three scenarios ship commented out (`thin_file`, `high_income`, `gig_worker`)
ready to uncomment.

## How an enterprise customer customises

Set `REALITYDB_CONFIG_DIR` to a directory holding only the files they want to
override. Anything absent falls back to the bundled defaults.

Verified with a directory containing **only** `scenarios.yaml` defining one
`acme_prime` tier: the custom scenario was the only one listed and generated at
its own DTI (30.0%) and LTV (66.7%), while `tax_year` and `ss_wage_base` fell
back to the bundled `financial.yaml`. `cfg.describe()` reports which file came
from where.

---

## CLI additions

```
$ python -m realitydb_docs.cli scenarios
Available scenarios:
  approved  — Prime borrower. DTI well within QM threshold. …
              income $102,000 | DTI target 36% | LTV 76.2%
  flagged   — Marginal borrower. DTI between QM and max thresholds …
              income $74,400 | DTI target 45% | LTV 82.6%
  rejected  — Rejected borrower. DTI exceeds maximum threshold of 50%. …
              income $57,600 | DTI target 55% | LTV 90.0%

$ python -m realitydb_docs.cli alignments
Alignment classes:
  A0  [AVAILABLE] Perfectly Aligned
  A1  [COMING]    Benign Variation
  …
Available now: A0
```

`--distribution` now validates against `cfg.list_scenarios()`, so a scenario
enabled in YAML is accepted without a code change.

---

## Deviations from the plan

1. **Part C was misattributed.** `profile.py` has no `SCENARIOS` dict (it was
   only ever in `packet.py`) and no `uniform(35000, 180000)` — that fallback
   lives in `bank_statement.py`, `paystub.py`, `loan_app.py` and `w2.py`. Done
   where the constants actually are.
2. **Part E needed no change**, as its own note anticipated: `w2.py` delegates
   FICA to `profile.py`.
3. **`bank_statement.py` and `loan_app.py` are not mentioned in the plan** but
   hold the ±3% payroll variation, the variable-transaction count, the income
   fallback and two watermark strings. Excluding them would have left
   `distributions.yaml`'s `payroll_variation` and `income` keys as config that
   nothing reads.
4. **Watermark text was inconsistent.** `w2`/`bank`/`loan` rendered
   `"SYNTHETIC - NOT VALID"` with a hyphen; `paystub` used an em dash. All four
   now read `documents.yaml`, so the rendered text changed on three documents.
   `test_watermark_present` asserts on the substring `SYNTHETIC` and is
   unaffected.
5. **`documents.yaml` is only partly consumed**, and says so in a header block
   naming which renderer reads which section. `w2`, `bank_statement` and
   `loan_app` keep their own palettes: each imitates a different real form and
   they do not share a scheme. Annotating that is the alternative to a config
   file that implies more coverage than it has.
6. **The YAML in the plan had an escape bug.** `footer.text` used a `>` block
   scalar containing `©`. YAML processes escapes in double-quoted scalars
   but **not** in block scalars, so the footer would have shipped the literal
   text `©`. Literal characters are used throughout instead.
7. **`_methodology()` is now scoped to the scenarios actually present.** It
   previously computed its stated ranges across every scenario in the table; had
   a future scenario been enabled, every manifest would have quoted a range
   wider than its own contents. Same honesty problem as the `data_sources` claim
   removed in the previous commit.
8. **Added `REALITYDB_CONFIG_DIR`.** Not in the plan, but `config/` sits beside
   the package rather than inside it, so `find_packages()` does not carry it
   into a wheel. The override path both fixes that and is the mechanism the
   plan's own "enterprise customization = ship scenarios.yaml" goal requires.
   Recorded as a `NOTE` in `setup.py`.
9. **PyYAML moved to runtime deps**, not dev: `requirements.txt` and
   `setup.py`'s `install_requires`. It was already installed in both
   interpreters.

---

## Known remaining issues

1. **Module-level snapshots ignore `reload()`.** `profile.SS_WAGE_BASE`,
   `paystub.TOTAL_PERIODS`, `packet.DTI_QM_THRESHOLD` and `paystub`'s colour and
   font constants are read once at import. Documented at each site; a caller
   expecting a live reload will not get one.
2. **`config/` is not packaged.** See deviation 8. A wheel install needs
   `REALITYDB_CONFIG_DIR`. The proper fix is a package-data layout, which
   collides with the `realitydb_docs/config.py` module name and would mean
   renaming one of them.
3. **The default pack distribution still covers three tiers only.**
   `DEFAULT_PACK_SCENARIOS` names them explicitly and the even split derives
   from its length, so it is no longer hardcoded to 3 — but a newly enabled
   scenario needs `--distribution` to appear in a pack.
4. **Nothing validates the YAML on load** beyond checking it parses to a
   mapping. A typo in a key surfaces as a `KeyError` deep inside a renderer
   rather than as a config error naming the file and key. A schema check is the
   obvious next hardening step.
5. **No test asserts config wiring.** The propagation and override checks above
   ran as scripts. If someone reverts a `cfg.` reference to a literal, all 419
   tests still pass — they assert internal consistency, which a hardcoded
   constant satisfies just as well. This is the same gap as PacketWise
   ISSUE-011 and it now applies here.
6. **`financial.yaml` declares four values nothing reads**:
   `additional_medicare_rate` / `_threshold` (no generated borrower earns above
   $200k), `retirement.annual_limit`, and the non-bi-weekly `pay_periods`. Each
   is annotated in place as declared-but-unapplied rather than left to imply it
   is in force.

---

## Next

1. **A1–A5 alignment classes.** `scenarios.yaml` now defines all six with
   `available` flags and `fraud_probability`, and `cli alignments` reports them;
   only A0 is implemented. This remains the product's differentiator.
2. **Schema validation on config load** (issue 4) — cheap, and it turns a
   confusing runtime failure into a clear one.
3. **A test that config is actually consulted** (issue 5).
