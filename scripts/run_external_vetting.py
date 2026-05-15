#!/usr/bin/env python3
"""Phase 5C: External catalog crossmatch vetting for AstroHunter KZ.

Loads a vetted candidate table, enriches it with RA/Dec coordinates from
the target and control catalogs, queries VSX, SIMBAD, and the TESS Eclipsing
Binary catalog for each candidate, integrates external flags into the
automated vetting status, saves an enriched table and summary, and generates
a diagnostic figure.

SCIENTIFIC CONSTRAINTS:
- External catalog checks REDUCE false-positive contamination but do NOT
  confirm exocomet detections.
- A catalog match is NOT a definitive false-positive verdict.
- Lack of a catalog match does NOT prove astrophysical validity.
- Remote catalog failures are reported transparently (status = 'failed').
- Manual inspection of every candidate remains mandatory.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from astrohunter.external_vetting import (
    EXTERNAL_VETTER_VERSION,
    FP_CHECK_FAILED,
    FP_KNOWN_VARIABLE,
    FP_NO_MATCH,
    FP_POSSIBLE_EB,
    FP_SIMBAD_PROBLEMATIC,
    STATUS_FAILED,
    STATUS_MATCHED,
    STATUS_NOT_ATTEMPTED,
    STATUS_NOT_FOUND,
    external_check_candidate_table,
    summarize_external_checks,
)
from astrohunter.vetting import apply_external_flags_to_vetting
from astrohunter.plotting import plot_external_catalog_flag_counts

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run_external_vetting")

FIGURES_DIR = Path("results/figures")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Phase 5C: External catalog crossmatch vetting.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument(
        "--candidate-table",
        default="results/tables/vetted_candidate_events_matched_scan.csv",
        help="Vetted candidate table to enrich with external checks.",
    )
    p.add_argument(
        "--target-catalog",
        default="catalogs/target_sample_enriched.csv",
        help="Target catalog CSV with tic_id, ra_deg, dec_deg columns.",
    )
    p.add_argument(
        "--control-pool",
        default="catalogs/control_pool.csv",
        help="Control pool CSV with tic_id, ra_deg, dec_deg columns.",
    )
    p.add_argument(
        "--output",
        default="results/tables/vetted_candidate_events_external_checked.csv",
        help="Output path for externally-checked candidate table.",
    )
    p.add_argument(
        "--summary-output",
        default="results/tables/external_crossmatch_summary.csv",
        help="Output path for catalog-match summary table.",
    )
    p.add_argument(
        "--radius-arcsec",
        type=float,
        default=10.0,
        help="Position-match radius for VSX and SIMBAD (arcsec). "
             "TESS-EB uses 3× this value.",
    )
    p.add_argument(
        "--skip-vsx",
        action="store_true",
        help="Skip VSX queries (offline/test mode).",
    )
    p.add_argument(
        "--skip-simbad",
        action="store_true",
        help="Skip SIMBAD queries (offline/test mode).",
    )
    p.add_argument(
        "--skip-tess-eb",
        action="store_true",
        help="Skip TESS-EB catalog queries (offline/test mode).",
    )
    return p.parse_args(argv)


def _build_coord_lookup(
    target_catalog_path: Path,
    control_pool_path: Path,
) -> dict[int, tuple[float, float]]:
    """Build a {tic_id: (ra_deg, dec_deg)} lookup from target and control catalogs."""
    lookup: dict[int, tuple[float, float]] = {}

    for path in [target_catalog_path, control_pool_path]:
        if not path.exists():
            logger.warning("Catalog not found for coord lookup: %s", path)
            continue
        try:
            df = pd.read_csv(path)
            if "tic_id" not in df.columns:
                logger.warning("No tic_id column in %s; skipping.", path)
                continue
            for _, row in df.iterrows():
                tic = int(row["tic_id"]) if pd.notna(row.get("tic_id")) else None
                ra = float(row["ra_deg"]) if "ra_deg" in df.columns and pd.notna(row.get("ra_deg")) else float("nan")
                dec = float(row["dec_deg"]) if "dec_deg" in df.columns and pd.notna(row.get("dec_deg")) else float("nan")
                if tic is not None:
                    lookup[tic] = (ra, dec)
        except Exception as exc:
            logger.warning("Could not load %s for coord lookup: %s", path, exc)

    return lookup


def _attach_coordinates(
    candidate_df: pd.DataFrame,
    coord_lookup: dict[int, tuple[float, float]],
) -> pd.DataFrame:
    """Add ra_deg and dec_deg columns by joining from coord_lookup via tic_id."""
    result = candidate_df.copy()
    if "ra_deg" not in result.columns:
        result["ra_deg"] = float("nan")
    if "dec_deg" not in result.columns:
        result["dec_deg"] = float("nan")

    n_found = 0
    for idx in result.index:
        tic = result.at[idx, "tic_id"] if "tic_id" in result.columns else None
        try:
            tic_int = int(tic)
        except (TypeError, ValueError):
            continue
        if tic_int in coord_lookup:
            ra, dec = coord_lookup[tic_int]
            result.at[idx, "ra_deg"] = ra
            result.at[idx, "dec_deg"] = dec
            n_found += 1

    logger.info("Coordinates attached for %d / %d candidates.", n_found, len(result))
    if n_found < len(result):
        logger.warning(
            "%d candidates have no RA/Dec — external checks will be not_attempted.",
            len(result) - n_found,
        )
    return result


def _print_results(candidate_df: pd.DataFrame) -> None:
    """Print external check counts by status."""
    total = len(candidate_df)
    print(f"\n  Total candidates checked: {total}")

    for label, col in [
        ("VSX", "vsx_check_status"),
        ("SIMBAD", "simbad_check_status"),
        ("TESS-EB", "tess_eb_check_status"),
    ]:
        if col not in candidate_df.columns:
            print(f"  {label}: column absent")
            continue
        counts = candidate_df[col].value_counts()
        matched = int(counts.get(STATUS_MATCHED, 0))
        not_found = int(counts.get(STATUS_NOT_FOUND, 0))
        failed = int(counts.get(STATUS_FAILED, 0))
        not_attempted = int(counts.get(STATUS_NOT_ATTEMPTED, 0))
        print(
            f"  {label}: matched={matched}  not_found={not_found}  "
            f"failed={failed}  not_attempted={not_attempted}"
        )

    if "external_false_positive_flag" in candidate_df.columns:
        print("\n  External false-positive flags:")
        for val, count in candidate_df["external_false_positive_flag"].value_counts().items():
            print(f"    {val}: {count}")

    if "automated_vetting_status" in candidate_df.columns:
        n_flagged = int((candidate_df["automated_vetting_status"] == "flagged").sum())
        n_pass = int((candidate_df["automated_vetting_status"] == "pass").sum())
        print(f"\n  After external integration:")
        print(f"    automated_vetting_status=pass:    {n_pass}")
        print(f"    automated_vetting_status=flagged: {n_flagged}")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    print("=" * 70)
    print("AstroHunter KZ — Phase 5C: External Catalog Crossmatch Vetting")
    print(f"External vetter version: {EXTERNAL_VETTER_VERSION}")
    print()
    print("SCIENTIFIC CONSTRAINTS:")
    print("  External catalog checks reduce false positives — NOT exocomet confirmation.")
    print("  A catalog match is NOT a definitive false-positive verdict.")
    print("  Lack of match does NOT prove astrophysical validity.")
    print("  Failed/not-attempted queries are reported transparently.")
    print("  Manual inspection of every candidate is still required.")
    print("=" * 70)

    # ------------------------------------------------------------------ load
    cand_path = Path(args.candidate_table)
    if not cand_path.exists():
        logger.error("Candidate table not found: %s", cand_path)
        print(f"\nERROR: Candidate table not found: {cand_path}")
        return 1

    candidate_df = pd.read_csv(cand_path, low_memory=False)
    n_cands = len(candidate_df)
    print(f"\nLoaded {n_cands} candidate(s) from {cand_path}")

    if n_cands == 0:
        logger.warning("Candidate table is empty; saving empty outputs.")
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        candidate_df.to_csv(out_path, index=False)
        summary_df = summarize_external_checks(candidate_df)
        Path(args.summary_output).parent.mkdir(parents=True, exist_ok=True)
        summary_df.to_csv(args.summary_output, index=False)
        print("Empty candidate table — empty outputs saved.")
        return 0

    # ----------------------------------------------------------- coordinates
    coord_lookup = _build_coord_lookup(
        Path(args.target_catalog),
        Path(args.control_pool),
    )
    print(f"Coordinate lookup built: {len(coord_lookup)} TIC IDs with RA/Dec")

    if "ra_deg" not in candidate_df.columns or candidate_df["ra_deg"].isna().all():
        candidate_df = _attach_coordinates(candidate_df, coord_lookup)

    n_with_coords = int(
        candidate_df["ra_deg"].notna().sum()
        if "ra_deg" in candidate_df.columns
        else 0
    )
    print(f"Candidates with usable coordinates: {n_with_coords} / {n_cands}")

    skip_flags = []
    if args.skip_vsx:
        skip_flags.append("VSX")
    if args.skip_simbad:
        skip_flags.append("SIMBAD")
    if args.skip_tess_eb:
        skip_flags.append("TESS-EB")
    if skip_flags:
        print(f"Skipping: {', '.join(skip_flags)} (--skip-* flags set)")

    # -------------------------------------------------------- external checks
    print(f"\nRunning external catalog checks (radius={args.radius_arcsec}\")")
    print("  This may take several seconds per candidate for remote queries.")

    candidate_df = external_check_candidate_table(
        candidate_df,
        radius_arcsec=args.radius_arcsec,
        skip_vsx=args.skip_vsx,
        skip_simbad=args.skip_simbad,
        skip_tess_eb=args.skip_tess_eb,
    )

    # ------------------------------------------- integrate into vetting status
    candidate_df = apply_external_flags_to_vetting(candidate_df)

    # --------------------------------------------------------------- results
    print("\n--- External Crossmatch Results ---")
    _print_results(candidate_df)

    # ------------------------------------------------------------------ save
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    candidate_df.to_csv(out_path, index=False)
    logger.info("Saved externally-checked table: %s (%d rows)", out_path, len(candidate_df))
    print(f"\nSaved enriched candidate table: {out_path}")

    summary_df = summarize_external_checks(candidate_df)
    sum_path = Path(args.summary_output)
    sum_path.parent.mkdir(parents=True, exist_ok=True)
    summary_df.to_csv(sum_path, index=False)
    logger.info("Saved crossmatch summary: %s", sum_path)
    print(f"Saved crossmatch summary:   {sum_path}")

    # --------------------------------------------------------------- figures
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    fig_path = FIGURES_DIR / "external_catalog_flag_counts.png"
    try:
        plot_external_catalog_flag_counts(candidate_df, output_path=fig_path)
        print(f"Saved figure: {fig_path}")
    except Exception as exc:
        logger.warning("External flag counts plot failed: %s", exc)

    print()
    print("REMINDER: Externally-flagged candidates require manual review.")
    print("          Not-found does NOT confirm astrophysical validity.")
    print("          Failed queries must be re-run with network access.")
    print("          Full paper requires manual vetting + follow-up observations.")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    sys.exit(main())
