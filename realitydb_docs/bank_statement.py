"""RealityDB Bank Statement Renderer using ReportLab.

Since Sprint 5 a statement is a VIEW of a BorrowerProfile. The account
holder, the employer behind the payroll deposit, the recurring debt amounts
and the ending balance all come from the profile, so the statement describes
the same borrower — with the same income and the same obligations — as the
W-2 and the loan application in the same packet.

  from realitydb_docs.profile import FinancialCaseGenerator
  from realitydb_docs.bank_statement import BankStatementRenderer

  profile = FinancialCaseGenerator().generate(seed=42, annual_income=87000,
                                              loan_amount=320000,
                                              property_value=420000)
  BankStatementRenderer(profile, month=10).render("output/bank_oct.pdf")

Recurring debits carry the profile's EXACT monthly amounts, so a downstream
DTI computed off the statement reconciles with the DTI printed on the 1003.
The beginning balance is derived so the final running balance equals
profile.checking_balance exactly — the statement reconciles with the assets
declared on the application.

The pre-Sprint-5 independent generator (_build_statement_data +
BankStatementStyleRenderer) is preserved for callers that build a statement
from explicit values, but it does not participate in profile consistency and
should not be wired into new packet generation.
"""
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
import calendar
import random
import os

from realitydb_docs.profile import (
    BorrowerProfile,
    FinancialCaseGenerator,
)

# ─── Style templates ────────────────────────────────────────────────
# Each style is a complete visual identity: header colour, bank name,
# typeface family and layout density.
STYLES: Dict[str, Dict[str, Any]] = {
    "corporate": {
        "bank_name": "First National Bank",
        "header_rgb": (0x1a / 255, 0x3a / 255, 0x6b / 255),   # navy #1a3a6b
        "accent_rgb": (0x1a / 255, 0x3a / 255, 0x6b / 255),
        "body_font": "Helvetica",
        "bold_font": "Helvetica-Bold",
        "header_height": 88,
        "row_height": 14,
        "zebra": True,
        "colour_amounts": False,
        "big_balance": False,
        "membership": "Member FDIC",
        "address": "1200 Commerce Street, Suite 400, Dallas, TX 75201",
    },
    "regional": {
        "bank_name": "Community Bank & Trust",
        "header_rgb": (0x2d / 255, 0x6a / 255, 0x4f / 255),   # green #2d6a4f
        "accent_rgb": (0x2d / 255, 0x6a / 255, 0x4f / 255),
        "body_font": "Times-Roman",
        "bold_font": "Times-Bold",
        "header_height": 74,
        "row_height": 12,
        "zebra": True,
        "colour_amounts": False,
        "big_balance": False,
        "membership": "Member NCUA",
        "address": "87 Main Street, Burlington, VT 05401",
    },
    "digital": {
        "bank_name": "Apex Digital Bank",
        "header_rgb": (0x1a / 255, 0x1a / 255, 0x2e / 255),   # dark #1a1a2e
        "accent_rgb": (0x1a / 255, 0x1a / 255, 0x2e / 255),
        "body_font": "Helvetica",
        "bold_font": "Helvetica-Bold",
        "header_height": 96,
        "row_height": 15,
        "zebra": False,
        "colour_amounts": True,
        "big_balance": True,
        "membership": "Member FDIC",
        "address": "One Market Plaza, San Francisco, CA 94105",
    },
}

CREDIT_RGB = (0.02, 0.55, 0.24)   # green
DEBIT_RGB = (0.72, 0.13, 0.13)    # red

# ─── Column geometry (Sprint 5: alignment fix) ──────────────────────
#
# Before Sprint 5 the header labels were all drawn left-aligned at
# `column_left + 4` while the three money values were drawn RIGHT-aligned at
# `column_right - 6`. Header and value therefore sat at opposite ends of the
# same column and the table read as misaligned on every statement.
#
# These constants are now the single source of truth for both the header row
# and the data rows. Money columns share a right edge between header and
# value; text columns share a left edge. Alignment no longer depends on the
# content of either row.
COL_DATE_X        = 40
COL_DESC_X        = 110
COL_DEBIT_X       = 360
COL_CREDIT_X      = 430
COL_BALANCE_X     = 500

