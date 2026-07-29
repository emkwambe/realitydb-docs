"""RealityDB Loan Application Renderer — Fannie Mae Form 1003.

Generates a simplified two-page Uniform Residential Loan Application. Not the
full ten-page form: a realistic summary carrying every field PacketWise needs
for underwriting (loan, property, borrower, employment, assets, liabilities,
declarations).

Consistency with the other generators in this package:
  annual_income          matches w2.generate_synthetic_w2_batch(
                           target_annual_income=...) within +/-2%
  debt_to_income_target  the DTI the finished form should show, so a packet's
                         underwriting outcome is predictable rather than
                         seed-dependent

Everything is derived from `seed`, so the same inputs always produce the same
document.
"""
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from dataclasses import dataclass, field
from typing import Optional, List
import os
import random

# ── Palette ────────────────────────────────────────────────────────────
SECTION_BG = (0x1a / 255, 0x3a / 255, 0x6b / 255)   # #1a3a6b
LABEL_GREY = (0x6b / 255, 0x72 / 255, 0x80 / 255)   # #6b7280
VALUE_BLACK = (0x11 / 255, 0x18 / 255, 0x27 / 255)  # #111827
ROW_SHADE = (0xf8 / 255, 0xfa / 255, 0xfc / 255)    # #f8fafc
FOOTER_GREY = (0.45, 0.45, 0.45)
DTI_GREEN = (0.05, 0.5, 0.2)
DTI_AMBER = (0.85, 0.55, 0.0)
DTI_RED = (0.75, 0.1, 0.1)

MARGIN = 0.75 * inch

FIRST_NAMES = [
    "James", "Mary", "Robert", "Patricia", "John", "Jennifer", "Michael",
    "Linda", "David", "Elizabeth", "William", "Barbara", "Richard", "Susan",
    "Joseph", "Jessica", "Thomas", "Sarah", "Charles", "Karen",
]
LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
    "Davis", "Rodriguez", "Martinez", "Hernandez", "Lopez", "Wilson",
    "Anderson", "Taylor", "Thomas", "Moore", "Jackson", "Martin", "Lee",
]
STREETS = [
    "Maple Avenue", "Oak Street", "Cedar Lane", "Birch Road", "Willow Drive",
    "Sycamore Court", "Chestnut Street", "Juniper Way", "Magnolia Boulevard",
    "Aspen Circle", "Hickory Lane", "Poplar Avenue",
]
CITIES = [
    ("Charlotte", "NC", "28202"), ("Raleigh", "NC", "27601"),
    ("Atlanta", "GA", "30303"), ("Columbus", "OH", "43215"),
    ("Austin", "TX", "78701"), ("Denver", "CO", "80202"),
    ("Portland", "OR", "97204"), ("Nashville", "TN", "37201"),
    ("Kansas City", "MO", "64106"), ("Richmond", "VA", "23219"),
]
EMPLOYERS = [
    "Acme Corporation", "TechStart Inc", "MetroHealth Systems",
    "Global Logistics LLC", "Summit Education Group", "Northwind Traders",
    "Bluepeak Manufacturing", "Cardinal Financial Services",
]
TITLES = [
    "Senior Analyst", "Operations Manager", "Registered Nurse",
    "Software Engineer", "Account Executive", "Project Manager",
    "Logistics Coordinator", "Staff Accountant", "Field Technician",
]
EMAIL_DOMAINS = ["gmail.com", "outlook.com", "yahoo.com", "proton.me"]


def _weighted(rng: random.Random, choices: List[tuple]):
    """Pick from [(value, weight), ...]."""
    values = [c[0] for c in choices]
    weights = [c[1] for c in choices]
    return rng.choices(values, weights=weights, k=1)[0]


def _money(v: float) -> str:
    return f"${v:,.0f}"


