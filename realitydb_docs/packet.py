"""
RealityDB Financial Cases — Case Bundler
=========================================
Generates complete underwriting cases
with documents, ground truth, and
evaluation layers.

Each case contains:
  documents/ — all rendered PDFs
  truth/     — ground truth JSON files
  evaluation/ — expected extractions
               and alignment matrix
  README.md  — case summary

This is the Phase 1 commercial product:
  A complete synthetic underwriting case
  that can be used to test any document
  AI, OCR pipeline, or underwriting system.

A note on how the truth layer is built
--------------------------------------
Every expected value is read from the same
object or renderer that produced the
document, never recomputed from a formula
written alongside it. A truth file that
disagrees with the PDF beside it is worse
than a missing one: a model scored against
it is marked wrong for being right. Where a
figure needs a renderer's internal
arithmetic (pay stub net pay, for
instance), the renderer is instantiated and
its attributes are read.

Usage:
  from realitydb_docs.packet import (
      CaseBundler,
      generate_case_pack,
  )

  # Single case
  bundler = CaseBundler()
  case_path = bundler.generate_case(
      seed=42,
      scenario="approved",
      output_dir="output/cases",
  )

  # Full pack (20 cases, ZIP)
  zip_path = generate_case_pack(
      count=20,
      output_dir="output",
      pack_name="auto_loan_starter",
  )
"""

import json
import os
import shutil
import zipfile
from datetime import datetime, timezone
from typing import Optional, Tuple

from realitydb_docs.config import cfg
from realitydb_docs.profile import (
    BorrowerProfile,
    FinancialCaseGenerator,
    SS_WAGE_BASE,
    SS_RATE,
    MEDICARE_RATE,
)
from realitydb_docs.w2 import W2Renderer
from realitydb_docs.bank_statement import BankStatementRenderer
from realitydb_docs.loan_app import LoanAppRenderer
from realitydb_docs.paystub import PayStubRenderer, TOTAL_PERIODS

GENERATOR_VERSION = "0.5.0"

# Underwriting thresholds the expected decision is reasoned against, from
# config/financial.yaml. A case pack ships without PacketWise, so its
# evaluation layer restates them; sourcing both from YAML is what stops the two
# copies drifting.
DTI_QM_THRESHOLD = cfg.dti_threshold_qm
DTI_MAX_THRESHOLD = cfg.dti_threshold_max
LTV_MAX_THRESHOLD = cfg.ltv_threshold
MIN_CREDIT_SCORE = cfg.min_credit_score

# The two pay stub periods shipped with each case: the current period and the
# one before it, which is what a lender asks for to confirm income is not a
# one-off.
STUB_PERIODS = (22, 21)

# Scenario tiers the default pack distribution splits across. Named here
# because generate_case_pack's even split has to know which three; every other
# scenario in scenarios.yaml is reachable via --distribution or
# generate_case(scenario=...).
DEFAULT_PACK_SCENARIOS = ("approved", "flagged", "rejected")


def _get_scenarios() -> dict:
    """Scenario parameters from config/scenarios.yaml.

    A function rather than a module-level dict so that enabling a scenario in
    YAML takes effect without re-importing, and so a config override directory
    is honoured.
    """
    return {
        name: cfg.scenario_params(name) for name in cfg.list_scenarios()
    }


def _methodology(scenario_names=None) -> dict:
    """How the financial parameters are chosen.

    Replaces an earlier `data_sources` list that named IRS SOI, HMDA, CFPB and
    Census ACS. Nothing in the generator derives a distribution from any of
    them, so shipping that list in a customer-facing manifest asserted a
    provenance the code does not have.

    Ranges are computed rather than written out, so a change to a scenario
    cannot leave the stated methodology behind.

    `scenario_names` scopes the ranges to the scenarios actually present. A
    manifest that quoted the range across every scenario defined in YAML would
    misdescribe its own contents the moment an unused scenario was enabled.
    """
    scenarios = _get_scenarios()
    if scenario_names:
        scenarios = {
            k: v for k, v in scenarios.items() if k in set(scenario_names)
        }
    if not scenarios:
        scenarios = _get_scenarios()

    incomes = [s["annual_income"] for s in scenarios.values()]
    dtis = [s["dti_target"] for s in scenarios.values()]
    ltvs = [
        s["loan_amount"] / s["property_value"] for s in scenarios.values()
    ]
    return {
        "scenarios_described": sorted(scenarios),
        "note": (
            "Financial parameters are synthetic and chosen to produce "
            "specific, reproducible underwriting outcomes. They are not "
            "sampled from, or calibrated against, any published dataset. "
            "See docs/research/DATA-SOURCES.md for what did and did not "
            "inform the parameter ranges."
        ),
        "income_range": (
            f"${min(incomes):,} - ${max(incomes):,} "
            f"(+/-{cfg.income_variation:.0%} per-case variation)"
        ),
        "dti_range": f"{min(dtis):.0%} - {max(dtis):.0%}",
        "ltv_range": f"{min(ltvs):.1%} - {max(ltvs):.1%}",
        "credit_score": (
            "Not modelled. BorrowerProfile carries an optional credit_score "
            "for callers that supply one; case packs do not, so no case in "
            "this pack states a credit score."
        ),
        "distribution": (
            f"Scenario tiers sized by DTI against the thresholds in "
            f"expected_decision.json: approved (DTI <="
            f"{DTI_QM_THRESHOLD:.0%}), flagged (DTI "
            f"{DTI_QM_THRESHOLD:.0%}-{DTI_MAX_THRESHOLD:.0%}), rejected "
            f"(DTI >{DTI_MAX_THRESHOLD:.0%}). Realised DTI equals the "
            f"scenario's target exactly. LTV is fixed per tier and is a "
            f"secondary factor: the flagged and rejected tiers also exceed "
            f"the {LTV_MAX_THRESHOLD:.0%} LTV limit."
        ),
        "reproducibility": (
            "Same seed and same generator_version reproduce the same case."
        ),
    }


