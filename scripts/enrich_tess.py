#!/usr/bin/env python
"""Add TESS light-curve availability metadata to a target table."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from astrohunter.catalogs import save_catalog


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Enrich targets with TESS availability.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--max-targets", type=int, default=None)
    return parser.parse_args()


def _clean_tic_id(value) -> str | None:
    if pd.isna(value):
        return None
    try:
        if float(value).is_integer():
            return str(int(float(value)))
    except Exception:
        pass
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "<na>"}:
        return None
    return text.replace("TIC", "").strip()


def _first_value(search_result, names: list[str]):
    try:
        table = search_result.table
        colnames = getattr(table, "colnames", [])
    except Exception:
        return pd.NA
    lookup = {str(column).lower(): column for column in colnames}
    for name in names:
        column = lookup.get(name.lower())
        if column is None:
            continue
        try:
            value = table[column][0]
        except Exception:
            continue
        if hasattr(value, "item"):
            try:
                value = value.item()
            except Exception:
                pass
        return value
    return pd.NA


def enrich_tess(df: pd.DataFrame, max_targets: int | None = None) -> pd.DataFrame:
    work = df.copy()
    for column in [
        "has_tess_lightcurve",
        "n_tess_products",
        "first_sector",
        "first_mission",
        "tess_query_status",
    ]:
        if column not in work.columns:
            work[column] = pd.NA

    try:
        import lightkurve as lk
    except ImportError:
        print("Warning: lightkurve is unavailable; marking all TESS queries failed.")
        work["has_tess_lightcurve"] = False
        work["n_tess_products"] = 0
        work["tess_query_status"] = "failed"
        return work

    limit = len(work) if max_targets is None else min(max_targets, len(work))
    print(f"Checking TESS availability for {limit} target rows...")
    for idx in work.index[:limit]:
        tic_id = _clean_tic_id(work.loc[idx].get("tic_id"))
        if tic_id is None:
            work.loc[idx, "has_tess_lightcurve"] = False
            work.loc[idx, "n_tess_products"] = 0
            work.loc[idx, "tess_query_status"] = "not_found"
            continue

        query = f"TIC {tic_id}"
        try:
            result = lk.search_lightcurve(query, mission="TESS")
        except Exception as exc:
            print(f"Warning: TESS query failed for {query}: {exc}")
            work.loc[idx, "has_tess_lightcurve"] = False
            work.loc[idx, "n_tess_products"] = 0
            work.loc[idx, "tess_query_status"] = "failed"
            continue

        n_products = int(len(result))
        work.loc[idx, "n_tess_products"] = n_products
        work.loc[idx, "has_tess_lightcurve"] = n_products > 0
        work.loc[idx, "tess_query_status"] = "found" if n_products > 0 else "not_found"
        if n_products > 0:
            work.loc[idx, "first_sector"] = _first_value(
                result,
                ["sequence_number", "sector", "Sector"],
            )
            work.loc[idx, "first_mission"] = _first_value(
                result,
                ["mission", "Mission", "obs_collection"],
            )

    if limit < len(work):
        work.loc[work.index[limit:], "tess_query_status"] = "not_attempted"
    return work


def main() -> int:
    args = parse_args()
    df = pd.read_csv(args.input)
    enriched = enrich_tess(df, max_targets=args.max_targets)
    output_path = save_catalog(enriched, args.output)
    available = int(enriched["has_tess_lightcurve"].astype(str).str.lower().isin(["true"]).sum())
    print(f"Saved TESS-enriched targets: {output_path}")
    print(f"TESS availability: {available}/{len(enriched)} targets have TESS data")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