@dataclass
class LoanApplicationData:
    # Section 1 — loan
    loan_purpose: str
    loan_amount: float
    loan_type: str
    rate_type: str
    amortization_term: str
    application_date: str
    # Section 2 — property
    property_address: str
    property_city_state_zip: str
    property_type: str
    property_value: float
    property_use: str
    ltv_ratio: float
    # Section 3 — borrower
    borrower_name: str
    ssn: str
    date_of_birth: str
    marital_status: str
    dependents: int
    current_address: str
    years_at_address: float
    phone: str
    email: str
    # Section 4 — employment
    employer_name: str
    position: str
    employment_type: str
    years_at_job: float
    gross_monthly_income: float
    other_income: float
    # Section 5 — assets
    checking_balance: float
    savings_balance: float
    retirement_balance: float
    down_payment: float
    down_payment_source: str
    # Section 6 — liabilities
    car_payment: float
    student_loan: float
    credit_card_minimum: float
    other_debt: float
    monthly_housing_payment: Optional[float]
    total_monthly_debt: float
    estimated_dti: float
    # Section 7 — declarations
    outstanding_judgments: str
    bankruptcy_7yr: str
    foreclosure_7yr: str
    federal_debt_delinquent: str
    # Optional underwriting extras
    credit_score: Optional[int] = None
    tax_year: int = 2024


