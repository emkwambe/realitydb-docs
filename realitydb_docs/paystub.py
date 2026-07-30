"""
RealityDB Financial Cases — Pay Stub Generator
===============================================
Generates realistic bi-weekly pay stubs
from a BorrowerProfile.

All values derive from the profile:
  Gross pay = annual_gross_income / 26
    (bi-weekly = 26 pay periods per year)
  Federal withholding: exact from profile
  State withholding: exact from profile
  Social Security: 6.2% of gross
  Medicare: 1.45% of gross
  401k: profile.retirement_contrib_rate
  Net pay: gross minus all deductions

YTD amounts are computed from the pay period
number, so at period 26 every YTD column ties
to the matching W-2 box:

  Gross YTD                  = annual_gross_income
  Gross YTD - 401k YTD       = W-2 box 1
  Federal YTD                = W-2 box 2
  Social Security YTD        = W-2 box 4
  Medicare YTD               = W-2 box 6
  State YTD                  = W-2 box 17

FICA is withheld on gross, not on box 1: a
pre-tax 401k deferral is exempt from income tax
but not from Social Security or Medicare.

Usage:
  from realitydb_docs.paystub import PayStubRenderer
  from realitydb_docs.profile import FinancialCaseGenerator

  gen = FinancialCaseGenerator()
  profile = gen.generate(seed=42, annual_income=87000, ...)

  # Most recent pay stub (period 22 of 26)
  PayStubRenderer(profile, pay_period=22).render(
      "output/paystub_recent.pdf"
  )

  # Prior pay stub (period 21 of 26)
  PayStubRenderer(profile, pay_period=21).render(
      "output/paystub_prior.pdf"
  )
"""

import os
import random
from datetime import date, timedelta

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

from realitydb_docs.profile import (
    BorrowerProfile,
    FinancialCaseGenerator,
    SS_WAGE_BASE,
    SS_RATE,
    MEDICARE_RATE,
)


# ── Layout constants ─────────────────────────────────────

PAGE_W, PAGE_H = letter   # 612 × 792 points
MARGIN = 0.65 * inch

# Colors
COLOR_HEADER_BG   = colors.HexColor("#1a3a6b")
COLOR_HEADER_TEXT = colors.white
COLOR_SECTION_BG  = colors.HexColor("#e8edf4")
COLOR_BORDER      = colors.HexColor("#cbd5e1")
COLOR_LABEL       = colors.HexColor("#6b7280")
COLOR_VALUE       = colors.HexColor("#111827")
COLOR_TOTAL_BG    = colors.HexColor("#1a3a6b")
COLOR_TOTAL_TEXT  = colors.white
COLOR_NET_BG      = colors.HexColor("#166534")
COLOR_NET_TEXT    = colors.white
COLOR_WATERMARK   = colors.HexColor("#d1d5db")
COLOR_ROW_SHADE   = colors.HexColor("#f1f5f9")

# Column geometry for the earnings/deductions table.
#
# Money columns are RIGHT-aligned and the header shares the value's right
# edge — the same rule the bank statement settled on in Sprint 5, because a
# left-aligned header over right-aligned figures is what reads as
# misalignment. Both edges are inside CONTENT_RIGHT: an earlier draft placed
# the YTD column at `COL_W_YTD + PAGE_W - MARGIN` = 619pt, which is off the
# right edge of a 612pt page, so the whole YTD column was clipped away.
CONTENT_LEFT  = MARGIN
CONTENT_RIGHT = PAGE_W - MARGIN            # 565.2
CONTENT_W     = CONTENT_RIGHT - CONTENT_LEFT
COL_DESC_X       = CONTENT_LEFT
COL_CURR_RIGHT   = CONTENT_RIGHT - 1.15 * inch   # 482.4
COL_YTD_RIGHT    = CONTENT_RIGHT                 # 565.2

# Vertical rhythm. Label/value baselines are stepped by more than the leading
# of the larger of the two fonts, so glyph boxes never intersect.
INFO_ROW_PITCH   = 22      # label-to-next-label
INFO_LABEL_DY    = 15      # first label below box top
INFO_VALUE_DY    = 11      # value below its own label
INFO_BOX_PAD     = 8       # padding under the last value

TOTAL_PERIODS = 26   # bi-weekly pay periods per year


