"""Phase 3 real-data scan script.

Scans real TESS light curves for candidate dip-like features using the
Phase 3 improved asymmetric-dip detector.  Saves a candidate event table
with full Phase 3 feature columns.

SCIENTIFIC CAUTION:
- Candidate features in this table require multi-sector validation, quality-
  flag vetting, and comparison against instrumental systematics before any
  astrophysical interpretation can be attempted.
- This script does NOT claim exocomet detections.
- The output is a *candidate feature list*, not a confirmed event catalog.

Usage:
    python scripts/run_scan.py \\
        --sample catalogs/target_sample_enriched.csv \\
        --max-targets 5 \\
        --max-lightcurves-per-star 1 \\
        --output results/tables/detector_candidate_events_dev.csv \\
        --sigma-threshold 4.0 \\
        --window-days 1.0
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from astrohunter.asymmetry import DETECTOR_VERSION, scan_lightcurve_for_asymmetric_dips
from astrohunter.lightcurves import load_or_download_lightcurve_cache

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("run_scan")

CACHE_DIR = Path("cache/lightcurves")
TABLES_DIR = Path("results/tables")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Phase 3 real-data dip scanner")
    p.add_argument("--sample", default="catalogs/target_sample_enriched.csv",
                   help="Target catalog CSV with tic_id column")
    p.add_argument("--max-targets", type=int, default=10,
                   help="Maximum number of targets to scan (dev subset)")
    p.add_argument("--max-lightcurves-per-star", type=int, default=1)
    p.add_argument("--output", default="results/tables/detector_candidate_events_dev.csv")
    p.add_argument("--sigma-threshold", type=float, default=4.0)
    p.add_argument("--window-days", type=float, default=1.0)
    return p.parse_args()


def main() -> None:
    args = _parse_args()

    print("\n" + "=" * 68)
    print("AstroHunter KZ — Phase 3 Real-Data Dip Scan (Dev)")
    print()
    print("SCIENTIFIC CAUTION:")
    print("  Candidates below require quality vetting, multi-sector")
    print("  confirmation, and instrumental systematics checks.")
    print("  This output is NOT a confirmed exocomet catalog.")
    print("=" * 68 + "\n")

    catalog_path = Path(args.sample)
    if not catalog_path.exists():
        logger.error("Catalog not found: %s", catalog_path)
        sys.exit(1)

    catalog = pd.read_csv(catalog_path, low_memory=False)
    if "tic_id" not in catalog.columns:
        logger.error("Column 'tic_id' not found in %s", catalog_path)
        sys.exit(1)

    tic_ids = (
        pd.to_numeric(catalog["tic_id"], errors="coerce")
        .dropna()
        .astype(int)
        .unique()
        .tolist()
    )
    tic_subset = tic_ids[: args.max_targets]
    logger.info("Scanning %d targets (max-targets=%d).", len(tic_subset), args.max_targets)

    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    all_events: list[pd.DataFrame] = []

    for tic_id in tic_subset:
        logger.info("Scanning TIC %s…", tic_id)

        # Attach catalog row metadata for the output
        cat_row = catalog[pd.to_numeric(catalog["tic_id"], errors="coerce") == tic_id].iloc[0]
        target_name = str(cat_row.get("target_name", f"TIC {tic_id}"))

        try:
            df = load_or_download_lightcurve_cache(
                tic_id, CACHE_DIR, max_lightcurves=args.max_lightcurves_per_star
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not retrieve light curve for TIC %s: %s", tic_id, exc)
            df = None

        if df is None or df.empty or "time_btjd" not in df.columns or "flux" not in df.columns:
            logger.warning("No usable data for TIC %s; skipping.", tic_id)
            continue

        t = df["time_btjd"].to_numpy(dtype=float)
        f = df["flux"].to_numpy(dtype=float)
        finite = np.isfinite(t) & np.isfinite(f)
        t, f = t[finite], f[finite]

        if t.size < 50:
            logger.warning("TIC %s: only %d finite points; skipping.", tic_id, t.size)
            continue

        try:
            events = scan_lightcurve_for_asymmetric_dips(
                t, f,
                sigma_threshold=args.sigma_threshold,
                window_days=args.window_days,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Detector failed for TIC %s: %s", tic_id, exc)
            continue

        n_ev = len(events)
        if n_ev == 0:
            logger.info("  TIC %s: no candidates above threshold.", tic_id)
            continue

        logger.info("  TIC %s: %d candidate(s) found.", tic_id, n_ev)
        events.insert(0, "tic_id", tic_id)
        events.insert(1, "target_name", target_name)
        product_label = str(df["product_label"].iloc[0]) if "product_label" in df.columns else "unknown"
        events.insert(2, "sector_or_product", product_label)
        events["n_lc_points"] = t.size

        all_events.append(events)

    if not all_events:
        print("\nNo candidate events found across scanned targets.")
        print("This may indicate all thresholds were satisfied, data was")
        print("unavailable, or all features were filtered as single-point-like.")
        empty = pd.DataFrame(columns=["tic_id", "target_name", "sector_or_product",
                                       "event_time_btjd", "depth_ppm", "local_snr",
                                       "detector_version"])
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        empty.to_csv(out, index=False)
        logger.info("Saved empty candidate table to %s", out)
        return

    result = pd.concat(all_events, ignore_index=True)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(out, index=False)
    logger.info("Saved candidate event table: %s (%d rows)", out, len(result))

    print("\n" + "=" * 68)
    print(f"Scan summary")
    print(f"  Targets scanned  : {len(tic_subset)}")
    print(f"  Total candidates : {len(result)}")
    print(f"  Detector version : {DETECTOR_VERSION}")
    print(f"  Output           : {out}")
    print("=" * 68)
    print()
    print("REMINDER: All candidates require:")
    print("  - Multi-sector confirmation")
    print("  - Quality-flag and systematics vetting")
    print("  - Stellar and instrumental context checks")
    print("  before any astrophysical interpretation.")
    print()


if __name__ == "__main__":
    main()