def _build_data(
    rng: random.Random,
    annual_income: Optional[float],
    loan_amount: Optional[float],
    property_value: Optional[float],
    debt_to_income_target: Optional[float],
    tax_year: int,
    credit_score: Optional[int],
    monthly_housing_payment: Optional[float],
) -> LoanApplicationData:
    # ── Section 1 — loan ──
    purpose = _weighted(rng, [("Purchase", 80), ("Refinance", 20)])
    loan_type = _weighted(rng, [("Conventional", 70), ("FHA", 20), ("VA", 10)])
    rate_type = _weighted(rng, [("Fixed", 80), ("ARM", 20)])
    term = _weighted(rng, [("30 Years", 70), ("15 Years", 20), ("20 Years", 10)])

    if loan_amount is None:
        loan_amount = round(rng.uniform(150_000, 750_000), -3)

    # ── Section 2 — property ──
    if property_value is None:
        # LTV lands in 70-90% by construction.
        property_value = round(loan_amount / rng.uniform(0.70, 0.90), -3)
    ltv = loan_amount / property_value if property_value else 0.0

    city, state, zipcode = rng.choice(CITIES)
    prop_address = f"{rng.randint(100, 9899)} {rng.choice(STREETS)}"
    prop_type = _weighted(rng, [("Single Family", 70), ("Condominium", 20),
                                ("Multi-Family (2-4 units)", 10)])
    prop_use = _weighted(rng, [("Primary Residence", 80), ("Investment", 20)])

    # ── Section 3 — borrower ──
    first, last = rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES)
    name = f"{first} {last}"
    # 900-XX-XXXX only: the 900 range is never issued by the SSA, so a
    # synthetic document can never collide with a real number.
    ssn = f"900-{rng.randint(10, 99):02d}-{rng.randint(1000, 9999):04d}"
    age = rng.randint(25, 65)
    dob = f"{rng.randint(1, 12):02d}/{rng.randint(1, 28):02d}/{tax_year - age}"
    marital = _weighted(rng, [("Married", 55), ("Single", 35), ("Separated", 10)])
    dependents = rng.choice([0, 0, 1, 1, 2, 3])
    # 70% of applicants have been at the address 2+ years.
    years_addr = (round(rng.uniform(2, 10), 1) if rng.random() < 0.70
                  else round(rng.uniform(0, 2), 1))
    cur_city, cur_state, cur_zip = rng.choice(CITIES)
    cur_address = (f"{rng.randint(100, 9899)} {rng.choice(STREETS)}, "
                   f"{cur_city}, {cur_state} {cur_zip}")
    phone = f"({rng.randint(200, 989)}) {rng.randint(200, 989)}-{rng.randint(1000, 9999)}"
    email = f"{first.lower()}.{last.lower()}@{rng.choice(EMAIL_DOMAINS)}"

    # ── Section 4 — employment ──
    employer = rng.choice(EMPLOYERS)
    position = rng.choice(TITLES)
    emp_type = _weighted(rng, [("Employed", 75), ("Self-Employed", 20),
                               ("Retired", 5)])
    years_job = round(rng.uniform(0, 15), 1)

    if annual_income is not None:
        # +/-2% keeps the form consistent with a W-2 generated for the same
        # income without making the two documents suspiciously identical.
        gross_monthly = round(annual_income / 12 * rng.uniform(0.98, 1.02), 2)
    else:
        gross_monthly = round(rng.uniform(3_000, 15_000), 2)
    other_income = round(rng.uniform(500, 2_000), 2) if rng.random() < 0.30 else 0.0

    # ── Section 5 — assets ──
    checking = round(rng.uniform(5_000, 50_000), 2)
    savings = round(rng.uniform(10_000, 100_000), 2)
    retirement = round(rng.uniform(0, 200_000), 2)
    down_payment = max(property_value - loan_amount, 0.0)
    dp_source = _weighted(rng, [("Savings", 60), ("Gift Funds", 25),
                                ("Sale of Property", 15)])

    # ── Section 6 — liabilities ──
    housing = monthly_housing_payment
    if debt_to_income_target is not None and gross_monthly > 0:
        # Size the non-housing liabilities so the finished form shows the
        # requested DTI. Housing (when supplied) counts toward the target,
        # because that is how the underwriting engine computes DTI.
        target_total = debt_to_income_target * gross_monthly
        budget = max(target_total - (housing or 0.0), 0.0)
        # Split across the four lines using the ratio of their nominal caps,
        # scaling past the caps when the target demands it — hitting the
        # requested DTI matters more than a cosmetic ceiling.
        caps = [650.0, 800.0, 500.0, 300.0]
        total_cap = sum(caps)
        car, student, card, other = [round(budget * c / total_cap, 2) for c in caps]
    else:
        car = round(rng.uniform(0, 650), 2)
        student = round(rng.uniform(0, 800), 2)
        card = round(rng.uniform(0, 500), 2)
        other = round(rng.uniform(0, 300), 2)

    total_debt = round(car + student + card + other + (housing or 0.0), 2)
    dti = total_debt / gross_monthly if gross_monthly else 0.0

    # ── Section 7 — declarations ──
    judgments = "Yes" if rng.random() < 0.05 else "No"
    bankruptcy = "Yes" if rng.random() < 0.10 else "No"
    foreclosure = "Yes" if rng.random() < 0.10 else "No"
    fed_delinquent = "Yes" if rng.random() < 0.02 else "No"

    app_date = f"{rng.randint(1, 12):02d}/{rng.randint(1, 28):02d}/{tax_year}"

    return LoanApplicationData(
        loan_purpose=purpose, loan_amount=loan_amount, loan_type=loan_type,
        rate_type=rate_type, amortization_term=term, application_date=app_date,
        property_address=prop_address,
        property_city_state_zip=f"{city}, {state} {zipcode}",
        property_type=prop_type, property_value=property_value,
        property_use=prop_use, ltv_ratio=ltv,
        borrower_name=name, ssn=ssn, date_of_birth=dob, marital_status=marital,
        dependents=dependents, current_address=cur_address,
        years_at_address=years_addr, phone=phone, email=email,
        employer_name=employer, position=position, employment_type=emp_type,
        years_at_job=years_job, gross_monthly_income=gross_monthly,
        other_income=other_income,
        checking_balance=checking, savings_balance=savings,
        retirement_balance=retirement, down_payment=down_payment,
        down_payment_source=dp_source,
        car_payment=car, student_loan=student, credit_card_minimum=card,
        other_debt=other, monthly_housing_payment=housing,
        total_monthly_debt=total_debt, estimated_dti=dti,
        outstanding_judgments=judgments, bankruptcy_7yr=bankruptcy,
        foreclosure_7yr=foreclosure, federal_debt_delinquent=fed_delinquent,
        credit_score=credit_score, tax_year=tax_year,
    )