# Column widths for header labels
COL_DATE_W        = 65
COL_DESC_W        = 245
COL_DEBIT_W       = 65
COL_CREDIT_W      = 65
COL_BALANCE_W     = 72    # 70 in the plan; 72 closes the table on the
                          # right margin (612 - 40), so the header band
                          # spans margin to margin.

TABLE_LEFT = COL_DATE_X
TABLE_RIGHT = COL_BALANCE_X + COL_BALANCE_W
TABLE_W = TABLE_RIGHT - TABLE_LEFT
MARGIN = COL_DATE_X

# Legacy alias. The pre-Sprint-5 renderer derived column positions by
# accumulating these widths from self.margin.
COL_WIDTHS = [COL_DATE_W, COL_DESC_W, COL_DEBIT_W, COL_CREDIT_W, COL_BALANCE_W]

FIRST_NAMES = ["James", "Mary", "Robert", "Patricia", "John", "Jennifer",
               "Michael", "Linda", "David", "Barbara", "Susan", "Daniel"]
LAST_NAMES = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia",
              "Miller", "Davis", "Rodriguez", "Martinez", "Wilson", "Anderson"]
STREETS = ["Oak Avenue", "Maple Street", "Cedar Lane", "Pine Ridge Road",
           "Elm Court", "Sycamore Drive", "Birch Hollow", "Willow Way"]
CITIES = [("Austin", "TX", "78701"), ("Columbus", "OH", "43215"),
          ("Raleigh", "NC", "27601"), ("Boise", "ID", "83702"),
          ("Madison", "WI", "53703"), ("Tucson", "AZ", "85701")]
EMPLOYERS = ["ACME CORP", "TECHSTART INC", "METROHEALTH", "GLOBAL LOGISTICS",
             "SUMMIT EDU GROUP", "NORTHWIND TRADING"]

# ─── Data model ─────────────────────────────────────────────────────


@dataclass
class Transaction:
    date: str
    description: str
    amount: float
    type: str          # "debit" or "credit"
    balance: float = 0.0


@dataclass
class MonthStatement:
    month: int
    year: int
    period_label: str
    beginning_balance: float
    ending_balance: float
    total_deposits: float
    total_withdrawals: float
    transactions: List[Transaction] = field(default_factory=list)


@dataclass
class BankStatementData:
    bank_name: str
    style: str
    account_holder: str
    account_number: str        # ****XXXX
    routing_number: str
    address: str
    bank_address: str
    membership: str
    months: List[MonthStatement] = field(default_factory=list)


def _money(value: float) -> float:
    return round(value, 2)


# ─── Legacy independent generation (pre-Sprint 5) ────────────────────
#
# DEPRECATED. These build a statement from values drawn independently of any
# BorrowerProfile, which is exactly the defect Sprint 5 fixes: a statement
# built this way names a different person than the W-2 beside it. Retained
# only so callers that pass explicit values keep working.

