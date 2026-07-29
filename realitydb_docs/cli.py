"""RealityDB Batch Generator — W-2s + Bank Statements + Loan Applications.
Run this to generate a full synthetic dataset for PacketWise testing."""
import argparse
import os
import sys

# Add the repo root (this file's grandparent) so package imports resolve
# whether the CLI is run as `python -m realitydb_docs.cli` or as a script.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from realitydb_docs.w2 import generate_synthetic_w2_batch
from realitydb_docs.bank_statement import generate_synthetic_bank_statement_batch

def main():
    parser = argparse.ArgumentParser(
        description="Generate a synthetic document set for PacketWise testing."
    )
    parser.add_argument("--output-dir", default="output",
                        help="directory for generated PDFs (default: output)")
    parser.add_argument("--w2-count", type=int, default=20,
                        help="number of W-2s to generate (default: 20)")
    parser.add_argument("--bank-count", type=int, default=10,
                        help="number of bank statements to generate (default: 10)")
    parser.add_argument("--seed", type=int, default=42,
                        help="base random seed (default: 42)")
    parser.add_argument("--annual-income", type=float, default=None,
                        help="target annual income; W-2 wages and statement "
                             "deposits are both generated against it")
    args = parser.parse_args()

    output_dir = args.output_dir
    os.makedirs(output_dir, exist_ok=True)

    print("=" * 60)
    print("REALITYDB SYNTHETIC DATASET GENERATOR")
    print("=" * 60)

    # 1. W-2 Forms
    print(f"\n[1/3] Generating {args.w2_count} W-2 Forms...")
    w2_files = generate_synthetic_w2_batch(
        count=args.w2_count,
        output_dir=output_dir,
        seed=args.seed,
        target_annual_income=args.annual_income,
    )

    # 2. Bank Statements
    print(f"\n[2/3] Generating {args.bank_count} Bank Statements...")
    bank_files = generate_synthetic_bank_statement_batch(
        count=args.bank_count,
        output_dir=output_dir,
        seed_start=args.seed,
        annual_incomes=[args.annual_income] if args.annual_income else None,
    )

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
