"""
RealityDB Financial Cases — BorrowerProfile
============================================
Single source of truth for all documents
in a synthetic underwriting case.

Every document (W-2, bank statement,
loan application, pay stub) is a VIEW
of this profile — not independently
generated.

This guarantees:
  Same name across all documents
  Same employer across all documents
  Income consistent across all documents
  Debts match declared liabilities
  Assets match bank ending balance
  Dates are chronologically consistent

Usage:
  from realitydb_docs.profile import (
      BorrowerProfile,
      FinancialCaseGenerator,
  )

  gen = FinancialCaseGenerator()
  profile = gen.generate(
      seed=42,
      annual_income=87000,
      loan_amount=320000,
      property_value=420000,
      dti_target=0.36,
      scenario="approved",
  )

  # All renderers receive the same profile
  W2Renderer(profile).render("output/w2.pdf")
  BankStatementRenderer(profile).render("output/bank.pdf")
  LoanAppRenderer(profile).render("output/app.pdf")
"""

import random
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from realitydb_docs.config import cfg


# ─── Name pools (Census-weighted) ────────────────────────

FIRST_NAMES = [
    "James", "Mary", "Robert", "Patricia", "John",
    "Jennifer", "Michael", "Linda", "William", "Barbara",
    "David", "Elizabeth", "Richard", "Susan", "Joseph",
    "Jessica", "Thomas", "Sarah", "Charles", "Karen",
    "Christopher", "Lisa", "Daniel", "Nancy", "Matthew",
    "Betty", "Anthony", "Margaret", "Mark", "Sandra",
    "Donald", "Ashley", "Steven", "Dorothy", "Paul",
    "Kimberly", "Andrew", "Emily", "Kenneth", "Donna",
    "George", "Michelle", "Joshua", "Carol", "Kevin",
    "Amanda", "Brian", "Melissa", "Edward", "Deborah",
    "Ronald", "Stephanie", "Timothy", "Rebecca", "Jason",
    "Sharon", "Jeffrey", "Laura", "Ryan", "Cynthia",
    "Jacob", "Kathleen", "Gary", "Amy", "Nicholas",
    "Angela", "Eric", "Shirley", "Jonathan", "Anna",
    "Stephen", "Brenda", "Larry", "Pamela", "Justin",
    "Emma", "Scott", "Nicole", "Brandon", "Helen",
    "Benjamin", "Samantha", "Samuel", "Katherine",
    "Raymond", "Christine", "Gregory", "Debra", "Frank",
    "Rachel", "Alexander", "Carolyn", "Patrick", "Janet",
    "Jack", "Catherine", "Dennis", "Maria", "Jerry",
    "Heather", "Tyler", "Diane", "Aaron", "Julie",
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones",
    "Garcia", "Miller", "Davis", "Rodriguez", "Martinez",
    "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson",
    "Thomas", "Taylor", "Moore", "Jackson", "Martin",
    "Lee", "Perez", "Thompson", "White", "Harris",
    "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson",
    "Walker", "Young", "Allen", "King", "Wright",
    "Scott", "Torres", "Nguyen", "Hill", "Flores",
    "Green", "Adams", "Nelson", "Baker", "Hall",
    "Rivera", "Campbell", "Mitchell", "Carter", "Roberts",
    "Turner", "Phillips", "Evans", "Edwards", "Collins",
    "Stewart", "Morris", "Morales", "Murphy", "Cook",
    "Rogers", "Gutierrez", "Ortiz", "Morgan", "Cooper",
    "Peterson", "Bailey", "Reed", "Kelly", "Howard",
    "Ramos", "Kim", "Cox", "Ward", "Richardson",
    "Watson", "Brooks", "Chavez", "Wood", "James",
    "Bennett", "Gray", "Mendoza", "Ruiz", "Hughes",
    "Price", "Alvarez", "Castillo", "Sanders", "Patel",
    "Myers", "Long", "Ross", "Foster", "Jimenez",
]

