"""
Manual delivery script for RealityDB case packs.

Usage:
  python deliver.py --email buyer@company.com --pack starter
  python deliver.py --email buyer@company.com --pack professional
  python deliver.py --email buyer@company.com --pack free

This generates the pack and prints instructions
for sending it. Full automation comes later.

Pack composition
----------------
free and starter are A0 packs: every material value
reconciles across every document. They are built by
packet.generate_case_pack().

professional additionally carries timeline cases from
timeline.generate_timeline_pack() — 18-month borrower
journeys including A4 fraud cases where the loan
application overstates income against the W-2 and the
bank deposits.

That distinction is load-bearing. generate_case_pack()
raises on any alignment other than A0, so a pack built
from it alone cannot contain a fraud case no matter what
its README says. The professional tier assembles both.
"""
import argparse
import os
import shutil
import zipfile

from realitydb_docs.packet import generate_case_pack
from realitydb_docs.timeline import generate_timeline_pack

DELIVERY_DIR = "output/delivery"

# Human-readable pack copy lives beside the code, in a tracked directory.
# It cannot live under output/ — that path is gitignored, and
# generate_case_pack() removes its staging directory after zipping, which
# would delete anything left there.
README_DIR = "delivery"

PACKS = {
    "free": {
        "count": 5,
        "seed_start": 1,
        "distribution": {
            "approved": 2, "flagged": 2, "rejected": 1
        },
        "name": "realitydb_free_sample",
        "price": "Free",
        "timeline_cases": 0,
        "readme": "README_FREE_SAMPLE.md",
        "description": "5 cases, 30 PDFs",
    },
    "starter": {
        "count": 50,
        "seed_start": 100,
        "distribution": {
            "approved": 20, "flagged": 15, "rejected": 15
        },
        "name": "realitydb_starter_pack",
        "price": "$299",
        "timeline_cases": 0,
        "readme": "README_STARTER.md",
        "description": "50 cases, 300 PDFs",
    },
    "professional": {
        "count": 150,
        "seed_start": 200,
        "distribution": {
            "approved": 60, "flagged": 45, "rejected": 45
        },
        "name": "realitydb_professional_pack",
        "price": "$799",
        # Kept at 10. These are what make the tier's fraud claim true;
        # generate_case_pack() raises on any alignment but A0, so without them
        # the pack is 150 clean cases and the A4 copy on the pricing page and
        # in README_PROFESSIONAL.md would be false.
        "timeline_cases": 10,
        "readme": "README_PROFESSIONAL.md",
        "description": "150 cases + 10 timeline, 960 PDFs",
    },
}


def _zip_dir(source_dir: str, zip_path: str, root: str) -> str:
    """Zip a directory, walking it in sorted order."""
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for base, dirs, files in os.walk(source_dir):
            dirs.sort()
            for name in sorted(files):
                full = os.path.join(base, name)
                zf.write(full, os.path.relpath(full, root))
    return zip_path


def build_pack(pack: str, output_dir: str = DELIVERY_DIR) -> str:
    """Build a pack and return the path to its ZIP.

    A pack with timeline_cases is assembled rather than zipped directly: the
    standard cases are generated unzipped, the timeline cases are generated
    into a subdirectory beside them, and the whole tree is zipped once.
    """
    cfg = PACKS[pack]
    os.makedirs(output_dir, exist_ok=True)

    if not cfg["timeline_cases"]:
        return generate_case_pack(
            count=cfg["count"],
            output_dir=output_dir,
            pack_name=cfg["name"],
            seed_start=cfg["seed_start"],
            distribution=cfg["distribution"],
            zip_output=True,
        )

    # ── Assembled pack ───────────────────────────────────
    staging = generate_case_pack(
        count=cfg["count"],
        output_dir=output_dir,
        pack_name=cfg["name"],
        seed_start=cfg["seed_start"],
        distribution=cfg["distribution"],
        zip_output=False,
    )

    timeline_root = os.path.join(staging, "timeline_cases")
    generate_timeline_pack(
        count=cfg["timeline_cases"],
        output_dir=timeline_root,
        pack_name="timeline",
        seed_start=cfg["seed_start"] + cfg["count"],
        months=18,
        zip_output=False,
    )

    zip_path = os.path.join(
        output_dir,
        f"{cfg['name']}_{cfg['count']}cases.zip",
    )
    _zip_dir(staging, zip_path, output_dir)
    shutil.rmtree(staging)
    return zip_path


def deliver(email: str, pack: str):
    if pack not in PACKS:
        print(f"Unknown pack: {pack}")
        print(f"Available: {list(PACKS.keys())}")
        return

    cfg = PACKS[pack]

    print(f"Generating {pack} pack for {email}...")

    zip_path = build_pack(pack)
    size_mb = os.path.getsize(zip_path) / 1024 / 1024

    readme_path = os.path.join(README_DIR, cfg["readme"])

    print()
    print("=" * 60)
    print("DELIVERY READY")
    print("=" * 60)
    print(f"Pack:    {pack} ({cfg['price']})")
    print(f"File:    {zip_path}")
    print(f"Size:    {size_mb:.2f} MB")
    print(f"Cases:   {cfg['count']} standard", end="")
    if cfg["timeline_cases"]:
        print(f" + {cfg['timeline_cases']} timeline (incl. A4 fraud)")
    else:
        print()
    print(f"Buyer:   {email}")
    print(f"README:  {readme_path}")
    print()
    print("NEXT STEPS:")
    print("1. Attach the ZIP to an email")
    print(f"2. Send to: {email}")
    print("3. Use this subject line:")
    print(f"   RealityDB Financial Cases - {pack.title()} Pack")
    print()
    print("EMAIL BODY TEMPLATE:")
    print("-" * 40)
    print("Hi,")
    print()
    print("Your RealityDB Financial Cases")
    print(f"{pack.title()} Pack is attached.")
    print()
    print(f"It contains {cfg['count']} complete synthetic")
    print("underwriting cases - W-2, bank statements,")
    print("loan application, pay stubs, ground truth")
    print("JSON, and evaluation layers.")
    if cfg["timeline_cases"]:
        print()
        print(f"It also includes {cfg['timeline_cases']} timeline cases:")
        print("18-month borrower journeys with life events,")
        print("including fraud cases where the loan")
        print("application overstates income against the")
        print("W-2 and the bank deposits.")
    print()
    print("Each case has a README.md explaining")
    print("the borrower and expected outcomes.")
    print()
    print("Questions: eddy@mpingo.ai")
    print()
    print("- Eddy Mkwambe")
    print("  Mpingo Systems LLC")
    print("  realitydb.dev/financial-cases/")
    print("-" * 40)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", required=True)
    parser.add_argument(
        "--pack",
        choices=["free", "starter", "professional"],
        default="free"
    )
    args = parser.parse_args()
    deliver(args.email, args.pack)