def _build_month(rng: random.Random, year: int, month: int,
                 beginning_balance: float,
                 monthly_income: float,
                 employer: str,
                 debt_to_income_target: Optional[float] = None) -> MonthStatement:
    """Build one month of transactions with a non-negative running balance."""
    days_in_month = calendar.monthrange(year, month)[1]
    entries: List[Transaction] = []

    # ── Income deposit: 1st or 15th ──
    deposit_day = rng.choice([1, 15])
    deposit_amount = _money(monthly_income * rng.uniform(0.97, 1.03))
    deposit_desc = rng.choice([
        f"DIRECT DEP {employer}",
        "ACH CREDIT PAYROLL",
        "DIRECT DEPOSIT",
    ])
    entries.append(Transaction(
        date=f"{month:02d}/{deposit_day:02d}/{year}",
        description=deposit_desc,
        amount=deposit_amount,
        type="credit",
    ))

    # ── Recurring debits: pick 4-7 ──
    recurring_pool = [
        ("housing", rng.choice(["RENT PAYMENT",
                                f"MORTGAGE PMT {rng.choice(['WELLSCO', 'PENNYMAC', 'FREEDOM MTG'])}"]),
         rng.uniform(800, 3000)),
        ("auto", "AUTO LOAN PMT", rng.uniform(200, 650)),
        ("utilities", rng.choice(["ELECTRIC BILL", "GAS UTILITY"]), rng.uniform(80, 250)),
        ("phone", "MOBILE PHONE", rng.uniform(45, 150)),
        ("internet", "INTERNET SVC", rng.uniform(40, 100)),
        ("subscription", rng.choice(["STREAMING SVC", "SUBSCRIPTION"]), rng.uniform(10, 50)),
        ("insurance", rng.choice(["AUTO INSURANCE", "RENTERS INS"]), rng.uniform(100, 400)),
        ("student", "STUDENT LOAN PMT", rng.uniform(200, 800)),
    ]
    if debt_to_income_target is not None:
        target_total = monthly_income * debt_to_income_target
        loan_items = [
            ("auto", "AUTO LOAN PMT", target_total * 0.60),
            ("student", "STUDENT LOAN PMT", target_total * 0.40),
        ]
        non_loan_pool = [item for item in recurring_pool
                         if item[0] not in ("auto", "student")]
        chosen = loan_items + rng.sample(non_loan_pool,
                                         rng.randint(2, len(non_loan_pool)))
    else:
        n_recurring = rng.randint(4, 7)
        chosen = rng.sample(recurring_pool, n_recurring)

    for _, desc, amount in chosen:
        day = rng.randint(2, min(28, days_in_month))
        entries.append(Transaction(
            date=f"{month:02d}/{day:02d}/{year}",
            description=desc,
            amount=_money(amount),
            type="debit",
        ))

    # ── Irregular debits: 5-15 ──
    irregular_pool = [
        ("GROCERY STORE", 30, 200),
        ("GAS STATION", 30, 80),
        ("RESTAURANT", 15, 80),
        ("ATM WITHDRAWAL", 100, 300),
        ("ONLINE PURCHASE", 20, 200),
    ]
    for _ in range(rng.randint(5, 15)):
        desc, low, high = rng.choice(irregular_pool)
        day = rng.randint(1, days_in_month)
        entries.append(Transaction(
            date=f"{month:02d}/{day:02d}/{year}",
            description=desc,
            amount=_money(rng.uniform(low, high)),
            type="debit",
        ))

    return _reconcile(entries, beginning_balance, year, month)


def _reconcile(entries: List[Transaction], beginning_balance: float,
               year: int, month: int) -> MonthStatement:
    """Order by day, compute the running balance, drop overdrafts."""
    entries.sort(key=lambda t: int(t.date.split("/")[1]))

    balance = beginning_balance
    kept: List[Transaction] = []
    deposits = 0.0
    withdrawals = 0.0
    for tx in entries:
        if tx.type == "credit":
            balance += tx.amount
            deposits += tx.amount
        else:
            # A transaction that would overdraw the account is skipped
            # rather than rendered — the statement never goes negative.
            if balance - tx.amount < 0:
                continue
            balance -= tx.amount
            withdrawals += tx.amount
        tx.balance = _money(balance)
        kept.append(tx)

    days_in_month = calendar.monthrange(year, month)[1]
    month_name = calendar.month_name[month]
    return MonthStatement(
        month=month,
        year=year,
        period_label=f"{month_name} 1 - {month_name} {days_in_month}, {year}",
        beginning_balance=_money(beginning_balance),
        ending_balance=_money(balance),
        total_deposits=_money(deposits),
        total_withdrawals=_money(withdrawals),
        transactions=kept,
    )


