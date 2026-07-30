"""
Cross-document consistency tests.

Verifies that W-2, bank statement, and loan
application generated from the same BorrowerProfile
describe the same person with consistent
financial attributes.

Runs across 25 seeds to catch edge cases.
All 275 checks must pass before any commit
that touches profile.py or any renderer.
"""
import os
import random
import tempfile

import pytest
import fitz  # PyMuPDF

from realitydb_docs.profile import (
    BorrowerProfile,
    FinancialCaseGenerator,
)
from realitydb_docs.w2 import W2Renderer
from realitydb_docs.bank_statement import BankStatementRenderer
from realitydb_docs.loan_app import LoanAppRenderer


# ── Test parameters ──────────────────────────────────────

SEEDS = list(range(1, 26))  # seeds 1-25

SCENARIOS = [
    {
        "annual_income": 102000,
        "loan_amount": 320000,
        "property_value": 420000,
        "dti_target": 0.36,
        "scenario": "approved",
    },
    {
        "annual_income": 74400,
        "loan_amount": 380000,
        "property_value": 460000,
        "dti_target": 0.45,
        "scenario": "flagged",
    },
    {
        "annual_income": 57600,
        "loan_amount": 450000,
        "property_value": 500000,
        "dti_target": 0.55,
        "scenario": "rejected",
    },
]


# ── Helpers ───────────────────────────────────────────────

def extract_text(pdf_path: str) -> str:
    """Extract all text from a PDF."""
    doc = fitz.open(pdf_path)
    text = ""
    for page in doc:
        text += page.get_text()
    doc.close()
    return text


def generate_all_docs(
    profile: BorrowerProfile,
    output_dir: str,
) -> dict:
    """Generate W-2, bank statement, and loan app."""
    paths = {}
    paths["w2"] = W2Renderer(profile).render(
        os.path.join(output_dir, "w2.pdf")
    )
    paths["bank"] = BankStatementRenderer(
        profile, month=10
    ).render(
        os.path.join(output_dir, "bank.pdf")
    )
    paths["loan"] = LoanAppRenderer(profile).render(
        os.path.join(output_dir, "loan.pdf")
    )
    return paths


# ── Fixtures ─────────────────────────────────────────────

@pytest.fixture(scope="session")
def generator():
    return FinancialCaseGenerator()


# ── Tests ─────────────────────────────────────────────────

@pytest.mark.consistency
@pytest.mark.parametrize("seed", SEEDS)
def test_name_consistent_across_documents(
    seed, generator, tmp_path
):
    """Same full name must appear in all three documents."""
    scenario = SCENARIOS[seed % len(SCENARIOS)]
    profile = generator.generate(seed=seed, **scenario)

    paths = generate_all_docs(profile, str(tmp_path))

    w2_text = extract_text(paths["w2"])
    bank_text = extract_text(paths["bank"])
    loan_text = extract_text(paths["loan"])

    assert profile.first_name in w2_text, (
        f"Seed {seed}: first name '{profile.first_name}' "
        f"missing from W-2"
    )
    assert profile.last_name in w2_text, (
        f"Seed {seed}: last name '{profile.last_name}' "
        f"missing from W-2"
    )
    assert profile.full_name in bank_text, (
        f"Seed {seed}: full name '{profile.full_name}' "
        f"missing from bank statement"
    )
    assert profile.full_name in loan_text, (
        f"Seed {seed}: full name '{profile.full_name}' "
        f"missing from loan application"
    )


@pytest.mark.consistency
@pytest.mark.parametrize("seed", SEEDS)
def test_employer_consistent_across_documents(
    seed, generator, tmp_path
):
    """Same employer must appear in all three documents."""
    scenario = SCENARIOS[seed % len(SCENARIOS)]
    profile = generator.generate(seed=seed, **scenario)

    paths = generate_all_docs(profile, str(tmp_path))

    w2_text = extract_text(paths["w2"])
    bank_text = extract_text(paths["bank"])
    loan_text = extract_text(paths["loan"])

    employer_word = profile.employer_name.split()[0]

    assert employer_word in w2_text, (
        f"Seed {seed}: employer '{profile.employer_name}' "
        f"missing from W-2"
    )
    assert employer_word.upper() in bank_text.upper(), (
        f"Seed {seed}: employer '{profile.employer_name}' "
        f"missing from bank statement"
    )
    assert employer_word in loan_text, (
        f"Seed {seed}: employer '{profile.employer_name}' "
        f"missing from loan application"
    )


