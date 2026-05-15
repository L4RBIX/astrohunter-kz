"""Phase 3 injection-recovery script.

Injects synthetic exocomet-like asymmetric dips into real TESS light curves
from the matched target/control sample, runs the Phase 3 asymmetric-dip
detector, and records per-injection recovery results.

PURPOSE: evaluate detector sensitivity only.
These results measure how well the pipeline recovers *synthetic* signals of
known amplitude.  They do NOT describe the purity of real candidates and do
NOT confirm exocomet detections.

Usage:
    python scripts/run_injection_recovery.py \\
        --sample catalogs/matched_pairs.csv \\
        --target-catalog catalogs/target_sample_enriched.csv \\
        --control-pool catalogs/control_pool.csv \\
        --n-lightcurves 4 \\
        --n-injections 40 \\
        --random-seed 42
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Make sure src/ is importable when the script is run from the repo root
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from astrohunter.asymmetry import scan_lightcurve_for_asymmetric_dips
from astrohunter.injection import INJECTOR_VERSION, run_injection_recovery_on_lightcurve
from astrohunter.lightcurves import load_or_download_lightcurve_cache
from astrohunter.plotting import (
    plot_injected_dip_example,
    plot_recovery_heatmap_depth_duration,
    plot_recovery_vs_depth,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("run_injection_recovery")

CACHE_DIR = Path("cache/lightcurves")
FIGURES_DIR = Path("results/figures")
TABLES_DIR = Path("results/tables")

REQUIRED_INJECTION_COLUMNS = [
    "injection_id", "sample_role", "tic_id", "sector_or_product",
    "injected_event_time_btjd", "injected_depth_ppm", "injected_ingress_hours",
    "injected_egress_hours", "injected_asymmetry_ratio",
    "recovered", "recovered_event_time_btjd", "timing_error_hours",
    "recovered_depth_ppm", "recovered_local_snr",
    "recovery_tolerance_hours", "noise_mad", "detector_version",
]


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Phase 3 injection-recovery pipeline")
    p.add_argument("--sample", default="catalogs/matched_pairs.csv",
                   help="Matched pairs CSV with target_tic_id and control_tic_id columns")
    p.add_argument("--target-catalog", default="catalogs/target_sample_enriched.csv",
                   help="Enriched target catalog CSV with tic_id column")
    p.add_argument("--control-pool", default="catalogs/control_pool.csv",
                   help="Control pool CSV with tic_id column")
    p.add_argument("--n-lightcurves", type=int, default=10,
                   help="Total number of light curves to process (dev subset)")
    p.add_argument("--n-injections", type=int, default=200,
                   help="Total number of injection-recovery trials")
    p.add_argument("--max-lightcurves-per-star", type=int, default=1)
    p.add_argument("--output", default="results/tables/injection_recovery.csv")
    p.add_argument("--random-seed", type=int, default=42)
    p.add_argument("--sigma-threshold", type=float, default=4.0)
    p.add_argument("--window-days", type=float, default=1.0)
    p.add_argument("--use-targets-only", action="store_true",
                   help="Only use target stars (from target-catalog)")
    p.add_argument("--use-controls-only", action="store_true",
                   help="Only use control stars (from control-pool)")
    p.add_argument("--tolerance-hours", type=float, default=3.0,
                   help="Timing tolerance in hours for recovery matching")
    return p.parse_args()


def _collect_tic_ids(args: argparse.Namespace) -> list[tuple[int, str]]:
    """Return list of (tic_id, sample_role) tuples from input catalogs."""
    entries: list[tuple[int, str]] = []

    def _add_from_csv(csv_path: str, tic_col: str, role: str) -> None:
        path = Path(csv_path)
        if not path.exists():
            logger.warning("Catalog not found: %s", csv_path)
            return
        try:
            df = pd.read_csv(path, low_memory=False)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not read %s: %s", csv_path, exc)
            return
        if tic_col not in df.columns:
            logger.warning("Column %r not found in %s", tic_col, csv_path)
            return
        ids = pd.to_numeric(df[tic_col], errors="coerce").dropna().astype(int).tolist()
        for tid in ids:
            entries.append((int(tid), role))
        logger.info("Loaded %d TIC IDs (%s) from %s.", len(ids), role, csv_path)

    if args.use_controls_only:
        _add_from_csv(args.control_pool, "tic_id", "control")
    elif args.use_targets_only:
        _add_from_csv(args.target_catalog, "tic_id", "target")
    else:
        # From matched pairs: both targets and controls
        pairs_path = Path(args.sample)
        if pairs_path.exists():
            try:
                pairs = pd.read_csv(pairs_path, low_memory=False)
                if "target_tic_id" in pairs.columns:
                    for tid in pd.to_numeric(pairs["target_tic_id"], errors="coerce").dropna().astype(int):
                        entries.append((int(tid), "target"))
                if "control_tic_id" in pairs.columns:
                    for tid in pd.to_numeric(pairs["control_tic_id"], errors="coerce").dropna().astype(int):
                        entries.append((int(tid), "control"))
                logger.info("Loaded %d entries from matched_pairs.", len(entries))
            except Exception as exc:  # noqa: BLE001
                logger.warning("Could not read matched_pairs: %s", exc)

        if not entries:
            _add_from_csv(args.target_catalog, "tic_id", "target")
            _add_from_csv(args.control_pool, "tic_id", "control")

    # Deduplicate while preserving order and role
    seen: set[int] = set()
    unique: list[tuple[int, str]] = []
    for tid, role in entries:
        if tid not in seen:
            seen.add(tid)
            unique.append((tid, role))
    return unique


def _make_detector(sigma_threshold: float, window_days: float):
    def _detect(t, f):
        return scan_lightcurve_for_asymmetric_dips(t, f, sigma_threshold=sigma_threshold,
                                                    window_days=window_days)
    return _detect


def main() -> None:
    args = _parse_args()
    rng = np.random.default_rng(args.random_seed)

    print("\n" + "=" * 68)
    print("AstroHunter KZ — Phase 3 Injection-Recovery")
    print("PURPOSE: detector sensitivity test only.")
    print("Results do NOT describe real candidate purity.")
    print("Results do NOT confirm exocomet detections.")
    print("=" * 68 + "\n")

    all_tic_entries = _collect_tic_ids(args)
    if not all_tic_entries:
        logger.error("No TIC IDs found. Check input catalog paths.")
        sys.exit(1)

    # Shuffle and take dev subset
    rng.shuffle(all_tic_entries)  # type: ignore[arg-type]
    tic_subset = all_tic_entries[: args.n_lightcurves]
    logger.info("Using %d light curves for injection-recovery.", len(tic_subset))

    n_per_lc = max(1, args.n_injections // len(tic_subset))
    detector_fn = _make_detector(args.sigma_threshold, args.window_days)

    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    all_rows: list[pd.DataFrame] = []
    injection_id = 0
    example_lc: tuple | None = None  # for example plot

    for tic_id, role in tic_subset:
        logger.info("Processing TIC %s (%s)…", tic_id, role)
        try:
            df = load_or_download_lightcurve_cache(
                tic_id, CACHE_DIR, max_lightcurves=args.max_lightcurves_per_star
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not get light curve for TIC %s: %s", tic_id, exc)
            df = None

        if df is None or df.empty or "time_btjd" not in df.columns or "flux" not in df.columns:
            logger.warning("No usable data for TIC %s; skipping.", tic_id)
            continue

        t = df["time_btjd"].to_numpy(dtype=float)
        f = df["flux"].to_numpy(dtype=float)
        finite = np.isfinite(t) & np.isfinite(f)
        t, f = t[finite], f[finite]

        if t.size < 50:
            logger.warning("TIC %s has only %d finite points; skipping.", tic_id, t.size)
            continue

        product_label = str(df["product_label"].iloc[0]) if "product_label" in df.columns else "unknown"
        seed_lc = int(rng.integers(0, 2**31))

        try:
            rec_df = run_injection_recovery_on_lightcurve(
                t, f, n_per_lc, detector_fn,
                tolerance_hours=args.tolerance_hours,
                random_state=seed_lc,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Injection-recovery failed for TIC %s: %s", tic_id, exc)
            continue

        if rec_df.empty:
            continue

        rec_df.insert(0, "injection_id", range(injection_id, injection_id + len(rec_df)))
        rec_df.insert(1, "sample_role", role)
        rec_df.insert(2, "tic_id", tic_id)
        rec_df.insert(3, "sector_or_product", product_label)
        rec_df["detector_version"] = INJECTOR_VERSION
        injection_id += len(rec_df)

        all_rows.append(rec_df)

        # Capture one example for example dip plot
        if example_lc is None and len(rec_df) > 0:
            example_lc = (t, f, rec_df)

        # Save partial results after each star
        _save_partial(all_rows, args.output)
        logger.info(
            "TIC %s done: %d trials, %d recovered.",
            tic_id, len(rec_df), int(rec_df["recovered"].sum()),
        )

    # Assemble final table
    if not all_rows:
        logger.error("No injection-recovery results produced.")
        sys.exit(1)

    result = pd.concat(all_rows, ignore_index=True)
    # Ensure required columns exist
    for col in REQUIRED_INJECTION_COLUMNS:
        if col not in result.columns:
            result[col] = np.nan

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(out_path, index=False)
    logger.info("Saved injection-recovery table: %s", out_path)

    # Summary
    total = len(result)
    n_rec = int(result["recovered"].sum())
    rate = n_rec / total if total > 0 else 0.0
    print("\n" + "=" * 68)
    print(f"Injection-recovery summary")
    print(f"  Total injections : {total}")
    print(f"  Recovered        : {n_rec}")
    print(f"  Recovery rate    : {rate:.1%}")
    print(f"  Output table     : {out_path}")
    print("=" * 68)
    print()
    print("REMINDER: These are sensitivity metrics on synthetic injections.")
    print("They do NOT imply the same fraction of real candidates are real exocomets.")
    print()

    # Plots
    try:
        plot_recovery_vs_depth(result, output_path=FIGURES_DIR / "recovery_vs_depth.png")
        logger.info("Saved recovery_vs_depth.png")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not generate recovery_vs_depth plot: %s", exc)

    try:
        plot_recovery_heatmap_depth_duration(
            result, output_path=FIGURES_DIR / "recovery_heatmap_depth_duration.png"
        )
        logger.info("Saved recovery_heatmap_depth_duration.png")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not generate heatmap plot: %s", exc)

    if example_lc is not None:
        t_ex, f_ex, rec_ex = example_lc
        _make_example_dip_plot(t_ex, f_ex, rec_ex)


def _save_partial(rows: list[pd.DataFrame], path: str) -> None:
    """Concatenate and save current partial results."""
    try:
        partial = pd.concat(rows, ignore_index=True)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        partial.to_csv(path, index=False)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Could not save partial results: %s", exc)


def _make_example_dip_plot(t, f, rec_df: pd.DataFrame) -> None:
    """Generate example injected-dip plot from the first trial."""
    from astrohunter.injection import inject_asymmetric_dip
    from astrohunter.plotting import plot_injected_dip_example

    row = rec_df.iloc[0]
    event_time = float(row.get("injected_event_time_btjd", np.nan))
    depth = float(row.get("injected_depth_ppm", 500.0))
    ingress = float(row.get("injected_ingress_hours", 2.0))
    egress = float(row.get("injected_egress_hours", 8.0))
    if not np.isfinite(event_time):
        return
    try:
        f_inj = inject_asymmetric_dip(t, f, event_time, depth, ingress, egress)
        FIGURES_DIR.mkdir(parents=True, exist_ok=True)
        plot_injected_dip_example(
            t, f, f_inj, event_time, depth, ingress, egress,
            output_path=FIGURES_DIR / "example_injected_dip.png",
        )
        logger.info("Saved example_injected_dip.png")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not save example dip plot: %s", exc)


if __name__ == "__main__":
    main()