def _build_statement_data(rng: random.Random, style: str,
                          annual_income: Optional[float],
                          year: int, month_1: int, month_2: int,
                          debt_to_income_target: Optional[float] = None) -> BankStatementData:
    """DEPRECATED — see the module docstring. Independent of BorrowerProfile."""
    cfg = STYLES[style]

    holder = f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"
    city, state, zipcode = rng.choice(CITIES)
    address = f"{rng.randint(100, 9899)} {rng.choice(STREETS)}, {city}, {state} {zipcode}"
    account_number = f"****{rng.randint(1000, 9999)}"
    routing_number = f"{rng.choice('01')}{rng.randint(10000000, 99999999)}"
    employer = rng.choice(EMPLOYERS)

    if annual_income:
        monthly_income = annual_income / 12.0
    else:
        monthly_income = rng.uniform(3000, 12000)

    beginning = _money(monthly_income * rng.uniform(1.5, 3.0))

    m1 = _build_month(rng, year, month_1, beginning, monthly_income, employer,
                      debt_to_income_target)
    m2 = _build_month(rng, year, month_2, m1.ending_balance, monthly_income, employer,
                      debt_to_income_target)

    return BankStatementData(
        bank_name=cfg["bank_name"],
        style=style,
        account_holder=holder,
        account_number=account_number,
        routing_number=routing_number,
        address=address,
        bank_address=cfg["address"],
        membership=cfg["membership"],
        months=[m1, m2],
    )


# ─── Rendering ──────────────────────────────────────────────────────