@pytest.mark.consistency
@pytest.mark.parametrize("seed", SEEDS)
def test_ssn_format_valid(seed, generator):
    """SSN must be in 900-XX-XXXX format."""
    scenario = SCENARIOS[seed % len(SCENARIOS)]
    profile = generator.generate(seed=seed, **scenario)

    parts = profile.ssn.split("-")
    assert len(parts) == 3, (
        f"Seed {seed}: SSN format invalid: {profile.ssn}"
    )
    assert parts[0] == "900", (
        f"Seed {seed}: SSN must start with 900, "
        f"got {parts[0]}"
    )
    assert len(parts[1]) == 2, (
        f"Seed {seed}: SSN middle must be 2 digits"
    )
    assert len(parts[2]) == 4, (
        f"Seed {seed}: SSN end must be 4 digits"
    )


@pytest.mark.consistency
@pytest.mark.parametrize("seed", SEEDS)
def test_dti_within_tolerance(seed, generator):
    """DTI must be within 3% of the target."""
    scenario = SCENARIOS[seed % len(SCENARIOS)]
    profile = generator.generate(seed=seed, **scenario)

    target = scenario["dti_target"]
    tolerance = 0.03

    assert abs(profile.dti_ratio - target) <= tolerance, (
        f"Seed {seed}: DTI {profile.dti_ratio:.3f} "
        f"not within {tolerance:.0%} of "
        f"target {target:.3f}"
    )


@pytest.mark.consistency
@pytest.mark.parametrize("seed", SEEDS)
def test_ltv_correct(seed, generator):
    """LTV must equal loan_amount / property_value."""
    scenario = SCENARIOS[seed % len(SCENARIOS)]
    profile = generator.generate(seed=seed, **scenario)

    expected_ltv = (
        scenario["loan_amount"] / scenario["property_value"]
    )

    assert abs(profile.ltv_ratio - expected_ltv) < 0.001, (
        f"Seed {seed}: LTV {profile.ltv_ratio:.4f} "
        f"does not match expected {expected_ltv:.4f}"
    )


@pytest.mark.consistency
@pytest.mark.parametrize("seed", SEEDS)
def test_income_reconciles_with_w2(seed, generator, tmp_path):
    """
    W-2 Box 1 wages must equal annual gross income
    less the pre-tax 401k deferral, and the figure
    must actually appear on the rendered form.
    """
    scenario = SCENARIOS[seed % len(SCENARIOS)]
    profile = generator.generate(seed=seed, **scenario)

    path = W2Renderer(profile).render(
        str(tmp_path / "w2.pdf")
    )
    text = extract_text(path)

    assert profile.w2_box1_wages > 0, (
        f"Seed {seed}: W-2 Box 1 wages must be positive"
    )

    # The exact reconciliation identity a lender checks. Asserting only
    # `box1 < gross` is wrong: retirement_contrib_rate can be 0.0, in which
    # case Box 1 correctly EQUALS gross. Five of these seeds (10-13, 18) draw
    # a 0% deferral.
    rate = profile.retirement_contrib_rate
    expected_box1 = profile.annual_gross_income * (1 - rate)
    assert abs(profile.w2_box1_wages - expected_box1) < 0.01, (
        f"Seed {seed}: Box 1 {profile.w2_box1_wages:,.2f} != "
        f"gross {profile.annual_gross_income:,.2f} less "
        f"{rate:.0%} deferral ({expected_box1:,.2f})"
    )
    if rate > 0:
        assert profile.w2_box1_wages < profile.annual_gross_income, (
            f"Seed {seed}: with a {rate:.0%} deferral Box 1 must be "
            f"below gross income"
        )
    else:
        assert profile.w2_box1_wages == profile.annual_gross_income, (
            f"Seed {seed}: with no deferral Box 1 must equal gross income"
        )

    assert profile.w2_box2_federal_withheld > 0, (
        f"Seed {seed}: Federal withholding must be positive"
    )

    # The Box 1 figure must be on the page, not merely on the object.
    assert f"{profile.w2_box1_wages:,.2f}" in text, (
        f"Seed {seed}: Box 1 wages "
        f"{profile.w2_box1_wages:,.2f} not found on the rendered W-2"
    )