EMPLOYERS = [
    "Northwind Traders", "Contoso Corporation",
    "Fabrikam Industries", "Woodgrove Bank",
    "Fourth Coffee", "Adventure Works",
    "Blue Yonder Airlines", "Trey Research",
    "Wide World Importers", "Coho Winery",
    "Alpine Ski House", "Bellows College",
    "City Power and Light", "Consolidated Messenger",
    "Datum Corporation", "Graphic Design Institute",
    "Humongous Insurance", "Litware Inc",
    "Lucerne Publishing", "Margie Travel",
    "Nod Publishers", "Proseware Inc",
    "School of Fine Art", "Southridge Video",
    "Tailspin Toys", "The Phone Company",
    "Wingtip Toys", "A Datum Corporation",
    "Relecloud", "VanArsdel Ltd",
]

JOB_TITLES = [
    "Senior Analyst", "Project Manager",
    "Software Engineer", "Accountant",
    "Operations Manager", "Sales Representative",
    "HR Specialist", "Financial Analyst",
    "Marketing Coordinator", "Data Analyst",
    "Systems Administrator", "Product Manager",
    "Business Analyst", "Account Manager",
    "Office Manager", "Customer Service Manager",
    "Supply Chain Analyst", "Quality Engineer",
    "Compliance Officer", "Risk Analyst",
]

STREET_NAMES = [
    "Oak", "Maple", "Cedar", "Pine", "Elm",
    "Washington", "Lincoln", "Jefferson", "Madison",
    "Adams", "Park", "Lake", "Hill", "River",
    "Valley", "Summit", "Ridge", "Forest", "Meadow",
    "Spring", "Creek", "Brook", "Mill", "Stone",
]

STREET_TYPES = [
    "Street", "Avenue", "Boulevard", "Drive",
    "Road", "Lane", "Way", "Court", "Place",
    "Circle",
]

CITIES_STATES = [
    ("Nashville", "TN", "37201"),
    ("Charlotte", "NC", "28201"),
    ("Atlanta", "GA", "30301"),
    ("Dallas", "TX", "75201"),
    ("Phoenix", "AZ", "85001"),
    ("Denver", "CO", "80201"),
    ("Columbus", "OH", "43201"),
    ("Indianapolis", "IN", "46201"),
    ("Kansas City", "MO", "64101"),
    ("Memphis", "TN", "38101"),
    ("Louisville", "KY", "40201"),
    ("Baltimore", "MD", "21201"),
    ("Milwaukee", "WI", "53201"),
    ("Albuquerque", "NM", "87101"),
    ("Tucson", "AZ", "85701"),
    ("Fresno", "CA", "93701"),
    ("Sacramento", "CA", "95801"),
    ("Mesa", "AZ", "85201"),
    ("Omaha", "NE", "68101"),
    ("Raleigh", "NC", "27601"),
]

EMAIL_DOMAINS = [
    "gmail.com", "yahoo.com", "outlook.com",
    "hotmail.com", "icloud.com", "aol.com",
]

# Tax constants, sourced from config/financial.yaml. These names are re-exported
# deliberately: w2.py, paystub.py and packet.py all import them from here, so
# sourcing them from config in this one place propagates to every renderer
# without touching any of them.
#
# They are read once at import. Editing financial.yaml and calling cfg.reload()
# does NOT move them — restart the process instead. Annual IRS updates are a
# deploy, not a hot reload.
SS_WAGE_BASE = cfg.ss_wage_base
SS_RATE = cfg.ss_rate
MEDICARE_RATE = cfg.medicare_rate


def _make_rngs(seed: int) -> dict:
    """
    Create independent random generators
    for each field category.

    Uses different prime multipliers so
    fields cannot correlate with each other.
    Demographic proxy correlations are
    structurally prevented.

    Same base seed always produces
    identical outputs (deterministic).
    """
    return {
        "name":      random.Random(seed * 7  + 1),
        "income":    random.Random(seed * 13 + 2),
        "address":   random.Random(seed * 17 + 3),
        "financial": random.Random(seed * 23 + 4),
        "dates":     random.Random(seed * 29 + 5),
        "employer":  random.Random(seed * 31 + 6),
        "misc":      random.Random(seed * 37 + 7),
        "debt":      random.Random(seed * 41 + 8),
    }