class BankStatementStyleRenderer:
    """Renders a bank statement PDF from an explicit BankStatementData record.

    This is the low-level renderer, one page per month. Named
    BankStatementRenderer before Sprint 5; that name now belongs to the
    profile-driven renderer below.
    """

    def __init__(self, style: str = "corporate"):
        if style not in STYLES:
            raise ValueError(f"Unknown style '{style}'. Choose from {list(STYLES)}.")
        self.style = style
        self.cfg = STYLES[style]
        self.width, self.height = letter
        self.margin = MARGIN

    # -- helpers ----------------------------------------------------

    def _watermark(self, c):
        """Diagonal SYNTHETIC marking on every page."""
        c.saveState()
        c.setFillColorRGB(0.5, 0.5, 0.5)
        try:
            c.setFillAlpha(0.20)
        except AttributeError:      # very old reportlab
            c.setFillColorRGB(0.85, 0.85, 0.85)
        c.translate(self.width / 2, self.height / 2)
        c.rotate(45)
        c.setFont("Helvetica-Bold", 36)
        c.drawCentredString(0, 0, "SYNTHETIC - NOT VALID")
        c.restoreState()

    def _fit(self, c, text, width, font, size):
        """Truncate text so it cannot run into the next column."""
        if c.stringWidth(text, font, size) <= width:
            return text
        while text and c.stringWidth(text + "…", font, size) > width:
            text = text[:-1]
        return text + "…"

    def _header(self, c, data: BankStatementData, month: MonthStatement):
        cfg = self.cfg
        h = cfg["header_height"]
        top = self.height - h

        c.setFillColorRGB(*cfg["header_rgb"])
        c.rect(0, top, self.width, h, stroke=0, fill=1)

        c.setFillColorRGB(1, 1, 1)
        c.setFont(cfg["bold_font"], 20)
        c.drawString(self.margin, top + h - 34, data.bank_name)
        c.setFont(cfg["body_font"], 10)
        c.drawString(self.margin, top + h - 52, "ACCOUNT STATEMENT")
        c.setFont(cfg["body_font"], 9)
        c.drawRightString(TABLE_RIGHT, top + h - 34,
                          f"Statement period: {month.period_label}")

        if cfg["big_balance"]:
            c.setFont(cfg["bold_font"], 22)
            c.drawRightString(TABLE_RIGHT, top + h - 66,
                              f"${month.ending_balance:,.2f}")
            c.setFont(cfg["body_font"], 7)
            c.drawRightString(TABLE_RIGHT, top + h - 78, "CURRENT BALANCE")

        return top

    def _account_block(self, c, data: BankStatementData, month: MonthStatement, top: float):
        """Two-column account / balance summary below the header.

        Each label and its value are drawn in a single string so text
        extraction keeps them on one line.
        """
        cfg = self.cfg
        y = top - 24
        c.setFillColorRGB(0, 0, 0)
        c.setFont(cfg["body_font"], 9)

        left = [
            f"Account Holder: {data.account_holder}",
            f"Account Number: {data.account_number}",
            f"Routing Number: {data.routing_number}",
            f"Address: {data.address}",
        ]
        right = [
            f"Beginning Balance: ${month.beginning_balance:,.2f}",
            f"Total Deposits: ${month.total_deposits:,.2f}",
            f"Total Withdrawals: ${month.total_withdrawals:,.2f}",
            f"Ending Balance: ${month.ending_balance:,.2f}",
        ]

        for i, line in enumerate(left):
            c.drawString(self.margin, y - i * 13,
                         self._fit(c, line, TABLE_W / 2 - 12, cfg["body_font"], 9))
        for i, line in enumerate(right):
            c.drawString(self.width / 2 + 10, y - i * 13, line)

        return y - max(len(left), len(right)) * 13 - 14

    def _table_header(self, c, y: float):
        """Header row. Text columns share a LEFT edge with their values,
        money columns share a RIGHT edge — see the column constants."""
        cfg = self.cfg

        c.setFillColorRGB(*cfg["accent_rgb"])
        c.rect(TABLE_LEFT, y - 4, TABLE_W, 16, stroke=0, fill=1)
        c.setFillColorRGB(1, 1, 1)
        c.setFont(cfg["bold_font"], 8)

        c.drawString(COL_DATE_X + 4, y, "Date")
        c.drawString(COL_DESC_X, y, "Description")
        c.drawRightString(COL_DEBIT_X + COL_DEBIT_W, y, "Debit")
        c.drawRightString(COL_CREDIT_X + COL_CREDIT_W, y, "Credit")
        c.drawRightString(COL_BALANCE_X + COL_BALANCE_W - 4, y, "Balance")

        c.setFillColorRGB(0, 0, 0)
        return y - 18

    def _row(self, c, tx: Transaction, y: float, shade: bool):
        cfg = self.cfg

        if cfg["zebra"] and shade:
            c.setFillColorRGB(0.965, 0.965, 0.965)
            c.rect(TABLE_LEFT, y - 3, TABLE_W, cfg["row_height"], stroke=0, fill=1)

        c.setFillColorRGB(0, 0, 0)
        c.setFont(cfg["body_font"], 8)
        c.drawString(COL_DATE_X + 4, y, tx.date)
        c.drawString(COL_DESC_X, y,
                     self._fit(c, tx.description, COL_DESC_W - 8,
                               cfg["body_font"], 8))

        if tx.type == "credit":
            c.setFillColorRGB(*CREDIT_RGB)
            c.drawRightString(COL_CREDIT_X + COL_CREDIT_W, y, f"${tx.amount:,.2f}")
        else:
            if cfg["colour_amounts"]:
                c.setFillColorRGB(*DEBIT_RGB)
            else:
                c.setFillColorRGB(0, 0, 0)
            c.drawRightString(COL_DEBIT_X + COL_DEBIT_W, y, f"${tx.amount:,.2f}")

        c.setFillColorRGB(0, 0, 0)
        c.drawRightString(COL_BALANCE_X + COL_BALANCE_W - 4, y, f"${tx.balance:,.2f}")

    def _footer(self, c, data: BankStatementData, page_no: int, total_pages: int):
        cfg = self.cfg
        c.setStrokeColorRGB(0.75, 0.75, 0.75)
        c.setLineWidth(0.5)
        c.line(self.margin, 52, TABLE_RIGHT, 52)

        c.setFillColorRGB(0.35, 0.35, 0.35)
        c.setFont(cfg["body_font"], 7)
        c.drawString(self.margin, 40, data.bank_address)
        c.drawString(self.margin, 30, data.membership)
        c.drawRightString(TABLE_RIGHT, 30, f"Page {page_no} of {total_pages}")
        c.setFillColorRGB(0, 0, 0)

    def render(self, data: BankStatementData, output_path: str) -> str:
        parent = os.path.dirname(os.path.abspath(output_path))
        os.makedirs(parent, exist_ok=True)
        c = canvas.Canvas(output_path, pagesize=letter)

        total_pages = len(data.months)
        for page_no, month in enumerate(data.months, start=1):
            self._watermark(c)
            top = self._header(c, data, month)
            y = self._account_block(c, data, month, top)
            y = self._table_header(c, y)

            for i, tx in enumerate(month.transactions):
                if y < 90:      # leave room for the closing note and footer
                    break
                self._row(c, tx, y, shade=(i % 2 == 1))
                y -= self.cfg["row_height"]

            c.setFont(self.cfg["body_font"], 7)
            c.setFillColorRGB(0.35, 0.35, 0.35)
            c.drawString(self.margin, max(y - 6, 62),
                         f"This statement covers the period {month.period_label}")
            c.setFillColorRGB(0, 0, 0)

            self._footer(c, data, page_no, total_pages)
            c.showPage()

        c.save()
        return output_path