def _draw_watermark(c: canvas.Canvas) -> None:
    """Diagonal SYNTHETIC watermark on every page."""
    c.saveState()
    c.setFont("Helvetica-Bold", 36)
    c.setFillColor(COLOR_WATERMARK)
    try:
        c.setFillAlpha(0.35)
    except AttributeError:      # very old reportlab
        pass
    c.translate(PAGE_W / 2, PAGE_H / 2)
    c.rotate(45)
    c.drawCentredString(0, 0, "SYNTHETIC — NOT VALID")
    c.restoreState()


def _info_box_height(n_rows: int) -> float:
    """Height needed to contain n label/value pairs."""
    return (
        INFO_LABEL_DY
        + (n_rows - 1) * INFO_ROW_PITCH
        + INFO_VALUE_DY
        + INFO_BOX_PAD
    )


def _draw_info_box(
    c: canvas.Canvas,
    x: float,
    y_top: float,
    width: float,
    height: float,
    pairs: list,
) -> None:
    """Draw a rounded panel of LABEL / value pairs."""
    c.setFillColor(COLOR_SECTION_BG)
    c.roundRect(x, y_top - height, width, height, 4, fill=1, stroke=0)
    for i, (label, value) in enumerate(pairs):
        ly = y_top - INFO_LABEL_DY - i * INFO_ROW_PITCH
        c.setFillColor(COLOR_LABEL)
        c.setFont("Helvetica", 7)
        c.drawString(x + 8, ly, label)
        c.setFillColor(COLOR_VALUE)
        c.setFont("Helvetica-Bold", 8.5)
        c.drawString(x + 8, ly - INFO_VALUE_DY, str(value))


def _draw_header(
    c: canvas.Canvas,
    profile: BorrowerProfile,
    pay_period: int,
    period_start: date,
    period_end: date,
    pay_date: date,
) -> float:
    """
    Draw company header and pay stub identification.
    Returns y position after header.
    """
    y = PAGE_H - MARGIN

    # ── Company banner ───────────────────────────────────
    banner_h = 0.6 * inch
    c.setFillColor(COLOR_HEADER_BG)
    c.rect(
        MARGIN, y - banner_h,
        CONTENT_W, banner_h,
        fill=1, stroke=0
    )
    c.setFillColor(COLOR_HEADER_TEXT)
    c.setFont("Helvetica-Bold", 13)
    c.drawString(
        MARGIN + 8,
        y - banner_h * 0.38,
        profile.employer_name.upper()
    )
    c.setFont("Helvetica", 8)
    c.drawString(
        MARGIN + 8,
        y - banner_h * 0.72,
        f"EIN: {profile.employer_ein}"
    )

    # PAY STUB label top right
    c.setFont("Helvetica-Bold", 10)
    c.drawRightString(
        CONTENT_RIGHT - 8,
        y - banner_h * 0.38,
        "PAY STUB"
    )
    c.setFont("Helvetica", 8)
    c.drawRightString(
        CONTENT_RIGHT - 8,
        y - banner_h * 0.72,
        f"Period {pay_period} of {TOTAL_PERIODS}"
    )

    y -= banner_h + 12

    # ── Employee and pay info panels ──────────────────────
    # Height is derived from the row count, not hardcoded: at 1.05in the last
    # two pairs fell outside the panel they were supposed to sit in.
    box_h = _info_box_height(5)
    mid = PAGE_W / 2
    left_w = mid - MARGIN - 6
    right_w = CONTENT_RIGHT - mid - 6

    emp_id = f"EMP-{profile.seed % 90000 + 10000}"
    ssn_masked = f"***-**-{profile.ssn.split('-')[-1]}"

    _draw_info_box(c, MARGIN, y, left_w, box_h, [
        ("EMPLOYEE NAME",   profile.full_name),
        ("EMPLOYEE ID",     emp_id),
        ("SSN",             ssn_masked),
        ("DEPARTMENT",      profile.job_title),
        ("EMPLOYMENT TYPE", profile.employment_type),
    ])

    _draw_info_box(c, mid + 6, y, right_w, box_h, [
        ("PAY PERIOD START", period_start.strftime("%B %d, %Y")),
        ("PAY PERIOD END",   period_end.strftime("%B %d, %Y")),
        ("PAY DATE",         pay_date.strftime("%B %d, %Y")),
        ("PAY FREQUENCY",    "Bi-Weekly"),
        ("TAX YEAR",         str(profile.tax_year)),
    ])

    return y - box_h - 16


