#!/usr/bin/env python
"""Crossmatch a target table against TIC and Gaia DR3 by sky position."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from astrohunter.catalogs import (
    crossmatch_targets_with_gaia,
    crossmatch_targets_with_tic,
    save_catalog,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Crossmatch real target rows to TIC and Gaia DR3 metadata."
    )
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--max-targets", type=int, default=None)
    parser.add_argument("--radius-arcsec", type=float, default=5.0)
    parser.add_argument("--skip-tic", action="store_true")
    parser.add_argument("--skip-gaia", action="store_true")
    return parser.parse_args()


def _ensure_status_columns(df: pd.DataFrame) -> pd.DataFrame:
    work = df.copy()
    for column in [
        "tic_id",
        "tmag",
        "teff_tic",
        "tic_match_sep_arcsec",
        "gaia_dr3_source_id",
        "bp_rp",
        "parallax",
        "gaia_match_sep_arcsec",
    ]:
        if column not in work.columns:
            work[column] = pd.NA
    if "tic_query_status" not in work.columns:
        work["tic_query_status"] = "not_attempted"
    if "gaia_query_status" not in work.columns:
        work["gaia_query_status"] = "not_attempted"
    return work


def _print_summary(df: pd.DataFrame) -> None:
    print("\nCrossmatch summary")
    print(f"  rows: {len(df)}")
    if "tic_query_status" in df.columns:
        print("  TIC statuses:")
        for status, count in df["tic_query_status"].value_counts(dropna=False).items():
            print(f"    {status}: {count}")
    if "gaia_query_status" in df.columns:
        print("  Gaia statuses:")
        for status, count in df["gaia_query_status"].value_counts(dropna=False).items():
            print(f"    {status}: {count}")


def main() -> int:
    args = parse_args()
    input_path = Path(args.input)
    if not input_path.exists():
        raise FileNotFoundError(input_path)

    targets = _ensure_status_columns(pd.read_csv(input_path))
    print(f"Loaded target table: {input_path} ({len(targets)} rows)")

    if args.skip_tic:
        print("Skipping TIC crossmatch by request.")
        targets["tic_query_status"] = "not_attempted"
    else:
        targets = crossmatch_targets_with_tic(
            targets,
            max_targets=args.max_targets,
            radius_arcsec=args.radius_arcsec,
        )

    if args.skip_gaia:
        print("Skipping Gaia crossmatch by request.")
        targets["gaia_query_status"] = "not_attempted"
    else:
        targets = crossmatch_targets_with_gaia(
            targets,
            max_targets=args.max_targets,
            radius_arcsec=args.radius_arcsec,
        )

    output_path = save_catalog(targets, args.output)
    print(f"Saved crossmatched targets: {output_path}")
    _print_summary(targets)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