@dataclass
class BorrowerProfile:
    """
    The canonical financial model.
    All document renderers receive this object.
    No renderer generates its own identity,
    income, or employer independently.
    """

    # ── Seeds ────────────────────────────────────────────
    seed: int

    # ── Identity (identical across all documents) ────────
    first_name: str
    last_name: str
    ssn: str           # 900-XX-XXXX format
    dob: date          # age 25–65
    phone: str
    email: str

    # ── Address ──────────────────────────────────────────
    street_number: int
    street_name: str
    street_type: str
    city: str
    state: str
    zip_code: str
    years_at_address: int

    # ── Employment ───────────────────────────────────────
    employer_name: str
    employer_ein: str   # XX-XXXXXXX synthetic
    job_title: str
    employment_type: str   # Employed / Self-employed
    years_at_job: float
    employment_start_date: date

    # ── Income model ─────────────────────────────────────
    annual_gross_income: float
    federal_withholding_rate: float
    state_withholding_rate: float
    retirement_contrib_rate: float  # 401k

    # ── Liabilities (monthly) ────────────────────────────
    monthly_rent_mortgage: float
    monthly_car_payment: float
    monthly_student_loan: float
    monthly_credit_card_min: float
    monthly_other_debt: float

    # ── Assets ───────────────────────────────────────────
    checking_balance: float   # matches bank stmt ending
    savings_balance: float
    retirement_balance: float

    # ── Loan request ─────────────────────────────────────
    loan_amount: float
    property_value: float
    loan_purpose: str   # Purchase / Refinance
    loan_type: str      # Conventional / FHA / VA
    amortization_years: int

    # ── Scenario ─────────────────────────────────────────
    expected_decision: str  # approved / flagged / rejected
    tax_year: int
    statement_month_1: int  # October = 10
    statement_month_2: int  # November = 11

    # ── Optional underwriting extras ─────────────────────
    # The real 1003 carries no credit score, but PacketWise
    # reads one off the application and treats a low score
    # as critical on its own. Carried on the profile so a
    # scenario's expected decision stays reproducible.
    credit_score: Optional[int] = None

    # ── Computed properties ──────────────────────────────

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    @property
    def street_address(self) -> str:
        return (
            f"{self.street_number} {self.street_name} "
            f"{self.street_type}"
        )

    @property
    def full_address(self) -> str:
        return (
            f"{self.street_address}, "
            f"{self.city}, {self.state} {self.zip_code}"
        )

    @property
    def city_state_zip(self) -> str:
        return f"{self.city}, {self.state} {self.zip_code}"

    @property
    def monthly_gross_income(self) -> float:
        return self.annual_gross_income / 12

    @property
    def w2_box1_wages(self) -> float:
        """Wages after pre-tax 401k deduction."""
        return self.annual_gross_income * (
            1 - self.retirement_contrib_rate
        )

    @property
    def w2_box2_federal_withheld(self) -> float:
        return self.w2_box1_wages * self.federal_withholding_rate

    @property
    def w2_box17_state_withheld(self) -> float:
        return self.w2_box1_wages * self.state_withholding_rate

    # FICA is computed on GROSS, not on Box 1. A pre-tax 401k deferral is
    # exempt from income tax but not from Social Security or Medicare, so on a
    # real W-2 boxes 3 and 5 exceed box 1 by the deferral. Computing FICA on
    # box 1 understated it and — since a pay stub necessarily withholds FICA
    # on the gross it pays — made the stub and the W-2 irreconcilable.

    @property
    def w2_box3_ss_wages(self) -> float:
        return min(self.annual_gross_income, SS_WAGE_BASE)

    @property
    def w2_box4_ss_withheld(self) -> float:
        return self.w2_box3_ss_wages * SS_RATE

    @property
    def w2_box5_medicare_wages(self) -> float:
        return self.annual_gross_income

    @property
    def w2_box6_medicare_withheld(self) -> float:
        return self.w2_box5_medicare_wages * MEDICARE_RATE

    @property
    def total_monthly_debt(self) -> float:
        return (
            self.monthly_rent_mortgage
            + self.monthly_car_payment
            + self.monthly_student_loan
            + self.monthly_credit_card_min
            + self.monthly_other_debt
        )

    @property
    def dti_ratio(self) -> float:
        if self.monthly_gross_income == 0:
            return 0.0
        return self.total_monthly_debt / self.monthly_gross_income

    @property
    def ltv_ratio(self) -> float:
        if self.property_value == 0:
            return 0.0
        return self.loan_amount / self.property_value

    @property
    def down_payment(self) -> float:
        return self.property_value - self.loan_amount

    @property
    def employer_payroll_description(self) -> str:
        """
        How the employer appears in bank deposits.
        Same employer — different format.
        E.g. "Northwind Traders" →
             "DIRECT DEP NORTHWIND TR"
        """
        name = self.employer_name.upper()
        words = name.split()
        short = " ".join(words[:2])[:16]
        return f"DIRECT DEP {short}"