@pytest.mark.consistency
@pytest.mark.parametrize("seed", SEEDS)
def test_checking_balance_positive(seed, generator):
    """Checking balance must be positive."""
    scenario = SCENARIOS[seed % len(SCENARIOS)]
    profile = generator.generate(seed=seed, **scenario)

    assert profile.checking_balance > 0, (
        f"Seed {seed}: Checking balance must be positive, "
        f"got {profile.checking_balance}"
    )


@pytest.mark.consistency
@pytest.mark.parametrize("seed", SEEDS)
def test_determinism(seed, generator):
    """Same seed must always produce identical profile.

    Parametrized over every seed rather than only 42: the decorator declares
    `seed`, so the signature has to accept it, and checking determinism at
    all 25 seeds is strictly stronger than checking it at one.
    """
    scenario = SCENARIOS[seed % len(SCENARIOS)]

    profile1 = generator.generate(seed=seed, **scenario)
    profile2 = generator.generate(seed=seed, **scenario)

    assert profile1.full_name == profile2.full_name, (
        "Determinism failed: different names from same seed"
    )
    assert profile1.employer_name == profile2.employer_name, (
        "Determinism failed: different employers from same seed"
    )
    assert profile1.annual_gross_income == profile2.annual_gross_income, (
        "Determinism failed: different income from same seed"
    )


@pytest.mark.consistency
@pytest.mark.parametrize("seed", SEEDS)
def test_watermark_present(seed, generator, tmp_path):
    """SYNTHETIC watermark must appear in all documents."""
    scenario = SCENARIOS[seed % len(SCENARIOS)]
    profile = generator.generate(seed=seed, **scenario)

    paths = generate_all_docs(profile, str(tmp_path))

    for doc_type, path in paths.items():
        text = extract_text(path)
        assert "SYNTHETIC" in text.upper(), (
            f"Seed {seed}: SYNTHETIC watermark missing "
            f"from {doc_type}"
        )


@pytest.mark.consistency
@pytest.mark.parametrize("seed", SEEDS)
def test_address_in_loan_app(seed, generator, tmp_path):
    """Borrower city and state must appear in loan app."""
    scenario = SCENARIOS[seed % len(SCENARIOS)]
    profile = generator.generate(seed=seed, **scenario)

    path = LoanAppRenderer(profile).render(
        str(tmp_path / "loan.pdf")
    )
    text = extract_text(path)

    assert profile.city in text, (
        f"Seed {seed}: City '{profile.city}' "
        f"missing from loan application"
    )
    assert profile.state in text, (
        f"Seed {seed}: State '{profile.state}' "
        f"missing from loan application"
    )


@pytest.mark.consistency
@pytest.mark.parametrize("seed", SEEDS)
def test_no_text_outside_page(seed, generator, tmp_path):
    """No text block should start outside page boundaries."""
    scenario = SCENARIOS[seed % len(SCENARIOS)]
    profile = generator.generate(seed=seed, **scenario)

    paths = generate_all_docs(profile, str(tmp_path))

    for doc_type, path in paths.items():
        doc = fitz.open(path)
        for page_num, page in enumerate(doc):
            page_rect = page.rect
            blocks = page.get_text("blocks")
            for block in blocks:
                x0, y0, x1, y1 = block[:4]
                assert x0 >= 0, (
                    f"Seed {seed} {doc_type} p{page_num+1}: "
                    f"text starts at x={x0:.1f} (off left edge)"
                )
                assert x1 <= page_rect.width + 2, (
                    f"Seed {seed} {doc_type} p{page_num+1}: "
                    f"text ends at x={x1:.1f} "
                    f"(page width={page_rect.width:.1f})"
                )
        doc.close()


# ── Pay stub tests ────────────────────────────────────────