def _draw_table_header(
    c: canvas.Canvas, y: float
) -> float:
    """Draw earnings/deductions table column headers."""
    hdr_h = 18
    c.setFillColor(COLOR_HEADER_BG)
    c.rect(
        MARGIN, y - hdr_h,
        CONTENT_W, hdr_h,
        fill=1, stroke=0
    )
    c.setFillColor(COLOR_HEADER_TEXT)
    c.setFont("Helvetica-Bold", 7.5)
    c.drawString(COL_DESC_X + 4, y - 12, "DESCRIPTION")
    c.drawRightString(COL_CURR_RIGHT, y - 12, "CURRENT ($)")
    c.drawRightString(COL_YTD_RIGHT - 4, y - 12, "YTD ($)")
    return y - hdr_h


def _draw_row(
    c: canvas.Canvas,
    y: float,
    label: str,
    current: float,
    ytd: float,
    shade: bool = False,
    bold: bool = False,
    label_indent: float = 4,
) -> float:
    """Draw one earnings or deduction row."""
    row_h = 16
    if shade:
        c.setFillColor(COLOR_ROW_SHADE)
        c.rect(
            MARGIN, y - row_h,
            CONTENT_W, row_h,
            fill=1, stroke=0
        )
    font = "Helvetica-Bold" if bold else "Helvetica"
    c.setFont(font, 8)
    c.setFillColor(COLOR_VALUE)
    c.drawString(
        COL_DESC_X + label_indent, y - 11, label
    )
    c.drawRightString(COL_CURR_RIGHT, y - 11, f"{current:,.2f}")
    c.drawRightString(COL_YTD_RIGHT - 4, y - 11, f"{ytd:,.2f}")
    # Light separator
    c.setStrokeColor(COLOR_BORDER)
    c.setLineWidth(0.3)
    c.line(MARGIN, y - row_h, CONTENT_RIGHT, y - row_h)
    return y - row_h


def _draw_section_label(
    c: canvas.Canvas, y: float, title: str
) -> float:
    """Draw a section divider label."""
    sec_h = 14
    c.setFillColor(COLOR_SECTION_BG)
    c.rect(
        MARGIN, y - sec_h,
        CONTENT_W, sec_h,
        fill=1, stroke=0
    )
    c.setFont("Helvetica-Bold", 7.5)
    c.setFillColor(COLOR_HEADER_BG)
    c.drawString(MARGIN + 4, y - 10, title)
    return y - sec_h


def _draw_total_row(
    c: canvas.Canvas,
    y: float,
    label: str,
    current: float,
    ytd: float,
    bg_color=None,
    text_color=None,
) -> float:
    """Draw a bold total row with background."""
    row_h = 20
    bg = bg_color or COLOR_TOTAL_BG
    tc = text_color or COLOR_TOTAL_TEXT
    c.setFillColor(bg)
    c.rect(
        MARGIN, y - row_h,
        CONTENT_W, row_h,
        fill=1, stroke=0
    )
    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(tc)
    c.drawString(MARGIN + 4, y - 13, label)
    c.drawRightString(COL_CURR_RIGHT, y - 13, f"{current:,.2f}")
    c.drawRightString(COL_YTD_RIGHT - 4, y - 13, f"{ytd:,.2f}")
    return y - row_h


def _draw_footer(
    c: canvas.Canvas,
    profile: BorrowerProfile,
) -> None:
    """Draw footer with legal notice."""
    y = MARGIN * 0.6
    c.setStrokeColor(COLOR_BORDER)
    c.setLineWidth(0.5)
    c.line(MARGIN, y + 10, CONTENT_RIGHT, y + 10)
    c.setFont("Helvetica", 6.5)
    c.setFillColor(COLOR_LABEL)
    c.drawCentredString(
        PAGE_W / 2, y + 2,
        "© 2026 Mpingo Systems LLC | "
        "RealityDB Synthetic Documents | "
        "For testing and development only | "
        "SYNTHETIC — NOT VALID"
    )