class FinancialCaseGenerator:
    """
    Generates a BorrowerProfile from a seed
    and scenario parameters.

    All financial attributes are derived from
    the annual_income and dti_target parameters
    to ensure cross-document consistency.
    """

    def generate(
        self,
        seed: int,
        annual_income: float,
        loan_amount: float,
        property_value: float,
        dti_target: float = 0.36,
        scenario: str = "approved",
        tax_year: Optional[int] = None,
        statement_month_1: int = 10,
        statement_month_2: int = 11,
        credit_score: Optional[int] = None,
    ) -> BorrowerProfile:
        """
        Generate a complete BorrowerProfile.

        All documents rendered from this profile
        will describe the same person with
        consistent financial attributes.
        """
        # Resolved here rather than as a default argument so a change to
        # financial.yaml's tax_year is picked up without re-importing.
        if tax_year is None:
            tax_year = cfg.tax_year

        rngs = _make_rngs(seed)

        # ── Identity ─────────────────────────────────────
        first = rngs["name"].choice(FIRST_NAMES)
        last = rngs["name"].choice(LAST_NAMES)

        # SSN: always 900-XX-XXXX (never issued by the SSA)
        ssn_cfg = cfg.ssn_config
        ssn_mid = rngs["misc"].randint(
            ssn_cfg["middle_min"], ssn_cfg["middle_max"]
        )
        ssn_end = rngs["misc"].randint(
            ssn_cfg["suffix_min"], ssn_cfg["suffix_max"]
        )
        ssn = f"{ssn_cfg['prefix']}-{ssn_mid:02d}-{ssn_end}"

        # DOB
        age_min, age_max = cfg.age_range
        age = rngs["misc"].randint(age_min, age_max)
        today = date(tax_year, 11, 15)
        dob = today.replace(year=today.year - age)

        phone_area = rngs["misc"].randint(200, 999)
        phone_mid = rngs["misc"].randint(200, 999)
        phone_end = rngs["misc"].randint(1000, 9999)
        phone = f"({phone_area}) {phone_mid}-{phone_end}"

        domain = rngs["misc"].choice(EMAIL_DOMAINS)
        email = (
            f"{first.lower()}.{last.lower()}"
            f"{rngs['misc'].randint(1, 99)}"
            f"@{domain}"
        )

        # ── Address ──────────────────────────────────────
        street_num = rngs["address"].randint(100, 9999)
        street_name = rngs["address"].choice(STREET_NAMES)
        street_type = rngs["address"].choice(STREET_TYPES)
        city, state, zip_code = rngs["address"].choice(
            CITIES_STATES
        )
        addr_min, addr_max = cfg.years_at_address_range
        years_at_addr = rngs["address"].randint(addr_min, addr_max)

        # ── Employment ───────────────────────────────────
        employer = rngs["employer"].choice(EMPLOYERS)
        title = rngs["employer"].choice(JOB_TITLES)
        emp_types, emp_weights = cfg.employment_types
        emp_type = rngs["employer"].choices(
            emp_types, weights=emp_weights
        )[0]
        job_min, job_max = cfg.years_at_job_range
        years_at_job = round(
            rngs["employer"].uniform(job_min, job_max), 1
        )
        job_months = int(years_at_job * 12)
        emp_start = today - timedelta(days=job_months * 30)

        ein_prefix = rngs["employer"].randint(10, 99)
        ein_suffix = rngs["employer"].randint(1000000, 9999999)
        employer_ein = f"{ein_prefix}-{ein_suffix}"

        # ── Income ───────────────────────────────────────
        # Add a small variation so documents look natural
        # while staying consistent
        iv = cfg.income_variation
        income_var = rngs["income"].uniform(1 - iv, 1 + iv)
        actual_income = annual_income * income_var

        fed_min, fed_max = cfg.withholding_federal_range
        federal_rate = rngs["income"].uniform(fed_min, fed_max)
        state_min, state_max = cfg.withholding_state_range
        state_rate = rngs["income"].uniform(state_min, state_max)
        # Deferral caps at 8%, not 10%. W-2 box 1 is gross minus the pre-tax
        # deferral, so the deferral rate IS the variance a lender sees between
        # the gross income stated on the 1003 and the wages documented on the
        # W-2. A 10% rate sits exactly on the usual 10% income-variance
        # tolerance, where rounding on the printed form decides whether the
        # check fires. 8% leaves the comparison unambiguous. The cap lives in
        # config/financial.yaml as retirement.cap.
        retirement_rate = rngs["income"].choice(
            cfg.capped_retirement_options
        )

        # ── Liabilities sized to DTI target ──────────────
        monthly = actual_income / 12

        # Housing uses the 28% rule as anchor
        housing_min, housing_max = cfg.housing_ratio_range
        housing = monthly * rngs["debt"].uniform(
            housing_min, housing_max
        )

        # Small credit card and other minimums
        cc_lo, cc_hi = cfg.credit_card_range
        cc_min = rngs["debt"].uniform(cc_lo, cc_hi)
        other_lo, other_hi = cfg.other_debt_range
        other = rngs["debt"].uniform(other_lo, other_hi)

        # Remaining debt budget to hit DTI target.
        # Every obligation counts against the target, including the credit
        # card minimum and the other-debt line — drawing those outside the
        # budget would push realised DTI past dti_target by 1.5-3.5% and make
        # a scenario sitting near an underwriting threshold land on the wrong
        # side of it.
        remaining_budget = (
            (dti_target * monthly) - housing - cc_min - other
        )
        remaining_budget = max(remaining_budget, 0)

        # Split remaining between the two instalment loans
        car_share, student_share = cfg.debt_shares
        car = remaining_budget * car_share
        student = remaining_budget * student_share

        # ── Assets ───────────────────────────────────────
        # Checking is a multiple of monthly income and becomes the bank
        # statement's ending balance.
        ch_min, ch_max = cfg.checking_months_range
        checking = monthly * rngs["financial"].uniform(ch_min, ch_max)
        sv_min, sv_max = cfg.savings_months_range
        savings = monthly * rngs["financial"].uniform(sv_min, sv_max)
        rb_min, rb_max = cfg.retirement_balance_range
        retirement_bal = (
            actual_income
            * rngs["financial"].uniform(rb_min, rb_max)
        )

        # ── Loan product ─────────────────────────────────
        loan_types, loan_type_weights = cfg.loan_types
        loan_terms, loan_term_weights = cfg.loan_terms

        return BorrowerProfile(
            seed=seed,
            first_name=first,
            last_name=last,
            ssn=ssn,
            dob=dob,
            phone=phone,
            email=email,
            street_number=street_num,
            street_name=street_name,
            street_type=street_type,
            city=city,
            state=state,
            zip_code=zip_code,
            years_at_address=years_at_addr,
            employer_name=employer,
            employer_ein=employer_ein,
            job_title=title,
            employment_type=emp_type,
            years_at_job=years_at_job,
            employment_start_date=emp_start,
            annual_gross_income=actual_income,
            federal_withholding_rate=federal_rate,
            state_withholding_rate=state_rate,
            retirement_contrib_rate=retirement_rate,
            monthly_rent_mortgage=round(housing, 2),
            monthly_car_payment=round(car, 2),
            monthly_student_loan=round(student, 2),
            monthly_credit_card_min=round(cc_min, 2),
            monthly_other_debt=round(other, 2),
            checking_balance=round(checking, 2),
            savings_balance=round(savings, 2),
            retirement_balance=round(retirement_bal, 2),
            loan_amount=loan_amount,
            property_value=property_value,
            loan_purpose="Purchase",
            loan_type=rngs["misc"].choices(
                loan_types, weights=loan_type_weights
            )[0],
            amortization_years=rngs["misc"].choices(
                loan_terms, weights=loan_term_weights
            )[0],
            expected_decision=scenario,
            tax_year=tax_year,
            statement_month_1=statement_month_1,
            statement_month_2=statement_month_2,
            credit_score=credit_score,
        )