class LoanApplicationRenderer:
    """Renders a two-page Form 1003 summary."""

    def __init__(self):
        self.width, self.height = letter
        self.margin = MARGIN
        self._row_index = 0

    # -- chrome ---------------------------------------------------------

    def _watermark(self, c):
        c.saveState()
        c.setFillColorRGB(0.5, 0.5, 0.5)
        try:
            c.setFillAlpha(0.40)
        except AttributeError:      # very old reportlab
            c.setFillColorRGB(0.85, 0.85, 0.85)
        c.translate(self.width / 2, self.height / 2)
        c.rotate(45)
        c.setFont("Helvetica-Bold", 36)
        c.drawCentredString(0, 0, "SYNTHETIC - NOT VALID")
        c.restoreState()

    def _footer(self, c):
        c.saveState()
        c.setFillColorRGB(*FOOTER_GREY)
        c.setFont("Helvetica", 8)
        c.drawCentredString(
            self.width / 2, 36,
            "(c) 2026 Mpingo Systems LLC | RealityDB Synthetic Documents | "
            "For testing and development only",
        )
        c.restoreState()

    def _page_header(self, c):
        c.setFillColorRGB(0, 0, 0)
        c.setFont("Helvetica-Bold", 14)
        c.drawCentredString(self.width / 2, self.height - self.margin - 4,
                            "UNIFORM RESIDENTIAL LOAN APPLICATION")
        c.setFillColorRGB(*LABEL_GREY)
        c.setFont("Helvetica", 10)
        c.drawCentredString(self.width / 2, self.height - self.margin - 20,
                            "Fannie Mae Form 1003 | Revised 2021")
        y = self.height - self.margin - 30
        c.setStrokeColorRGB(0, 0, 0)
        c.setLineWidth(2)
        c.line(self.margin, y, self.width - self.margin, y)
        return y - 18

    def _section(self, c, y: float, title: str) -> float:
        """Dark header band. Returns the y for the first field row."""
        h = 16
        c.setFillColorRGB(*SECTION_BG)
        c.rect(self.margin, y - h, self.width - 2 * self.margin, h,
               stroke=0, fill=1)
        c.setFillColorRGB(1, 1, 1)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(self.margin + 6, y - h + 5, title)
        self._row_index = 0
        return y - h - 4

    def _field_row(self, c, y: float, left: tuple, right: Optional[tuple] = None,
                   value_color=None) -> float:
        """One row holding up to two label/value pairs.

        Label and value are drawn close together on a shared baseline so the
        pair extracts as a single line of text — PyMuPDF splits a line when
        the horizontal gap is wide, which would break the extractor's
        `Label: value` regexes.
        """
        h = 14
        if self._row_index % 2 == 1:
            c.setFillColorRGB(*ROW_SHADE)
            c.rect(self.margin, y - h + 2, self.width - 2 * self.margin, h,
                   stroke=0, fill=1)
        self._row_index += 1

        half = (self.width - 2 * self.margin) / 2
        for idx, pair in enumerate((left, right)):
            if pair is None:
                continue
            label, value = pair
            x = self.margin + 6 + idx * half
            c.setFillColorRGB(*LABEL_GREY)
            c.setFont("Helvetica", 7.5)
            label_text = f"{label}:"
            c.drawString(x, y - h + 5, label_text)
            offset = c.stringWidth(label_text, "Helvetica", 7.5) + 4
            if value_color and idx == 0:
                c.setFillColorRGB(*value_color)
            else:
                c.setFillColorRGB(*VALUE_BLACK)
            c.setFont("Helvetica", 9)
            c.drawString(x + offset, y - h + 5, str(value))
        return y - h

    # -- pages ----------------------------------------------------------

    def _page_one(self, c, d: LoanApplicationData):
        self._watermark(c)
        y = self._page_header(c)

        y = self._section(c, y, "SECTION 1 - LOAN INFORMATION")
        y = self._field_row(c, y, ("Loan Purpose", d.loan_purpose),
                            ("Loan Type", d.loan_type))
        y = self._field_row(c, y, ("Loan Amount", _money(d.loan_amount)),
                            ("Interest Rate Type", d.rate_type))
        y = self._field_row(c, y, ("Amortization Term", d.amortization_term),
                            ("Application Date", d.application_date))
        y -= 10

        y = self._section(c, y, "SECTION 2 - PROPERTY INFORMATION")
        y = self._field_row(c, y, ("Property Address", d.property_address))
        y = self._field_row(c, y, ("City / State / ZIP", d.property_city_state_zip),
                            ("Property Type", d.property_type))
        y = self._field_row(c, y, ("Property Value", _money(d.property_value)),
                            ("Property Use", d.property_use))
        y = self._field_row(c, y, ("LTV Ratio", f"{d.ltv_ratio * 100:.1f}%"),
                            ("Down Payment", _money(d.down_payment)))
        y -= 10

        y = self._section(c, y, "SECTION 3 - BORROWER INFORMATION")
        y = self._field_row(c, y, ("Borrower Name", d.borrower_name),
                            ("SSN", d.ssn))
        y = self._field_row(c, y, ("Date of Birth", d.date_of_birth),
                            ("Marital Status", d.marital_status))
        y = self._field_row(c, y, ("Dependents", d.dependents),
                            ("Years at Current Address", f"{d.years_at_address:.1f}"))
        y = self._field_row(c, y, ("Current Address", d.current_address))
        y = self._field_row(c, y, ("Phone", d.phone), ("Email", d.email))
        if d.credit_score is not None:
            y = self._field_row(c, y, ("Credit Score", d.credit_score))

        self._footer(c)

    def _page_two(self, c, d: LoanApplicationData):
        self._watermark(c)
        y = self._page_header(c)

        y = self._section(c, y, "SECTION 4 - EMPLOYMENT AND INCOME")
        y = self._field_row(c, y, ("Employer Name", d.employer_name),
                            ("Position / Title", d.position))
        y = self._field_row(c, y, ("Employment Type", d.employment_type),
                            ("Years at Current Job", f"{d.years_at_job:.1f}"))
        y = self._field_row(c, y,
                            ("Gross Monthly Income", _money(d.gross_monthly_income)),
                            ("Other Monthly Income", _money(d.other_income)))
        y -= 10

        y = self._section(c, y, "SECTION 5 - ASSETS")
        y = self._field_row(c, y, ("Checking Account", _money(d.checking_balance)),
                            ("Savings Account", _money(d.savings_balance)))
        y = self._field_row(c, y, ("Retirement Account", _money(d.retirement_balance)),
                            ("Down Payment Amount", _money(d.down_payment)))
        y = self._field_row(c, y, ("Down Payment Source", d.down_payment_source))
        y -= 10

        y = self._section(c, y, "SECTION 6 - MONTHLY LIABILITIES")
        y = self._field_row(c, y, ("Car Payment", _money(d.car_payment)),
                            ("Student Loan", _money(d.student_loan)))
        y = self._field_row(c, y, ("Credit Card Minimum", _money(d.credit_card_minimum)),
                            ("Other Monthly Debt", _money(d.other_debt)))
        if d.monthly_housing_payment is not None:
            y = self._field_row(
                c, y,
                ("Monthly Housing Payment", _money(d.monthly_housing_payment)))
        y = self._field_row(c, y, ("Total Monthly Debt", _money(d.total_monthly_debt)))

        dti_pct = d.estimated_dti * 100
        if dti_pct < 43:
            colour = DTI_GREEN
        elif dti_pct <= 50:
            colour = DTI_AMBER
        else:
            colour = DTI_RED
        y = self._field_row(c, y, ("Estimated DTI", f"{dti_pct:.1f}%"),
                            value_color=colour)
        y -= 10

        y = self._section(c, y, "SECTION 7 - DECLARATIONS")
        y = self._field_row(c, y,
                            ("Outstanding Judgments", d.outstanding_judgments),
                            ("Bankruptcy (last 7 years)", d.bankruptcy_7yr))
        y = self._field_row(c, y,
                            ("Foreclosure (last 7 years)", d.foreclosure_7yr),
                            ("Delinquent on Federal Debt", d.federal_debt_delinquent))

        # ── Signature block ──
        sig_y = 120
        c.setFillColorRGB(*VALUE_BLACK)
        c.setFont("Helvetica", 9)
        c.drawString(self.margin, sig_y, "Borrower Signature: _____________________________")
        c.drawString(self.margin, sig_y - 20, "Date: ___________________________")
        c.setFillColorRGB(*LABEL_GREY)
        c.setFont("Helvetica", 7.5)
        c.drawString(self.margin, sig_y - 38,
                     "By signing, borrower certifies information is true and complete.")

        self._footer(c)

    def render(self, d: LoanApplicationData, output_path: str) -> str:
        directory = os.path.dirname(os.path.abspath(output_path))
        os.makedirs(directory, exist_ok=True)
        c = canvas.Canvas(output_path, pagesize=letter)
        self._page_one(c, d)
        c.showPage()
        self._page_two(c, d)
        c.showPage()
        c.save()
        return output_path


