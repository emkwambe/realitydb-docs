"""RealityDB Batch Generator — W-2s + Bank Statements + Loan Applications
+ Pay Stubs.
Run this to generate a full synthetic dataset for PacketWise testing."""
import argparse
import os
import sys

# Add the repo root (this file's grandparent) so package imports resolve
# whether the CLI is run as `python -m realitydb_docs.cli` or as a script.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from realitydb_docs.w2 import generate_synthetic_w2_batch
from realitydb_docs.bank_statement import generate_synthetic_bank_statement_batch
from realitydb_docs.loan_app import generate_loan_application_batch
from realitydb_docs.paystub import (
    TOTAL_PERIODS,
    generate_paystub_batch,
)
from realitydb_docs.packet import SCENARIOS, generate_case_pack

# Subcommands understood by main(). Anything else falls through to the
# original flat-flag interface (--w2-count/--bank-count), which shipped
# first and is still used by scripts, so it must keep working.
SUBCOMMANDS = ("loan-app", "w2", "bank-statement", "paystub", "packet")


def _parse_distribution(raw, count):
    """Parse `--distribution approved:3,flagged:3,rejected:3`."""
    if raw is None:
        return None
    distribution = {}
    for part in str(raw).split(","):
        part = part.strip()
        if not part:
            continue
        if ":" not in part:
            raise SystemExit(
                f"--distribution entries must be scenario:count, "
                f"got {part!r}"
            )
        scenario, _, number = part.partition(":")
        scenario = scenario.strip()
        if scenario not in SCENARIOS:
            raise SystemExit(
                f"--distribution: unknown scenario {scenario!r}; "
                f"choose from {sorted(SCENARIOS)}"
            )
        try:
            distribution[scenario] = int(number)
        except ValueError:
            raise SystemExit(
                f"--distribution: {number!r} is not an integer"
            )
    if not distribution:
        raise SystemExit("--distribution named no scenarios")
    total = sum(distribution.values())
    if total != count:
        raise SystemExit(
            f"--distribution sums to {total} but --count is {count}"
        )
    return distribution


def _packet_command(argv):
    """`cli.py packet --count N ...`"""
    parser = argparse.ArgumentParser(
        prog="cli.py packet",
        description="Generate a complete case pack (documents + truth + "
                    "evaluation layers) as a ZIP.",
    )
    parser.add_argument("--count", type=int, default=9)
    parser.add_argument("--output", "--output-dir", dest="output",
                        default="output")
    parser.add_argument("--seed-start", type=int, default=1)
    parser.add_argument("--pack-name", default="auto_loan_starter")
    parser.add_argument(
        "--distribution", default=None,
        help="scenario:count pairs, e.g. "
             "approved:3,flagged:3,rejected:3 (default: even split)",
    )
    parser.add_argument(
        "--no-zip", action="store_true",
        help="leave the case folders in place instead of zipping them",
    )
    args = parser.parse_args(argv)

    if args.count < 1:
        raise SystemExit(f"--count must be at least 1, got {args.count}")

    distribution = _parse_distribution(args.distribution, args.count)
    try:
        result = generate_case_pack(
            count=args.count,
            output_dir=args.output,
            pack_name=args.pack_name,
            seed_start=args.seed_start,
            distribution=distribution,
            zip_output=not args.no_zip,
        )
    except (FileExistsError, ValueError) as exc:
        raise SystemExit(str(exc))

    print(f"\nPack written to {os.path.abspath(result)}")
    return result


def _parse_periods(raw):
    """Parse `--periods 21,22` into a validated tuple."""
    if raw is None:
        return (21, 22)
    try:
        periods = tuple(
            int(part) for part in str(raw).split(",") if part.strip()
        )
    except ValueError:
        raise SystemExit(
            f"--periods must be comma-separated integers, got {raw!r}"
        )
    if not periods:
        raise SystemExit("--periods must name at least one pay period")
    out_of_range = [p for p in periods if not 1 <= p <= TOTAL_PERIODS]
    if out_of_range:
        raise SystemExit(
            f"--periods out of range 1-{TOTAL_PERIODS}: {out_of_range}"
        )
    return periods


def _paystub_command(argv):
    """`cli.py paystub --count N ...`"""
    parser = argparse.ArgumentParser(
        prog="cli.py paystub",
        description="Generate bi-weekly pay stub PDFs.",
    )
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--output", "--output-dir", dest="output",
                        default="output")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--annual-income", type=float, default=None,
                        help="applies to every document")
    parser.add_argument(
        "--periods", default=None,
        help=f"comma-separated pay periods 1-{TOTAL_PERIODS} "
             f"(default: 21,22 — the two most recent)",
    )
    args = parser.parse_args(argv)

    periods = _parse_periods(args.periods)
    results = generate_paystub_batch(
        count=args.count,
        output_dir=args.output,
        seed_start=args.seed,
        annual_incomes=[args.annual_income] if args.annual_income else None,
        pay_periods=periods,
    )
    print(
        f"\n{len(results)} pay stub(s) in {os.path.abspath(args.output)}"
    )
    return [path for path, _ in results]


