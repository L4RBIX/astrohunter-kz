#!/usr/bin/env python
"""Run the Phase 1 beta Pic positive-control pipeline."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from astrohunter.asymmetry import add_asymmetry_scores, detect_candidate_dips
from astrohunter.lightcurves import (
    clean_normalize_lightcurve,
    download_limited_lightcurves,
    lightcurve_to_dataframe,
)
from astrohunter.plotting import (
    plot_full_lightcurve,
    plot_lightcurve_with_events,
    plot_zoom_window,
)


DEFAULT_TARGET = "TIC 270577175"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Download a limited number of public TESS light curves for beta Pic "
            "and detect simple candidate dip-like features."
        )
    )
    parser.add_argument("--target", default=DEFAULT_TARGET)
    parser.add_argument("--max-lightcurves", type=int, default=1)
    parser.add_argument("--output-dir", default="results")
    parser.add_argument("--sigma-threshold", type=float, default=4.0)
    parser.add_argument("--window-days", type=float, default=0.5)
    return parser.parse_args()


def _combine_lightcurves(collection):
    if len(collection) == 1:
        return collection[0]
    print(f"Stitching {len(collection)} downloaded light curves...")
    try:
        return collection.stitch()
    except Exception as exc:
        raise RuntimeError(f"Could not stitch downloaded light curves: {exc}") from exc


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    figures_dir = output_dir / "figures"
    tables_dir = output_dir / "tables"
    figures_dir.mkdir(parents=True, exist_ok=True)
    tables_dir.mkdir(parents=True, exist_ok=True)

    print("AstroHunter KZ Phase 1 beta Pic positive control")
    print("This run identifies candidate dip-like features only.")
    print(f"Target: {args.target}")
    print(f"Maximum light curves to download: {args.max_lightcurves}")

    collection = download_limited_lightcurves(
        args.target,
        mission="TESS",
        max_lightcurves=args.max_lightcurves,
    )
    lc = clean_normalize_lightcurve(_combine_lightcurves(collection))
    df = lightcurve_to_dataframe(lc)
    if df.empty:
        raise RuntimeError("No finite light-curve points remained after cleaning.")

    time = df["time_btjd"].to_numpy()
    flux = df["flux"].to_numpy()

    events = detect_candidate_dips(
        time,
        flux,
        sigma_threshold=args.sigma_threshold,
        min_distance=5,
        window_days=args.window_days,
    )
    events = add_asymmetry_scores(events, time, flux, window_days=args.window_days)

    table_path = tables_dir / "beta_pic_candidate_dips.csv"
    events.to_csv(table_path, index=False)

    fig = plot_full_lightcurve(
        time,
        flux,
        "Beta Pic / TIC 270577175 TESS Light Curve",
        output_path=figures_dir / "beta_pic_full_lightcurve.png",
    )
    plt.close(fig)

    fig = plot_lightcurve_with_events(
        time,
        flux,
        events,
        "Beta Pic TESS Light Curve with Candidate Dip-Like Features",
        output_path=figures_dir / "beta_pic_lightcurve_with_detected_dips.png",
    )
    plt.close(fig)

    if not events.empty:
        strongest = events.sort_values("depth", ascending=False).iloc[0]
        start = strongest["event_time_btjd"] - args.window_days / 2.0
        end = strongest["event_time_btjd"] + args.window_days / 2.0
        fig = plot_zoom_window(
            time,
            flux,
            start,
            end,
            f"Beta Pic Strongest Candidate Dip-Like Feature near BTJD {strongest['event_time_btjd']:.3f}",
            output_path=figures_dir / "beta_pic_zoom_strongest_dip.png",
        )
        plt.close(fig)

    print("\nRun summary")
    print(f"  points after cleaning: {len(df)}")
    print(f"  candidate dip-like features: {len(events)}")
    if events.empty:
        print("  deepest candidate: none")
    else:
        deepest = events.sort_values("depth", ascending=False).iloc[0]
        print(
            "  deepest candidate: "
            f"BTJD {deepest['event_time_btjd']:.6f}, "
            f"depth {deepest['depth']:.6g} "
            f"({deepest['depth_ppm']:.1f} ppm)"
        )
    print(f"  saved table: {table_path}")
    print(
        "\nScientific caution: these are candidate dip-like features, not "
        "confirmed exocomets. The strongest Phase 1 features may be "
        "instrumental/systematic and require quality-flag and multi-sector "
        "validation."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
