#!/usr/bin/env python3
"""Phase 5F: Build manual review gallery and candidate inspection package.

Loads the Phase 5E consolidated candidate tables, selects events for visual
inspection, generates per-TIC light-curve plots, saves a disposition template
for human reviewers, and produces a priority overview figure.

SCIENTIFIC CAUTION:
- Visual review does NOT confirm exocomet detections.
- Disposition labels produced here are preliminary.
- TIC 444335503 (control, 20 events) must be treated as likely overtriggered
  until all events have been individually inspected.
- Final paper/report requires completed manual review, multi-sector
  confirmation, and expert validation.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from astrohunter.inspection import (
    INSPECTION_VERSION,
    MANUAL_LABEL_ALLOWED,
    build_inspection_target_list,
    create_disposition_template,
    create_star_event_gallery,
    load_cached_lightcurve_for_tic,
)
from astrohunter.plotting import plot_manual_review_priority_overview

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("build_manual_review_gallery")

FIGURES_DIR = Path("results/figures")
TABLES_DIR = Path("results/tables")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Phase 5F: Build manual review gallery and inspection package.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument(
        "--candidate-table",
        default="results/tables/full_matched_external_checked_candidates.csv",
        help="Full event-level candidate table (Phase 5D/5E output).",
    )
    p.add_argument(
        "--priority-table",
        default="results/tables/full_matched_manual_review_priority.csv",
        help="Manual review priority table (Phase 5E output).",
    )
    p.add_argument(
        "--star-summary",
        default="results/tables/full_matched_star_level_summary.csv",
        help="Star-level summary table (Phase 5E output).",
    )
    p.add_argument(
        "--overtriggered",
        default="results/tables/full_matched_overtriggered_stars.csv",
        help="Overtriggered-star table (Phase 5E output).",
    )
    p.add_argument(
        "--output-dir",
        default="results/candidates/manual_review_gallery",
        help="Root directory for per-TIC gallery folders.",
    )
    p.add_argument(
        "--disposition-output",
        default="results/tables/full_matched_manual_review_disposition_template.csv",
        help="Output path for the disposition template CSV.",
    )
    p.add_argument(
        "--inspection-targets-output",
        default="results/tables/full_matched_inspection_targets.csv",
        help="Output path for the inspection target list CSV.",
    )
    p.add_argument(
        "--max-events-per-star",
        type=int,
        default=5,
        help="Maximum events per TIC in the inspection list.",
    )
    p.add_argument(
        "--window-days",
        type=float,
        default=1.0,
        help="Total window width (days) for event zoom plots.",
    )
    p.add_argument(
        "--cache-dir",
        default="cache/lightcurves",
        help="Directory containing cached Parquet light curves.",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:  # noqa: PLR0912, PLR0915
    args = _parse_args(argv)

    print("=" * 70)
    print("AstroHunter KZ — Phase 5F: Manual Review Gallery")
    print(f"Inspection version : {INSPECTION_VERSION}")
    print()
    print("SCIENTIFIC CAUTION:")
    print("  Visual review does NOT confirm exocomet detections.")
    print("  Disposition labels are preliminary.")
    print("  TIC 444335503 must be treated as likely overtriggered until inspected.")
    print("  Final paper requires completed review and expert validation.")
    print("=" * 70)

    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    Path(args.output_dir).mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ load
    cand_path = Path(args.candidate_table)
    if not cand_path.exists():
        logger.error("Candidate table not found: %s", cand_path)
        print(f"\nERROR: Candidate table not found: {cand_path}")
        return 1

    candidate_df = pd.read_csv(cand_path, low_memory=False)
    logger.info("Loaded %d events from %s.", len(candidate_df), cand_path)
    print(f"\nLoaded {len(candidate_df)} candidate events.")

    priority_df = pd.DataFrame()
    pri_path = Path(args.priority_table)
    if pri_path.exists():
        priority_df = pd.read_csv(pri_path, low_memory=False)
        logger.info("Priority table: %d rows.", len(priority_df))
    else:
        logger.warning("Priority table not found: %s — will use empty.", pri_path)

    star_summary_df = pd.DataFrame()
    ss_path = Path(args.star_summary)
    if ss_path.exists():
        star_summary_df = pd.read_csv(ss_path)
        logger.info("Star summary: %d rows.", len(star_summary_df))
    else:
        logger.warning("Star summary not found: %s.", ss_path)

    ot_df = pd.DataFrame()
    ot_path = Path(args.overtriggered)
    if ot_path.exists():
        ot_df = pd.read_csv(ot_path)
        logger.info("Overtriggered stars: %d rows.", len(ot_df))
    else:
        logger.warning("Overtriggered table not found: %s.", ot_path)

    # ------------------------------------------------------ inspection list
    print(f"\nBuilding inspection target list (max {args.max_events_per_star} events/star)…")
    inspection_df = build_inspection_target_list(
        candidate_df=candidate_df,
        priority_df=priority_df,
        overtriggered_df=ot_df,
        max_events_per_star=args.max_events_per_star,
    )

    n_inspection_tics = inspection_df["tic_id"].nunique() if not inspection_df.empty else 0
    n_inspection_events = len(inspection_df)
    print(f"  → {n_inspection_tics} TICs selected, {n_inspection_events} events total.")

    if not inspection_df.empty and "inspection_reason" in inspection_df.columns:
        for reason in ["pass_vetting", "medium_priority", "overtriggered_top5", "target_top_event"]:
            n = int(inspection_df["inspection_reason"].str.contains(reason).sum())
            print(f"     {reason:<26}: {n} event(s)")

    # Save inspection targets
    inspection_df.to_csv(args.inspection_targets_output, index=False)
    logger.info("Inspection targets: %s (%d rows)", args.inspection_targets_output, n_inspection_events)
    print(f"\nSaved inspection targets: {args.inspection_targets_output}")

    # ------------------------------------------------- disposition template
    disp_df = create_disposition_template(inspection_df)
    disp_df.to_csv(args.disposition_output, index=False)
    logger.info("Disposition template: %s (%d rows)", args.disposition_output, len(disp_df))
    print(f"Saved disposition template: {args.disposition_output}")
    print(f"  Allowed manual_label values: {', '.join(MANUAL_LABEL_ALLOWED)}")

    # -------------------------------------------------------- priority figure
    overview_fig_path = FIGURES_DIR / "manual_review_priority_overview.png"
    try:
        plot_manual_review_priority_overview(
            star_summary_df=star_summary_df,
            output_path=overview_fig_path,
        )
        print(f"Saved priority overview figure: {overview_fig_path}")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Priority overview figure failed: %s", exc)

    # --------------------------------------------------------- per-TIC gallery
    print(f"\nGenerating gallery for {n_inspection_tics} TIC(s) in {args.output_dir}/ …")

    total_plots = 0
    tic_results: list[dict] = []

    if inspection_df.empty:
        print("  (No inspection events — gallery is empty.)")
    else:
        inspection_tics = inspection_df["tic_id"].unique()
        for tic_id in inspection_tics:
            tic_events = inspection_df[inspection_df["tic_id"] == tic_id].copy()
            role = tic_events["sample_role"].iloc[0] if "sample_role" in tic_events.columns else "?"
            name = tic_events["target_name"].iloc[0] if "target_name" in tic_events.columns else f"TIC {tic_id}"
            priority = (
                tic_events["recommended_review_priority"].iloc[0]
                if "recommended_review_priority" in tic_events.columns
                else "?"
            )
            logger.info(
                "Gallery TIC %s [%s] %s  priority=%s  %d events",
                tic_id, role, name, priority, len(tic_events),
            )

            lc_df = load_cached_lightcurve_for_tic(tic_id, cache_dir=args.cache_dir)
            has_lc = lc_df is not None and not lc_df.empty

            try:
                created = create_star_event_gallery(
                    tic_id=tic_id,
                    events_df=tic_events,
                    lc_df=lc_df,
                    output_dir=args.output_dir,
                    window_days=args.window_days,
                )
                n_plots = sum(1 for p in created if str(p).endswith(".png"))
                total_plots += n_plots
                tic_results.append({
                    "tic_id": tic_id,
                    "sample_role": role,
                    "target_name": name,
                    "recommended_review_priority": priority,
                    "n_inspection_events": len(tic_events),
                    "n_plots_generated": n_plots,
                    "has_cached_lc": has_lc,
                    "gallery_dir": str(Path(args.output_dir) / f"tic_{tic_id}"),
                })
            except Exception as exc:  # noqa: BLE001
                logger.error("Gallery failed for TIC %s: %s", tic_id, exc)
                tic_results.append({
                    "tic_id": tic_id,
                    "sample_role": role,
                    "target_name": name,
                    "recommended_review_priority": priority,
                    "n_inspection_events": len(tic_events),
                    "n_plots_generated": 0,
                    "has_cached_lc": has_lc,
                    "gallery_dir": "ERROR",
                })

    # ------------------------------------------------------------ printout
    print("\n" + "=" * 70)
    print("Phase 5F Gallery Summary")
    print("=" * 70)
    print(f"  TICs selected for inspection  : {n_inspection_tics}")
    print(f"  Total inspection events        : {n_inspection_events}")
    print(f"  Total plots generated          : {total_plots}")
    print(f"  Disposition template           : {args.disposition_output}")
    print(f"  Priority overview figure       : {overview_fig_path}")
    print()
    print("  Per-TIC summary:")
    for r in tic_results:
        lc_flag = "LC✓" if r["has_cached_lc"] else "LC✗"
        print(
            f"    TIC {r['tic_id']:<12} [{r['sample_role']:<7}]  {r['target_name']:<22}"
            f"  {r['recommended_review_priority']:<22}  "
            f"{r['n_inspection_events']} events  "
            f"{r['n_plots_generated']} plots  {lc_flag}"
        )
    print()
    print("  Gallery root: " + args.output_dir)
    print()
    print("REMINDERS:")
    print("  Visual review does NOT confirm exocomet detections.")
    print("  TIC 444335503 is overtriggered — inspect all events for variability.")
    print("  Fill manual_label column in disposition template after review.")
    print(f"  Allowed labels: {', '.join(MANUAL_LABEL_ALLOWED)}")
    print("  Final paper requires multi-sector confirmation and expert review.")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    sys.exit(main())
