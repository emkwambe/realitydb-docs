"""RealityDB Bank Statement Renderer using ReportLab.

Generates two-month synthetic bank statement PDFs in three bank styles.
Every document is deterministic for a given seed: the same seed always
produces the same borrower, the same transactions and the same balances.

The `annual_income` parameter exists so a statement can be generated to
match a W-2 produced by `w2.generate_synthetic_w2_batch(target_annual_income=...)`,
keeping documented income consistent across a loan packet.
"""
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime
import calendar
import random
import os

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


# ─── Transaction generation ─────────────────────────────────────────

def _money(value: float) -> float:
    return round(value, 2)


def _build_month(rng: random.Random, year: int, month: int,
                 beginning_balance: float,
                 monthly_income: float,
                 employer: str) -> MonthStatement:
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

    # ── Order by day, then compute the running balance ──
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
                          year: int, month_1: int, month_2: int) -> BankStatementData:
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

    m1 = _build_month(rng, year, month_1, beginning, monthly_income, employer)
    m2 = _build_month(rng, year, month_2, m1.ending_balance, monthly_income, employer)

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

# Date | Description | Debit | Credit | Balance
COL_WIDTHS = [60, 220, 80, 80, 90]


class BankStatementRenderer:
    """Renders a two-month bank statement PDF in one of three bank styles."""

    def __init__(self, style: str = "corporate"):
        if style not in STYLES:
            raise ValueError(f"Unknown style '{style}'. Choose from {list(STYLES)}.")
        self.style = style
        self.cfg = STYLES[style]
        self.width, self.height = letter
        self.margin = 45

    # -- helpers ----------------------------------------------------

    def _col_x(self):
        """Left edge of each column."""
        xs, x = [], self.margin
        for w in COL_WIDTHS:
            xs.append(x)
            x += w
        return xs

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
        c.drawRightString(self.width - self.margin, top + h - 34,
                          f"Statement period: {month.period_label}")

        if cfg["big_balance"]:
            c.setFont(cfg["bold_font"], 22)
            c.drawRightString(self.width - self.margin, top + h - 66,
                              f"${month.ending_balance:,.2f}")
            c.setFont(cfg["body_font"], 7)
            c.drawRightString(self.width - self.margin, top + h - 78, "CURRENT BALANCE")

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
        ]
        right = [
            f"Beginning Balance: ${month.beginning_balance:,.2f}",
            f"Total Deposits: ${month.total_deposits:,.2f}",
            f"Total Withdrawals: ${month.total_withdrawals:,.2f}",
            f"Ending Balance: ${month.ending_balance:,.2f}",
        ]

        for i, line in enumerate(left):
            c.drawString(self.margin, y - i * 13, line)
        for i, line in enumerate(right):
            c.drawString(self.width / 2 + 10, y - i * 13, line)

        return y - max(len(left), len(right)) * 13 - 14

    def _table_header(self, c, y: float):
        cfg = self.cfg
        xs = self._col_x()
        table_w = sum(COL_WIDTHS)

        c.setFillColorRGB(*cfg["accent_rgb"])
        c.rect(self.margin, y - 4, table_w, 16, stroke=0, fill=1)
        c.setFillColorRGB(1, 1, 1)
        c.setFont(cfg["bold_font"], 8)
        for x, label in zip(xs, ["Date", "Description", "Debit", "Credit", "Balance"]):
            c.drawString(x + 4, y, label)
        c.setFillColorRGB(0, 0, 0)
        return y - 18

    def _row(self, c, tx: Transaction, y: float, shade: bool):
        cfg = self.cfg
        xs = self._col_x()
        table_w = sum(COL_WIDTHS)

        if cfg["zebra"] and shade:
            c.setFillColorRGB(0.965, 0.965, 0.965)
            c.rect(self.margin, y - 3, table_w, cfg["row_height"], stroke=0, fill=1)

        c.setFillColorRGB(0, 0, 0)
        c.setFont(cfg["body_font"], 8)
        c.drawString(xs[0] + 4, y, tx.date)
        c.drawString(xs[1] + 4, y, tx.description[:34])

        if tx.type == "credit":
            if cfg["colour_amounts"]:
                c.setFillColorRGB(*CREDIT_RGB)
            else:
                c.setFillColorRGB(*CREDIT_RGB)
            c.drawRightString(xs[3] + COL_WIDTHS[3] - 6, y, f"${tx.amount:,.2f}")
        else:
            if cfg["colour_amounts"]:
                c.setFillColorRGB(*DEBIT_RGB)
            else:
                c.setFillColorRGB(0, 0, 0)
            c.drawRightString(xs[2] + COL_WIDTHS[2] - 6, y, f"${tx.amount:,.2f}")

        c.setFillColorRGB(0, 0, 0)
        c.drawRightString(xs[4] + COL_WIDTHS[4] - 6, y, f"${tx.balance:,.2f}")

    def _footer(self, c, data: BankStatementData, page_no: int, total_pages: int):
        cfg = self.cfg
        c.setStrokeColorRGB(0.75, 0.75, 0.75)
        c.setLineWidth(0.5)
        c.line(self.margin, 52, self.width - self.margin, 52)

        c.setFillColorRGB(0.35, 0.35, 0.35)
        c.setFont(cfg["body_font"], 7)
        c.drawString(self.margin, 40, data.bank_address)
        c.drawString(self.margin, 30, data.membership)
        c.drawRightString(self.width - self.margin, 30, f"Page {page_no} of {total_pages}")
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


# ─── Public API ─────────────────────────────────────────────────────

def generate_synthetic_bank_statement(
    output_path: str,
    seed: int = 42,
    style: str = "corporate",
    annual_income: float = None,
    statement_year: int = 2024,
    statement_month_1: int = 10,
    statement_month_2: int = 11,
) -> str:
    """
    Generate a 2-month bank statement PDF.

    Args:
      output_path: where to save the PDF
      seed: random seed (deterministic)
      style: corporate|regional|digital
      annual_income: if provided, monthly deposits will be approximately
        annual_income/12 (+/-5%). This ensures income consistency with the
        W-2 generator.
      statement_year: year for statements
      statement_month_1: first month (1-12)
      statement_month_2: second month (1-12)

    Returns:
      output_path (the saved file)
    """
    if style not in STYLES:
        raise ValueError(f"Unknown style '{style}'. Choose from {list(STYLES)}.")
    for m in (statement_month_1, statement_month_2):
        if not 1 <= m <= 12:
            raise ValueError(f"Month out of range: {m}")

    rng = random.Random(seed)
    data = _build_statement_data(rng, style, annual_income,
                                 statement_year, statement_month_1, statement_month_2)
    renderer = BankStatementRenderer(style=style)
    return renderer.render(data, output_path)


def generate_synthetic_bank_statement_batch(
    count: int,
    output_dir: str,
    seed_start: int = 42,
    annual_incomes: list = None,
    style: str = None,
) -> list:
    """
    Generate multiple bank statements.

    Args:
      count: number to generate
      output_dir: directory for output files
      seed_start: first seed (increments per doc)
      annual_incomes: list of target incomes (one per statement, for W-2 matching)
      style: if None, randomly varies style across corporate/regional/digital

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
        )
        paths.append(path)
        income_note = f" | target ${income:,.0f}" if income else ""
        print(f"  Generated: {filename} | {this_style}{income_note}")

    return paths


if __name__ == "__main__":
    generate_synthetic_bank_statement_batch(count=3, output_dir="output")