def _render_bank_statement_pdf(
    output_path: str,
    account_holder: str,
    account_last4: str,
    routing: str,
    bank_name: str,
    statement_month: int,
    statement_year: int,
    transactions: list,
    beginning_balance: float,
    ending_balance: float,
    style: str = "corporate",
    account_address: str = "",
) -> str:
    """Field-level entry point.

    `transactions` is a list of {date, description, credit, debit} dicts.
    Running balances are computed here from `beginning_balance`, so the last
    row always agrees with the summary block.
    """
    if style not in STYLES:
        raise ValueError(f"Unknown style '{style}'. Choose from {list(STYLES)}.")

    entries = [
        Transaction(
            date=t["date"],
            description=t["description"],
            amount=_money(t["credit"] if t.get("credit") else t["debit"]),
            type="credit" if t.get("credit") else "debit",
        )
        for t in transactions
    ]
    month = _reconcile(entries, beginning_balance, statement_year, statement_month)

    data = BankStatementData(
        bank_name=bank_name,
        style=style,
        account_holder=account_holder,
        account_number=f"****{account_last4}",
        routing_number=routing,
        address=account_address,
        bank_address=STYLES[style]["address"],
        membership=STYLES[style]["membership"],
        months=[month],
    )
    return BankStatementStyleRenderer(style=style).render(data, output_path)