@pytest.mark.consistency
@pytest.mark.parametrize("seed", SEEDS)
def test_paystub_name_matches_profile(
    seed, generator, tmp_path
):
    """Pay stub employee name must match profile."""
    from realitydb_docs.paystub import PayStubRenderer

    scenario = SCENARIOS[seed % len(SCENARIOS)]
    profile = generator.generate(seed=seed, **scenario)

    path = PayStubRenderer(profile, pay_period=22).render(
        str(tmp_path / "paystub.pdf")
    )
    text = extract_text(path)

    assert profile.full_name in text, (
        f"Seed {seed}: '{profile.full_name}' "
        f"missing from pay stub"
    )
    # The banner renders the employer upper-cased, the way a payroll system
    # prints it. Compare case-insensitively — a literal `employer_name in
    # text` never matches a title-case employer.
    assert profile.employer_name.upper() in text.upper(), (
        f"Seed {seed}: '{profile.employer_name}' "
        f"missing from pay stub"
    )


@pytest.mark.consistency
@pytest.mark.parametrize("seed", SEEDS)
def test_paystub_ytd_consistent_with_w2(
    seed, generator
):
    """
    Every pay stub YTD column at period 26 must tie
    to the matching W-2 box, within $0.01.
    """
    from realitydb_docs.paystub import PayStubRenderer

    scenario = SCENARIOS[seed % len(SCENARIOS)]
    profile = generator.generate(seed=seed, **scenario)

    r = PayStubRenderer(profile, pay_period=26)

    # Comparing gross YTD to annual income alone is the weakest of the
    # available identities and does not actually involve a W-2 box. All six
    # are asserted so a change to either tax model breaks this test.
    identities = [
        ("gross YTD vs annual gross income",
         r.gross_ytd, profile.annual_gross_income),
        ("gross less 401k YTD vs W-2 box 1",
         r.taxable_ytd, profile.w2_box1_wages),
        ("federal YTD vs W-2 box 2",
         r.fed_tax_ytd, profile.w2_box2_federal_withheld),
        ("social security YTD vs W-2 box 4",
         r.ss_tax_ytd, profile.w2_box4_ss_withheld),
        ("medicare YTD vs W-2 box 6",
         r.medicare_ytd, profile.w2_box6_medicare_withheld),
        ("state YTD vs W-2 box 17",
         r.state_tax_ytd, profile.w2_box17_state_withheld),
    ]
    for label, got, want in identities:
        assert abs(got - want) < 0.01, (
            f"Seed {seed}: {label} — pay stub {got:,.2f} "
            f"does not match W-2 {want:,.2f}"
        )


@pytest.mark.consistency
@pytest.mark.parametrize("seed", SEEDS)
def test_paystub_net_positive(seed, generator):
    """Net pay must always be positive."""
    from realitydb_docs.paystub import PayStubRenderer

    scenario = SCENARIOS[seed % len(SCENARIOS)]
    profile = generator.generate(seed=seed, **scenario)

    r = PayStubRenderer(profile, pay_period=22)

    assert r.net_pay > 0, (
        f"Seed {seed}: Net pay is negative: {r.net_pay:.2f}"
    )
    # Deductions must not swallow the cheque either.
    assert r.net_pay < r.gross_per_period, (
        f"Seed {seed}: Net pay {r.net_pay:.2f} must be below "
        f"gross {r.gross_per_period:.2f}"
    )


@pytest.mark.consistency
@pytest.mark.parametrize("seed", SEEDS)
def test_paystub_watermark(seed, generator, tmp_path):
    """SYNTHETIC watermark must appear on pay stub."""
    from realitydb_docs.paystub import PayStubRenderer

    scenario = SCENARIOS[seed % len(SCENARIOS)]
    profile = generator.generate(seed=seed, **scenario)

    path = PayStubRenderer(profile, pay_period=22).render(
        str(tmp_path / "paystub.pdf")
    )
    text = extract_text(path)

    assert "SYNTHETIC" in text.upper(), (
        f"Seed {seed}: SYNTHETIC watermark missing "
        f"from pay stub"
    )


# ── Case bundler tests ────────────────────────────────────

