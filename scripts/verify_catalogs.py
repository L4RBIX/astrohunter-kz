#!/usr/bin/env python
"""Verify Phase 2/2C catalog completeness without making science claims."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from astrohunter.catalogs import save_catalog


PLACEHOLDER_TOKENS = {
    "not_attempted",
    "not_attempted_placeholder",
    "placeholder",
    "nan",
    "none",
    "<na>",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify a Phase 2 target catalog CSV.")
    parser.add_argument("--catalog", default="catalogs/target_sample_enriched.csv")
    parser.add_argument(
        "--output",
        default="results/tables/catalog_verification_report.csv",
    )
    return parser.parse_args()


def _count_valid_coords(df: pd.DataFrame) -> int:
    if not {"ra_deg", "dec_deg"}.issubset(df.columns):
        return 0
    ra = pd.to_numeric(df["ra_deg"], errors="coerce")
    dec = pd.to_numeric(df["dec_deg"], errors="coerce")
    return int((np.isfinite(ra) & np.isfinite(dec)).sum())


def _count_true(df: pd.DataFrame, column: str) -> int:
    if column not in df.columns:
        return 0
    return int(df[column].astype(str).str.lower().isin(["true", "1", "yes", "y"]).sum())


def _count_status(df: pd.DataFrame, column: str, status: str) -> int:
    if column not in df.columns:
        return 0
    return int((df[column].astype(str).str.lower() == status).sum())


def _placeholder_count(df: pd.DataFrame) -> int:
    scientific_columns = [
        "tic_id",
        "gaia_dr3_source_id",
        "tmag",
        "bp_rp",
        "parallax",
        "teff",
    ]
    count = 0
    for column in scientific_columns:
        if column not in df.columns:
            continue
        values = df[column].dropna().astype(str).str.strip().str.lower()
        count += int(values.isin(PLACEHOLDER_TOKENS).sum())
    return count


def build_verification_report(df: pd.DataFrame) -> pd.DataFrame:
    """Build a metric/value verification report for one target catalog."""
    rows: list[dict[str, object]] = [
        {"metric": "n_rows", "value": len(df)},
        {"metric": "valid_ra_dec_count", "value": _count_valid_coords(df)},
        {"metric": "tess_available_count", "value": _count_true(df, "has_tess_lightcurve")},
        {"metric": "tic_matched_count", "value": _count_status(df, "tic_query_status", "matched")},
        {"metric": "gaia_matched_count", "value": _count_status(df, "gaia_query_status", "matched")},
        {"metric": "placeholder_scientific_value_count", "value": _placeholder_count(df)},
    ]

    if "source_catalog" in df.columns:
        for source, count in df["source_catalog"].value_counts(dropna=False).items():
            rows.append(
                {
                    "metric": "source_catalog_count",
                    "label": source,
                    "value": int(count),
                }
            )

    metadata_columns = [
        "tic_id",
        "gaia_dr3_source_id",
        "tmag",
        "bp_rp",
        "parallax",
        "has_tess_lightcurve",
        "n_tess_products",
    ]
    for column in metadata_columns:
        if column not in df.columns:
            missing = len(df)
        else:
            missing = int(df[column].isna().sum())
        rows.append({"metric": "missing_metadata_count", "label": column, "value": missing})

    return pd.DataFrame(rows)


def _diff_stats(df: pd.DataFrame, left: str, right: str) -> tuple[float, float]:
    if left not in df.columns or right not in df.columns:
        return np.nan, np.nan
    diff = (
        pd.to_numeric(df[left], errors="coerce")
        - pd.to_numeric(df[right], errors="coerce")
    ).abs().dropna()
    if diff.empty:
        return np.nan, np.nan
    return float(diff.mean()), float(diff.std(ddof=0))


def build_matched_pairs_report(
    df: pd.DataFrame,
    target_catalog: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Build verification metrics for matched_pairs.csv."""
    rows: list[dict[str, object]] = [{"metric": "n_pairs", "value": len(df)}]
    if target_catalog is not None and "has_tess_lightcurve" in target_catalog.columns:
        eligible = int(
            target_catalog["has_tess_lightcurve"]
            .astype(str)
            .str.lower()
            .isin(["true", "1", "yes", "y"])
            .sum()
        )
        rows.append({"metric": "n_unmatched_targets", "value": max(0, eligible - len(df))})
    elif "unmatched_target_count" in df.columns and len(df) > 0:
        rows.append({"metric": "n_unmatched_targets", "value": int(df["unmatched_target_count"].iloc[0])})
    else:
        rows.append(
            {
                "metric": "n_unmatched_targets",
                "value": pd.NA,
                "label": "not_available_without_target_catalog",
            }
        )

    for metric_name, left, right in [
        ("tmag_diff", "tmag_target", "tmag_control"),
        ("bp_rp_diff", "bp_rp_target", "bp_rp_control"),
        ("parallax_diff", "parallax_target", "parallax_control"),
    ]:
        mean, std = _diff_stats(df, left, right)
        rows.append({"metric": f"{metric_name}_mean", "value": mean})
        rows.append({"metric": f"{metric_name}_std", "value": std})
    return pd.DataFrame(rows)


def _looks_like_matched_pairs(df: pd.DataFrame) -> bool:
    return {"target_tic_id", "control_tic_id", "match_quality_score"}.issubset(df.columns)


def _load_sibling_target_catalog(catalog_path: Path) -> pd.DataFrame | None:
    target_path = catalog_path.parent / "target_sample_enriched.csv"
    if not target_path.exists():
        return None
    try:
        return pd.read_csv(target_path)
    except Exception:
        return None


def main() -> int:
    args = parse_args()
    catalog_path = Path(args.catalog)
    if not catalog_path.exists():
        raise FileNotFoundError(catalog_path)

    df = pd.read_csv(catalog_path)
    if _looks_like_matched_pairs(df):
        report = build_matched_pairs_report(df, _load_sibling_target_catalog(catalog_path))
    else:
        report = build_verification_report(df)
    output_path = save_catalog(report, args.output)

    print(f"Catalog: {catalog_path}")
    for _, row in report.iterrows():
        label = f" ({row['label']})" if "label" in report.columns and pd.notna(row.get("label")) else ""
        print(f"  {row['metric']}{label}: {row['value']}")
    print(f"Saved verification report: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
