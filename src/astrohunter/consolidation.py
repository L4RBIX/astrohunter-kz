"""Phase 5E: Candidate consolidation, per-star summaries, and review prioritisation.

Converts event-level candidate tables into star-level summaries and human-review
packages.  These are prioritisation tools only — they do NOT confirm exocomet
detections and do NOT replace manual inspection of individual light curves.

Scientific constraints:
- Repeated events on one TIC may reflect stellar variability, systematics, or
  contamination, not multiple exocomet transits.
- Stars flagged as overtriggered require special scrutiny before any event on
  them is accepted as a candidate.
- Priority labels are heuristic classifiers, not scientific verdicts.
- All candidates require manual review regardless of priority label.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

CONSOLIDATION_VERSION = "phase5e_v1"

# Priority labels (ordered high → low concern)
PRIORITY_HIGH = "high"
PRIORITY_MEDIUM = "medium"
PRIORITY_LOW = "low"
PRIORITY_OVERTRIGGERED = "overtriggered_review"

# External false-positive flags that indicate meaningful contamination concern
_CONCERN_FLAGS = frozenset({
    "known_variable_match",
    "possible_eclipsing_binary_match",
    "simbad_nonstellar_or_problematic_type",
})

# Heuristic flag columns (all boolean in the candidate table)
_VETTING_FLAG_COLS = [
    "flag_low_snr",
    "flag_edge_event",
    "flag_single_point_like",
    "flag_likely_flare_shape",
    "flag_low_delta_chi2",
    "flag_poor_asymmetry_fit",
]

# Minimum score threshold for medium priority
_MEDIUM_SCORE_THRESHOLD = 0.65
_MEDIUM_SNR_THRESHOLD = 6.0


def _safe_bool_any(series: pd.Series, value: Any = True) -> bool:
    """Return True if any element of series equals value (handles bool/str dtype)."""
    try:
        return bool((series == value).any())
    except Exception:  # noqa: BLE001
        return False


def _flag_count_per_row(candidate_df: pd.DataFrame) -> pd.Series:
    """Count how many vetting flags are set per row."""
    present = [c for c in _VETTING_FLAG_COLS if c in candidate_df.columns]
    if not present:
        return pd.Series(0, index=candidate_df.index)
    flag_df = candidate_df[present].copy()
    for c in present:
        flag_df[c] = flag_df[c].map(lambda v: bool(v) if not isinstance(v, bool) else v)
    return flag_df.sum(axis=1)


def _assign_star_priority(
    n_events: int,
    n_pass: int,
    has_concern_flag: bool,
    has_tess_eb: bool,
    max_score: float,
    max_snr: float,
    n_external_flags: int,
    overtrigger_threshold: int,
) -> str:
    """Return recommended review priority for one star.

    Rules (evaluated in order):
    1. overtriggered_review — star has >= overtrigger_threshold events
    2. high — at least one pass event, no concern-level external flag
    3. medium — pass event with mild external concern, OR high score/SNR with no flags
    4. low — everything else
    """
    if n_events >= overtrigger_threshold:
        return PRIORITY_OVERTRIGGERED
    if n_pass > 0 and not has_concern_flag and not has_tess_eb:
        return PRIORITY_HIGH
    if n_pass > 0:
        return PRIORITY_MEDIUM
    if (
        np.isfinite(max_score)
        and max_score >= _MEDIUM_SCORE_THRESHOLD
        and n_external_flags == 0
        and not has_concern_flag
    ):
        return PRIORITY_MEDIUM
    if (
        np.isfinite(max_snr)
        and max_snr >= _MEDIUM_SNR_THRESHOLD
        and n_external_flags == 0
        and not has_concern_flag
    ):
        return PRIORITY_MEDIUM
    return PRIORITY_LOW


def summarize_candidates_by_star(
    candidate_df: pd.DataFrame,
    overtrigger_threshold: int = 5,
) -> pd.DataFrame:
    """Aggregate event-level candidates into one row per TIC (star-level summary).

    Does NOT modify or remove rows from the input.  Returns a new DataFrame
    with one row per unique tic_id.

    Parameters
    ----------
    candidate_df:
        Event-level candidate table (Phase 5C or 5D output).
    overtrigger_threshold:
        Stars with >= this many events are labelled overtriggered_review.

    Returns
    -------
    pd.DataFrame with columns: tic_id, target_name, sample_role, n_events,
        n_pass_automated_vetting, n_external_flags, max_final_candidate_score,
        max_local_snr, median_local_snr, max_depth_ppm, min_event_time_btjd,
        max_event_time_btjd, has_known_variable_match, has_tess_eb_match,
        recommended_review_priority, consolidation_version.
    """
    if candidate_df.empty:
        return pd.DataFrame(columns=[
            "tic_id", "target_name", "sample_role", "n_events",
            "n_pass_automated_vetting", "n_external_flags",
            "max_final_candidate_score", "max_local_snr", "median_local_snr",
            "max_depth_ppm", "min_event_time_btjd", "max_event_time_btjd",
            "has_known_variable_match", "has_tess_eb_match",
            "recommended_review_priority", "consolidation_version",
        ])

    def _agg(grp: pd.DataFrame) -> pd.Series:
        # Core identifiers (take first row value — stable within a TIC)
        name = str(grp["target_name"].iloc[0]) if "target_name" in grp.columns else f"TIC {grp.name}"
        role = str(grp["sample_role"].iloc[0]) if "sample_role" in grp.columns else "unknown"

        n_events = len(grp)

        n_pass = int((grp["automated_vetting_status"] == "pass").sum()) if "automated_vetting_status" in grp.columns else 0

        # External flags: rows where external concern was raised
        n_ext = 0
        if "flag_external_catalog_match" in grp.columns:
            n_ext = int(grp["flag_external_catalog_match"].map(
                lambda v: bool(v) if not isinstance(v, bool) else v
            ).sum())

        # Score / SNR
        score_col = "final_candidate_score"
        max_score = float(grp[score_col].max()) if score_col in grp.columns and not grp[score_col].isna().all() else float("nan")

        snr_col = "local_snr"
        max_snr = float(grp[snr_col].max()) if snr_col in grp.columns and not grp[snr_col].isna().all() else float("nan")
        med_snr = float(grp[snr_col].median()) if snr_col in grp.columns and not grp[snr_col].isna().all() else float("nan")

        depth_col = "depth_ppm"
        max_depth = float(grp[depth_col].max()) if depth_col in grp.columns and not grp[depth_col].isna().all() else float("nan")

        time_col = "event_time_btjd"
        min_time = float(grp[time_col].min()) if time_col in grp.columns and not grp[time_col].isna().all() else float("nan")
        max_time = float(grp[time_col].max()) if time_col in grp.columns and not grp[time_col].isna().all() else float("nan")

        # External catalog concern flags
        has_concern = False
        if "external_false_positive_flag" in grp.columns:
            has_concern = bool(grp["external_false_positive_flag"].isin(_CONCERN_FLAGS).any())

        has_tess_eb = False
        if "tess_eb_check_status" in grp.columns:
            has_tess_eb = _safe_bool_any(grp["tess_eb_check_status"], "matched")

        priority = _assign_star_priority(
            n_events=n_events,
            n_pass=n_pass,
            has_concern_flag=has_concern,
            has_tess_eb=has_tess_eb,
            max_score=max_score,
            max_snr=max_snr,
            n_external_flags=n_ext,
            overtrigger_threshold=overtrigger_threshold,
        )

        return pd.Series({
            "target_name": name,
            "sample_role": role,
            "n_events": n_events,
            "n_pass_automated_vetting": n_pass,
            "n_external_flags": n_ext,
            "max_final_candidate_score": max_score,
            "max_local_snr": max_snr,
            "median_local_snr": med_snr,
            "max_depth_ppm": max_depth,
            "min_event_time_btjd": min_time,
            "max_event_time_btjd": max_time,
            "has_known_variable_match": has_concern,
            "has_tess_eb_match": has_tess_eb,
            "recommended_review_priority": priority,
            "consolidation_version": CONSOLIDATION_VERSION,
        })

    summary = candidate_df.groupby("tic_id", sort=False).apply(_agg, include_groups=False).reset_index()
    return summary.sort_values("n_events", ascending=False).reset_index(drop=True)


def select_top_event_per_star(
    candidate_df: pd.DataFrame,
    sort_by: str = "final_candidate_score",
) -> pd.DataFrame:
    """Select the single highest-scoring event per TIC.

    Ties in sort_by are broken by local_snr descending.

    Parameters
    ----------
    candidate_df:
        Event-level candidate table.
    sort_by:
        Column to rank events within each TIC (descending).

    Returns
    -------
    pd.DataFrame — one row per TIC, the top event.
    """
    if candidate_df.empty:
        return candidate_df.copy()

    sort_cols = [sort_by]
    if sort_by != "local_snr" and "local_snr" in candidate_df.columns:
        sort_cols.append("local_snr")

    # Only sort by columns that exist
    sort_cols = [c for c in sort_cols if c in candidate_df.columns]
    if not sort_cols:
        logger.warning("sort_by column %r not found; returning first event per TIC.", sort_by)
        return candidate_df.groupby("tic_id", sort=False).first().reset_index()

    ranked = candidate_df.sort_values(sort_cols, ascending=False)
    return ranked.groupby("tic_id", sort=False).first().reset_index()


def identify_overtriggered_stars(
    candidate_df: pd.DataFrame,
    threshold_events: int = 5,
) -> pd.DataFrame:
    """Return TICs that have >= threshold_events candidate events.

    High event counts on one star typically indicate stellar variability,
    systematics, or contamination, not multiple exocomet transits.

    Parameters
    ----------
    candidate_df:
        Event-level candidate table.
    threshold_events:
        Minimum event count to label a star as overtriggered.

    Returns
    -------
    pd.DataFrame with columns: tic_id, sample_role, target_name, n_events.
        Sorted by n_events descending.
    """
    if candidate_df.empty:
        return pd.DataFrame(columns=["tic_id", "sample_role", "target_name", "n_events"])

    counts = candidate_df.groupby("tic_id").size().rename("n_events").reset_index()
    overtriggered = counts[counts["n_events"] >= threshold_events].copy()

    # Attach role and name from first occurrence per TIC
    first = candidate_df.drop_duplicates(subset=["tic_id"])[
        [c for c in ["tic_id", "sample_role", "target_name"] if c in candidate_df.columns]
    ].copy()
    overtriggered = overtriggered.merge(first, on="tic_id", how="left")
    return overtriggered.sort_values("n_events", ascending=False).reset_index(drop=True)


def build_manual_review_priority_table(
    candidate_df: pd.DataFrame,
    max_events_per_star: int = 3,
    overtrigger_threshold: int = 5,
) -> pd.DataFrame:
    """Build a concise review table with up to max_events_per_star per TIC.

    Events are sorted by final_candidate_score descending within each TIC.
    A recommended_review_priority column is attached based on star-level rules.

    This table is intended for human reviewers and is NOT a scientific result.
    """
    if candidate_df.empty:
        return candidate_df.copy()

    sort_col = "final_candidate_score" if "final_candidate_score" in candidate_df.columns else None

    # Sort and take top N per TIC
    if sort_col:
        ranked = candidate_df.sort_values(sort_col, ascending=False)
    else:
        ranked = candidate_df.copy()

    top_n = (
        ranked.groupby("tic_id", sort=False, group_keys=False)
        .head(max_events_per_star)
        .reset_index(drop=True)
    )

    # Attach priority from star-level summary
    star_summary = summarize_candidates_by_star(candidate_df, overtrigger_threshold=overtrigger_threshold)
    priority_map = dict(zip(star_summary["tic_id"], star_summary["recommended_review_priority"]))
    top_n = top_n.copy()
    top_n["recommended_review_priority"] = top_n["tic_id"].map(priority_map).fillna(PRIORITY_LOW)
    top_n["consolidation_version"] = CONSOLIDATION_VERSION

    return top_n.reset_index(drop=True)


def summarize_pass_candidates(candidate_df: pd.DataFrame) -> pd.DataFrame:
    """Return all pass-vetting candidates with key columns for quick inspection.

    IMPORTANT: Pass candidates on overtriggered stars may reflect variability
    or systematics, not exocomet transits.  Manual review is required.
    """
    if candidate_df.empty or "automated_vetting_status" not in candidate_df.columns:
        return pd.DataFrame()

    pass_df = candidate_df[candidate_df["automated_vetting_status"] == "pass"].copy()

    display_cols = [c for c in [
        "tic_id", "target_name", "sample_role", "event_time_btjd",
        "depth_ppm", "local_snr", "duration_hours", "final_candidate_score",
        "automated_vetting_status", "external_false_positive_flag",
        "vsx_match_name", "simbad_otype", "tess_eb_check_status",
        "external_vetting_notes",
    ] if c in pass_df.columns]

    return pass_df[display_cols].reset_index(drop=True)


def attach_scan_status(
    candidate_df: pd.DataFrame,
    scan_status_df: pd.DataFrame,
) -> pd.DataFrame:
    """Join per-star scan metadata (cache_used, scan_timestamp, success) to events.

    Merges on tic_id.  Columns from scan_status_df that already exist in
    candidate_df are not overwritten.
    """
    if scan_status_df.empty or "tic_id" not in scan_status_df.columns:
        return candidate_df.copy()

    status_cols = [
        c for c in ["tic_id", "cache_used", "scan_timestamp", "success", "failure_reason"]
        if c in scan_status_df.columns
    ]
    new_cols = [c for c in status_cols if c != "tic_id" and c not in candidate_df.columns]
    if not new_cols:
        return candidate_df.copy()

    merge_df = scan_status_df[["tic_id"] + new_cols].drop_duplicates(subset=["tic_id"])
    result = candidate_df.merge(merge_df, on="tic_id", how="left")
    return result