class PayStubRenderer:
    """
    Renders a bi-weekly pay stub from a BorrowerProfile.

    Pay period numbers run 1–26 (bi-weekly).
    Period 26 ends December 31 of the tax year.
    Period 22 ends approximately November 5.
    Period 21 ends approximately October 22.

    YTD amounts are computed from the pay period
    number so that at period 26 each YTD column
    ties to the matching W-2 box — see the module
    docstring for the full set of identities.
    """

    def __init__(
        self,
        profile: BorrowerProfile,
        pay_period: int = 22,
    ):
        if not 1 <= pay_period <= TOTAL_PERIODS:
            raise ValueError(
                f"pay_period must be 1-{TOTAL_PERIODS}, "
                f"got {pay_period}"
            )
        self.profile = profile
        self.pay_period = pay_period
        self._compute_amounts()
        self._compute_dates()

    def _compute_amounts(self) -> None:
        """Compute all monetary amounts from profile."""
        p = self.profile

        # Gross pay per period (bi-weekly)
        self.gross_per_period = (
            p.annual_gross_income / TOTAL_PERIODS
        )

        # Income tax withholding is on box 1 (post-deferral) wages.
        self.fed_tax = (
            p.w2_box1_wages
            * p.federal_withholding_rate
            / TOTAL_PERIODS
        )
        self.state_tax = (
            p.w2_box1_wages
            * p.state_withholding_rate
            / TOTAL_PERIODS
        )

        # FICA is on gross — a 401k deferral is exempt from income tax but
        # not from Social Security or Medicare.
        self.ss_wages = min(p.annual_gross_income, SS_WAGE_BASE)
        self.ss_tax = self.ss_wages * SS_RATE / TOTAL_PERIODS
        self.medicare_tax = (
            p.annual_gross_income * MEDICARE_RATE / TOTAL_PERIODS
        )
        self.retirement = (
            self.gross_per_period
            * p.retirement_contrib_rate
        )

        self.total_deductions = (
            self.fed_tax
            + self.state_tax
            + self.ss_tax
            + self.medicare_tax
            + self.retirement
        )
        self.net_pay = (
            self.gross_per_period - self.total_deductions
        )

        # YTD = current × pay_period number
        pp = self.pay_period
        self.gross_ytd       = self.gross_per_period * pp
        self.fed_tax_ytd     = self.fed_tax * pp
        self.state_tax_ytd   = self.state_tax * pp
        self.ss_tax_ytd      = self.ss_tax * pp
        self.medicare_ytd    = self.medicare_tax * pp
        self.retirement_ytd  = self.retirement * pp
        self.deductions_ytd  = self.total_deductions * pp
        self.net_ytd         = self.net_pay * pp

        # Taxable YTD is the figure that ties to W-2 box 1.
        self.taxable_ytd = self.gross_ytd - self.retirement_ytd

    def _compute_dates(self) -> None:
        """Compute pay period start, end, and pay date."""
        # Period 26 ends December 31
        year_end = date(self.profile.tax_year, 12, 31)
        period_days = 14

        # End date of this period
        periods_from_end = TOTAL_PERIODS - self.pay_period
        end = year_end - timedelta(
            days=periods_from_end * period_days
        )
        start = end - timedelta(days=period_days - 1)
        pay_date = end + timedelta(days=3)

        self.period_start = start
        self.period_end = end
        self.pay_date = pay_date

    def render(self, output_path: str) -> str:
        """Render pay stub PDF. Returns output_path."""
        os.makedirs(
            os.path.dirname(os.path.abspath(output_path)),
            exist_ok=True
        )

        c = canvas.Canvas(output_path, pagesize=letter)

        _draw_watermark(c)

        y = _draw_header(
            c,
            self.profile,
            self.pay_period,
            self.period_start,
            self.period_end,
            self.pay_date,
        )

        # ── Earnings section ─────────────────────────────
        y = _draw_section_label(c, y, "EARNINGS")
        y = _draw_table_header(c, y)

        y = _draw_row(
            c, y,
            "Regular Pay",
            self.gross_per_period,
            self.gross_ytd,
            shade=False,
            label_indent=12,
        )

        y = _draw_total_row(
            c, y,
            "GROSS PAY",
            self.gross_per_period,
            self.gross_ytd,
        )

        y -= 8

        # ── Deductions section ───────────────────────────
        y = _draw_section_label(c, y, "DEDUCTIONS")
        y = _draw_table_header(c, y)

        rows = [
            ("Federal Income Tax",    self.fed_tax,      self.fed_tax_ytd),
            (f"{self.profile.state} State Income Tax",
                                      self.state_tax,    self.state_tax_ytd),
            ("Social Security Tax",   self.ss_tax,       self.ss_tax_ytd),
            ("Medicare Tax",          self.medicare_tax,  self.medicare_ytd),
        ]
        if self.profile.retirement_contrib_rate > 0:
            rows.append((
                f"401(k) "
                f"({self.profile.retirement_contrib_rate:.0%})",
                self.retirement,
                self.retirement_ytd,
            ))

        for i, (label, curr, ytd) in enumerate(rows):
            y = _draw_row(
                c, y, label, curr, ytd,
                shade=(i % 2 == 1),
                label_indent=12,
            )

        y = _draw_total_row(
            c, y,
            "TOTAL DEDUCTIONS",
            self.total_deductions,
            self.deductions_ytd,
        )

        y -= 12

        # ── Net pay ──────────────────────────────────────
        y = _draw_total_row(
            c, y,
            "NET PAY",
            self.net_pay,
            self.net_ytd,
            bg_color=COLOR_NET_BG,
            text_color=COLOR_NET_TEXT,
        )

        y -= 16

        # ── Taxable wages note (ties the stub to the W-2) ─
        c.setFont("Helvetica", 7.5)
        c.setFillColor(COLOR_LABEL)
        c.drawString(
            MARGIN + 4, y - 10,
            "Taxable wages YTD (gross less pre-tax deferrals): "
            f"${self.taxable_ytd:,.2f}"
        )
        y -= 22

        # ── Leave / accruals (cosmetic) ──────────────────
        y = _draw_section_label(c, y, "LEAVE BALANCES")
        rng = random.Random(self.profile.seed * 67)
        vac_accrued = round(rng.uniform(40, 160), 1)
        sick_accrued = round(rng.uniform(24, 80), 1)

        c.setFont("Helvetica", 8)
        c.setFillColor(COLOR_VALUE)
        c.drawString(
            MARGIN + 4, y - 12,
            f"Vacation: {vac_accrued} hrs available"
        )
        c.drawString(
            PAGE_W / 2 + 4, y - 12,
            f"Sick: {sick_accrued} hrs available"
        )
        y -= 24

        # ── Direct deposit notice ────────────────────────
        c.setFont("Helvetica-Oblique", 7.5)
        c.setFillColor(COLOR_LABEL)
        c.drawString(
            MARGIN + 4, y - 10,
            "Direct deposit to account ending "
            f"****{(self.profile.seed % 9000) + 1000}"
        )

        _draw_footer(c, self.profile)

        c.save()
        return output_path


