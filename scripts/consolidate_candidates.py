#!/usr/bin/env python3
"""Phase 5E: Candidate consolidation, per-star summaries, and manual review package.

Loads the externally-checked candidate table, builds star-level summaries,
selects top events per TIC, identifies overtriggered stars, and produces
a prioritised manual review table and diagnostic figures.

SCIENTIFIC CAUTION:
- Consolidation is NOT confirmation of exocomet detections.
- Repeated events on one TIC may indicate stellar variability, systematics,
  or contamination — NOT multiple exocomet transits.
- Priority labels are heuristic classifiers, not scientific verdicts.
- All candidates require manual inspection of individual light curves.
- Star-level summaries are for prioritisation only.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from astrohunter.consolidation import (
    CONSOLIDATION_VERSION,
    PRIORITY_HIGH,
    PRIORITY_LOW,
    PRIORITY_MEDIUM,
    PRIORITY_OVERTRIGGERED,
    attach_scan_status,
    build_manual_review_priority_table,
    identify_overtriggered_stars,
    select_top_event_per_star,
    summarize_candidates_by_star,
    summarize_pass_candidates,
)
from astrohunter.plotting import (
    plot_candidates_per_star,
    plot_pass_candidates_by_role,
    plot_top_scores_by_star,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("consolidate_candidates")

FIGURES_DIR = Path("results/figures")
TABLES_DIR = Path("results/tables")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Phase 5E: Candidate consolidation and manual review package.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument(
        "--candidate-table",
        default="results/tables/full_matched_external_checked_candidates.csv",
        help="Externally-checked candidate table (Phase 5C/5D output).",
    )
    p.add_argument(
        "--scan-status",
        default="results/tables/full_matched_scan_status.csv",
        help="Per-star scan status table (Phase 5D output).",
    )
    p.add_argument(
        "--output-star-summary",
        default="results/tables/full_matched_star_level_summary.csv",
        help="Output path for star-level summary table.",
    )
    p.add_argument(
        "--output-top-events",
        default="results/tables/full_matched_top_event_per_star.csv",
        help="Output path for top event per TIC table.",
    )
    p.add_argument(
        "--output-review-priority",
        default="results/tables/full_matched_manual_review_priority.csv",
        help="Output path for manual review priority table.",
    )
    p.add_argument(
        "--output-overtriggered",
        default="results/tables/full_matched_overtriggered_stars.csv",
        help="Output path for overtriggered stars table.",
    )
    p.add_argument(
        "--max-events-per-star",
        type=int,
        default=3,
        help="Maximum events per TIC in the manual review priority table.",
    )
    p.add_argument(
        "--overtrigger-threshold",
        type=int,
        default=5,
        help="Minimum events per TIC to flag as overtriggered.",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:  # noqa: PLR0915
    args = _parse_args(argv)

    print("=" * 70)
    print("AstroHunter KZ — Phase 5E: Candidate Consolidation")
    print(f"Consolidation version : {CONSOLIDATION_VERSION}")
    print()
    print("SCIENTIFIC CAUTION:")
    print("  Consolidation is NOT confirmation of exocomet detections.")
    print("  Repeated events on one star may indicate variability or systematics.")
    print("  Priority labels are heuristic — all candidates require manual review.")
    print("=" * 70)

    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ load
    cand_path = Path(args.candidate_table)
    if not cand_path.exists():
        logger.error("Candidate table not found: %s", cand_path)
        print(f"\nERROR: Candidate table not found: {cand_path}")
        return 1

    candidate_df = pd.read_csv(cand_path, low_memory=False)
    n_events = len(candidate_df)
    n_unique_tics = candidate_df["tic_id"].nunique() if "tic_id" in candidate_df.columns else 0
    logger.info("Loaded %d events from %d unique TICs.", n_events, n_unique_tics)
    print(f"\nLoaded {n_events} candidate events from {n_unique_tics} unique TICs.")

    # Attach scan status metadata
    scan_path = Path(args.scan_status)
    if scan_path.exists():
        scan_df = pd.read_csv(scan_path)
        candidate_df = attach_scan_status(candidate_df, scan_df)
        logger.info("Scan status attached from %s.", scan_path)
    else:
        logger.warning("Scan status not found: %s", scan_path)

    # ----------------------------------------------------------------- stars
    print(f"\nBuilding star-level summary (overtrigger threshold = {args.overtrigger_threshold})…")
    star_summary = summarize_candidates_by_star(
        candidate_df,
        overtrigger_threshold=args.overtrigger_threshold,
    )

    # ---------------------------------------------------------- top events
    top_events = select_top_event_per_star(candidate_df)

    # Attach priority from star summary to top_events
    priority_map = dict(zip(star_summary["tic_id"], star_summary["recommended_review_priority"]))
    top_events = top_events.copy()
    top_events["recommended_review_priority"] = top_events["tic_id"].map(priority_map).fillna(PRIORITY_LOW)

    # ---------------------------------------------------------- review table
    print(f"Building manual review priority table (max {args.max_events_per_star} events/star)…")
    review_df = build_manual_review_priority_table(
        candidate_df,
        max_events_per_star=args.max_events_per_star,
        overtrigger_threshold=args.overtrigger_threshold,
    )

    # ------------------------------------------------------- overtriggered
    ot_df = identify_overtriggered_stars(candidate_df, threshold_events=args.overtrigger_threshold)

    # -------------------------------------------------------- pass candidates
    pass_df = summarize_pass_candidates(candidate_df)

    # ----------------------------------------------------------------- save
    star_summary.to_csv(args.output_star_summary, index=False)
    logger.info("Star-level summary: %s (%d rows)", args.output_star_summary, len(star_summary))

    top_events.to_csv(args.output_top_events, index=False)
    logger.info("Top events per TIC: %s (%d rows)", args.output_top_events, len(top_events))

    review_df.to_csv(args.output_review_priority, index=False)
    logger.info("Review priority table: %s (%d rows)", args.output_review_priority, len(review_df))

    ot_df.to_csv(args.output_overtriggered, index=False)
    logger.info("Overtriggered stars: %s (%d rows)", args.output_overtriggered, len(ot_df))

    # --------------------------------------------------------------- figures
    prefix = Path(args.output_star_summary).stem.replace("_star_level_summary", "")
    fig_dir = FIGURES_DIR

    cps_fig = fig_dir / f"{prefix}_candidates_per_star.png"
    try:
        plot_candidates_per_star(
            star_summary,
            output_path=cps_fig,
            overtrigger_threshold=args.overtrigger_threshold,
        )
        print(f"Saved figure: {cps_fig}")
    except Exception as exc:  # noqa: BLE001
        logger.warning("candidates_per_star plot failed: %s", exc)

    ts_fig = fig_dir / f"{prefix}_top_scores_by_star.png"
    try:
        plot_top_scores_by_star(top_events, output_path=ts_fig)
        print(f"Saved figure: {ts_fig}")
    except Exception as exc:  # noqa: BLE001
        logger.warning("top_scores_by_star plot failed: %s", exc)

    pc_fig = fig_dir / f"{prefix}_pass_candidates_by_role.png"
    try:
        plot_pass_candidates_by_role(candidate_df, output_path=pc_fig)
        print(f"Saved figure: {pc_fig}")
    except Exception as exc:  # noqa: BLE001
        logger.warning("pass_candidates_by_role plot failed: %s", exc)

    # ------------------------------------------------------------ printout
    print("\n" + "=" * 70)
    print("Phase 5E Consolidation Summary")
    print("=" * 70)
    print(f"  Total candidate events    : {n_events}")
    print(f"  Unique TICs with candidates: {n_unique_tics}")

    n_target_tics = int((star_summary["sample_role"] == "target").sum()) if "sample_role" in star_summary.columns else "?"
    n_control_tics = int((star_summary["sample_role"] == "control").sum()) if "sample_role" in star_summary.columns else "?"
    print(f"  Target  TICs              : {n_target_tics}")
    print(f"  Control TICs              : {n_control_tics}")
    print()

    print(f"  Overtriggered TICs (>= {args.overtrigger_threshold} events): {len(ot_df)}")
    if not ot_df.empty:
        for _, row in ot_df.head(5).iterrows():
            role = row.get("sample_role", "?")
            name = row.get("target_name", row.get("tic_id", "?"))
            print(f"    TIC {row['tic_id']}  ({role})  {row['n_events']} events  [{name}]")
    print()

    priority_counts = star_summary["recommended_review_priority"].value_counts() if "recommended_review_priority" in star_summary.columns else {}
    print("  Review priorities:")
    for label in [PRIORITY_HIGH, PRIORITY_MEDIUM, PRIORITY_LOW, PRIORITY_OVERTRIGGERED]:
        count = int(priority_counts.get(label, 0))
        print(f"    {label:<22s}: {count} star(s)")
    print()

    print(f"  Pass-vetting candidates: {len(pass_df)}")
    if not pass_df.empty and "sample_role" in pass_df.columns:
        for role in ["target", "control"]:
            n = int((pass_df["sample_role"] == role).sum())
            print(f"    {role}: {n}")
        if len(pass_df) > 0:
            print()
            print("  Pass candidate details (automated vetting only — manual review required):")
            show_cols = [c for c in [
                "tic_id", "target_name", "sample_role", "local_snr",
                "final_candidate_score", "external_false_positive_flag",
            ] if c in pass_df.columns]
            for _, row in pass_df.iterrows():
                vals = {c: row.get(c, "?") for c in show_cols}
                snr = f"{vals.get('local_snr', '?'):.2f}" if isinstance(vals.get("local_snr"), float) else "?"
                score = f"{vals.get('final_candidate_score', '?'):.3f}" if isinstance(vals.get("final_candidate_score"), float) else "?"
                print(
                    f"    TIC {vals.get('tic_id','?'):<12} {vals.get('target_name','?'):<20}"
                    f" [{vals.get('sample_role','?')}]  SNR={snr}  score={score}"
                    f"  ext={vals.get('external_false_positive_flag','?')}"
                )
    print()
    print("  Output tables:")
    print(f"    {args.output_star_summary}")
    print(f"    {args.output_top_events}")
    print(f"    {args.output_review_priority}")
    print(f"    {args.output_overtriggered}")
    print()
    print("REMINDERS:")
    print("  All candidates require manual inspection of light curves.")
    print("  Pass candidates on overtriggered stars may be variability/systematics.")
    print("  External catalog matches are heuristic — not scientific verdicts.")
    print("  Full paper requires multi-sector confirmation and expert review.")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    sys.exit(main())
