#!/usr/bin/env python3
"""Phase 5D: Full matched survey pipeline for AstroHunter KZ.

Orchestrates the complete scan → rank → vet → external-check → stats
pipeline across all 28 matched target and control stars.  Supports
resumable execution: stars that succeeded in a previous run are skipped
automatically when --resume is set.

SCIENTIFIC CAUTION:
- All detected events are candidates only.
- Automated detection, ML ranking, and automated vetting are NOT
  scientific confirmation.
- External catalog checks reduce false-positive contamination but do
  NOT confirm exocomet detections.
- Rate statistics on this scan are preliminary.
- Full survey coverage requires network access for all 56 stars.
- Manual inspection of every candidate remains mandatory.
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
import subprocess
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
logger = logging.getLogger("run_full_matched_pipeline")

PIPELINE_VERSION = "phase5d_v1"
TABLES_DIR = Path("results/tables")
FIGURES_DIR = Path("results/figures")
CACHE_DIR = Path("cache/lightcurves")
SCRIPTS_DIR = Path(__file__).resolve().parent

_SCAN_EMPTY_COLUMNS = [
    "pair_id", "sample_role", "tic_id", "target_name", "sector_or_product",
    "event_time_btjd", "depth_ppm", "local_snr", "duration_hours",
    "detector_version", "n_lc_points",
]
_STATUS_COLUMNS = [
    "tic_id", "sample_role", "matched_pair_id", "star_name",
    "attempted", "success", "failure_reason", "n_candidates",
    "cache_used", "scan_timestamp",
]


# --------------------------------------------------------------------------- #
# Pure helper functions — unit-testable, no I/O                               #
# --------------------------------------------------------------------------- #

def _build_scan_status_row(
    tic_id: int,
    sample_role: str,
    matched_pair_id: int,
    star_name: str,
    success: bool,
    failure_reason: str,
    n_candidates: int,
    cache_used: bool,
) -> dict:
    """Build one row for the per-star scan status table."""
    return {
        "tic_id": tic_id,
        "sample_role": sample_role,
        "matched_pair_id": matched_pair_id,
        "star_name": star_name,
        "attempted": True,
        "success": success,
        "failure_reason": failure_reason,
        "n_candidates": n_candidates,
        "cache_used": cache_used,
        "scan_timestamp": datetime.datetime.utcnow().isoformat(),
    }


def _get_resume_tics(status_df: pd.DataFrame) -> set[int]:
    """Return TIC IDs that were successfully scanned in a previous run."""
    if status_df.empty or "success" not in status_df.columns:
        return set()
    done = status_df[status_df["success"] == True]  # noqa: E712
    if "tic_id" not in done.columns:
        return set()
    return {int(t) for t in done["tic_id"].dropna() if pd.notna(t)}


def _deduplicate_scan_list(
    scan_list: list[tuple[int, str, int, str]],
) -> list[tuple[int, str, int, str]]:
    """Remove duplicate TIC IDs from scan_list, keeping the first occurrence."""
    seen: set[int] = set()
    result: list[tuple[int, str, int, str]] = []
    for entry in scan_list:
        tic = entry[0]
        if tic not in seen:
            seen.add(tic)
            result.append(entry)
    return result


def _build_scan_list(
    matched_pairs: pd.DataFrame,
    limit_pairs: int | None,
    include_targets: bool = True,
    include_controls: bool = True,
) -> list[tuple[int, str, int, str]]:
    """Build the (tic_id, role, pair_id, name) scan list from matched_pairs."""
    if limit_pairs is not None:
        matched_pairs = matched_pairs.head(limit_pairs)

    scan_list: list[tuple[int, str, int, str]] = []
    for pair_id, row in matched_pairs.iterrows():
        if include_targets:
            t_tic = int(pd.to_numeric(row.get("target_tic_id"), errors="coerce") or 0)
            if t_tic:
                name = str(row.get("target_name", f"TIC {t_tic}"))
                scan_list.append((t_tic, "target", int(pair_id), name))

        if include_controls:
            c_tic = int(pd.to_numeric(row.get("control_tic_id"), errors="coerce") or 0)
            if c_tic:
                scan_list.append((c_tic, "control", int(pair_id), f"TIC {c_tic}"))

    return _deduplicate_scan_list(scan_list)


def _build_run_summary(
    candidates_df: pd.DataFrame | None,
    status_df: pd.DataFrame,
    rate_summary_df: pd.DataFrame | None,
    phases_run: list[str],
    phases_skipped: list[str],
    output_prefix: str,
) -> dict:
    """Build the pipeline run summary dictionary."""
    def _count(df, role_col, role_val, flag_col, flag_val):
        if df.empty or role_col not in df.columns or flag_col not in df.columns:
            return 0
        mask = (df[role_col] == role_val) & (df[flag_col] == flag_val)  # noqa: E712
        return int(mask.sum())

    n_ts = _count(status_df, "sample_role", "target", "success", True)
    n_tf = _count(status_df, "sample_role", "target", "success", False)
    n_cs = _count(status_df, "sample_role", "control", "success", True)
    n_cf = _count(status_df, "sample_role", "control", "success", False)

    n_cands_total = len(candidates_df) if candidates_df is not None else 0
    n_cands_target = int(
        (candidates_df["sample_role"] == "target").sum()
        if candidates_df is not None and "sample_role" in candidates_df.columns else 0
    )
    n_cands_control = int(
        (candidates_df["sample_role"] == "control").sum()
        if candidates_df is not None and "sample_role" in candidates_df.columns else 0
    )

    summary: dict = {
        "pipeline_version": PIPELINE_VERSION,
        "output_prefix": output_prefix,
        "phases_run": ",".join(phases_run),
        "phases_skipped": ",".join(phases_skipped),
        "n_target_attempted": n_ts + n_tf,
        "n_target_success": n_ts,
        "n_target_failed": n_tf,
        "n_control_attempted": n_cs + n_cf,
        "n_control_success": n_cs,
        "n_control_failed": n_cf,
        "n_candidates_total": n_cands_total,
        "n_candidates_target": n_cands_target,
        "n_candidates_control": n_cands_control,
        "run_timestamp": datetime.datetime.utcnow().isoformat(),
    }

    if rate_summary_df is not None and not rate_summary_df.empty:
        rr_row = rate_summary_df.iloc[0]
        summary["rate_ratio"] = float(rr_row.get("rate_ratio", float("nan")))
        summary["rate_ratio_ci_lo"] = float(rr_row.get("rate_ratio_ci_lo", float("nan")))
        summary["rate_ratio_ci_hi"] = float(rr_row.get("rate_ratio_ci_hi", float("nan")))

    return summary


# --------------------------------------------------------------------------- #
# Local scan implementation (mirrors run_matched_scan._scan_one_star)         #
# --------------------------------------------------------------------------- #

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


# --------------------------------------------------------------------------- #
# Pipeline phase functions                                                     #
# --------------------------------------------------------------------------- #

def _run_scan_phase(
    args: argparse.Namespace,
    scan_list: list[tuple[int, str, int, str]],
    resume_tics: set[int],
    out_scan: Path,
    status_path: Path,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Scan all stars; save per-star status and partial candidates after each star.

    Returns (candidates_df, status_df).
    """
    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # Load any previously-saved candidates and status for resume
    existing_events: list[pd.DataFrame] = []
    existing_status_rows: list[dict] = []

    if args.resume and out_scan.exists():
        try:
            prev = pd.read_csv(out_scan, low_memory=False)
            if not prev.empty:
                existing_events.append(prev)
                logger.info(
                    "Resume: loaded %d existing candidates from %s.", len(prev), out_scan
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not load existing scan output: %s", exc)

    if args.resume and status_path.exists():
        try:
            prev_status = pd.read_csv(status_path)
            existing_status_rows = prev_status.to_dict("records")
            logger.info(
                "Resume: loaded %d existing status rows from %s.",
                len(existing_status_rows), status_path,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not load existing scan status: %s", exc)

    # Filter out already-succeeded stars
    to_scan = [e for e in scan_list if e[0] not in resume_tics]
    skipped = len(scan_list) - len(to_scan)
    if skipped:
        logger.info("Resume: skipping %d previously-succeeded star(s).", skipped)

    new_events: list[pd.DataFrame] = []
    new_status_rows: list[dict] = []

    n_total = len(to_scan)
    for i, (tic_id, role, pair_id, name) in enumerate(to_scan):
        cache_file = CACHE_DIR / f"tic_{tic_id}.parquet"
        cache_used = cache_file.exists()

        logger.info(
            "[%d/%d] %s TIC %d (%s) cache=%s …",
            i + 1, n_total, role.upper(), tic_id, name, cache_used,
        )

        events_df, status_str = _scan_one_star(
            tic_id, role, pair_id, name,
            max_lcs=args.max_lightcurves_per_star,
            sigma_threshold=args.sigma_threshold,
            window_days=args.window_days,
        )

        success = (
            events_df is not None
            or status_str == "no_candidates"
        )
        n_cands = len(events_df) if events_df is not None else 0
        failure_reason = "" if success else status_str

        new_status_rows.append(_build_scan_status_row(
            tic_id=tic_id,
            sample_role=role,
            matched_pair_id=pair_id,
            star_name=name,
            success=success,
            failure_reason=failure_reason,
            n_candidates=n_cands,
            cache_used=cache_used,
        ))

        if events_df is not None and not events_df.empty:
            new_events.append(events_df)
            logger.info("  → %d candidate(s).", n_cands)
        elif success:
            logger.info("  → no candidates above threshold.")
        else:
            logger.warning("  → failed (%s).", status_str)

        # Checkpoint after each star
        all_status = existing_status_rows + new_status_rows
        pd.DataFrame(all_status).to_csv(status_path, index=False)

        all_events_so_far = existing_events + new_events
        if all_events_so_far:
            pd.concat(all_events_so_far, ignore_index=True).to_csv(out_scan, index=False)

    # Build final DataFrames
    all_events = existing_events + new_events
    if all_events:
        candidates_df = pd.concat(all_events, ignore_index=True)
    else:
        candidates_df = pd.DataFrame(columns=_SCAN_EMPTY_COLUMNS)

    all_status_rows = existing_status_rows + new_status_rows
    status_df = (
        pd.DataFrame(all_status_rows)
        if all_status_rows
        else pd.DataFrame(columns=_STATUS_COLUMNS)
    )

    candidates_df.to_csv(out_scan, index=False)
    status_df.to_csv(status_path, index=False)
    logger.info(
        "Scan done: %d candidates, %d status rows.", len(candidates_df), len(status_df)
    )

    # Save .meta.json for downstream stats exposure estimation
    success_col = status_df["success"] == True  # noqa: E712
    t_mask = (status_df["sample_role"] == "target") & success_col
    c_mask = (status_df["sample_role"] == "control") & success_col
    t_success = [int(x) for x in status_df.loc[t_mask, "tic_id"].tolist()]
    c_success = [int(x) for x in status_df.loc[c_mask, "tic_id"].tolist()]
    t_fail = int(((status_df["sample_role"] == "target") & ~success_col).sum())
    c_fail = int(((status_df["sample_role"] == "control") & ~success_col).sum())

    meta = {
        "n_target_attempted": len(t_success) + t_fail,
        "n_control_attempted": len(c_success) + c_fail,
        "n_target_success": len(t_success),
        "n_control_success": len(c_success),
        "n_target_failed": t_fail,
        "n_control_failed": c_fail,
        "target_tics_scanned": t_success,
        "control_tics_scanned": c_success,
        "sigma_threshold": args.sigma_threshold,
        "window_days": args.window_days,
        "max_lightcurves_per_star": args.max_lightcurves_per_star,
        "pipeline_version": PIPELINE_VERSION,
        "detector_version": DETECTOR_VERSION,
    }
    meta_path = out_scan.with_suffix(".meta.json")
    with open(meta_path, "w") as fh:
        json.dump(meta, fh, indent=2)
    logger.info("Saved scan metadata: %s", meta_path)

    return candidates_df, status_df


def _run_subscript(script_name: str, argv: list[str]) -> int:
    """Run a sibling script as a subprocess; return its exit code."""
    cmd = [sys.executable, str(SCRIPTS_DIR / script_name)] + argv
    logger.info("Running: %s", " ".join(str(c) for c in cmd))
    result = subprocess.run(cmd, check=False)
    return result.returncode


def _run_ranking_phase(
    args: argparse.Namespace,
    in_path: Path,
    out_ranked: Path,
    out_eval: Path,
) -> int:
    return _run_subscript("rank_matched_scan.py", [
        "--injection-table", args.injection_table,
        "--candidate-table", str(in_path),
        "--output-ranked", str(out_ranked),
        "--output-eval", str(out_eval),
        "--random-seed", str(args.random_seed),
    ])


def _run_vetting_phase(
    args: argparse.Namespace,
    in_path: Path,
    out_vetted: Path,
    out_manual: Path,
) -> int:
    return _run_subscript("run_vetting.py", [
        "--candidate-table", str(in_path),
        "--output-vetted", str(out_vetted),
        "--output-manual", str(out_manual),
        "--snr-threshold", str(args.snr_threshold),
    ])


def _run_external_phase(
    args: argparse.Namespace,
    in_path: Path,
    out_external: Path,
    out_ext_summary: Path,
) -> int:
    argv = [
        "--candidate-table", str(in_path),
        "--target-catalog", args.target_catalog,
        "--control-pool", args.control_pool,
        "--output", str(out_external),
        "--summary-output", str(out_ext_summary),
        "--radius-arcsec", str(args.external_radius_arcsec),
    ]
    if args.skip_vsx:
        argv.append("--skip-vsx")
    if args.skip_simbad:
        argv.append("--skip-simbad")
    if args.skip_tess_eb:
        argv.append("--skip-tess-eb")
    return _run_subscript("run_external_vetting.py", argv)


def _run_stats_phase(
    args: argparse.Namespace,
    in_path: Path,
    out_stats: Path,
    scan_meta_path: Path,
) -> tuple[int, pd.DataFrame | None]:
    argv = [
        "--vetted-candidates", str(in_path),
        "--matched-pairs", args.matched_pairs,
        "--output", str(out_stats),
        "--n-bootstrap", "1000",
        "--random-seed", str(args.random_seed),
    ]
    if scan_meta_path.exists():
        argv.extend(["--scan-meta", str(scan_meta_path)])
    rc = _run_subscript("run_stats.py", argv)
    rate_df = None
    if rc == 0 and out_stats.exists():
        try:
            rate_df = pd.read_csv(out_stats)
        except Exception:  # noqa: BLE001
            pass
    return rc, rate_df


# --------------------------------------------------------------------------- #
# Argument parser                                                              #
# --------------------------------------------------------------------------- #

def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Phase 5D: Full matched survey pipeline — "
            "scan → rank → vet → external-check → stats."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # Input catalogs
    p.add_argument("--matched-pairs", default="catalogs/matched_pairs.csv")
    p.add_argument("--target-catalog", default="catalogs/target_sample_enriched.csv")
    p.add_argument("--control-pool", default="catalogs/control_pool.csv")
    p.add_argument(
        "--injection-table",
        default="results/tables/injection_recovery.csv",
        help="Injection-recovery table for ML ranking.",
    )

    # Output
    p.add_argument(
        "--output-prefix",
        default="full_matched",
        help="Prefix for all output file names.",
    )

    # Scan parameters
    p.add_argument("--max-lightcurves-per-star", type=int, default=1)
    p.add_argument("--sigma-threshold", type=float, default=4.0)
    p.add_argument("--window-days", type=float, default=1.0)

    # Vetting / stats parameters
    p.add_argument("--snr-threshold", type=float, default=5.0)
    p.add_argument("--random-seed", type=int, default=42)

    # External vetting parameters
    p.add_argument("--external-radius-arcsec", type=float, default=10.0)
    p.add_argument("--skip-vsx", action="store_true")
    p.add_argument("--skip-simbad", action="store_true")
    p.add_argument("--skip-tess-eb", action="store_true")

    # Pipeline control
    p.add_argument(
        "--resume",
        action="store_true",
        help="Skip stars that were already successfully scanned.",
    )
    p.add_argument("--skip-scan", action="store_true",
                   help="Skip the scan phase; load existing scan output.")
    p.add_argument("--skip-ranking", action="store_true",
                   help="Skip ML ranking; load existing ranked output.")
    p.add_argument("--skip-vetting", action="store_true",
                   help="Skip automated vetting; load existing vetted output.")
    p.add_argument("--skip-external", action="store_true",
                   help="Skip external catalog crossmatch.")
    p.add_argument("--skip-stats", action="store_true",
                   help="Skip rate statistics computation.")
    p.add_argument(
        "--limit-pairs",
        type=int,
        default=None,
        help="Process only the first N matched pairs (for testing).",
    )

    return p.parse_args(argv)


# --------------------------------------------------------------------------- #
# Main                                                                        #
# --------------------------------------------------------------------------- #

def main(argv: list[str] | None = None) -> int:  # noqa: PLR0912, PLR0915
    args = _parse_args(argv)
    prefix = args.output_prefix

    print("=" * 70)
    print("AstroHunter KZ — Phase 5D: Full Matched Survey Pipeline")
    print(f"Pipeline version : {PIPELINE_VERSION}")
    print(f"Output prefix    : {prefix}")
    print()
    print("SCIENTIFIC CAUTION:")
    print("  All detected events are candidates only.")
    print("  Rate statistics are preliminary until full survey coverage.")
    print("  Manual inspection of every candidate remains mandatory.")
    print("=" * 70)

    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ paths
    out_scan = TABLES_DIR / f"{prefix}_detector_candidates.csv"
    out_scan_meta = out_scan.with_suffix(".meta.json")
    status_path = TABLES_DIR / f"{prefix}_scan_status.csv"
    out_ranked = TABLES_DIR / f"{prefix}_ranked_candidates.csv"
    out_eval = TABLES_DIR / f"{prefix}_ml_eval.csv"
    out_vetted = TABLES_DIR / f"{prefix}_vetted_candidates.csv"
    out_manual = TABLES_DIR / f"{prefix}_manual_vetting_sheet.csv"
    out_external = TABLES_DIR / f"{prefix}_external_checked_candidates.csv"
    out_ext_summary = TABLES_DIR / f"{prefix}_external_crossmatch_summary.csv"
    out_stats = TABLES_DIR / f"{prefix}_rate_ratio_summary.csv"
    out_run_summary = TABLES_DIR / f"{prefix}_run_summary.csv"

    # ----------------------------------------------------------- load pairs
    pairs_path = Path(args.matched_pairs)
    if not pairs_path.exists():
        logger.error("matched_pairs.csv not found: %s", pairs_path)
        print(f"\nERROR: matched_pairs.csv not found: {pairs_path}")
        return 1

    matched_pairs = pd.read_csv(pairs_path)
    scan_list = _build_scan_list(matched_pairs, args.limit_pairs)
    n_targets = sum(1 for _, role, _, _ in scan_list if role == "target")
    n_controls = sum(1 for _, role, _, _ in scan_list if role == "control")

    print(
        f"\nScan plan: {n_targets} unique target stars, "
        f"{n_controls} unique control stars  ({len(scan_list)} total)"
    )
    if args.limit_pairs:
        print(f"  (limited to first {args.limit_pairs} pairs via --limit-pairs)")

    # ------------------------------------------------- resume: load done TICs
    resume_tics: set[int] = set()
    if args.resume and status_path.exists():
        try:
            existing_status = pd.read_csv(status_path)
            resume_tics = _get_resume_tics(existing_status)
            if resume_tics:
                print(f"  Resume mode: {len(resume_tics)} previously-succeeded star(s) will be skipped.")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not load status for resume: %s", exc)

    phases_run: list[str] = []
    phases_skipped: list[str] = []
    status_df = pd.DataFrame(columns=_STATUS_COLUMNS)
    rate_summary_df: pd.DataFrame | None = None

    # ================================================================== SCAN
    if args.skip_scan:
        phases_skipped.append("scan")
        print("\n[SKIP] Scan phase (--skip-scan).")
        candidates_df = pd.DataFrame(columns=_SCAN_EMPTY_COLUMNS)
        if out_scan.exists():
            try:
                candidates_df = pd.read_csv(out_scan, low_memory=False)
                print(f"  Loaded existing {len(candidates_df)} candidate(s) from {out_scan}")
            except Exception as exc:  # noqa: BLE001
                logger.warning("Could not load existing scan: %s", exc)
        if status_path.exists():
            try:
                status_df = pd.read_csv(status_path)
            except Exception:  # noqa: BLE001
                pass
    else:
        print("\n[PHASE 1/5] Scan: detecting asymmetric dip candidates …")
        candidates_df, status_df = _run_scan_phase(
            args, scan_list, resume_tics, out_scan, status_path
        )
        phases_run.append("scan")
        print(f"  → {len(candidates_df)} candidate(s) detected.")

    logger.info("Scan phase output: %d candidates.", len(candidates_df))

    # ============================================================== RANKING
    # Determine which table goes into ranking
    ranking_in = out_scan
    if args.skip_ranking:
        phases_skipped.append("ranking")
        print("\n[SKIP] Ranking phase (--skip-ranking).")
        if not out_ranked.exists():
            logger.warning("--skip-ranking but no existing ranked table at %s.", out_ranked)
        else:
            print(f"  Using existing ranked table: {out_ranked}")
    else:
        print("\n[PHASE 2/5] Ranking: ML scoring of candidate events …")
        inj_path = Path(args.injection_table)
        if not inj_path.exists():
            logger.error("Injection table not found: %s", inj_path)
            print(f"\nERROR: Injection table not found: {inj_path}")
            print("  Run scripts/run_injection_recovery.py first.")
            print("  Skipping ranking — downstream phases will use unranked candidates.")
            phases_skipped.append("ranking")
        else:
            rc = _run_ranking_phase(args, ranking_in, out_ranked, out_eval)
            if rc != 0:
                logger.warning("Ranking phase exited with code %d; continuing.", rc)
            else:
                phases_run.append("ranking")
                print(f"  → Ranked table saved: {out_ranked}")

    # ============================================================== VETTING
    vetting_in = out_ranked if out_ranked.exists() else ranking_in
    if args.skip_vetting:
        phases_skipped.append("vetting")
        print("\n[SKIP] Vetting phase (--skip-vetting).")
        if not out_vetted.exists():
            logger.warning("--skip-vetting but no existing vetted table at %s.", out_vetted)
        else:
            print(f"  Using existing vetted table: {out_vetted}")
    else:
        print("\n[PHASE 3/5] Vetting: applying automated heuristic flags …")
        rc = _run_vetting_phase(args, vetting_in, out_vetted, out_manual)
        if rc != 0:
            logger.warning("Vetting phase exited with code %d; continuing.", rc)
        else:
            phases_run.append("vetting")
            print(f"  → Vetted table saved: {out_vetted}")

    # ========================================================== EXTERNAL
    external_in = out_vetted if out_vetted.exists() else vetting_in
    if args.skip_external:
        phases_skipped.append("external")
        print("\n[SKIP] External vetting phase (--skip-external).")
    else:
        print("\n[PHASE 4/5] External: crossmatching VSX / SIMBAD / TESS-EB …")
        rc = _run_external_phase(args, external_in, out_external, out_ext_summary)
        if rc != 0:
            logger.warning("External vetting phase exited with code %d; continuing.", rc)
        else:
            phases_run.append("external")
            print(f"  → Externally-checked table saved: {out_external}")

    # ================================================================ STATS
    stats_in = (
        out_external if out_external.exists()
        else (out_vetted if out_vetted.exists()
              else external_in)
    )
    if args.skip_stats:
        phases_skipped.append("stats")
        print("\n[SKIP] Stats phase (--skip-stats).")
    else:
        print("\n[PHASE 5/5] Statistics: computing target/control rate ratio …")
        rc, rate_summary_df = _run_stats_phase(
            args, stats_in, out_stats, out_scan_meta
        )
        if rc != 0:
            logger.warning("Stats phase exited with code %d; continuing.", rc)
        else:
            phases_run.append("stats")
            print(f"  → Rate-ratio summary saved: {out_stats}")

    # ========================================================== RUN SUMMARY
    candidates_for_summary = candidates_df if not candidates_df.empty else None
    if stats_in.exists():
        try:
            final_cands = pd.read_csv(stats_in, low_memory=False)
            if not final_cands.empty:
                candidates_for_summary = final_cands
        except Exception:  # noqa: BLE001
            pass

    run_summary = _build_run_summary(
        candidates_df=candidates_for_summary,
        status_df=status_df,
        rate_summary_df=rate_summary_df,
        phases_run=phases_run,
        phases_skipped=phases_skipped,
        output_prefix=prefix,
    )
    run_summary_df = pd.DataFrame([run_summary])
    run_summary_df.to_csv(out_run_summary, index=False)
    logger.info("Saved run summary: %s", out_run_summary)

    # ============================================================= PRINTOUT
    print("\n" + "=" * 70)
    print("Phase 5D Full Matched Pipeline — Run Summary")
    print("=" * 70)
    print(f"  Phases run     : {', '.join(phases_run) or 'none'}")
    print(f"  Phases skipped : {', '.join(phases_skipped) or 'none'}")
    print()
    print(f"  Target  stars scanned ok : {run_summary['n_target_success']}")
    print(f"  Target  stars failed     : {run_summary['n_target_failed']}")
    print(f"  Control stars scanned ok : {run_summary['n_control_success']}")
    print(f"  Control stars failed     : {run_summary['n_control_failed']}")
    print()
    print(f"  Candidates (target) : {run_summary['n_candidates_target']}")
    print(f"  Candidates (control): {run_summary['n_candidates_control']}")
    print(f"  Candidates (total)  : {run_summary['n_candidates_total']}")
    if rate_summary_df is not None:
        rr = run_summary.get("rate_ratio", float("nan"))
        rr_lo = run_summary.get("rate_ratio_ci_lo", float("nan"))
        rr_hi = run_summary.get("rate_ratio_ci_hi", float("nan"))
        if np.isfinite(rr):
            print(f"  Rate ratio (T/C)    : {rr:.3f}  [{rr_lo:.3f}, {rr_hi:.3f}]")
        else:
            print("  Rate ratio (T/C)    : undefined (control count = 0)")
    print()
    print(f"  Run summary  : {out_run_summary}")
    print(f"  Scan status  : {status_path}")
    print()
    print("REMINDERS:")
    print("  Rate statistics are PRELIMINARY. N < 10 candidates = unstable.")
    print("  All candidates require manual inspection.")
    print("  External catalog matches are heuristic, not scientific verdicts.")
    print("  Full paper requires manual vetting + multi-sector confirmation.")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    sys.exit(main())