CASE_FILES = [
    "documents/w2_2024.pdf",
    "documents/bank_oct_2024.pdf",
    "documents/bank_nov_2024.pdf",
    "documents/loan_app_1003.pdf",
    "documents/paystub_period22.pdf",
    "documents/paystub_period21.pdf",
    "truth/borrower.json",
    "truth/employment.json",
    "truth/income.json",
    "truth/liabilities.json",
    "truth/case_manifest.json",
    "evaluation/expected_extractions.json",
    "evaluation/alignment_matrix.json",
    "evaluation/expected_decision.json",
    "README.md",
]


@pytest.mark.consistency
def test_packet_generates_all_files(tmp_path):
    """A case folder must contain all 15 files, none empty."""
    from realitydb_docs.packet import CaseBundler

    case_dir = CaseBundler().generate_case(
        seed=42, scenario="approved", output_dir=str(tmp_path)
    )
    for item in CASE_FILES:
        path = os.path.join(case_dir, item)
        assert os.path.exists(path), f"Missing: {item}"
        assert os.path.getsize(path) > 0, f"Empty: {item}"


@pytest.mark.consistency
def test_manifest_name_matches_documents(tmp_path):
    """The name in the manifest must be the name on the documents."""
    import json

    from realitydb_docs.packet import CaseBundler

    case_dir = CaseBundler().generate_case(
        seed=42, scenario="approved", output_dir=str(tmp_path)
    )
    with open(
        os.path.join(case_dir, "truth", "case_manifest.json"),
        encoding="utf-8",
    ) as fh:
        manifest = json.load(fh)

    expected_name = manifest["borrower"]["full_name"]

    w2_text = extract_text(
        os.path.join(case_dir, "documents", "w2_2024.pdf")
    )
    assert expected_name.split()[0] in w2_text, (
        f"Name {expected_name} not found in W-2"
    )

    loan_text = extract_text(
        os.path.join(case_dir, "documents", "loan_app_1003.pdf")
    )
    assert expected_name in loan_text, (
        f"Name {expected_name} not found in loan app"
    )


@pytest.mark.consistency
def test_manifest_decision_correct(tmp_path):
    """expected_decision.json must record the scenario asked for."""
    import json

    from realitydb_docs.packet import CaseBundler

    bundler = CaseBundler()
    for i, scenario in enumerate(["approved", "flagged", "rejected"]):
        case_dir = bundler.generate_case(
            seed=200 + i, scenario=scenario, output_dir=str(tmp_path)
        )
        with open(
            os.path.join(
                case_dir, "evaluation", "expected_decision.json"
            ),
            encoding="utf-8",
        ) as fh:
            decision = json.load(fh)

        assert decision["expected_decision"] == scenario, (
            f"Scenario {scenario}: decision mismatch in "
            f"expected_decision.json"
        )


@pytest.mark.consistency
@pytest.mark.parametrize("seed", SEEDS[:8])
def test_expected_extractions_appear_on_documents(seed, tmp_path):
    """
    Every expected extraction must be present on its document.

    This is the gate on the layer a customer actually buys. A truth file
    that disagrees with the PDF beside it is worse than a missing one: a
    model scored against it is marked wrong for being right.

    Three formatting differences make this non-trivial, and stating the
    underlying value instead of the printed one fails on all three:
    the 1003 prints money to whole dollars, a bank payroll deposit jitters
    +/-3% around monthly gross, and the pay stub upper-cases the employer.
    """
    import json

    from realitydb_docs.packet import CaseBundler

    scenario = ["approved", "flagged", "rejected"][seed % 3]
    case_dir = CaseBundler().generate_case(
        seed=seed, scenario=scenario, output_dir=str(tmp_path)
    )
    with open(
        os.path.join(
            case_dir, "evaluation", "expected_extractions.json"
        ),
        encoding="utf-8",
    ) as fh:
        expected = json.load(fh)

    checked = 0
    for doc_key, fields in expected.items():
        if doc_key.startswith("_"):
            continue
        body = extract_text(
            os.path.join(case_dir, "documents", f"{doc_key}.pdf")
        )
        whole_dollars = doc_key == "loan_app_1003"
        for name, value in fields.items():
            if value is None or isinstance(value, bool):
                continue
            if name.endswith(("_reference", "_pct", "_normalized")):
                continue
            if isinstance(value, (int, float)):
                if name in (
                    "pay_period_number", "pay_periods_per_year", "tax_year"
                ):
                    needle = str(int(value))
                elif name in ("ltv_ratio", "dti_ratio"):
                    continue  # asserted via the *_as_printed strings
                elif whole_dollars:
                    needle = f"{value:,.0f}"
                else:
                    needle = f"{value:,.2f}"
            elif isinstance(value, str) and (
                name.endswith("name") or name.endswith("as_printed")
            ):
                needle = value
            else:
                continue
            checked += 1
            assert needle in body, (
                f"Seed {seed}: {doc_key}.{name} = {needle!r} "
                f"is not present on the rendered document"
            )

    assert checked > 50, (
        f"Seed {seed}: only {checked} values checked — the assertion "
        f"loop is not covering the documents"
    )


