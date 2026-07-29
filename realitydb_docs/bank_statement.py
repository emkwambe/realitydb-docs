"""RealityDB Bank Statement Renderer using ReportLab."""
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from dataclasses import dataclass
from typing import List, Dict
from datetime import datetime, timedelta
import random
import os

@dataclass
class Transaction:
    date: str
    description: str
    amount: float
    type: str  # "debit" or "credit"

@dataclass
class BankStatementData:
    bank_name: str
    account_holder: str
    account_number: str
    statement_period: str
    beginning_balance: float
    ending_balance: float
    transactions: List[Transaction]

class BankStatementRenderer:
    """Renders a realistic bank statement PDF."""

    def __init__(self, output_dir: str = "output"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        self.width, self.height = letter

    def render(self, data: BankStatementData, filename: str):
        filepath = os.path.join(self.output_dir, filename)
        c = canvas.Canvas(filepath, pagesize=letter)

        # ─── Header ───
        c.setFont("Helvetica-Bold", 18)
        c.drawString(50, self.height - 60, data.bank_name)
        c.setFont("Helvetica", 10)
        c.drawString(50, self.height - 80, "Account Statement")
        c.drawRightString(self.width - 50, self.height - 60, data.statement_period)

        # ─── Account Info ───
        y = self.height - 120
        c.setFont("Helvetica-Bold", 10)
        c.drawString(50, y, "Account Holder:")
        c.setFont("Helvetica", 10)
        c.drawString(160, y, data.account_holder)

        c.setFont("Helvetica-Bold", 10)
        c.drawString(50, y - 18, "Account Number:")
        c.setFont("Courier", 10)
        c.drawString(160, y - 18, data.account_number)

        # ─── Balance Summary Box ───
        box_y = y - 60
        c.setFillColorRGB(0.96, 0.96, 0.96)
        c.rect(50, box_y - 60, self.width - 100, 60, stroke=1, fill=1)
        c.setFillColorRGB(0, 0, 0)

        c.setFont("Helvetica-Bold", 10)
        c.drawString(70, box_y - 25, "Beginning Balance")
        c.drawString(220, box_y - 25, "Total Deposits")
        c.drawString(370, box_y - 25, "Total Withdrawals")
        c.drawString(500, box_y - 25, "Ending Balance")

        total_deposits = sum(t.amount for t in data.transactions if t.type == "credit")
        total_withdrawals = sum(t.amount for t in data.transactions if t.type == "debit")

        c.setFont("Courier", 11)
        c.drawString(70, box_y - 45, f"${data.beginning_balance:,.2f}")
        c.drawString(220, box_y - 45, f"${total_deposits:,.2f}")
        c.drawString(370, box_y - 45, f"${total_withdrawals:,.2f}")
        c.drawString(500, box_y - 45, f"${data.ending_balance:,.2f}")

        # ─── Transaction Table ───
        table_y = box_y - 100
        c.setFont("Helvetica-Bold", 9)
        c.drawString(50, table_y, "Date")
        c.drawString(130, table_y, "Description")
        c.drawString(400, table_y, "Amount")
        c.drawString(500, table_y, "Balance")

        # Header line
        c.setStrokeColorRGB(0.7, 0.7, 0.7)
        c.line(50, table_y - 5, self.width - 50, table_y - 5)

        running_balance = data.beginning_balance
        c.setFont("Helvetica", 9)
        row_y = table_y - 22

        for tx in data.transactions:
            if row_y < 80:
                c.showPage()
                row_y = self.height - 80
                # Redraw header
                c.setFont("Helvetica-Bold", 9)
                c.drawString(50, row_y, "Date")
                c.drawString(130, row_y, "Description")
                c.drawString(400, row_y, "Amount")
                c.drawString(500, row_y, "Balance")
                c.line(50, row_y - 5, self.width - 50, row_y - 5)
                row_y -= 22
                c.setFont("Helvetica", 9)

            c.drawString(50, row_y, tx.date)
            c.drawString(130, row_y, tx.description[:35])

            if tx.type == "credit":
                c.setFillColorRGB(0, 0.5, 0)
                c.drawString(400, row_y, f"+${tx.amount:,.2f}")
                running_balance += tx.amount
            else:
                c.setFillColorRGB(0.7, 0, 0)
                c.drawString(400, row_y, f"-${tx.amount:,.2f}")
                running_balance -= tx.amount

            c.setFillColorRGB(0, 0, 0)
            c.drawString(500, row_y, f"${running_balance:,.2f}")

            # Light row separator
            c.setStrokeColorRGB(0.9, 0.9, 0.9)
            c.line(50, row_y - 4, self.width - 50, row_y - 4)

            row_y -= 18

        # ─── Footer ───
        c.setFont("Helvetica", 7)
        c.setFillColorRGB(0.5, 0.5, 0.5)
        c.drawString(50, 30, "This statement is provided for your records. Please review all transactions and report discrepancies within 60 days.")
        c.drawRightString(self.width - 50, 30, "Page 1 of 1")

        c.save()
        return filepath


def generate_synthetic_bank_statement(output_dir: str = "output"):
    """Generate a realistic bank statement."""
    renderer = BankStatementRenderer(output_dir=output_dir)

    banks = ["Chase Bank", "Bank of America", "Wells Fargo", "Citibank", "Capital One"]
    descriptions = [
        "Payroll Deposit", "Direct Deposit", "ACH Transfer", "Check #1024",
        "Auto Loan Payment", "Student Loan", "Credit Card Payment", "Netflix",
        "Spotify", "Uber", "Amazon.com", "Grocery Store", "Gas Station",
        "Rent Payment", "Electric Bill", "Internet Service", "Phone Bill"
    ]

    bank = random.choice(banks)
    beginning = round(random.uniform(2000, 25000), 2)

    transactions = []
    balance = beginning
    start_date = datetime(2024, 3, 1)

    # Add recurring debits
    recurring = [
        ("Auto Loan Payment", round(random.uniform(350, 650), 2)),
        ("Student Loan", round(random.uniform(200, 500), 2)),
        ("Rent Payment", round(random.uniform(1200, 2800), 2)),
    ]

    for day in range(1, 32):
        date = (start_date + timedelta(days=day-1)).strftime("%m/%d/%Y")

        # Payroll on 1st and 15th
        if day in [1, 15]:
            amount = round(random.uniform(3500, 8500), 2)
            transactions.append(Transaction(date, "Payroll Deposit", amount, "credit"))
            balance += amount

        # Recurring debits
        if day == 5:
            for desc, amt in recurring:
                transactions.append(Transaction(date, desc, amt, "debit"))
                balance -= amt

        # Random transactions
        if random.random() < 0.3:
            desc = random.choice(descriptions)
            amt = round(random.uniform(15, 400), 2)
            tx_type = random.choice(["debit", "credit"])
            transactions.append(Transaction(date, desc, amt, tx_type))
            if tx_type == "credit":
                balance += amt
            else:
                balance -= amt

    data = BankStatementData(
        bank_name=bank,
        account_holder=random.choice(["John Doe", "Sarah Highdebt", "Mike Risky", "Jane Smith"]),
        account_number=f"****{random.randint(1000,9999)}",
        statement_period="March 1 - March 31, 2024",
        beginning_balance=beginning,
        ending_balance=round(balance, 2),
        transactions=transactions
    )

    path = renderer.render(data, "bank_statement_001.pdf")
    print(f"Generated: {path}")
    return path


if __name__ == "__main__":
    generate_synthetic_bank_statement()