def generate_loan_application(
    output_path: str,
    seed: int = 42,
    annual_income: float = None,
    loan_amount: float = None,
    property_value: float = None,
    debt_to_income_target: float = None,
    tax_year: int = 2024,
    credit_score: int = None,
    monthly_housing_payment: float = None,
) -> str:
    """
    Generate a loan application PDF.

    When annual_income is provided:
      monthly income matches +/-2%
      Consistent with W-2 generator

    When loan_amount + property_value provided:
      Uses those values directly
      LTV = loan_amount / property_value

    When debt_to_income_target provided:
      Sizes monthly liabilities to hit
      target DTI against monthly income
      Consistent with bank statement generator

    credit_score and monthly_housing_payment are optional underwriting
    extras: the real 1003 carries neither, but PacketWise reads both off the
    application, so they are printed when supplied and omitted when not.

    Returns: output_path
    """
    rng = random.Random(seed)
    data = _build_data(rng, annual_income, loan_amount, property_value,
                       debt_to_income_target, tax_year, credit_score,
                       monthly_housing_payment)
    return LoanApplicationRenderer().render(data, output_path)


def generate_loan_application_batch(
    count: int,
    output_dir: str,
    seed_start: int = 42,
    annual_incomes: list = None,
    loan_amounts: list = None,
    property_values: list = None,
    debt_to_income_targets: list = None,
    tax_year: int = 2024,
    credit_scores: list = None,
    monthly_housing_payments: list = None,
) -> list:
    """
    Generate multiple loan applications.
    Returns list of output paths.
    Naming: loan_app_001.pdf, loan_app_002.pdf

    The list parameters cycle when shorter than `count`, so a single value
    applies to every document.
    """
    os.makedirs(output_dir, exist_ok=True)

    def pick(values, i):
        if not values:
            return None
        return values[i % len(values)]

    paths = []
    for i in range(count):
        path = os.path.join(output_dir, f"loan_app_{i + 1:03d}.pdf")
        paths.append(generate_loan_application(
            output_path=path,
            seed=seed_start + i,
            annual_income=pick(annual_incomes, i),
            loan_amount=pick(loan_amounts, i),
            property_value=pick(property_values, i),
            debt_to_income_target=pick(debt_to_income_targets, i),
            tax_year=tax_year,
            credit_score=pick(credit_scores, i),
            monthly_housing_payment=pick(monthly_housing_payments, i),
        ))
    return paths


if __name__ == "__main__":
    out = generate_loan_application("output/loan_app_demo.pdf", seed=42,
                                    annual_income=87000)
    print(f"Generated: {out}")