class BankStatementRenderer:
    """
    Renders bank statements from a BorrowerProfile.

    Deposits: profile.monthly_gross_income ± 3%
    Recurring debts: exactly profile.monthly_X values
    Ending balance: profile.checking_balance
    Account holder: profile.full_name (SAME as W-2)
    Payroll description: profile.employer_payroll_description
    """

    def __init__(
        self,
        profile: BorrowerProfile,
        month: int = None,
        style: str = None,
    ):
        self.profile = profile
        self.month = month or profile.statement_month_1
        if not 1 <= self.month <= 12:
            raise ValueError(f"Month out of range: {self.month}")
        self.style = style or "corporate"
        if self.style not in STYLES:
            raise ValueError(
                f"Unknown style '{self.style}'. Choose from {list(STYLES)}."
            )
        self.rng = random.Random(
            profile.seed * 43 + self.month
        )

    def render(self, output_path: str) -> str:
        """Render one month bank statement PDF."""

        # Build transactions from profile values
        transactions = self._build_transactions()

        _render_bank_statement_pdf(
            output_path=output_path,
            account_holder=self.profile.full_name,
            account_last4=str(
                (self.profile.seed % 9000) + 1000
            ),
            routing=self._generate_routing(),
            bank_name=self._bank_name(),
            statement_month=self.month,
            statement_year=self.profile.tax_year,
            transactions=transactions,
            beginning_balance=self._beginning_balance(transactions),
            ending_balance=self.profile.checking_balance,
            style=self.style,
            account_address=self.profile.full_address,
        )
        return output_path

    def _generate_routing(self) -> str:
        r = random.Random(self.profile.seed * 11)
        return f"0{r.randint(10000000, 99999999)}"

    def _bank_name(self) -> str:
        return STYLES[self.style]["bank_name"]

    def _beginning_balance(self, transactions: list) -> float:
        """Beginning = ending - (deposits - withdrawals).

        Derived rather than jittered, so the final running balance lands
        exactly on profile.checking_balance and the statement reconciles
        with the assets declared on the loan application.
        """
        net = sum(
            (t["credit"] or 0.0) - (t["debit"] or 0.0)
            for t in transactions
        )
        return _money(max(self.profile.checking_balance - net, 0.0))

    def _build_transactions(self) -> list:
        """
        Build transaction list from profile values.

        Recurring debts use EXACT profile values.
        Payroll uses profile.monthly_gross_income ± 3%.
        Variable spending is randomized.
        """
        transactions = []
        month = self.month
        year = self.profile.tax_year

        days_in_month = calendar.monthrange(year, month)[1]

        # ── Payroll deposit (1st or 15th) ────────────────
        payroll_day = self.rng.choice([1, 15])
        payroll_var = self.rng.uniform(0.97, 1.03)
        payroll_amount = (
            self.profile.monthly_gross_income * payroll_var
        )
        transactions.append({
            "date": f"{month:02d}/{payroll_day:02d}/{year}",
            "description": self.profile.employer_payroll_description,
            "credit": round(payroll_amount, 2),
            "debit": None,
        })

        # ── Recurring debts (EXACT from profile) ─────────
        # Days are drawn from a profile-scoped generator so the same
        # obligation falls on the same day of every month.
        recurring_day_rng = random.Random(
            self.profile.seed * 59
        )

        if self.profile.monthly_rent_mortgage > 0:
            day = recurring_day_rng.randint(1, 5)
            transactions.append({
                "date": f"{month:02d}/{day:02d}/{year}",
                "description": "RENT PAYMENT",
                "credit": None,
                "debit": round(
                    self.profile.monthly_rent_mortgage, 2
                ),
            })

        if self.profile.monthly_car_payment > 0:
            day = recurring_day_rng.randint(6, 12)
            transactions.append({
                "date": f"{month:02d}/{day:02d}/{year}",
                "description": "AUTO LOAN PMT",
                "credit": None,
                "debit": round(
                    self.profile.monthly_car_payment, 2
                ),
            })

        if self.profile.monthly_student_loan > 0:
            day = recurring_day_rng.randint(13, 18)
            transactions.append({
                "date": f"{month:02d}/{day:02d}/{year}",
                "description": "STUDENT LOAN PMT",
                "credit": None,
                "debit": round(
                    self.profile.monthly_student_loan, 2
                ),
            })

        if self.profile.monthly_credit_card_min > 0:
            day = recurring_day_rng.randint(19, 25)
            transactions.append({
                "date": f"{month:02d}/{day:02d}/{year}",
                "description": "CREDIT CARD MIN PMT",
                "credit": None,
                "debit": round(
                    self.profile.monthly_credit_card_min, 2
                ),
            })

        # ── Variable spending ─────────────────────────────
        num_variable = self.rng.randint(8, 16)
        variable_types = [
            ("GROCERY STORE", 30, 180),
            ("GAS STATION", 30, 75),
            ("RESTAURANT", 12, 65),
            ("ATM WITHDRAWAL", 60, 300),
            ("ONLINE PURCHASE", 15, 180),
        ]

        for _ in range(num_variable):
            desc, low, high = self.rng.choice(variable_types)
            amount = round(self.rng.uniform(low, high), 2)
            day = self.rng.randint(1, days_in_month)
            transactions.append({
                "date": f"{month:02d}/{day:02d}/{year}",
                "description": desc,
                "credit": None,
                "debit": amount,
            })

        # Sort by date
        transactions.sort(
            key=lambda t: t["date"]
        )

        return transactions