def _as_printed_dollars(value: float) -> float:
    """The whole-dollar figure the 1003 actually prints.

    loan_app._money() formats with "${v:,.0f}", so a value of 8654.60 appears
    on the page as $8,655. Stating 8654.60 as an expected extraction would ask
    for a figure the document does not contain. Formatted through the same
    rule rather than round() so the two cannot disagree on a half-cent.
    """
    return float(f"{value:,.0f}".replace(",", ""))


def _payroll_deposit(renderer: BankStatementRenderer) -> Optional[float]:
    """The payroll credit as it appears on a rendered statement.

    The deposit carries +/-3% jitter around monthly gross, so the exact
    monthly figure is not on the page and has to be read back.
    """
    description = renderer.profile.employer_payroll_description
    for tx in renderer._build_transactions():
        if tx["description"] == description and tx.get("credit"):
            return round(tx["credit"], 2)
    return None


def _utcnow() -> str:
    """Timezone-aware UTC timestamp.

    datetime.utcnow() is deprecated from Python 3.12 and returns a naive
    datetime, which is what made it worth deprecating.
    """
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class CaseBundler:
    """
    Generates complete underwriting cases.

    Each case has a unique seed that
    deterministically produces the same
    documents, truth, and evaluation layers.
    Same seed + same version = same case.
    """

    def __init__(self):
        self.generator = FinancialCaseGenerator()

    def generate_case(
        self,
        seed: int,
        scenario: str = "approved",
        annual_income: float = None,
        loan_amount: float = None,
        property_value: float = None,
        dti_target: float = None,
        output_dir: str = "output/cases",
        alignment: str = "A0",
    ) -> str:
        """
        Generate a complete underwriting case.

        Args:
            seed: Deterministic seed.
                  Same seed always produces same case.
            scenario: approved / flagged / rejected
            annual_income: Override default for scenario
            loan_amount: Override default for scenario
            property_value: Override default for scenario
            dti_target: Override default for scenario
            output_dir: Parent directory for case folder
            alignment: A0 (clean) only in this version.
                       A3/A4 fraud injection in Sprint 8.

        Returns:
            Path to generated case folder.
        """
        case_dir, _ = self.generate_case_with_profile(
            seed=seed,
            scenario=scenario,
            annual_income=annual_income,
            loan_amount=loan_amount,
            property_value=property_value,
            dti_target=dti_target,
            output_dir=output_dir,
            alignment=alignment,
        )
        return case_dir

    def generate_case_with_profile(
        self,
        seed: int,
        scenario: str = "approved",
        annual_income: float = None,
        loan_amount: float = None,
        property_value: float = None,
        dti_target: float = None,
        output_dir: str = "output/cases",
        alignment: str = "A0",
    ) -> Tuple[str, BorrowerProfile]:
        """As generate_case, but also returns the profile.

        Pack generation needs the profile for its summary rows. Returning it
        here avoids generating the same profile twice, which would be two
        code paths that have to agree forever.
        """
        if alignment != "A0":
            raise ValueError(
                f"alignment {alignment!r} is not supported yet; only A0 "
                f"(perfectly aligned) exists in this version. Controlled "
                f"misalignment (A1-A5) is Sprint 8."
            )
        all_scenarios = _get_scenarios()
        if scenario not in all_scenarios:
            raise ValueError(
                f"unknown scenario {scenario!r}; "
                f"choose from {sorted(all_scenarios)}"
            )

        # Get scenario defaults
        defaults = all_scenarios[scenario]
        income = annual_income or defaults["annual_income"]
        loan = loan_amount or defaults["loan_amount"]
        prop = property_value or defaults["property_value"]
        dti = dti_target or defaults["dti_target"]

        # Generate profile
        profile = self.generator.generate(
            seed=seed,
            annual_income=income,
            loan_amount=loan,
            property_value=prop,
            dti_target=dti,
            scenario=scenario,
        )

        # Create case folder
        case_id = f"case-{seed:06d}"
        case_dir = os.path.join(output_dir, case_id)
        docs_dir = os.path.join(case_dir, "documents")
        truth_dir = os.path.join(case_dir, "truth")
        eval_dir = os.path.join(case_dir, "evaluation")

        os.makedirs(docs_dir, exist_ok=True)
        os.makedirs(truth_dir, exist_ok=True)
        os.makedirs(eval_dir, exist_ok=True)

        # Generate documents
        doc_paths = self._render_documents(profile, docs_dir)

        # Write truth layer
        self._write_truth(profile, truth_dir, doc_paths, alignment)

        # Write evaluation layer
        self._write_evaluation(
            profile, eval_dir, doc_paths, alignment
        )

        # Write README
        self._write_readme(
            profile, case_dir, case_id,
            scenario, alignment, doc_paths
        )

        return case_dir, profile

    def _render_documents(
        self,
        profile: BorrowerProfile,
        docs_dir: str,
    ) -> dict:
        """Render all documents. Returns path dict."""
        paths = {}

        paths["w2_2024"] = W2Renderer(
            profile, year_offset=0
        ).render(
            os.path.join(docs_dir, "w2_2024.pdf")
        )

        paths["bank_oct_2024"] = BankStatementRenderer(
            profile, month=10, style="corporate"
        ).render(
            os.path.join(docs_dir, "bank_oct_2024.pdf")
        )

        paths["bank_nov_2024"] = BankStatementRenderer(
            profile, month=11, style="corporate"
        ).render(
            os.path.join(docs_dir, "bank_nov_2024.pdf")
        )

        paths["loan_app_1003"] = LoanAppRenderer(
            profile
        ).render(
            os.path.join(docs_dir, "loan_app_1003.pdf")
        )

        for period in STUB_PERIODS:
            key = f"paystub_period{period}"
            paths[key] = PayStubRenderer(
                profile, pay_period=period
            ).render(
                os.path.join(docs_dir, f"{key}.pdf")
            )

        return paths

    def _write_truth(
        self,
        profile: BorrowerProfile,
        truth_dir: str,
        doc_paths: dict,
        alignment: str,
    ) -> None:
        """Write ground truth JSON files."""

        # borrower.json — identity
        borrower = {
            "full_name": profile.full_name,
            "first_name": profile.first_name,
            "last_name": profile.last_name,
            "ssn": profile.ssn,
            "ssn_last4": profile.ssn.split("-")[-1],
            "dob": profile.dob.isoformat(),
            "phone": profile.phone,
            "email": profile.email,
            "address": {
                "street": profile.street_address,
                "city": profile.city,
                "state": profile.state,
                "zip": profile.zip_code,
                "full": profile.full_address,
            },
            "years_at_address": profile.years_at_address,
        }
        self._write_json(
            os.path.join(truth_dir, "borrower.json"), borrower
        )

        # employment.json
        employment = {
            "employer_name": profile.employer_name,
            "employer_ein": profile.employer_ein,
            "job_title": profile.job_title,
            "employment_type": profile.employment_type,
            "years_at_job": profile.years_at_job,
            "employment_start_date": (
                profile.employment_start_date.isoformat()
            ),
            "payroll_deposit_description": (
                profile.employer_payroll_description
            ),
        }
        self._write_json(
            os.path.join(truth_dir, "employment.json"), employment
        )

        # income.json
        # Every W-2 box is read off the profile rather than restated as a
        # formula here. FICA (boxes 3-6) is computed on GROSS, not on box 1: a
        # pre-tax 401k deferral is exempt from income tax but not from Social
        # Security or Medicare, so boxes 3 and 5 exceed box 1 by the deferral.
        income = {
            "annual_gross_income": round(profile.annual_gross_income, 2),
            "monthly_gross_income": round(profile.monthly_gross_income, 2),
            "w2_box1_wages": round(profile.w2_box1_wages, 2),
            "w2_box2_federal_withheld": round(
                profile.w2_box2_federal_withheld, 2
            ),
            "w2_box3_ss_wages": round(profile.w2_box3_ss_wages, 2),
            "w2_box4_ss_withheld": round(profile.w2_box4_ss_withheld, 2),
            "w2_box5_medicare_wages": round(
                profile.w2_box5_medicare_wages, 2
            ),
            "w2_box6_medicare_withheld": round(
                profile.w2_box6_medicare_withheld, 2
            ),
            "w2_box17_state_withheld": round(
                profile.w2_box17_state_withheld, 2
            ),
            "federal_withholding_rate": round(
                profile.federal_withholding_rate, 4
            ),
            "state_withholding_rate": round(
                profile.state_withholding_rate, 4
            ),
            "retirement_contrib_rate": round(
                profile.retirement_contrib_rate, 4
            ),
            "ss_wage_base": SS_WAGE_BASE,
            "ss_rate": SS_RATE,
            "medicare_rate": MEDICARE_RATE,
            "pay_periods_per_year": TOTAL_PERIODS,
            "gross_per_period": round(
                profile.annual_gross_income / TOTAL_PERIODS, 2
            ),
            "reconciliation": {
                "w2_box1": "annual_gross_income x (1 - retirement_contrib_rate)",
                "w2_box3": "min(annual_gross_income, ss_wage_base)",
                "w2_box5": "annual_gross_income",
                "paystub_taxable_ytd_at_period_26": "equals w2_box1_wages",
            },
        }
        self._write_json(
            os.path.join(truth_dir, "income.json"), income
        )

        # liabilities.json
        liabilities = {
            "monthly_rent_mortgage": round(
                profile.monthly_rent_mortgage, 2
            ),
            "monthly_car_payment": round(profile.monthly_car_payment, 2),
            "monthly_student_loan": round(profile.monthly_student_loan, 2),
            "monthly_credit_card_min": round(
                profile.monthly_credit_card_min, 2
            ),
            "monthly_other_debt": round(profile.monthly_other_debt, 2),
            "total_monthly_debt": round(profile.total_monthly_debt, 2),
            "dti_ratio": round(profile.dti_ratio, 4),
            "assets": {
                "checking_balance": round(profile.checking_balance, 2),
                "savings_balance": round(profile.savings_balance, 2),
                "retirement_balance": round(profile.retirement_balance, 2),
            },
        }
        self._write_json(
            os.path.join(truth_dir, "liabilities.json"), liabilities
        )

        # case_manifest.json — master truth file
        manifest = {
            "case_id": f"case-{profile.seed:06d}",
            "generated_at": _utcnow(),
            "generator_version": GENERATOR_VERSION,
            "seed": profile.seed,
            "tax_year": profile.tax_year,
            "alignment": alignment,
            "scenario": profile.expected_decision,
            "borrower": {
                "full_name": profile.full_name,
                "ssn_last4": profile.ssn.split("-")[-1],
                "address": profile.full_address,
            },
            "employment": {
                "employer": profile.employer_name,
                "title": profile.job_title,
                "type": profile.employment_type,
                "years": profile.years_at_job,
            },
            "financials": {
                "annual_gross_income": round(
                    profile.annual_gross_income, 2
                ),
                "monthly_gross_income": round(
                    profile.monthly_gross_income, 2
                ),
                "total_monthly_debt": round(
                    profile.total_monthly_debt, 2
                ),
                "dti_ratio": round(profile.dti_ratio, 4),
                "loan_amount": profile.loan_amount,
                "property_value": profile.property_value,
                "ltv_ratio": round(profile.ltv_ratio, 4),
                "checking_balance": round(profile.checking_balance, 2),
            },
            "ground_truth": {
                "expected_decision": profile.expected_decision,
                "fraud_flags": [],
                "alignment_class": alignment,
                "notes": (
                    "Perfectly aligned case. "
                    "All documents describe the same "
                    "borrower with consistent financials."
                ),
            },
            "documents": {
                k: f"documents/{os.path.basename(v)}"
                for k, v in doc_paths.items()
            },
            "methodology": _methodology([profile.expected_decision]),
            "legal": {
                "synthetic": True,
                "watermark": "SYNTHETIC — NOT VALID",
                "ssn_range": "900-xx-xxxx (never issued by the SSA)",
                "prohibited_uses": [
                    "Submitting to real lenders",
                    "Identity fraud",
                    "Discriminatory AI training",
                ],
            },
        }
        self._write_json(
            os.path.join(truth_dir, "case_manifest.json"), manifest
        )

    def _write_evaluation(
        self,
        profile: BorrowerProfile,
        eval_dir: str,
        doc_paths: dict,
        alignment: str,
    ) -> None:
        """Write evaluation layer JSON files."""

        # The pay stub's arithmetic (which base each withholding is taken on,
        # how net pay falls out) lives in PayStubRenderer. Instantiating it is
        # the only way to state expected values that match the rendered
        # document; restating the formula here would drift the moment either
        # side changed, and it would already be wrong today — income tax is
        # withheld on box 1 wages, not on gross.
        stubs = {
            period: PayStubRenderer(profile, pay_period=period)
            for period in STUB_PERIODS
        }

        # expected_extractions.json
        #
        # This file is DOCUMENT truth, not world truth: it states what is
        # actually printed on each page, which is what an extractor can
        # possibly return. truth/ holds the exact underlying values.
        #
        # The two differ in three ways here, and stating world truth would
        # make these expectations unreachable:
        #   - the 1003 prints money to whole dollars, so 8,654.60 appears as
        #     $8,655
        #   - a bank payroll deposit carries +/-3% jitter, so exact monthly
        #     gross never appears
        #   - the pay stub banner prints the employer upper-cased
        extractions = {
            "_document_truth_note": (
                "Values are as PRINTED on each document. Where a document "
                "rounds or reformats, the printed form is given here and the "
                "exact value is in truth/. See _formatting for per-document "
                "rules."
            ),
            "_formatting": {
                "w2_2024": "money to 2dp",
                "bank_oct_2024": "money to 2dp; payroll deposit jitters "
                                 "+/-3% around monthly gross",
                "bank_nov_2024": "money to 2dp; payroll deposit jitters "
                                 "+/-3% around monthly gross",
                "loan_app_1003": "money to WHOLE DOLLARS; ratios as "
                                 "percentages to 1dp",
                "paystub_period22": "money to 2dp; employer upper-cased",
                "paystub_period21": "money to 2dp; employer upper-cased",
            },
            "w2_2024": {
                "document_type": "w2",
                "employee_name": profile.full_name,
                "employee_ssn": profile.ssn,
                "employer_name": profile.employer_name,
                "employer_ein": profile.employer_ein,
                "tax_year": profile.tax_year,
                "wages_box_1": round(profile.w2_box1_wages, 2),
                "federal_withheld_box_2": round(
                    profile.w2_box2_federal_withheld, 2
                ),
                "ss_wages_box_3": round(profile.w2_box3_ss_wages, 2),
                "ss_withheld_box_4": round(
                    profile.w2_box4_ss_withheld, 2
                ),
                "medicare_wages_box_5": round(
                    profile.w2_box5_medicare_wages, 2
                ),
                "medicare_withheld_box_6": round(
                    profile.w2_box6_medicare_withheld, 2
                ),
                "state_wages_box_16": round(profile.w2_box1_wages, 2),
                "state_withheld_box_17": round(
                    profile.w2_box17_state_withheld, 2
                ),
            },
            # Every money field below is the WHOLE-DOLLAR figure the 1003
            # prints, produced with the renderer's own format string so the
            # two cannot drift.
            "loan_app_1003": {
                "document_type": "loan_application",
                "borrower_name": profile.full_name,
                "ssn": profile.ssn,
                "ssn_last4": profile.ssn.split("-")[-1],
                "employer_name": profile.employer_name,
                "job_title": profile.job_title,
                "employment_type": profile.employment_type,
                "gross_monthly_income": _as_printed_dollars(
                    profile.monthly_gross_income
                ),
                "loan_amount": _as_printed_dollars(profile.loan_amount),
                "property_value": _as_printed_dollars(
                    profile.property_value
                ),
                "ltv_ratio": round(profile.ltv_ratio, 4),
                "ltv_ratio_as_printed": f"{profile.ltv_ratio * 100:.1f}%",
                "down_payment": _as_printed_dollars(profile.down_payment),
                "monthly_housing_payment": _as_printed_dollars(
                    profile.monthly_rent_mortgage
                ),
                "car_payment": _as_printed_dollars(
                    profile.monthly_car_payment
                ),
                "student_loan": _as_printed_dollars(
                    profile.monthly_student_loan
                ),
                "credit_card_minimum": _as_printed_dollars(
                    profile.monthly_credit_card_min
                ),
                "total_monthly_debt": _as_printed_dollars(
                    profile.total_monthly_debt
                ),
                "dti_ratio": round(profile.dti_ratio, 4),
                "dti_ratio_as_printed": f"{profile.dti_ratio * 100:.1f}%",
                "checking_balance": _as_printed_dollars(
                    profile.checking_balance
                ),
                "savings_balance": _as_printed_dollars(
                    profile.savings_balance
                ),
                "retirement_balance": _as_printed_dollars(
                    profile.retirement_balance
                ),
            },
        }

        # Both statements carry the same holder, payroll description and
        # recurring debts; only the month and the payroll amount differ. The
        # ending balance is the declared checking balance by construction.
        #
        # The deposit is read back off the renderer rather than stated as
        # monthly gross: the payroll credit carries +/-3% jitter, so the exact
        # monthly gross figure never appears on the page.
        for key, month, month_name in (
            ("bank_oct_2024", profile.statement_month_1, "October 2024"),
            ("bank_nov_2024", profile.statement_month_2, "November 2024"),
        ):
            renderer = BankStatementRenderer(
                profile, month=month, style="corporate"
            )
            deposit = _payroll_deposit(renderer)
            extractions[key] = {
                "document_type": "bank_statement",
                "account_holder": profile.full_name,
                "statement_month": month_name,
                "payroll_description": (
                    profile.employer_payroll_description
                ),
                "payroll_deposit": deposit,
                "monthly_gross_income_reference": round(
                    profile.monthly_gross_income, 2
                ),
                "payroll_deposit_tolerance_pct": 3.0,
                "ending_balance": round(profile.checking_balance, 2),
                "recurring_debts": {
                    "rent_mortgage": round(
                        profile.monthly_rent_mortgage, 2
                    ),
                    "car_payment": round(profile.monthly_car_payment, 2),
                    "student_loan": round(
                        profile.monthly_student_loan, 2
                    ),
                    "credit_card_min": round(
                        profile.monthly_credit_card_min, 2
                    ),
                },
            }

        for period, stub in stubs.items():
            fields = {
                "document_type": "pay_stub",
                "employee_name": profile.full_name,
                # The banner prints the employer upper-cased, so that is what
                # an extractor returns. The canonical form is given alongside
                # for entity resolution.
                "employer_name": profile.employer_name.upper(),
                "employer_name_normalized": profile.employer_name,
                "ssn_as_printed": (
                    f"***-**-{profile.ssn.split('-')[-1]}"
                ),
                "ssn_last4": profile.ssn.split("-")[-1],
                "pay_period_number": period,
                "pay_periods_per_year": TOTAL_PERIODS,
                "pay_period_start": stub.period_start.isoformat(),
                "pay_period_end": stub.period_end.isoformat(),
                "pay_date": stub.pay_date.isoformat(),
                "pay_frequency": "Bi-Weekly",
                "gross_pay": round(stub.gross_per_period, 2),
                "federal_tax_withheld": round(stub.fed_tax, 2),
                "state_tax_withheld": round(stub.state_tax, 2),
                "ss_tax_withheld": round(stub.ss_tax, 2),
                "medicare_tax_withheld": round(stub.medicare_tax, 2),
                "total_deductions": round(stub.total_deductions, 2),
                "net_pay": round(stub.net_pay, 2),
                "ytd_gross": round(stub.gross_ytd, 2),
                "ytd_federal_tax": round(stub.fed_tax_ytd, 2),
                "ytd_state_tax": round(stub.state_tax_ytd, 2),
                "ytd_ss_tax": round(stub.ss_tax_ytd, 2),
                "ytd_medicare_tax": round(stub.medicare_ytd, 2),
                "ytd_net_pay": round(stub.net_ytd, 2),
                "ytd_taxable": round(stub.taxable_ytd, 2),
            }
            # The renderer omits the 401(k) row entirely when the borrower
            # defers nothing, so the expected extraction has to omit it too —
            # otherwise it asks for a line that is not on the page.
            if profile.retirement_contrib_rate > 0:
                fields["retirement_deduction"] = round(stub.retirement, 2)
                fields["ytd_retirement"] = round(stub.retirement_ytd, 2)
            extractions[f"paystub_period{period}"] = fields

        self._write_json(
            os.path.join(eval_dir, "expected_extractions.json"),
            extractions,
        )

        # alignment_matrix.json
        latest = stubs[max(stubs)]
        annualized_taxable = (
            latest.taxable_ytd / latest.pay_period * TOTAL_PERIODS
        )
        checks = [
            {
                "field": "borrower_name",
                "documents": [
                    "w2_2024", "bank_oct_2024", "bank_nov_2024",
                    "loan_app_1003", "paystub_period22",
                    "paystub_period21",
                ],
                "expected_value": profile.full_name,
                "aligned": True,
                "comparison": "exact",
                "note": "Same full name across all six documents",
            },
            {
                "field": "employer_name",
                "documents": [
                    "w2_2024", "loan_app_1003",
                    "paystub_period22", "paystub_period21",
                ],
                "expected_value": profile.employer_name,
                "aligned": True,
                "comparison": "case-insensitive",
                "per_document": {
                    "w2_2024": profile.employer_name,
                    "loan_app_1003": profile.employer_name,
                    "paystub_period22": profile.employer_name.upper(),
                    "paystub_period21": profile.employer_name.upper(),
                    "bank_oct_2024": (
                        profile.employer_payroll_description
                    ),
                },
                "note": (
                    "The pay stub banner prints the employer upper-cased "
                    "and the bank statement shows an abbreviated payroll "
                    "descriptor, so this field aligns case-insensitively "
                    "rather than exactly."
                ),
            },
            {
                # Stated per document rather than as one number with a
                # tolerance. W-2 box 1 is NOT annual gross — it is gross less
                # the pre-tax deferral — so asserting all three agree within
                # 5% would be false for any borrower deferring more than
                # about 5%.
                "field": "annual_income",
                "documents": [
                    "w2_2024", "loan_app_1003", "paystub_period22",
                ],
                "aligned": True,
                "comparison": "derived",
                "per_document": {
                    "w2_2024.wages_box_1": round(
                        profile.w2_box1_wages, 2
                    ),
                    "loan_app_1003.gross_monthly_income x 12": round(
                        profile.monthly_gross_income * 12, 2
                    ),
                    "paystub_period22.ytd_gross annualized": round(
                        latest.gross_ytd / latest.pay_period
                        * TOTAL_PERIODS, 2
                    ),
                    "paystub_period22.ytd_taxable annualized": round(
                        annualized_taxable, 2
                    ),
                },
                "reconciliation": (
                    "w2.wages_box_1 == annual_gross x "
                    "(1 - retirement_contrib_rate); "
                    "paystub ytd_taxable annualized == w2.wages_box_1 "
                    "exactly; paystub ytd_gross annualized == "
                    "annual_gross. Comparing YTD GROSS to box 1 differs by "
                    "the deferral rate and is the common mistake."
                ),
                "retirement_contrib_rate": round(
                    profile.retirement_contrib_rate, 4
                ),
                "note": (
                    "Three documents state income on three different bases. "
                    "They reconcile exactly; they are not equal."
                ),
            },
            {
                "field": "monthly_car_payment",
                "documents": ["bank_oct_2024", "bank_nov_2024",
                              "loan_app_1003"],
                "expected_value": round(profile.monthly_car_payment, 2),
                "aligned": True,
                "comparison": "exact",
                "note": (
                    "AUTO LOAN PMT on both statements equals the declared "
                    "car payment on the 1003, to the cent"
                ),
            },
            {
                "field": "student_loan_payment",
                "documents": ["bank_oct_2024", "bank_nov_2024",
                              "loan_app_1003"],
                "expected_value": round(profile.monthly_student_loan, 2),
                "aligned": True,
                "comparison": "exact",
                "note": (
                    "STUDENT LOAN PMT on both statements equals the "
                    "declared student loan on the 1003, to the cent"
                ),
            },
            {
                "field": "monthly_housing_payment",
                "documents": ["bank_oct_2024", "bank_nov_2024",
                              "loan_app_1003"],
                "expected_value": round(
                    profile.monthly_rent_mortgage, 2
                ),
                "aligned": True,
                "comparison": "exact",
                "note": (
                    "RENT PAYMENT on both statements equals the declared "
                    "housing payment on the 1003"
                ),
            },
            {
                "field": "checking_balance",
                "documents": ["bank_oct_2024", "loan_app_1003"],
                "expected_value": round(profile.checking_balance, 2),
                "aligned": True,
                "comparison": "exact",
                "note": (
                    "Statement ending balance equals the checking account "
                    "declared on the 1003; the beginning balance is derived "
                    "so the running total lands on it"
                ),
            },
            {
                "field": "ssn",
                "documents": ["w2_2024", "loan_app_1003",
                              "paystub_period22"],
                "expected_value": profile.ssn,
                "aligned": True,
                "comparison": "last4",
                "per_document": {
                    "w2_2024": profile.ssn,
                    "loan_app_1003": profile.ssn,
                    "paystub_period22": (
                        f"***-**-{profile.ssn.split('-')[-1]}"
                    ),
                },
                "note": (
                    "The pay stub masks all but the last four digits, so "
                    "this field aligns on the last four"
                ),
            },
            {
                "field": "address",
                "documents": ["w2_2024", "loan_app_1003"],
                "expected_value": profile.full_address,
                "aligned": True,
                "comparison": "exact",
                "note": (
                    "Borrower address on the W-2 (boxes e/f) and on the "
                    "1003. The pay stub does not carry an address."
                ),
            },
        ]

        aligned = sum(1 for c in checks if c["aligned"])
        matrix = {
            "alignment_class": alignment,
            "alignment_description": (
                "A0 — perfectly aligned. Every material value reconciles "
                "across every document that states it."
            ),
            "checks": checks,
            # Counted, not hardcoded: a hardcoded total silently goes stale
            # the first time a check is added.
            "total_checks": len(checks),
            "aligned_checks": aligned,
            "misaligned_checks": len(checks) - aligned,
            "fraud_flags": [],
        }
        self._write_json(
            os.path.join(eval_dir, "alignment_matrix.json"), matrix
        )

        # expected_decision.json
        decision_notes = {
            "approved": (
                "DTI within QM threshold (<=43%), "
                "LTV within limit (<=80%), "
                "income verified across documents."
            ),
            "flagged": (
                "DTI between QM and max thresholds "
                "(43%-50%). Requires manual review."
            ),
            "rejected": (
                "DTI exceeds maximum threshold (>50%) "
                "or credit score below minimum (620)."
            ),
        }
        decision = {
            "expected_decision": profile.expected_decision,
            "decision_factors": {
                "dti_ratio": round(profile.dti_ratio, 4),
                "ltv_ratio": round(profile.ltv_ratio, 4),
                "annual_income": round(profile.annual_gross_income, 2),
                "total_monthly_debt": round(
                    profile.total_monthly_debt, 2
                ),
                "loan_amount": profile.loan_amount,
                "credit_score": profile.credit_score,
            },
            "rules_evaluated": [
                {
                    "rule": "DTI_THRESHOLD_QM",
                    "threshold": DTI_QM_THRESHOLD,
                    "actual": round(profile.dti_ratio, 4),
                    "passed": profile.dti_ratio <= DTI_QM_THRESHOLD,
                    "severity_if_failed": "warning",
                },
                {
                    "rule": "DTI_THRESHOLD_MAX",
                    "threshold": DTI_MAX_THRESHOLD,
                    "actual": round(profile.dti_ratio, 4),
                    "passed": profile.dti_ratio <= DTI_MAX_THRESHOLD,
                    "severity_if_failed": "critical",
                },
                {
                    "rule": "LTV_RATIO",
                    "threshold": LTV_MAX_THRESHOLD,
                    "actual": round(profile.ltv_ratio, 4),
                    "passed": profile.ltv_ratio <= LTV_MAX_THRESHOLD,
                    "severity_if_failed": "warning",
                },
            ],
            "rationale": decision_notes.get(
                profile.expected_decision, ""
            ),
            "fraud_flags": [],
            "alignment_class": alignment,
            "note": (
                "The expected decision is the scenario the case was built "
                "for. Thresholds are restated in this file so the "
                "evaluation layer is self-describing without the "
                "underwriting engine that normally supplies them."
            ),
        }
        self._write_json(
            os.path.join(eval_dir, "expected_decision.json"), decision
        )

    def _write_readme(
        self,
        profile: BorrowerProfile,
        case_dir: str,
        case_id: str,
        scenario: str,
        alignment: str,
        doc_paths: dict,
    ) -> None:
        """Write human-readable case summary."""
        dti_pct = profile.dti_ratio * 100
        ltv_pct = profile.ltv_ratio * 100

        content = f"""# {case_id.upper()}

**RealityDB Financial Cases — Synthetic Underwriting Case**
Generated by Mpingo Systems LLC | v{GENERATOR_VERSION}

---

## Borrower Summary

| Field | Value |
|-------|-------|
| Name | {profile.full_name} |
| SSN | {profile.ssn[:7]}XXXX (last 4: {profile.ssn.split("-")[-1]}) |
| Address | {profile.full_address} |
| Employer | {profile.employer_name} |
| Job Title | {profile.job_title} |
| Employment Type | {profile.employment_type} |

---

## Financial Profile

| Metric | Value |
|--------|-------|
| Annual Gross Income | ${profile.annual_gross_income:,.2f} |
| Monthly Gross Income | ${profile.monthly_gross_income:,.2f} |
| W-2 Box 1 Wages | ${profile.w2_box1_wages:,.2f} |
| 401(k) Deferral Rate | {profile.retirement_contrib_rate:.0%} |
| Total Monthly Debt | ${profile.total_monthly_debt:,.2f} |
| DTI Ratio | {dti_pct:.1f}% |
| Loan Amount | ${profile.loan_amount:,.0f} |
| Property Value | ${profile.property_value:,.0f} |
| LTV Ratio | {ltv_pct:.1f}% |
| Checking Balance | ${profile.checking_balance:,.2f} |

Note: W-2 Box 1 is annual gross less the pre-tax 401(k) deferral. The three
income-bearing documents state income on different bases and reconcile
exactly — see `evaluation/alignment_matrix.json`.

---

## Case Classification

| Field | Value |
|-------|-------|
| Alignment Class | {alignment} — Perfectly Aligned |
| Expected Decision | **{scenario.upper()}** |
| Seed | {profile.seed} |
| Tax Year | {profile.tax_year} |

Same seed and same generator version always produce this exact case.

---

## Documents

| File | Description |
|------|-------------|
| documents/w2_2024.pdf | IRS W-2 Wage and Tax Statement {profile.tax_year} |
| documents/bank_oct_2024.pdf | Bank Statement October {profile.tax_year} |
| documents/bank_nov_2024.pdf | Bank Statement November {profile.tax_year} |
| documents/loan_app_1003.pdf | Fannie Mae 1003 Loan Application |
| documents/paystub_period22.pdf | Pay Stub Period 22 (most recent) |
| documents/paystub_period21.pdf | Pay Stub Period 21 (prior) |

---

## Ground Truth

| File | Contents |
|------|----------|
| truth/borrower.json | Identity and address |
| truth/employment.json | Employer and job details |
| truth/income.json | Income model, every W-2 box, withholding rates |
| truth/liabilities.json | Debts and assets |
| truth/case_manifest.json | Complete case metadata |

---

## Evaluation

| File | Contents |
|------|----------|
| evaluation/expected_extractions.json | What each document should extract |
| evaluation/alignment_matrix.json | Cross-document field alignment |
| evaluation/expected_decision.json | Expected underwriting outcome |

---

## Legal Notice

All documents are synthetic.
No real borrower data is included.
SSNs use the 900-xx-xxxx range, which the SSA has never issued.
All documents are watermarked SYNTHETIC — NOT VALID.

Permitted uses: testing, QA, AI training, research.
Prohibited uses: submitting to real lenders, fraud.

© 2026 Mpingo Systems LLC | eddy@mpingo.ai
https://realitydb.dev/financial-cases/
"""
        self._write_text(os.path.join(case_dir, "README.md"), content)

    @staticmethod
    def _write_json(path: str, data: dict) -> None:
        """Write JSON file with pretty formatting."""
        # encoding is explicit: open() defaults to the locale encoding, which
        # on Windows is cp1252 and cannot represent the em dash or "≤" that
        # appear in these files.
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str, ensure_ascii=False)
            f.write("\n")

    @staticmethod
    def _write_text(path: str, content: str) -> None:
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)


