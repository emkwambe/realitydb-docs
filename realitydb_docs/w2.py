"""RealityDB W-2 Renderer using ReportLab.
Generates realistic W-2 wage and tax statement PDFs.

Since Sprint 5 the W-2 is a VIEW of a BorrowerProfile: identity, employer,
wages and withholding all come from the profile, so the W-2 describes the
same person as the bank statement and the loan application in the same
packet. Nothing on this form is generated independently any more.

  from realitydb_docs.profile import FinancialCaseGenerator
  from realitydb_docs.w2 import W2Renderer

  profile = FinancialCaseGenerator().generate(seed=42, annual_income=87000,
                                              loan_amount=320000,
                                              property_value=420000)
  W2Renderer(profile).render("output/w2.pdf")

The pre-Sprint-5 low-level interface (W2Data + W2FormRenderer) is preserved
for callers that build a form field by field.
"""
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from dataclasses import dataclass
from typing import Optional
import random
import os

from realitydb_docs.profile import (
    BorrowerProfile,
    FinancialCaseGenerator,
    SS_WAGE_BASE,
    SS_RATE,
    MEDICARE_RATE,
)

# ─── Layout constants (Sprint 5: text overlap / border fixes) ────────
#
# Three defects were fixed here, all of them geometry rather than data:
#
#   1. The four wage boxes were 145pt wide with 15pt gaps starting at x=50,
#      so the fourth box ran to x=675 — past the 612pt page and well past
#      the form border at x=572. Box 4 and box 17 were clipped off the page.
#      BOX_W/BOX_GAP below are sized so all four boxes close inside
#      CONTENT_RIGHT.
#   2. The employer/employee boxes straddled the horizontal rule under the
#      header, so `_draw_box`'s label was drawn directly on top of the line.
#      The boxes now start BOX_CLEARANCE below the rule.
#   3. Labels sat 10pt below the box top at 7pt type with no stated padding.
#      Padding is now explicit and the label/value baselines are guaranteed
#      at least MIN_LABEL_VALUE_GAP apart.
FORM_BORDER_INSET = 1      # outer border inset from the page margin
CONTENT_LEFT = 50
CONTENT_RIGHT = 562        # form border sits at x=572; 10pt of quiet space
BOX_PADDING_LEFT = 4       # points from left edge
BOX_PADDING_TOP = 2        # points from top edge
BOX_TEXT_CLEARANCE = 3     # text never starts within 3pt of a border
LABEL_FONT_SIZE = 6.5
VALUE_FONT_SIZE = 9
MIN_LABEL_VALUE_GAP = 10   # minimum baseline separation inside a box

BOX_GAP = 10
BOX_W = (CONTENT_RIGHT - CONTENT_LEFT - 3 * BOX_GAP) / 4   # 4 boxes per row
BOX_H = 59                 # was 55; +4pt so label and value never crowd
BOX_CLEARANCE = 11         # gap below the header rule
BLOCK_CLEARANCE = 12       # gap between a text block and the next box row
HEADER_RULE_DY = 80        # header rule at height - 80


@dataclass
class W2Data:
    employer_name: str
    employer_ein: str
    employee_name: str
    employee_ssn: str
    wages_box_1: float
    federal_tax_box_2: float
    ss_wages_box_3: float
    ss_tax_box_4: float
    medicare_wages_box_5: float
    medicare_tax_box_6: float
    state_wages_box_16: Optional[float] = None
    state_tax_box_17: Optional[float] = None
    year: int = 2024
    control_number: Optional[str] = None
    employee_address: Optional[str] = None