# ── Batch function ────────────────────────────────────────

def generate_paystub_batch(
    count: int,
    output_dir: str,
    seed_start: int = 42,
    annual_incomes: list = None,
    pay_periods: tuple = (21, 22),
) -> list:
    """
    Generate pay stubs for multiple borrowers.

    Each borrower gets len(pay_periods) stubs.
    Default: periods 21 and 22 (two most recent).

    Returns: list of (paystub_path, profile) tuples.
    """
    os.makedirs(output_dir, exist_ok=True)
    gen = FinancialCaseGenerator()
    results = []

    for i in range(count):
        seed = seed_start + i
        income = (
            annual_incomes[i % len(annual_incomes)]
            if annual_incomes
            else random.Random(seed * 71).uniform(
                35000, 180000
            )
        )
        profile = gen.generate(
            seed=seed,
            annual_income=income,
            loan_amount=320000,
            property_value=420000,
        )

        for pp in pay_periods:
            renderer = PayStubRenderer(profile, pp)
            filename = f"paystub_{i+1:03d}_period{pp:02d}.pdf"
            path = os.path.join(output_dir, filename)
            renderer.render(path)
            results.append((path, profile))
            print(
                f"  Generated: {filename} | "
                f"{profile.full_name} | "
                f"Period {pp} | "
                f"Net: ${renderer.net_pay:,.2f}"
            )

    return results


if __name__ == "__main__":
    generate_paystub_batch(count=3, output_dir="output")