def _pack_readme(
    pack_name: str,
    count: int,
    distribution: dict,
    seed_start: int,
) -> str:
    """Top-level README for a case pack."""
    dist_rows = "\n".join(
        f"| {scenario} | {n} |" for scenario, n in distribution.items()
    )
    return f"""# RealityDB Financial Cases — {pack_name}

**{count} complete synthetic underwriting cases**
Mpingo Systems LLC | generator v{GENERATOR_VERSION}

---

## What is in this pack

{count} borrower cases. Each case is a self-contained folder holding six
rendered PDFs, five ground-truth JSON files, three evaluation JSON files and
a README.

| | Count |
|--|-------|
| Cases | {count} |
| Documents | {count * 6} |
| Ground-truth files | {count * 5} |
| Evaluation files | {count * 3} |

### Scenario distribution

| Scenario | Cases |
|----------|-------|
{dist_rows}

Seeds {seed_start}–{seed_start + count - 1}. Same seed and same generator
version always reproduce the same case exactly.

---

## Case structure

```
case-NNNNNN/
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

`PACK_MANIFEST.json` at the root indexes every case with its borrower,
income, DTI, LTV and expected decision.

---

## Alignment class A0

Every case in this pack is **A0 — perfectly aligned**: every material value
reconciles across every document that states it. Use it for OCR baselines,
field-extraction accuracy and happy-path workflow testing.

The three income-bearing documents state income on three different bases and
reconcile exactly rather than being equal:

- W-2 Box 1 = annual gross less the pre-tax 401(k) deferral
- Pay stub YTD taxable, annualized = W-2 Box 1, to the cent
- Pay stub YTD gross, annualized = annual gross

Comparing pay stub YTD *gross* against W-2 Box 1 differs by the deferral rate.
`evaluation/alignment_matrix.json` states each document's basis explicitly.

Controlled misalignment — benign variation through coordinated fraud
(A1–A5) — is not in this pack.

---

## Legal Notice

All documents are synthetic. No real borrower data is included. SSNs use the
900-xx-xxxx range, which the SSA has never issued. Every document is
watermarked SYNTHETIC — NOT VALID.

Permitted uses: software development, QA, model training, internal
evaluation, demonstrations, research.

Prohibited uses: representing these documents as authentic, submitting them
to real lenders, identity fraud, removing synthetic markings, resale of the
raw dataset.

© 2026 Mpingo Systems LLC | eddy@mpingo.ai
https://realitydb.dev/financial-cases/
"""