# ─── Public API ─────────────────────────────────────────────────────

def generate_synthetic_bank_statement(
    output_path: str,
    seed: int = 42,
    style: str = "corporate",
    annual_income: float = None,
    statement_year: int = 2024,
    statement_month_1: int = 10,
    statement_month_2: int = 11,
    debt_to_income_target: float = None,
) -> str:
    """
    Generate a bank statement PDF for one borrower.

    Backward-compatible entry point. Now builds a BorrowerProfile and
    renders statement_month_1 from it, so the statement's holder, employer,
    income and obligations belong to one coherent borrower.

    Args:
      output_path: where to save the PDF
      seed: random seed (deterministic)
      style: corporate|regional|digital
      annual_income: target annual income; monthly deposits are
        annual_income/12 (+/-3%). Drawn from $35,000-$180,000 if omitted.
      statement_year: year for the statement
      statement_month_1: the month rendered (1-12)
      statement_month_2: carried onto the profile for callers that render a
        second month with BankStatementRenderer(profile, month=...)
      debt_to_income_target: DTI the profile's liabilities are sized to.
        Defaults to 0.36.

    Returns:
      output_path (the saved file)
    """
    for m in (statement_month_1, statement_month_2):
        if not 1 <= m <= 12:
            raise ValueError(f"Month out of range: {m}")

    gen = FinancialCaseGenerator()
    income = annual_income or (
        random.Random(seed * 71).uniform(35000, 180000)
    )
    profile = gen.generate(
        seed=seed,
        annual_income=income,
        loan_amount=320000,
        property_value=420000,
        dti_target=0.36 if debt_to_income_target is None
        else debt_to_income_target,
        tax_year=statement_year,
        statement_month_1=statement_month_1,
        statement_month_2=statement_month_2,
    )
    renderer = BankStatementRenderer(
        profile, month=statement_month_1, style=style
    )
    return renderer.render(output_path)


def generate_synthetic_bank_statement_batch(
    count: int,
    output_dir: str,
    seed_start: int = 42,
    annual_incomes: list = None,
    style: str = None,
    debt_to_income_target: float = None,
) -> list:
    """
    Generate multiple bank statements.

    Args:
      count: number to generate
      output_dir: directory for output files
      seed_start: first seed (increments per doc)
      annual_incomes: list of target incomes (one per statement, for W-2 matching)
      style: if None, randomly varies style across corporate/regional/digital
      debt_to_income_target: DTI the profile's liabilities are sized to;
        see generate_synthetic_bank_statement()

    Returns:
      list of output file paths
    """
    os.makedirs(output_dir, exist_ok=True)
    style_cycle = ["corporate", "regional", "digital"]
    paths = []

    for i in range(count):
        seed = seed_start + i
        this_style = style if style else style_cycle[i % len(style_cycle)]

        income = None
        if annual_incomes:
            income = annual_incomes[i % len(annual_incomes)]

        filename = f"bank_stmt_{i + 1:03d}_{this_style}.pdf"
        path = os.path.join(output_dir, filename)
        generate_synthetic_bank_statement(
            output_path=path,
            seed=seed,
            style=this_style,
            annual_income=income,
            debt_to_income_target=debt_to_income_target,
        )
        paths.append(path)
        income_note = f" | target ${income:,.0f}" if income else ""
        print(f"  Generated: {filename} | {this_style}{income_note}")

    return paths


if __name__ == "__main__":
    generate_synthetic_bank_statement_batch(count=3, output_dir="output")
