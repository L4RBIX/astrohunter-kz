"""Phase 5 automated vetting for AstroHunter KZ candidate events.

Automated vetting applies transparent, reproducible flag criteria to candidate
event tables.  It does NOT confirm or reject any astrophysical interpretation.
Every flagged candidate still requires manual review before any scientific claim.

External catalog crossmatches (EB catalogs, VSX, SIMBAD) are NOT performed by
this module.  Placeholder status columns are added to track their absence.

SCIENTIFIC CONSTRAINTS:
- Automated flags are heuristic filters, not confirmation tests.
- Passing automated vetting does NOT confirm an exocomet detection.
- All candidates require multi-sector validation and follow-up.
- Rate statistics derived from this output are preliminary.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

VETTER_VERSION = "phase5_v1"

# Automated flag column names
AUTOMATED_FLAG_COLUMNS: list[str] = [
    "flag_low_snr",
    "flag_edge_event",
    "flag_single_point_like",
    "flag_likely_flare_shape",
    "flag_low_delta_chi2",
    "flag_poor_asymmetry_fit",
]

# Placeholder external-crossmatch status columns
EXTERNAL_CHECK_COLUMNS: list[str] = [
    "eb_catalog_check_status",
    "vsx_check_status",
    "simbad_check_status",
]

# Manual review columns added for human annotators
MANUAL_REVIEW_COLUMNS: list[str] = [
    "manual_reviewer",
    "manual_review_date",
    "manual_review_notes",
    "manual_disposition",
]


# ---------------------------------------------------------------------------
# Individual flag functions
# ---------------------------------------------------------------------------

def flag_low_snr(
    candidate_df: pd.DataFrame,
    snr_threshold: float = 5.0,
) -> pd.Series:
    """Return boolean Series: True where local_snr < snr_threshold.

    Parameters
    ----------
    candidate_df:
        Candidate event DataFrame with a ``local_snr`` column.
    snr_threshold:
        Events with SNR below this value are flagged.  Default 5.0σ.

    Returns
    -------
    pd.Series
        Boolean flag Series named ``flag_low_snr``.
    """
    if "local_snr" not in candidate_df.columns:
        logger.warning("'local_snr' column absent; all rows flagged flag_low_snr=True.")
        return pd.Series(True, index=candidate_df.index, name="flag_low_snr")
    snr = pd.to_numeric(candidate_df["local_snr"], errors="coerce")
    return (snr < snr_threshold).fillna(True).rename("flag_low_snr")


def flag_edge_events(candidate_df: pd.DataFrame) -> pd.Series:
    """Return boolean Series: True where edge_event == True.

    Parameters
    ----------
    candidate_df:
        Candidate event DataFrame.

    Returns
    -------
    pd.Series
        Boolean flag Series named ``flag_edge_event``.
    """
    if "edge_event" not in candidate_df.columns:
        logger.warning("'edge_event' column absent; flag_edge_event set to False.")
        return pd.Series(False, index=candidate_df.index, name="flag_edge_event")
    return candidate_df["edge_event"].astype(bool).rename("flag_edge_event")


def flag_single_point_like(candidate_df: pd.DataFrame) -> pd.Series:
    """Return boolean Series: True where single_point_like == True.

    Parameters
    ----------
    candidate_df:
        Candidate event DataFrame.

    Returns
    -------
    pd.Series
        Boolean flag Series named ``flag_single_point_like``.
    """
    if "single_point_like" not in candidate_df.columns:
        logger.warning("'single_point_like' absent; flag_single_point_like set to False.")
        return pd.Series(False, index=candidate_df.index, name="flag_single_point_like")
    return candidate_df["single_point_like"].astype(bool).rename("flag_single_point_like")


def flag_likely_flare_shape(candidate_df: pd.DataFrame) -> pd.Series:
    """Return boolean Series: True for events with flare-like morphology.

    Heuristic: skewness > 0 AND egress_ingress_ratio < 1.0.
    A genuine exocomet-like dip is expected to have fast ingress and slow
    egress (egress_ingress_ratio > 1.0) and negative skewness in the
    inverted-flux representation.  Positive skewness with a ratio < 1
    suggests a flux-increase (flare) rather than a flux-dip.

    This flag is heuristic only and may misclassify asymmetric noise.

    Parameters
    ----------
    candidate_df:
        Candidate event DataFrame.

    Returns
    -------
    pd.Series
        Boolean flag Series named ``flag_likely_flare_shape``.
    """
    idx = candidate_df.index
    skew_col = pd.to_numeric(
        candidate_df.get("skewness", pd.Series(np.nan, index=idx)),
        errors="coerce",
    )
    ratio_col = pd.to_numeric(
        candidate_df.get("egress_ingress_ratio", pd.Series(np.nan, index=idx)),
        errors="coerce",
    )
    flare = (skew_col > 0) & (ratio_col < 1.0)
    return flare.fillna(False).rename("flag_likely_flare_shape")


def flag_low_quality_fit(
    candidate_df: pd.DataFrame,
    delta_chi2_threshold: float = 5.0,
) -> pd.Series:
    """Return boolean Series for events with weak asymmetry model evidence.

    Two sub-flags are combined:
    - ``flag_low_delta_chi2``: delta_chi2_asym < *delta_chi2_threshold*
    - ``flag_poor_asymmetry_fit``: egress_ingress_ratio NaN or near 1.0
      (model fit may have failed or produced a near-symmetric result)

    Parameters
    ----------
    candidate_df:
        Candidate event DataFrame.
    delta_chi2_threshold:
        Minimum Δχ² for the asymmetric model to be considered better.
        Default 5.0 (weak evidence threshold).

    Returns
    -------
    pd.DataFrame
        Two-column DataFrame with ``flag_low_delta_chi2`` and
        ``flag_poor_asymmetry_fit``.
    """
    idx = candidate_df.index

    dchi2 = pd.to_numeric(
        candidate_df.get("delta_chi2_asym", pd.Series(np.nan, index=idx)),
        errors="coerce",
    )
    flag_dchi2 = (dchi2 < delta_chi2_threshold).fillna(True).rename("flag_low_delta_chi2")

    ratio = pd.to_numeric(
        candidate_df.get("egress_ingress_ratio", pd.Series(np.nan, index=idx)),
        errors="coerce",
    )
    flag_fit = (ratio.isna() | (ratio.between(0.9, 1.1))).rename("flag_poor_asymmetry_fit")

    return pd.DataFrame({"flag_low_delta_chi2": flag_dchi2, "flag_poor_asymmetry_fit": flag_fit})


# ---------------------------------------------------------------------------
# Composite vetting
# ---------------------------------------------------------------------------

def add_basic_vetting_flags(
    candidate_df: pd.DataFrame,
    snr_threshold: float = 5.0,
    delta_chi2_threshold: float = 5.0,
) -> pd.DataFrame:
    """Attach all automated vetting flag columns to the candidate DataFrame.

    Computes and attaches:
    - flag_low_snr
    - flag_edge_event
    - flag_single_point_like
    - flag_likely_flare_shape
    - flag_low_delta_chi2
    - flag_poor_asymmetry_fit
    - needs_manual_review  (True if ANY flag is set)
    - automated_vetting_status  ("pass" / "flagged")
    - eb_catalog_check_status  = "not_attempted"
    - vsx_check_status         = "not_attempted"
    - simbad_check_status      = "not_attempted"
    - vetter_version

    Parameters
    ----------
    candidate_df:
        Ranked or raw candidate event DataFrame.
    snr_threshold:
        SNR threshold for flag_low_snr.
    delta_chi2_threshold:
        Δχ² threshold for flag_low_delta_chi2.

    Returns
    -------
    pd.DataFrame
        Copy of *candidate_df* with vetting columns appended.
    """
    result = candidate_df.copy()

    result["flag_low_snr"] = flag_low_snr(result, snr_threshold=snr_threshold).values
    result["flag_edge_event"] = flag_edge_events(result).values
    result["flag_single_point_like"] = flag_single_point_like(result).values
    result["flag_likely_flare_shape"] = flag_likely_flare_shape(result).values

    fit_flags = flag_low_quality_fit(result, delta_chi2_threshold=delta_chi2_threshold)
    result["flag_low_delta_chi2"] = fit_flags["flag_low_delta_chi2"].values
    result["flag_poor_asymmetry_fit"] = fit_flags["flag_poor_asymmetry_fit"].values

    # Aggregate: any flag set → needs manual review
    flag_cols = [c for c in AUTOMATED_FLAG_COLUMNS if c in result.columns]
    any_flag = result[flag_cols].any(axis=1)
    result["needs_manual_review"] = any_flag
    result["automated_vetting_status"] = np.where(any_flag, "flagged", "pass")

    # External crossmatch placeholders
    for col in EXTERNAL_CHECK_COLUMNS:
        result[col] = "not_attempted"

    result["vetter_version"] = VETTER_VERSION

    n_flagged = int(any_flag.sum())
    n_pass = int((~any_flag).sum())
    logger.info(
        "Automated vetting complete: %d pass, %d flagged (of %d total).",
        n_pass, n_flagged, len(result),
    )
    return result


def add_manual_review_columns(candidate_df: pd.DataFrame) -> pd.DataFrame:
    """Add blank manual-review columns to the candidate DataFrame.

    These columns are intended to be filled by a human reviewer.  They are
    left as empty strings / NaN so the output file can serve as a vetting
    worksheet.

    Parameters
    ----------
    candidate_df:
        Candidate DataFrame (already vetting-flagged).

    Returns
    -------
    pd.DataFrame
        Copy with ``manual_reviewer``, ``manual_review_date``,
        ``manual_review_notes``, and ``manual_disposition`` columns.
    """
    result = candidate_df.copy()
    for col in MANUAL_REVIEW_COLUMNS:
        if col not in result.columns:
            result[col] = ""
    return result


# ---------------------------------------------------------------------------
# Summary and sheet
# ---------------------------------------------------------------------------

def compute_vetting_summary(candidate_df: pd.DataFrame) -> dict[str, Any]:
    """Return a summary dict of vetting flag counts.

    Parameters
    ----------
    candidate_df:
        Candidate DataFrame with vetting flag columns.

    Returns
    -------
    dict
        Keys: total, n_pass, n_flagged, flag counts per flag column,
        fraction_flagged, vetter_version.
    """
    total = len(candidate_df)
    summary: dict[str, Any] = {"total_candidates": total}

    flag_cols = [c for c in AUTOMATED_FLAG_COLUMNS if c in candidate_df.columns]
    for col in flag_cols:
        summary[col] = int(candidate_df[col].sum())

    if "automated_vetting_status" in candidate_df.columns:
        summary["n_pass"] = int((candidate_df["automated_vetting_status"] == "pass").sum())
        summary["n_flagged"] = int((candidate_df["automated_vetting_status"] == "flagged").sum())
    else:
        summary["n_pass"] = total
        summary["n_flagged"] = 0

    summary["fraction_flagged"] = (
        summary["n_flagged"] / total if total > 0 else float("nan")
    )
    summary["vetter_version"] = VETTER_VERSION

    if total < 10:
        logger.warning(
            "Only %d candidates in vetting summary — statistics are highly preliminary.", total
        )

    return summary


def create_manual_vetting_sheet(candidate_df: pd.DataFrame) -> pd.DataFrame:
    """Create a manual-review worksheet from a vetted candidate DataFrame.

    Selects the most informative columns for human review and ensures
    manual-review placeholder columns are present.  Sorted by
    ``final_candidate_score`` descending when available.

    Parameters
    ----------
    candidate_df:
        Vetted candidate DataFrame.

    Returns
    -------
    pd.DataFrame
        Worksheet with key columns for human annotation.
    """
    priority_cols = [
        "tic_id", "target_name", "event_time_btjd",
        "depth_ppm", "local_snr", "duration_hours", "fwhm_hours",
        "egress_ingress_ratio", "delta_chi2_asym", "skewness",
        "edge_event", "single_point_like",
        "final_candidate_score", "ml_score", "quality_score",
        "automated_vetting_status", "needs_manual_review",
        "flag_low_snr", "flag_edge_event", "flag_single_point_like",
        "flag_likely_flare_shape", "flag_low_delta_chi2", "flag_poor_asymmetry_fit",
        "eb_catalog_check_status", "vsx_check_status", "simbad_check_status",
        "manual_reviewer", "manual_review_date",
        "manual_review_notes", "manual_disposition",
    ]

    df = add_manual_review_columns(candidate_df)

    available = [c for c in priority_cols if c in df.columns]
    sheet = df[available].copy()

    if "final_candidate_score" in sheet.columns:
        sheet = sheet.sort_values("final_candidate_score", ascending=False)

    return sheet
