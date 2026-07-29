"""RealityDB Batch Generator — W-2s + Bank Statements + Loan Applications.
Run this to generate a full synthetic dataset for PacketWise testing."""
import os
import sys

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from w2_renderer import generate_synthetic_w2_batch
from bank_statement_renderer import generate_synthetic_bank_statement

def main():
    output_dir = "output"
    os.makedirs(output_dir, exist_ok=True)

    print("=" * 60)
    print("REALITYDB SYNTHETIC DATASET GENERATOR")
    print("=" * 60)

    # 1. W-2 Forms
    print("\n[1/3] Generating W-2 Forms...")
    w2_files = generate_synthetic_w2_batch(count=20, output_dir=output_dir)

    # 2. Bank Statements
    print("\n[2/3] Generating Bank Statements...")
    bank_files = []
    for i in range(10):
        path = generate_synthetic_bank_statement(output_dir=output_dir)
        bank_files.append(path)

    # 3. Summary
    print("\n" + "=" * 60)
    print("DATASET SUMMARY")
    print("=" * 60)
    print(f"W-2 Forms:        {len(w2_files)}")
    print(f"Bank Statements:  {len(bank_files)}")
    print(f"Output directory: {os.path.abspath(output_dir)}")
    print("\nDone! Use these files to test PacketWise IDP pipeline.")

if __name__ == "__main__":
    main()
