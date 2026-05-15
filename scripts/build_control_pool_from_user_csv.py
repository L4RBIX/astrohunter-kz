#!/usr/bin/env python
"""Normalize a user-provided real non-disk control pool CSV."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from astrohunter.catalogs import normalize_control_pool_columns, save_catalog


REQUIRED_COLUMNS = {
    "tic_id",
    "ra_deg",
    "dec_deg",
    "n_tess_products",
    "has_tess_lightcurve",
    "ir_excess_flag",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Normalize a real TIC/Gaia/MAST-derived non-disk control pool."
    )
    parser.add_argument("input_csv")
    parser.add_argument("--output", default="catalogs/control_pool.csv")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input_csv)
    if not input_path.exists():
        raise FileNotFoundError(input_path)

    pool = normalize_control_pool_columns(pd.read_csv(input_path))
    missing = sorted(column for column in REQUIRED_COLUMNS if column not in pool.columns)
    if missing:
        print(f"Warning: normalized control pool missing required columns: {missing}")

    non_disk = pool["ir_excess_flag"].astype(str).str.lower().isin(["false", "0", "no", "n"])
    has_tess = pool["has_tess_lightcurve"].astype(str).str.lower().isin(["true", "1", "yes", "y"])
    usable = pool[non_disk & has_tess].copy()
    print(f"Input rows: {len(pool)}")
    print(f"Usable non-disk TESS controls after basic filtering: {len(usable)}")

    if args.dry_run:
        print(f"Dry run: would save normalized pool to {args.output}")
        return 0

    output_path = save_catalog(pool, args.output)
    print(f"Saved normalized real control pool: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
