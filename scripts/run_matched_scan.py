#!/usr/bin/env python3
"""Phase 5B matched target/control scan for AstroHunter KZ.

Scans TESS light curves for all matched target and control stars listed in
matched_pairs.csv using the Phase 3 asymmetric-dip detector.  Attaches
sample_role ('target' or 'control') and pair metadata to every detected
candidate event.

Cached light curves are reused automatically.  Stars that fail to download
are skipped with a warning; partial results are saved after every star so
that no data is lost if the run is interrupted.

SCIENTIFIC CAUTION:
- All detected events are candidates only.
- Automated detection is NOT scientific confirmation.
- Matched-scan candidate counts are preliminary statistics.
- Full vetting and multi-sector confirmation are required.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from astrohunter.asymmetry import DETECTOR_VERSION, scan_lightcurve_for_asymmetric_dips
from astrohunter.lightcurves import load_or_download_lightcurve_cache

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run_matched_scan")

CACHE_DIR = Path("cache/lightcurves")
TABLES_DIR = Path("results/tables")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Phase 5B: Scan matched target and control stars for candidate dip events.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--matched-pairs", default="catalogs/matched_pairs.csv",
                   help="matched_pairs.csv with target_tic_id / control_tic_id columns.")
    p.add_argument("--target-catalog", default="catalogs/target_sample_enriched.csv",
                   help="Target sample CSV with tic_id and target_name columns.")
    p.add_argument("--control-pool", default="catalogs/control_pool.csv",
                   help="Control pool CSV with tic_id column.")
    p.add_argument("--output", default="results/tables/detector_candidate_events_matched_scan.csv",
                   help="Output path for candidate event table.")
    p.add_argument("--max-pairs", type=int, default=28,
                   help="Maximum number of matched pairs to process.")
    p.add_argument("--max-lightcurves-per-star", type=int, default=1,
                   help="Maximum TESS light curves to download per star.")
    p.add_argument("--sigma-threshold", type=float, default=4.0,
                   help="Dip detection sigma threshold.")
    p.add_argument("--window-days", type=float, default=1.0,
                   help="Feature extraction window in days.")
    p.add_argument("--include-targets", action="store_true", default=True,
                   help="Scan target stars (default: True).")
    p.add_argument("--include-controls", action="store_true", default=True,
                   help="Scan control stars (default: True).")
    p.add_argument("--no-targets", dest="include_targets", action="store_false",
                   help="Skip target stars.")
    p.add_argument("--no-controls", dest="include_controls", action="store_false",
                   help="Skip control stars.")
    return p.parse_args(argv)


def _load_name_map(target_catalog_path: Path, control_pool_path: Path) -> dict[int, str]:
    """Build a TIC-ID → identifier string map from both catalogs."""
    name_map: dict[int, str] = {}

    if target_catalog_path.exists():
        ts = pd.read_csv(target_catalog_path, low_memory=False)
        if "tic_id" in ts.columns:
            for _, row in ts.iterrows():
                tic = int(pd.to_numeric(row["tic_id"], errors="coerce") or 0)
                if tic:
                    name = str(row.get("target_name", f"TIC {tic}"))
                    name_map[tic] = name

    if control_pool_path.exists():
        cp = pd.read_csv(control_pool_path, low_memory=False)
        if "tic_id" in cp.columns:
            for _, row in cp.iterrows():
                tic = int(pd.to_numeric(row["tic_id"], errors="coerce") or 0)
                if tic and tic not in name_map:
                    name_map[tic] = f"TIC {tic}"

    return name_map


def _scan_one_star(
    tic_id: int,
    role: str,
    pair_id: int,
    name: str,
    max_lcs: int,
    sigma_threshold: float,
    window_days: float,
) -> tuple[pd.DataFrame | None, str]:
    """Scan one star; return (events_df_or_None, status_string)."""
    try:
        df = load_or_download_lightcurve_cache(tic_id, CACHE_DIR, max_lightcurves=max_lcs)
    except Exception as exc:  # noqa: BLE001
        return None, f"download_failed: {exc}"

    if df is None or df.empty:
        return None, "no_data"
    if "time_btjd" not in df.columns or "flux" not in df.columns:
        return None, "missing_columns"

    t = df["time_btjd"].to_numpy(dtype=float)
    f = df["flux"].to_numpy(dtype=float)
    mask = np.isfinite(t) & np.isfinite(f)
    t, f = t[mask], f[mask]

    if t.size < 50:
        return None, f"too_few_points:{t.size}"

    try:
        events = scan_lightcurve_for_asymmetric_dips(
            t, f,
            sigma_threshold=sigma_threshold,
            window_days=window_days,
        )
    except Exception as exc:  # noqa: BLE001
        return None, f"detector_failed: {exc}"

    if events.empty:
        return None, "no_candidates"

    product_label = (
        str(df["product_label"].iloc[0]) if "product_label" in df.columns else "unknown"
    )
    events.insert(0, "pair_id", pair_id)
    events.insert(1, "sample_role", role)
    events.insert(2, "tic_id", tic_id)
    events.insert(3, "target_name", name)
    events.insert(4, "sector_or_product", product_label)
    events["n_lc_points"] = t.size

    return events, f"ok:{len(events)}_candidates"


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    print("=" * 70)
    print("AstroHunter KZ — Phase 5B: Matched Target/Control Scan")
    print(f"Detector version: {DETECTOR_VERSION}")
    print()
    print("SCIENTIFIC CAUTION:")
    print("  All detected events are candidates only.")
    print("  Automated detection is NOT scientific confirmation.")
    print("  Rate statistics on this scan are preliminary.")
    print("=" * 70)

    # ------------------------------------------------------------------ paths
    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    pairs_path = Path(args.matched_pairs)
    if not pairs_path.exists():
        logger.error("matched_pairs.csv not found: %s", pairs_path)
        return 1

    matched_pairs = pd.read_csv(pairs_path)
    matched_pairs = matched_pairs.head(args.max_pairs)
    n_pairs = len(matched_pairs)
    logger.info("Loaded %d matched pairs (max_pairs=%d).", n_pairs, args.max_pairs)

    name_map = _load_name_map(Path(args.target_catalog), Path(args.control_pool))

    # --------------------------------------------------------- build scan list
    scan_list: list[tuple[int, str, int, str]] = []  # (tic_id, role, pair_id, name)

    for pair_id, row in matched_pairs.iterrows():
        if args.include_targets:
            t_tic = int(pd.to_numeric(row.get("target_tic_id", None), errors="coerce") or 0)
            if t_tic:
                scan_list.append((t_tic, "target", pair_id, name_map.get(t_tic, f"TIC {t_tic}")))

        if args.include_controls:
            c_tic = int(pd.to_numeric(row.get("control_tic_id", None), errors="coerce") or 0)
            if c_tic:
                scan_list.append((c_tic, "control", pair_id, name_map.get(c_tic, f"TIC {c_tic}")))

    # Deduplicate: same TIC could appear in multiple pairs; keep first occurrence
    seen_tics: set[int] = set()
    unique_scan_list: list[tuple[int, str, int, str]] = []
    for entry in scan_list:
        tic = entry[0]
        if tic not in seen_tics:
            seen_tics.add(tic)
            unique_scan_list.append(entry)

    n_targets_to_scan = sum(1 for _, role, _, _ in unique_scan_list if role == "target")
    n_controls_to_scan = sum(1 for _, role, _, _ in unique_scan_list if role == "control")
    print(
        f"\nScan plan: {n_targets_to_scan} unique target stars, "
        f"{n_controls_to_scan} unique control stars  "
        f"({len(unique_scan_list)} total)"
    )

    # ------------------------------------------------------------------- scan
    all_events: list[pd.DataFrame] = []
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    stats: dict[str, list] = {
        "target_attempted": [], "target_success": [], "target_failed": [],
        "control_attempted": [], "control_success": [], "control_failed": [],
    }

    for i, (tic_id, role, pair_id, name) in enumerate(unique_scan_list):
        logger.info(
            "[%d/%d] %s TIC %s (%s) …",
            i + 1, len(unique_scan_list), role.upper(), tic_id, name,
        )
        stats[f"{role}_attempted"].append(tic_id)

        events_df, status = _scan_one_star(
            tic_id, role, pair_id, name,
            max_lcs=args.max_lightcurves_per_star,
            sigma_threshold=args.sigma_threshold,
            window_days=args.window_days,
        )

        if events_df is not None and not events_df.empty:
            all_events.append(events_df)
            stats[f"{role}_success"].append(tic_id)
            n_ev = len(events_df)
            logger.info("  → %d candidate(s).", n_ev)
        else:
            stats[f"{role}_failed"].append(tic_id)
            if "no_candidates" in status:
                logger.info("  → no candidates above threshold.")
            else:
                logger.warning("  → skipped (%s).", status)

        # Save partial results after each star
        if all_events:
            partial = pd.concat(all_events, ignore_index=True)
            partial.to_csv(out_path, index=False)

    # ------------------------------------------------------ save final output
    if all_events:
        result = pd.concat(all_events, ignore_index=True)
    else:
        result = pd.DataFrame(columns=[
            "pair_id", "sample_role", "tic_id", "target_name", "sector_or_product",
            "event_time_btjd", "depth_ppm", "local_snr", "duration_hours",
            "detector_version", "n_lc_points",
        ])

    result.to_csv(out_path, index=False)
    logger.info("Saved candidate table: %s (%d rows)", out_path, len(result))

    # Save scan metadata (for exposure estimation in stats)
    meta = {
        "n_target_attempted": len(stats["target_attempted"]),
        "n_control_attempted": len(stats["control_attempted"]),
        "n_target_success": len(stats["target_success"]),
        "n_control_success": len(stats["control_success"]),
        "n_target_failed": len(stats["target_failed"]),
        "n_control_failed": len(stats["control_failed"]),
        "target_tics_scanned": stats["target_success"],
        "control_tics_scanned": stats["control_success"],
        "target_tics_failed": stats["target_failed"],
        "control_tics_failed": stats["control_failed"],
        "sigma_threshold": args.sigma_threshold,
        "window_days": args.window_days,
        "max_lightcurves_per_star": args.max_lightcurves_per_star,
        "detector_version": DETECTOR_VERSION,
    }
    meta_path = out_path.with_suffix(".meta.json")
    with open(meta_path, "w") as fh:
        json.dump(meta, fh, indent=2)
    logger.info("Saved scan metadata: %s", meta_path)

    # ------------------------------------------------------------ print summary
    n_t_cands = int((result["sample_role"] == "target").sum()) if not result.empty else 0
    n_c_cands = int((result["sample_role"] == "control").sum()) if not result.empty else 0

    print("\n" + "=" * 70)
    print("Phase 5B Matched Scan Summary")
    print("=" * 70)
    print(f"  Target  stars attempted : {len(stats['target_attempted'])}")
    print(f"  Target  stars with data  : {len(stats['target_success'])}")
    print(f"  Target  stars failed     : {len(stats['target_failed'])}")
    print(f"  Control stars attempted : {len(stats['control_attempted'])}")
    print(f"  Control stars with data  : {len(stats['control_success'])}")
    print(f"  Control stars failed     : {len(stats['control_failed'])}")
    print()
    print(f"  Target  candidates       : {n_t_cands}")
    print(f"  Control candidates       : {n_c_cands}")
    print(f"  Total candidates         : {len(result)}")
    print(f"  Detector version         : {DETECTOR_VERSION}")
    print(f"  Output                   : {out_path}")
    print(f"  Scan metadata            : {meta_path}")
    if stats["target_failed"]:
        print(f"\n  Failed target TICs  : {stats['target_failed'][:10]}"
              f"{'...' if len(stats['target_failed']) > 10 else ''}")
    if stats["control_failed"]:
        print(f"  Failed control TICs : {stats['control_failed'][:10]}"
              f"{'...' if len(stats['control_failed']) > 10 else ''}")
    print()
    print("REMINDER: All candidate events require manual vetting and")
    print("          multi-sector confirmation before any interpretation.")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    sys.exit(main())