class W2FormRenderer:
    """Renders a W-2 form to PDF from an explicit W2Data record.

    This is the low-level renderer. Prefer W2Renderer, which drives it from
    a BorrowerProfile and so keeps the W-2 consistent with the rest of the
    packet. Named W2Renderer before Sprint 5.
    """

    def __init__(self, output_dir: str = "output"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        self.width, self.height = letter  # 612 x 792 pts

    def render(self, data: W2Data, filename: str, add_noise: bool = False):
        """Render a single W-2 PDF."""
        filepath = os.path.join(self.output_dir, filename)
        c = canvas.Canvas(filepath, pagesize=letter)

        # ─── Watermark (drawn first, so it sits under the form) ───
        self._watermark(c)

        # ─── Background / Form Lines ───
        self._draw_form_outline(c)

        # ─── Header ───
        c.setFont("Helvetica-Bold", 14)
        c.drawString(CONTENT_LEFT, self.height - 48,
                     f"{data.year} W-2 Wage and Tax Statement")
        c.setFont("Helvetica", 8)
        # Baselines stepped by more than the leading of the LARGER font on
        # each side. A 14pt title followed 12pt later by an 8pt line leaves
        # the title's descenders inside the next line's glyph box, which
        # reads as overlapping text.
        c.drawString(CONTENT_LEFT, self.height - 64,
                     f"For calendar year {data.year}")
        c.drawString(CONTENT_LEFT, self.height - 75,
                     "Copy A — For Social Security Administration")

        if data.control_number:
            c.drawRightString(CONTENT_RIGHT, self.height - 48,
                              f"Control #: {data.control_number}")

        # ─── Identity blocks ───
        # Both boxes start BOX_CLEARANCE below the header rule so no label
        # is ever drawn on the line.
        id_box_h = 46
        id_box_top = self.height - HEADER_RULE_DY - BOX_CLEARANCE
        id_box_y = id_box_top - id_box_h
        half = (CONTENT_RIGHT - CONTENT_LEFT - BOX_GAP) / 2
        right_x = CONTENT_LEFT + half + BOX_GAP

        # Employer (Box b)
        self._draw_box(c, CONTENT_LEFT, id_box_y, half, id_box_h,
                       "b Employer identification number (EIN)")
        c.setFont("Courier", VALUE_FONT_SIZE)
        c.setFillColorRGB(0, 0, 0)
        c.drawString(CONTENT_LEFT + BOX_PADDING_LEFT,
                     id_box_y + BOX_TEXT_CLEARANCE + 8, data.employer_ein)

        # Employee (Box a)
        self._draw_box(c, right_x, id_box_y, half, id_box_h,
                       "a Employee's social security number")
        c.setFont("Courier", VALUE_FONT_SIZE + 1)
        c.drawString(right_x + BOX_PADDING_LEFT,
                     id_box_y + BOX_TEXT_CLEARANCE + 8, data.employee_ssn)

        # Names and addresses below the boxes
        text_y = id_box_y - 16
        c.setFont("Helvetica", 8)
        c.setFillColorRGB(0.3, 0.3, 0.3)
        c.drawString(CONTENT_LEFT, text_y, "c Employer name and address")
        c.drawString(right_x, text_y, "e/f Employee name and address")

        c.setFillColorRGB(0, 0, 0)
        c.setFont("Helvetica-Bold", VALUE_FONT_SIZE + 1)
        c.drawString(CONTENT_LEFT, text_y - 14, data.employer_name)
        c.drawString(right_x, text_y - 14, data.employee_name)

        if data.employee_address:
            c.setFont("Helvetica", 8)
            c.drawString(right_x, text_y - 26,
                         self._fit(c, data.employee_address, half, "Helvetica", 8))

        # ─── Wage boxes ───
        # The row is positioned by its TOP edge, BLOCK_CLEARANCE below the
        # employee-address baseline. Positioning it by its bottom edge is
        # what let the box-1/box-3 labels land on the employer and employee
        # names — the two share a left edge, so any vertical collision was a
        # visible overlap.
        address_baseline = text_y - 26
        box_row_top = address_baseline - BLOCK_CLEARANCE
        box_y = box_row_top - BOX_H
        self._draw_amount_row(c, box_y, [
            ("1 Wages, tips, other compensation", data.wages_box_1),
            ("2 Federal income tax withheld", data.federal_tax_box_2),
            ("3 Social security wages", data.ss_wages_box_3),
            ("4 Social security tax withheld", data.ss_tax_box_4),
        ])

        box_y2 = box_y - BOX_H - 12
        second = [
            ("5 Medicare wages and tips", data.medicare_wages_box_5),
            ("6 Medicare tax withheld", data.medicare_tax_box_6),
        ]
        if data.state_wages_box_16:
            second.append(("16 State wages, tips, etc.", data.state_wages_box_16))
        if data.state_tax_box_17:
            second.append(("17 State income tax", data.state_tax_box_17))
        self._draw_amount_row(c, box_y2, second)

        # ─── Footer ───
        c.setFont("Helvetica", 7)
        c.setFillColorRGB(0, 0, 0)
        c.drawString(CONTENT_LEFT, 42,
                     "Department of the Treasury — Internal Revenue Service")
        c.drawRightString(CONTENT_RIGHT, 42, f"Form W-2 ({data.year})")

        # ─── Optional: Add subtle noise for realism ───
        if add_noise:
            self._add_scan_noise(c)

        c.save()
        return filepath

    # -- drawing helpers ------------------------------------------------

    def _watermark(self, c):
        """Diagonal SYNTHETIC marking on every page.

        The bank statement and the 1003 have carried this since they were
        written; the W-2 did not, which left the one document in a packet a
        reader was most likely to mistake for genuine without any marking at
        all. Matches the other two renderers exactly.
        """
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

    def _draw_form_outline(self, c):
        """Draw the outer border of the W-2 form, inset from the margin."""
        c.setStrokeColorRGB(0, 0, 0)
        c.setLineWidth(1.5)
        inset = FORM_BORDER_INSET
        c.rect(40 + inset, 30 + inset,
               self.width - 80 - 2 * inset, self.height - 60 - 2 * inset,
               stroke=1, fill=0)
        c.setLineWidth(0.5)
        c.line(40 + inset, self.height - HEADER_RULE_DY,
               self.width - 40 - inset, self.height - HEADER_RULE_DY)

    def _draw_amount_row(self, c, y, items):
        """Draw up to four labelled money boxes across one row."""
        for idx, (label, value) in enumerate(items):
            x = CONTENT_LEFT + idx * (BOX_W + BOX_GAP)
            self._draw_box(c, x, y, BOX_W, BOX_H, label)
            c.setFillColorRGB(0, 0, 0)
            c.setFont("Courier", VALUE_FONT_SIZE)
            c.drawString(x + BOX_PADDING_LEFT, y + 18, f"{value:,.2f}")

    def _draw_box(self, c, x, y, w, h, label):
        """Draw a labelled box.

        The label baseline is placed BOX_PADDING_TOP below the box top, and
        the caller draws its value at y+18 — MIN_LABEL_VALUE_GAP or more
        below the label on every box size used here.
        """
        c.setStrokeColorRGB(0, 0, 0)
        c.setLineWidth(0.5)
        c.rect(x, y, w, h, stroke=1, fill=0)
        label_baseline = y + h - LABEL_FONT_SIZE - BOX_PADDING_TOP
        assert label_baseline - (y + 18) >= MIN_LABEL_VALUE_GAP, (
            f"box too short for label+value: h={h}"
        )
        c.setFont("Helvetica", LABEL_FONT_SIZE)
        c.setFillColorRGB(0.3, 0.3, 0.3)
        c.drawString(x + BOX_PADDING_LEFT, label_baseline,
                     self._fit(c, label, w, "Helvetica", LABEL_FONT_SIZE))
        c.setFillColorRGB(0, 0, 0)

    def _fit(self, c, text, width, font, size):
        """Truncate text so it cannot run into the box border."""
        budget = width - BOX_PADDING_LEFT - BOX_TEXT_CLEARANCE
        if c.stringWidth(text, font, size) <= budget:
            return text
        while text and c.stringWidth(text + "…", font, size) > budget:
            text = text[:-1]
        return text + "…"

    def _add_scan_noise(self, c):
        """Add subtle scan artifacts (light gray dots)."""
        c.setStrokeColorRGB(0.85, 0.85, 0.85)
        c.setLineWidth(0.2)
        for _ in range(200):
            x = random.randint(0, int(self.width))
            y = random.randint(0, int(self.height))
            c.line(x, y, x + 1, y)


# Pre-Sprint-5 name. Kept so existing imports of the low-level renderer
# under its old name do not break; W2Renderer itself is now profile-driven.
_LegacyW2Renderer = W2FormRenderer


def _render_w2_pdf(
    output_path: str,
    employee_name: str,
    employee_ssn: str,
    employee_address: str,
    employer_name: str,
    employer_ein: str,
    tax_year: int,
    wages: float,
    federal_withheld: float,
    ss_wages: float,
    ss_withheld: float,
    medicare_wages: float,
    medicare_withheld: float,
    state_wages: Optional[float] = None,
    state_withheld: Optional[float] = None,
    control_number: Optional[str] = None,
    add_noise: bool = False,
) -> str:
    """Field-level entry point for drawing one W-2 to `output_path`."""
    directory = os.path.dirname(os.path.abspath(output_path))
    os.makedirs(directory, exist_ok=True)

    data = W2Data(
        employer_name=employer_name,
        employer_ein=employer_ein,
        employee_name=employee_name,
        employee_ssn=employee_ssn,
        employee_address=employee_address,
        wages_box_1=round(wages, 2),
        federal_tax_box_2=round(federal_withheld, 2),
        ss_wages_box_3=round(ss_wages, 2),
        ss_tax_box_4=round(ss_withheld, 2),
        medicare_wages_box_5=round(medicare_wages, 2),
        medicare_tax_box_6=round(medicare_withheld, 2),
        state_wages_box_16=None if state_wages is None else round(state_wages, 2),
        state_tax_box_17=None if state_withheld is None else round(state_withheld, 2),
        year=tax_year,
        control_number=control_number,
    )
    renderer = W2FormRenderer(output_dir=directory)
    renderer.render(data, os.path.basename(output_path), add_noise=add_noise)
    return output_path


class W2Renderer:
    """
    Renders a W-2 from a BorrowerProfile.
    All values come from the profile —
    nothing is generated independently.
    """

    def __init__(
        self,
        profile: BorrowerProfile,
        year_offset: int = 0,
    ):
        self.profile = profile
        self.tax_year = profile.tax_year + year_offset

        # For prior year W-2 slightly different wages
        if year_offset != 0:
            rng = random.Random(
                profile.seed * 53 + abs(year_offset)
            )
            self.annual_wages = (
                profile.w2_box1_wages
                * rng.uniform(0.92, 1.08)
            )
        else:
            self.annual_wages = profile.w2_box1_wages

    def render(self, output_path: str, add_noise: bool = False) -> str:
        """Render W-2 PDF. Returns output_path."""
        p = self.profile
        # Recover the gross the wages were deferred out of, so FICA is
        # computed on gross the way a payroll system does. For year_offset=0
        # this returns profile.annual_gross_income exactly.
        rate = p.retirement_contrib_rate
        gross = (
            self.annual_wages / (1 - rate) if rate < 1
            else self.annual_wages
        )
        ss_wages = min(gross, SS_WAGE_BASE)
        _render_w2_pdf(
            output_path=output_path,
            employee_name=p.full_name,
            employee_ssn=p.ssn,
            employee_address=p.full_address,
            employer_name=p.employer_name,
            employer_ein=p.employer_ein,
            tax_year=self.tax_year,
            wages=self.annual_wages,
            federal_withheld=(
                self.annual_wages * p.federal_withholding_rate
            ),
            ss_wages=ss_wages,
            ss_withheld=ss_wages * SS_RATE,
            medicare_wages=gross,
            medicare_withheld=gross * MEDICARE_RATE,
            state_wages=self.annual_wages,
            state_withheld=(
                self.annual_wages * p.state_withholding_rate
            ),
            control_number=f"{(p.seed * 7919) % 900000 + 100000}",
            add_noise=add_noise,
        )
        return output_path


def generate_synthetic_w2_batch(
    count: int = 10,
    output_dir: str = "output",
    seed: int = 42,
    tax_year: int = 2024,
    target_annual_income: float = None,
) -> list:
    """Generate a batch of synthetic W-2s.

    Backward-compatible batch function. Now uses BorrowerProfile internally,
    so each W-2's name, employer and wages belong to one coherent borrower
    rather than being drawn from independent pools.

    Args:
      count: number of W-2s to generate
      output_dir: directory for output files
      seed: base random seed (deterministic; incremented per document)
      tax_year: calendar year printed on the form
      target_annual_income: if provided, every profile is built against this
        income so the W-2 agrees with the rest of its packet. If omitted,
        income is drawn from $35,000-$180,000 per document.
    """
    os.makedirs(output_dir, exist_ok=True)

    gen = FinancialCaseGenerator()
    paths = []

    for i in range(count):
        profile = gen.generate(
            seed=seed + i,
            annual_income=target_annual_income or (
                random.Random(seed + i * 97).uniform(
                    35000, 180000
                )
            ),
            loan_amount=320000,     # placeholder — not printed on a W-2
            property_value=420000,  # placeholder — not printed on a W-2
            dti_target=0.36,
            tax_year=tax_year,
        )

        renderer = W2Renderer(profile, year_offset=0)

        # Determine noisy vs clean
        rng_style = random.Random(seed + i * 7)
        is_noisy = rng_style.random() < 0.3
        suffix = "noisy" if is_noisy else "clean"

        filename = f"w2_{i + 1:03d}_{suffix}.pdf"
        output_path = os.path.join(output_dir, filename)

        renderer.render(output_path, add_noise=is_noisy)
        paths.append(output_path)

        print(
            f"  Generated: {filename} | "
            f"{profile.full_name} | "
            f"${profile.w2_box1_wages:,.2f}"
        )

    return paths


if __name__ == "__main__":
    print("Generating synthetic W-2 batch...")
    files = generate_synthetic_w2_batch(count=20, output_dir="output")
    print(f"\nDone. {len(files)} W-2s generated in output/")