@pytest.mark.consistency
@pytest.mark.parametrize("seed", SEEDS[:8])
def test_paystub_ytd_ties_to_w2_in_truth_layer(seed, tmp_path):
    """
    The truth layer's own numbers must reconcile.

    Annualized YTD taxable wages from the pay stub must equal W-2 box 1,
    and FICA must be computed on gross rather than on box 1 — boxes 3 and 5
    exceed box 1 by the deferral on a real W-2.
    """
    import json

    from realitydb_docs.packet import CaseBundler
    from realitydb_docs.paystub import TOTAL_PERIODS

    scenario = ["approved", "flagged", "rejected"][seed % 3]
    case_dir = CaseBundler().generate_case(
        seed=seed, scenario=scenario, output_dir=str(tmp_path)
    )

    def load(*parts):
        with open(os.path.join(case_dir, *parts), encoding="utf-8") as fh:
            return json.load(fh)

    income = load("truth", "income.json")
    expected = load("evaluation", "expected_extractions.json")
    w2 = expected["w2_2024"]
    stub = expected["paystub_period22"]

    annualized = (
        stub["ytd_taxable"] / stub["pay_period_number"] * TOTAL_PERIODS
    )
    assert abs(annualized - w2["wages_box_1"]) < 0.01, (
        f"Seed {seed}: annualized YTD taxable {annualized:,.2f} != "
        f"W-2 box 1 {w2['wages_box_1']:,.2f}"
    )

    rate = income["retirement_contrib_rate"]
    assert abs(
        w2["medicare_wages_box_5"] - income["annual_gross_income"]
    ) < 0.01, (
        f"Seed {seed}: box 5 must be gross, not box 1"
    )
    if rate > 0:
        assert w2["ss_wages_box_3"] > w2["wages_box_1"], (
            f"Seed {seed}: with a {rate:.0%} deferral box 3 must exceed "
            f"box 1"
        )


@pytest.mark.rendering
@pytest.mark.parametrize("seed", SEEDS)
def test_paystub_no_text_outside_page(seed, generator, tmp_path):
    """
    No pay stub text may fall outside the page.

    Gates the bug class this renderer shipped with: the YTD column was
    right-aligned at 619pt on a 612pt page, so the entire column was
    clipped away without any value being wrong.
    """
    from realitydb_docs.paystub import PayStubRenderer

    scenario = SCENARIOS[seed % len(SCENARIOS)]
    profile = generator.generate(seed=seed, **scenario)

    path = PayStubRenderer(profile, pay_period=22).render(
        str(tmp_path / "paystub.pdf")
    )
    doc = fitz.open(path)
    try:
        for page_num, page in enumerate(doc):
            for w in page.get_text("words"):
                x0, _, x1, _ = w[:4]
                assert x0 >= 0, (
                    f"Seed {seed} paystub p{page_num+1}: "
                    f"{w[4]!r} starts at x={x0:.1f}"
                )
                assert x1 <= page.rect.width + 2, (
                    f"Seed {seed} paystub p{page_num+1}: "
                    f"{w[4]!r} ends at x={x1:.1f} "
                    f"(page width={page.rect.width:.1f})"
                )
    finally:
        doc.close()
