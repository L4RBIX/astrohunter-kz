#!/usr/bin/env python3
"""Phase 5 automated vetting CLI for AstroHunter KZ.

Loads the ranked candidate event table, applies automated vetting flags,
adds manual-review placeholder columns, and saves two output tables:
- vetted_candidate_events_dev.csv  (full vetting output)
- manual_vetting_sheet.csv         (worksheet for human review)

IMPORTANT: Automated vetting is NOT confirmation.
All candidates still require manual review.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

# Ensure the package is importable when running from the repo root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from astrohunter.vetting import (
    add_basic_vetting_flags,
    compute_vetting_summary,
    create_manual_vetting_sheet,
    VETTER_VERSION,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run_vetting")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Phase 5: Apply automated vetting flags to ranked candidate events.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument(
        "--candidate-table",
        default="results/tables/ranked_candidate_events_dev.csv",
        help="Path to ranked candidate events CSV (Phase 4 output).",
    )
    p.add_argument(
        "--output-vetted",
        default="results/tables/vetted_candidate_events_dev.csv",
        help="Output path for vetted candidate table.",
    )
    p.add_argument(
        "--output-manual",
        default="results/tables/manual_vetting_sheet.csv",
        help="Output path for manual review worksheet.",
    )
    p.add_argument(
        "--snr-threshold",
        type=float,
        default=5.0,
        help="SNR threshold below which events are flagged flag_low_snr.",
    )
    p.add_argument(
        "--delta-chi2-threshold",
        type=float,
        default=5.0,
        help="Δχ² threshold below which events are flagged flag_low_delta_chi2.",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    print("=" * 70)
    print("AstroHunter KZ — Phase 5: Automated Candidate Vetting")
    print(f"Vetter version: {VETTER_VERSION}")
    print()
    print("IMPORTANT: Automated vetting applies heuristic flags only.")
    print("           It does NOT confirm or reject exocomet detections.")
    print("           All candidates require manual review.")
    print("=" * 70)

    # ------------------------------------------------------------------ load
    candidate_path = Path(args.candidate_table)
    if not candidate_path.exists():
        logger.error("Candidate table not found: %s", candidate_path)
        print(f"\nERROR: Candidate table not found: {candidate_path}")
        print("Run Phase 4 first: scripts/train_event_ranker.py")
        return 1

    candidate_df = pd.read_csv(candidate_path)
    n_input = len(candidate_df)
    logger.info("Loaded %d candidates from %s", n_input, candidate_path)
    print(f"\nLoaded {n_input} candidate event(s) from {candidate_path}")

    if n_input == 0:
        logger.warning("No candidates to vet.")
        print("No candidates found. Saving empty output tables.")
        candidate_df.to_csv(args.output_vetted, index=False)
        candidate_df.to_csv(args.output_manual, index=False)
        return 0

    # -------------------------------------------------------------- vetting
    print(
        f"\nApplying automated vetting flags "
        f"(SNR threshold={args.snr_threshold}, Δχ² threshold={args.delta_chi2_threshold})..."
    )

    vetted_df = add_basic_vetting_flags(
        candidate_df,
        snr_threshold=args.snr_threshold,
        delta_chi2_threshold=args.delta_chi2_threshold,
    )

    # ----------------------------------------------------------- summary
    summary = compute_vetting_summary(vetted_df)

    print("\n--- Automated Vetting Summary ---")
    print(f"  Total candidates:        {summary['total_candidates']}")
    print(f"  Pass automated vetting:  {summary.get('n_pass', '?')}")
    print(f"  Flagged:                 {summary.get('n_flagged', '?')}")
    print()
    print("  Flag counts:")
    flag_cols = [k for k in summary if k.startswith("flag_")]
    for fc in flag_cols:
        print(f"    {fc:<30s}: {summary[fc]}")
    print()
    print("  External crossmatch status: NOT ATTEMPTED")
    print("    eb_catalog_check_status = not_attempted")
    print("    vsx_check_status        = not_attempted")
    print("    simbad_check_status     = not_attempted")

    if summary.get("total_candidates", 0) < 10:
        print()
        print(
            "  WARNING: Only {} candidate(s) total. "
            "Automated flags are heuristic on this tiny sample.".format(
                summary["total_candidates"]
            )
        )

    # ----------------------------------------------------------- save vetted
    out_vetted = Path(args.output_vetted)
    out_vetted.parent.mkdir(parents=True, exist_ok=True)
    vetted_df.to_csv(out_vetted, index=False)
    logger.info("Saved vetted candidate table: %s (%d rows)", out_vetted, len(vetted_df))
    print(f"\nSaved vetted candidate table: {out_vetted}")

    # --------------------------------------------------------- manual sheet
    manual_sheet = create_manual_vetting_sheet(vetted_df)
    out_manual = Path(args.output_manual)
    out_manual.parent.mkdir(parents=True, exist_ok=True)
    manual_sheet.to_csv(out_manual, index=False)
    logger.info("Saved manual vetting sheet: %s (%d rows)", out_manual, len(manual_sheet))
    print(f"Saved manual vetting sheet:  {out_manual}")

    # -------------------------------------------------------- candidate list
    print("\n--- Candidates (sorted by final_candidate_score) ---")
    sort_col = "final_candidate_score" if "final_candidate_score" in vetted_df.columns else None
    display_df = vetted_df.sort_values(sort_col, ascending=False) if sort_col else vetted_df

    for _, row in display_df.iterrows():
        name = row.get("target_name", row.get("tic_id", "?"))
        snr = row.get("local_snr", float("nan"))
        score = row.get("final_candidate_score", float("nan"))
        status = row.get("automated_vetting_status", "?")
        flags = [
            fc for fc in [
                "flag_low_snr", "flag_edge_event", "flag_single_point_like",
                "flag_likely_flare_shape", "flag_low_delta_chi2", "flag_poor_asymmetry_fit",
            ]
            if row.get(fc, False)
        ]
        flag_str = ", ".join(flags) if flags else "none"
        print(
            f"  {name:<20s}  SNR={snr:5.2f}  score={score:.3f}  "
            f"status={status:<8s}  flags=[{flag_str}]"
        )

    print()
    print("Next step: manually review manual_vetting_sheet.csv")
    print("           then run scripts/run_stats.py for rate statistics.")
    print()
    print("REMINDER: Automated vetting flags are NOT scientific confirmation.")
    print("          All candidates require multi-sector validation.")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    sys.exit(main())