def _default_distribution(count: int) -> dict:
    """Even split across the three scenarios, remainder to the front."""
    tiers = list(DEFAULT_PACK_SCENARIOS)
    per_scenario = count // len(tiers)
    remainder = count % len(tiers)
    return {
        tier: per_scenario + (1 if i < remainder else 0)
        for i, tier in enumerate(tiers)
    }


def generate_case_pack(
    count: int = 20,
    output_dir: str = "output",
    pack_name: str = "auto_loan_starter",
    seed_start: int = 1,
    distribution: dict = None,
    zip_output: bool = True,
) -> str:
    """
    Generate a complete case pack as a ZIP file.

    Args:
        count: Number of cases to generate
        output_dir: Where to write the ZIP
        pack_name: Name prefix for the ZIP
        seed_start: First seed (increments per case)
        distribution: Dict of scenario->count.
            Default: even split across scenarios.
        zip_output: If True, create ZIP and clean up
            the case folders. If False, leave folders.

    Returns:
        Path to generated ZIP file (or folder if
        zip_output=False).
    """
    if count < 1:
        raise ValueError(f"count must be at least 1, got {count}")

    if distribution is None:
        distribution = _default_distribution(count)

    known = set(_get_scenarios())
    unknown = set(distribution) - known
    if unknown:
        raise ValueError(
            f"unknown scenario(s) in distribution: {sorted(unknown)}; "
            f"choose from {sorted(known)}"
        )
    if sum(distribution.values()) != count:
        raise ValueError(
            f"distribution sums to {sum(distribution.values())} "
            f"but count is {count}"
        )

    # Build ordered list of scenarios
    scenario_list = []
    for scenario, n in distribution.items():
        scenario_list.extend([scenario] * n)
    scenario_list = scenario_list[:count]

    bundler = CaseBundler()
    cases_dir = os.path.join(output_dir, f"{pack_name}_cases")

    # The staging directory is removed wholesale once the ZIP is written, so
    # it must not be one that already holds anything: otherwise unrelated
    # files would be packed into a customer deliverable and then deleted.
    if os.path.isdir(cases_dir) and os.listdir(cases_dir):
        raise FileExistsError(
            f"staging directory is not empty: {cases_dir}\n"
            f"It is deleted after the ZIP is written, so it must be empty "
            f"or absent. Remove it or choose another --pack-name."
        )
    os.makedirs(cases_dir, exist_ok=True)

    case_summaries = []

    print(f"\nGenerating {count} cases...")
    print(f"Distribution: {distribution}")
    print("-" * 50)

    for i, scenario in enumerate(scenario_list):
        seed = seed_start + i

        case_dir, profile = bundler.generate_case_with_profile(
            seed=seed,
            scenario=scenario,
            output_dir=cases_dir,
        )

        case_id = f"case-{seed:06d}"
        case_summaries.append({
            "case_id": case_id,
            "scenario": scenario,
            "borrower_name": profile.full_name,
            "employer_name": profile.employer_name,
            "annual_income": round(profile.annual_gross_income, 2),
            "dti_ratio": round(profile.dti_ratio, 4),
            "ltv_ratio": round(profile.ltv_ratio, 4),
            "expected_decision": scenario,
            "alignment_class": "A0",
        })

        print(
            f"  [{i+1:03d}/{count}] {case_id} | "
            f"{scenario:8s} | "
            f"{profile.full_name:25s} | "
            f"DTI {profile.dti_ratio:.1%}"
        )

    # Write pack manifest
    pack_manifest = {
        "pack_name": pack_name,
        "generated_at": _utcnow(),
        "generator_version": GENERATOR_VERSION,
        "total_cases": count,
        "distribution": distribution,
        "seed_range": f"{seed_start}-{seed_start + count - 1}",
        "alignment": "A0",
        "documents_per_case": 6,
        "total_documents": count * 6,
        "truth_files_per_case": 5,
        "evaluation_files_per_case": 3,
        "methodology": _methodology(list(distribution)),
        "cases": case_summaries,
    }

    manifest_path = os.path.join(cases_dir, "PACK_MANIFEST.json")
    CaseBundler._write_json(manifest_path, pack_manifest)

    CaseBundler._write_text(
        os.path.join(cases_dir, "README.md"),
        _pack_readme(pack_name, count, distribution, seed_start),
    )

    print(f"\nPack manifest: {manifest_path}")

    if not zip_output:
        return cases_dir

    # Create ZIP
    zip_name = f"{pack_name}_{count}cases.zip"
    zip_path = os.path.join(output_dir, zip_name)

    print(f"Creating ZIP: {zip_path}")
    with zipfile.ZipFile(
        zip_path, "w", zipfile.ZIP_DEFLATED
    ) as zf:
        for root, dirs, files in os.walk(cases_dir):
            dirs.sort()
            for file in sorted(files):
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, output_dir)
                zf.write(file_path, arcname)

    # Clean up the staging folders now they are inside the ZIP.
    shutil.rmtree(cases_dir)

    zip_size_mb = os.path.getsize(zip_path) / 1024 / 1024
    print(f"ZIP size: {zip_size_mb:.2f} MB")
    print(f"Cases: {count}")
    print(f"Documents: {count * 6}")

    return zip_path
