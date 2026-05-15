#!/usr/bin/env python3
"""Phase 5 candidate-yield rate statistics CLI for AstroHunter KZ.

Loads the vetted candidate table and matched-pairs catalog, computes
preliminary target/control candidate-yield rate statistics, saves a
summary table, and generates diagnostic figures.

IMPORTANT: Dev-sample statistics are preliminary.
With < 10 total candidates, rate ratios are unstable.
These results do NOT constitute a scientific claim.
Full survey data are required for interpretation.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from astrohunter.stats import (
    summarize_rate_statistics,
    compute_candidate_yield_by_role,
    MIN_CANDIDATES_FOR_STABLE_STATS,
    STATS_VERSION,
)
from astrohunter.plotting import (
    plot_rate_ratio_summary,
    plot_candidate_score_vs_snr,
    plot_vetting_flag_counts,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run_stats")

FIGURES_DIR = Path("results/figures")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Phase 5: Compute preliminary candidate yield rate statistics.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument(
        "--vetted-candidates",
        default="results/tables/vetted_candidate_events_dev.csv",
        help="Path to vetted candidate events CSV (Phase 5 vetting output).",
    )
    p.add_argument(
        "--matched-pairs",
        default="catalogs/matched_pairs.csv",
        help="Path to matched_pairs.csv for exposure estimation.",
    )
    p.add_argument(
        "--output",
        default="results/tables/rate_ratio_summary.csv",
        help="Output path for rate-ratio summary table.",
    )
    p.add_argument(
        "--n-bootstrap",
        type=int,
        default=1000,
        help="Number of bootstrap replicates for CI estimation.",
    )
    p.add_argument(
        "--random-seed",
        type=int,
        default=42,
        help="Random seed for reproducibility.",
    )
    return p.parse_args(argv)


def _print_summary_table(summary_df: pd.DataFrame) -> None:
    """Print a human-readable rate-ratio summary."""
    for _, row in summary_df.iterrows():
        subset = row.get("subset", "?")
        print(f"\n  [ {subset} ]")
        print(f"    Total candidates:    {row.get('total_candidates', '?')}")
        print(f"    Target candidates:   {row.get('target_count', '?')}")
        print(f"    Control candidates:  {row.get('control_count', '?')}")
        print(f"    Unknown-role:        {row.get('unknown_role_candidates', '?')}")

        t_rate = row.get("target_rate", float("nan"))
        c_rate = row.get("control_rate", float("nan"))
        rr = row.get("rate_ratio", float("nan"))
        rr_lo = row.get("rate_ratio_ci_lo", float("nan"))
        rr_hi = row.get("rate_ratio_ci_hi", float("nan"))

        print(f"    Target rate:         {t_rate:.4f} cand/star (95% CI: "
              f"[{row.get('target_rate_ci_lo', float('nan')):.4f}, "
              f"{row.get('target_rate_ci_hi', float('nan')):.4f}])")
        print(f"    Control rate:        {c_rate:.4f} cand/star (95% CI: "
              f"[{row.get('control_rate_ci_lo', float('nan')):.4f}, "
              f"{row.get('control_rate_ci_hi', float('nan')):.4f}])")

        if np.isfinite(rr):
            print(f"    Rate ratio (T/C):    {rr:.3f}  (Poisson CI: [{rr_lo:.3f}, {rr_hi:.3f}])")
        else:
            print("    Rate ratio (T/C):    undefined (control count = 0)")

        boot_med = row.get("bootstrap_rate_ratio_median", float("nan"))
        boot_lo = row.get("bootstrap_ci_lo", float("nan"))
        boot_hi = row.get("bootstrap_ci_hi", float("nan"))
        if np.isfinite(boot_med):
            print(
                f"    Bootstrap RR median: {boot_med:.3f}  "
                f"(95% CI: [{boot_lo:.3f}, {boot_hi:.3f}], "
                f"n={row.get('n_finite_replicates', '?')} finite replicates)"
            )

        pval = row.get("p_value_fisher", float("nan"))
        print(f"    Fisher exact p:      {pval:.4f}  — {row.get('interpretation', '')}")

        warn = row.get("preliminary_warning")
        boot_warn = row.get("stability_warning")
        if warn:
            print(f"\n    *** WARNING: {warn}")
        if boot_warn:
            print(f"    *** WARNING: {boot_warn}")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    print("=" * 70)
    print("AstroHunter KZ — Phase 5: Candidate Yield Rate Statistics")
    print(f"Stats version: {STATS_VERSION}")
    print()
    print("IMPORTANT: Dev-sample statistics are PRELIMINARY.")
    print(f"           Rate ratios unstable when total candidates < "
          f"{MIN_CANDIDATES_FOR_STABLE_STATS}.")
    print("           These results do NOT constitute a scientific claim.")
    print("=" * 70)

    # ------------------------------------------------------------------ load
    vet_path = Path(args.vetted_candidates)
    if not vet_path.exists():
        logger.error("Vetted candidate table not found: %s", vet_path)
        print(f"\nERROR: Vetted candidate table not found: {vet_path}")
        print("Run Phase 5 vetting first: scripts/run_vetting.py")
        return 1

    candidate_df = pd.read_csv(vet_path)
    n_candidates = len(candidate_df)
    logger.info("Loaded %d vetted candidates from %s", n_candidates, vet_path)
    print(f"\nLoaded {n_candidates} vetted candidate(s) from {vet_path}")

    pairs_path = Path(args.matched_pairs)
    if pairs_path.exists():
        matched_pairs_df = pd.read_csv(pairs_path)
        n_pairs = len(matched_pairs_df)
        logger.info("Loaded %d matched pairs from %s", n_pairs, pairs_path)
        print(f"Loaded {n_pairs} matched pairs from {pairs_path}")
    else:
        logger.warning("Matched pairs not found: %s; exposure set to 1.", pairs_path)
        matched_pairs_df = pd.DataFrame()
        print(f"WARNING: matched_pairs not found at {pairs_path}. Exposure proxy = 1 star each.")

    # ----------------------------------------------------------- role counts
    yields = compute_candidate_yield_by_role(candidate_df, matched_pairs_df)
    print(
        f"\nRole assignment from matched-pairs catalog:"
        f"\n  Target  candidates: {yields['target_candidates']}"
        f"\n  Control candidates: {yields['control_candidates']}"
        f"\n  Unknown-role:       {yields['unknown_candidates']}"
        f"\n  Target  exposure:   {yields['target_exposure']:.0f} unique target stars"
        f"\n  Control exposure:   {yields['control_exposure']:.0f} unique control stars"
    )

    if n_candidates < MIN_CANDIDATES_FOR_STABLE_STATS:
        print(
            f"\n*** WARNING: Only {n_candidates} total candidate(s). "
            "Rate statistics are HIGHLY PRELIMINARY and UNSTABLE. ***"
        )

    # ------------------------------------------------------------- compute
    print("\nComputing rate statistics...")
    summary_df = summarize_rate_statistics(
        candidate_df,
        matched_pairs_df,
        n_bootstrap=args.n_bootstrap,
        random_state=args.random_seed,
    )

    print("\n--- Rate-Ratio Summary ---")
    _print_summary_table(summary_df)

    # --------------------------------------------------------------- save
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    summary_df.to_csv(out_path, index=False)
    logger.info("Saved rate-ratio summary: %s", out_path)
    print(f"\nSaved rate-ratio summary: {out_path}")

    # ------------------------------------------------------------- figures
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    rr_fig = FIGURES_DIR / "rate_ratio_plot.png"
    try:
        plot_rate_ratio_summary(summary_df, output_path=rr_fig)
        print(f"Saved figure: {rr_fig}")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Rate-ratio plot failed: %s", exc)

    snr_fig = FIGURES_DIR / "candidate_score_vs_snr.png"
    try:
        plot_candidate_score_vs_snr(candidate_df, output_path=snr_fig)
        print(f"Saved figure: {snr_fig}")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Score-vs-SNR plot failed: %s", exc)

    flag_fig = FIGURES_DIR / "vetting_flag_counts.png"
    try:
        plot_vetting_flag_counts(candidate_df, output_path=flag_fig)
        print(f"Saved figure: {flag_fig}")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Vetting flag counts plot failed: %s", exc)

    print()
    print("REMINDER: Rate statistics on the dev sample are preliminary.")
    print("          Full-survey scanning is required for scientific claims.")
    print("          External catalog crossmatches (EB/VSX/SIMBAD) are NOT performed.")
    print("          All candidates require manual vetting before interpretation.")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    sys.exit(main())
