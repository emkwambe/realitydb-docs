"""RealityDB W-2 Renderer using ReportLab.
Generates realistic W-2 wage and tax statement PDFs."""
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from dataclasses import dataclass
from typing import Optional
import random
import os

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

class W2Renderer:
    """Renders a W-2 form to PDF using ReportLab."""

    def __init__(self, output_dir: str = "output"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        self.width, self.height = letter  # 612 x 792 pts

    def render(self, data: W2Data, filename: str, add_noise: bool = False):
        """Render a single W-2 PDF."""
        filepath = os.path.join(self.output_dir, filename)
        c = canvas.Canvas(filepath, pagesize=letter)

        # ─── Background / Form Lines ───
        self._draw_form_outline(c)

        # ─── Header ───
        c.setFont("Helvetica-Bold", 14)
        c.drawString(50, self.height - 50, f"{data.year} W-2 Wage and Tax Statement")
        c.setFont("Helvetica", 8)
        c.drawString(50, self.height - 65, f"For calendar year {data.year}")
        c.drawString(50, self.height - 75, "Copy A — For Social Security Administration")

        if data.control_number:
            c.drawRightString(self.width - 50, self.height - 50, f"Control #: {data.control_number}")

        # ─── Employer Info (Box b + top left) ───
        self._draw_box(c, 50, self.height - 140, 240, 70, "b Employer identification number (EIN)")
        c.setFont("Courier", 10)
        c.drawString(60, self.height - 125, data.employer_ein)

        c.setFont("Helvetica", 9)
        c.drawString(50, self.height - 160, "Employer name:")
        c.setFont("Helvetica-Bold", 10)
        c.drawString(50, self.height - 175, data.employer_name)

        # ─── Employee Info ───
        self._draw_box(c, 310, self.height - 140, 250, 70, "a Employee's social security number")
        c.setFont("Courier", 11)
        c.drawString(320, self.height - 125, data.employee_ssn)

        c.setFont("Helvetica", 9)
        c.drawString(310, self.height - 160, "Employee name:")
        c.setFont("Helvetica-Bold", 10)
        c.drawString(310, self.height - 175, data.employee_name)

        # ─── Wage Boxes ───
        box_y = self.height - 260
        box_h = 55
        box_w = 145
        gap = 15

        # Box 1
        self._draw_box(c, 50, box_y, box_w, box_h, "1 Wages, tips, other compensation")
        c.setFont("Courier", 10)
        c.drawString(60, box_y + 20, f"{data.wages_box_1:,.2f}")

        # Box 2
        self._draw_box(c, 50 + box_w + gap, box_y, box_w, box_h, "2 Federal income tax withheld")
        c.drawString(60 + box_w + gap, box_y + 20, f"{data.federal_tax_box_2:,.2f}")

        # Box 3
        self._draw_box(c, 50 + (box_w + gap) * 2, box_y, box_w, box_h, "3 Social security wages")
        c.drawString(60 + (box_w + gap) * 2, box_y + 20, f"{data.ss_wages_box_3:,.2f}")

        # Box 4
        self._draw_box(c, 50 + (box_w + gap) * 3, box_y, box_w, box_h, "4 Social security tax withheld")
        c.drawString(60 + (box_w + gap) * 3, box_y + 20, f"{data.ss_tax_box_4:,.2f}")

        # Second row
        box_y2 = box_y - box_h - gap

        # Box 5
        self._draw_box(c, 50, box_y2, box_w, box_h, "5 Medicare wages and tips")
        c.drawString(60, box_y2 + 20, f"{data.medicare_wages_box_5:,.2f}")

        # Box 6
        self._draw_box(c, 50 + box_w + gap, box_y2, box_w, box_h, "6 Medicare tax withheld")
        c.drawString(60 + box_w + gap, box_y2 + 20, f"{data.medicare_tax_box_6:,.2f}")

        # Box 16 (State wages)
        if data.state_wages_box_16:
            self._draw_box(c, 50 + (box_w + gap) * 2, box_y2, box_w, box_h, "16 State wages, tips, etc.")
            c.drawString(60 + (box_w + gap) * 2, box_y2 + 20, f"{data.state_wages_box_16:,.2f}")

        # Box 17 (State tax)
        if data.state_tax_box_17:
            self._draw_box(c, 50 + (box_w + gap) * 3, box_y2, box_w, box_h, "17 State income tax")
            c.drawString(60 + (box_w + gap) * 3, box_y2 + 20, f"{data.state_tax_box_17:,.2f}")

        # ─── Footer ───
        c.setFont("Helvetica", 7)
        c.drawString(50, 40, "Department of the Treasury — Internal Revenue Service")
        c.drawRightString(self.width - 50, 40, f"Form W-2 ({data.year})")

        # ─── Optional: Add subtle noise for realism ───
        if add_noise:
            self._add_scan_noise(c)

        c.save()
        return filepath

    def _draw_form_outline(self, c):
        """Draw the outer border of the W-2 form."""
        c.setStrokeColorRGB(0, 0, 0)
        c.setLineWidth(1.5)
        c.rect(40, 30, self.width - 80, self.height - 60, stroke=1, fill=0)
        c.setLineWidth(0.5)
        c.line(40, self.height - 80, self.width - 40, self.height - 80)

    def _draw_box(self, c, x, y, w, h, label):
        """Draw a labeled box."""
        c.setStrokeColorRGB(0, 0, 0)
        c.setLineWidth(0.5)
        c.rect(x, y, w, h, stroke=1, fill=0)
        c.setFont("Helvetica", 7)
        c.setFillColorRGB(0.3, 0.3, 0.3)
        c.drawString(x + 4, y + h - 10, label)
        c.setFillColorRGB(0, 0, 0)

    def _add_scan_noise(self, c):
        """Add subtle scan artifacts (light gray dots)."""
        c.setStrokeColorRGB(0.85, 0.85, 0.85)
        c.setLineWidth(0.2)
        for _ in range(200):
            x = random.randint(0, int(self.width))
            y = random.randint(0, int(self.height))
            c.line(x, y, x + 1, y)


def generate_synthetic_w2_batch(
    count: int = 10,
    output_dir: str = "output",
    seed: int = 42,
    tax_year: int = 2024,
    target_annual_income: float = None,
):
    """Generate a batch of synthetic W-2s with realistic data.

    Args:
      count: number of W-2s to generate
      output_dir: directory for output files
      seed: random seed (deterministic)
      tax_year: calendar year printed on the form
      target_annual_income: if provided, Box 1 wages land within +/-3% of
        this figure — realistic year-to-year drift — so the W-2 agrees with
        the income stated on a loan application. If omitted, wages are drawn
        at random from $28,000-$180,000 as before.
    """
    rng = random.Random(seed)
    renderer = W2Renderer(output_dir=output_dir)
    employers = [
        ("Acme Corporation", "12-3456789"),
        ("TechStart Inc", "98-7654321"),
        ("MetroHealth Systems", "55-1234567"),
        ("Global Logistics LLC", "77-8889999"),
        ("Summit Education Group", "33-4445555"),
    ]

    first_names = ["James", "Mary", "Robert", "Patricia", "John", "Jennifer", "Michael", "Linda"]
    last_names = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis"]

    files = []
    for i in range(count):
        emp_name, emp_ein = rng.choice(employers)
        fname = rng.choice(first_names)
        lname = rng.choice(last_names)

        if target_annual_income:
            wages = round(target_annual_income * rng.uniform(0.97, 1.03), 2)
        else:
            wages = round(rng.uniform(28000, 180000), 2)
        ss_wages = min(wages, 160200)  # 2023 SS cap

        data = W2Data(
            employer_name=emp_name,
            employer_ein=emp_ein,
            employee_name=f"{fname} {lname}",
            employee_ssn=f"{rng.randint(900,999):03d}-{rng.randint(10,99):02d}-{rng.randint(1000,9999):04d}",
            wages_box_1=wages,
            federal_tax_box_2=round(wages * rng.uniform(0.12, 0.22), 2),
            ss_wages_box_3=ss_wages,
            ss_tax_box_4=round(ss_wages * 0.062, 2),
            medicare_wages_box_5=wages,
            medicare_tax_box_6=round(wages * 0.0145, 2),
            state_wages_box_16=wages,
            state_tax_box_17=round(wages * rng.uniform(0.03, 0.07), 2),
            year=tax_year,
            control_number=f"{rng.randint(100000,999999)}"
        )

        # Mix of clean and noisy
        add_noise = rng.random() < 0.3
        filename = f"w2_{i+1:03d}_{'noisy' if add_noise else 'clean'}.pdf"
        path = renderer.render(data, filename, add_noise=add_noise)
        files.append(path)
        print(f"  Generated: {filename} | {data.employee_name} | ${data.wages_box_1:,.2f}")

    return files


if __name__ == "__main__":
    print("Generating synthetic W-2 batch...")
    files = generate_synthetic_w2_batch(count=20, output_dir="output")
    print(f"\nDone. {len(files)} W-2s generated in output/")