def _loan_app_command(argv):
    """`cli.py loan-app --count N ...`"""
    parser = argparse.ArgumentParser(
        prog="cli.py loan-app",
        description="Generate Fannie Mae 1003 loan application PDFs.",
    )
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--output", "--output-dir", dest="output", default="output")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--annual-income", type=float, default=None,
                        help="applies to every document (+/-2%% variation)")
    parser.add_argument("--loan-amount", type=float, default=None)
    parser.add_argument("--property-value", type=float, default=None)
    parser.add_argument("--dti-target", type=float, default=None,
                        help="target debt-to-income ratio, e.g. 0.36")
    parser.add_argument("--credit-score", type=int, default=None)
    parser.add_argument("--monthly-housing-payment", type=float, default=None)
    args = parser.parse_args(argv)

    def as_list(v):
        return None if v is None else [v]

    paths = generate_loan_application_batch(
        count=args.count,
        output_dir=args.output,
        seed_start=args.seed,
        annual_incomes=as_list(args.annual_income),
        loan_amounts=as_list(args.loan_amount),
        property_values=as_list(args.property_value),
        debt_to_income_targets=as_list(args.dti_target),
        credit_scores=as_list(args.credit_score),
        monthly_housing_payments=as_list(args.monthly_housing_payment),
    )
    for p in paths:
        print(f"  Generated: {p}")
    print(f"\n{len(paths)} loan application(s) in {os.path.abspath(args.output)}")
    return paths


def _w2_command(argv):
    """`cli.py w2 --count N ...`"""
    parser = argparse.ArgumentParser(prog="cli.py w2")
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--output", "--output-dir", dest="output", default="output")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--annual-income", type=float, default=None)
    args = parser.parse_args(argv)
    return generate_synthetic_w2_batch(
        count=args.count, output_dir=args.output, seed=args.seed,
        target_annual_income=args.annual_income,
    )


def _bank_statement_command(argv):
    """`cli.py bank-statement --count N ...`"""
    parser = argparse.ArgumentParser(prog="cli.py bank-statement")
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--output", "--output-dir", dest="output", default="output")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--annual-income", type=float, default=None)
    parser.add_argument("--dti-target", type=float, default=None)
    args = parser.parse_args(argv)
    return generate_synthetic_bank_statement_batch(
        count=args.count, output_dir=args.output, seed_start=args.seed,
        annual_incomes=[args.annual_income] if args.annual_income else None,
        debt_to_income_target=args.dti_target,
    )


def main():
    # Subcommand form takes precedence; without one, the legacy flat form runs.
    if len(sys.argv) > 1 and sys.argv[1] in SUBCOMMANDS:
        command, argv = sys.argv[1], sys.argv[2:]
        if command == "loan-app":
            return _loan_app_command(argv)
        if command == "w2":
            return _w2_command(argv)
        if command == "paystub":
            return _paystub_command(argv)
        if command == "packet":
            return _packet_command(argv)
        return _bank_statement_command(argv)

    parser = argparse.ArgumentParser(
        description="Generate a synthetic document set for PacketWise testing.",
        epilog="Subcommands: w2 | bank-statement | loan-app | paystub | "
               "packet (e.g. `cli.py packet --count 9 --output output/`)",
    )
    parser.add_argument("--output-dir", default="output",
                        help="directory for generated PDFs (default: output)")
    parser.add_argument("--w2-count", type=int, default=20,
                        help="number of W-2s to generate (default: 20)")
    parser.add_argument("--bank-count", type=int, default=10,
                        help="number of bank statements to generate (default: 10)")
    parser.add_argument("--loan-app-count", type=int, default=0,
                        help="number of loan applications to generate "
                             "(default: 0 — use the `loan-app` subcommand for "
                             "the full set of 1003 options)")
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

    # 3. Loan Applications (opt-in)
    loan_files = []
    if args.loan_app_count:
        print(f"\n[3/3] Generating {args.loan_app_count} Loan Applications...")
        loan_files = generate_loan_application_batch(
            count=args.loan_app_count,
            output_dir=output_dir,
            seed_start=args.seed,
            annual_incomes=[args.annual_income] if args.annual_income else None,
        )

    # 4. Summary
    print("\n" + "=" * 60)
    print("DATASET SUMMARY")
    print("=" * 60)
    print(f"W-2 Forms:        {len(w2_files)}")
    print(f"Bank Statements:  {len(bank_files)}")
    print(f"Loan Apps:        {len(loan_files)}")
    print(f"Output directory: {os.path.abspath(output_dir)}")
    print("\nDone! Use these files to test PacketWise IDP pipeline.")

if __name__ == "__main__":
    main()
