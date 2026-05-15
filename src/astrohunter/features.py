"""Phase 4 event feature engineering for the ML event ranker.

This module converts injection-recovery and real-candidate tables into
a consistent feature matrix used by the ML ranker.

IMPORTANT: do not include injected ground-truth columns (injected_depth_ppm,
injected_ingress_hours, injected_egress_hours, injected_asymmetry_ratio, or
injected_event_time_btjd) in REQUIRED_FEATURE_COLUMNS.  Those values are
unavailable for real candidate events and would constitute feature leakage.

The features derived from injection-recovery (recovered_depth_ppm,
recovered_local_snr) are available only for *recovered* injections and are NaN
for missed injections.  This limitation is documented and handled via zero-fill
imputation.  All limitations must be noted when interpreting model output.
"""

from __future__ import annotations

import logging
import warnings

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Feature definitions
# ---------------------------------------------------------------------------

# Canonical detector-output feature names used for ML training and scoring.
# Must NOT include injected_ ground-truth columns.
REQUIRED_FEATURE_COLUMNS: list[str] = [
    "depth_ppm",
    "local_snr",
    "noise_mad",
    "duration_hours",
    "fwhm_hours",
    "ingress_duration_hours",
    "egress_duration_hours",
    "egress_ingress_ratio",
    "skewness",
    "kurtosis",
    "delta_chi2_asym",
    "n_points_window",
    "edge_event",
    "single_point_like",
]

# Ground-truth columns from injection table that must NOT be used as features.
GROUND_TRUTH_COLUMNS: list[str] = [
    "injected_event_time_btjd",
    "injected_depth_ppm",
    "injected_ingress_hours",
    "injected_egress_hours",
    "injected_asymmetry_ratio",
    "recovered_event_time_btjd",
    "timing_error_hours",
    "recovery_tolerance_hours",
]

# Features used specifically in the rule-based quality score.
QUALITY_FEATURE_COLUMNS: list[str] = [
    "local_snr",
    "egress_ingress_ratio",
    "delta_chi2_asym",
    "edge_event",
    "single_point_like",
    "fwhm_hours",
    "duration_hours",
]


# ---------------------------------------------------------------------------
# Feature selection
# ---------------------------------------------------------------------------

def select_event_feature_columns(df: pd.DataFrame) -> list[str]:
    """Return REQUIRED_FEATURE_COLUMNS that are present in *df*.

    Columns listed in GROUND_TRUTH_COLUMNS are always excluded even if present.

    Parameters
    ----------
    df:
        Feature DataFrame (training or candidate).

    Returns
    -------
    list[str]
        Ordered list of available feature column names.
    """
    ground_truth_set = set(GROUND_TRUTH_COLUMNS)
    available = [
        col for col in REQUIRED_FEATURE_COLUMNS
        if col in df.columns and col not in ground_truth_set
    ]
    missing = [col for col in REQUIRED_FEATURE_COLUMNS if col not in df.columns]
    if missing:
        logger.debug("Feature columns not present in DataFrame: %s", missing)
    return available


# ---------------------------------------------------------------------------
# Training feature table
# ---------------------------------------------------------------------------

def build_training_feature_table(injection_df: pd.DataFrame) -> pd.DataFrame:
    """Build the ML training feature table from the injection-recovery table.

    Maps injection-recovery column names to canonical feature names:
    - ``recovered_depth_ppm``  → ``depth_ppm``   (NaN for missed injections)
    - ``recovered_local_snr``  → ``local_snr``   (NaN for missed injections)
    - ``noise_mad``            → ``noise_mad``   (always available)

    All other REQUIRED_FEATURE_COLUMNS that are absent in injection_df are
    included as all-NaN columns.  ``select_event_feature_columns`` and
    ``impute_missing_features`` will handle them downstream.

    A ``label`` column (0 / 1) is derived from the ``recovered`` column.

    Diagnostic columns from the injection table (injection_id, tic_id,
    sample_role, injected_* values) are carried over for inspection but
    are NOT in REQUIRED_FEATURE_COLUMNS.

    Parameters
    ----------
    injection_df:
        Contents of ``results/tables/injection_recovery.csv``.

    Returns
    -------
    pd.DataFrame
        Feature table with REQUIRED_FEATURE_COLUMNS + label + diagnostics.
    """
    idx = injection_df.index
    result: dict[str, pd.Series] = {}

    # --- canonical feature mappings ---
    def _get(src_names: list[str], fill: float = np.nan) -> pd.Series:
        for name in src_names:
            if name in injection_df.columns:
                return pd.to_numeric(injection_df[name], errors="coerce")
        return pd.Series(fill, index=idx, dtype=float)

    result["depth_ppm"] = _get(["recovered_depth_ppm", "depth_ppm"])
    result["local_snr"] = _get(["recovered_local_snr", "local_snr"])
    result["noise_mad"] = _get(["noise_mad"])

    # --- remaining REQUIRED_FEATURE_COLUMNS ---
    for col in REQUIRED_FEATURE_COLUMNS:
        if col in result:
            continue
        if col in injection_df.columns:
            result[col] = pd.to_numeric(injection_df[col], errors="coerce")
        else:
            result[col] = pd.Series(np.nan, index=idx, dtype=float)

    df = pd.DataFrame(result, index=idx)

    # --- label ---
    if "recovered" in injection_df.columns:
        df["label"] = injection_df["recovered"].astype(bool).astype(int)
    else:
        logger.warning("'recovered' column not found; label will be missing.")

    # --- diagnostic columns (not model features) ---
    for col in [
        "injection_id", "tic_id", "sample_role",
        "injected_depth_ppm", "injected_ingress_hours",
        "injected_egress_hours", "injected_asymmetry_ratio",
    ]:
        if col in injection_df.columns:
            df[col] = injection_df[col].values

    return df


# ---------------------------------------------------------------------------
# Candidate feature table
# ---------------------------------------------------------------------------

def build_candidate_feature_table(candidate_df: pd.DataFrame) -> pd.DataFrame:
    """Build the scoring feature table from the real-data candidate event table.

    The candidate table (detector_candidate_events_dev.csv) already contains
    the full Phase 3 feature set.  This function normalises column types and
    ensures REQUIRED_FEATURE_COLUMNS are present (adding NaN columns for any
    that are absent).

    Metadata columns (tic_id, target_name, event_time_btjd, …) are preserved
    alongside the feature columns for output.

    Parameters
    ----------
    candidate_df:
        Contents of ``results/tables/detector_candidate_events_dev.csv``.

    Returns
    -------
    pd.DataFrame
        Feature table aligned to REQUIRED_FEATURE_COLUMNS.
    """
    idx = candidate_df.index
    result: dict[str, pd.Series] = {}

    for col in REQUIRED_FEATURE_COLUMNS:
        if col in candidate_df.columns:
            result[col] = pd.to_numeric(candidate_df[col], errors="coerce")
        else:
            result[col] = pd.Series(np.nan, index=idx, dtype=float)
            logger.debug("Candidate table missing feature %r; set to NaN.", col)

    df = pd.DataFrame(result, index=idx)

    # Preserve metadata columns
    meta_cols = [c for c in candidate_df.columns if c not in REQUIRED_FEATURE_COLUMNS]
    for col in meta_cols:
        df[col] = candidate_df[col].values

    return df


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_feature_table(
    df: pd.DataFrame,
    require_label: bool = False,
) -> tuple[bool, list[str]]:
    """Check a feature table for common issues.

    Parameters
    ----------
    df:
        Feature DataFrame.
    require_label:
        If True, raise ValueError when ``label`` column is absent.

    Returns
    -------
    (is_valid, issues)
        ``is_valid`` is False when any hard requirement is violated.
        ``issues`` is a list of human-readable issue strings.
    """
    issues: list[str] = []
    is_valid = True

    if len(df) == 0:
        issues.append("DataFrame is empty.")
        is_valid = False

    if require_label:
        if "label" not in df.columns:
            raise ValueError("'label' column is required but not present in feature table.")
        n_classes = df["label"].nunique()
        if n_classes < 2:
            issues.append(
                f"label column has only {n_classes} unique value(s): "
                f"{df['label'].unique().tolist()}. Both classes are required for training."
            )
            is_valid = False

    missing_feats = [c for c in REQUIRED_FEATURE_COLUMNS if c not in df.columns]
    if missing_feats:
        issues.append(f"Missing REQUIRED_FEATURE_COLUMNS: {missing_feats}")

    all_nan_feats = [
        c for c in REQUIRED_FEATURE_COLUMNS
        if c in df.columns and df[c].isna().all()
    ]
    if all_nan_feats:
        issues.append(f"All-NaN feature columns (will be zero-filled): {all_nan_feats}")

    for issue in issues:
        logger.warning("Feature table validation: %s", issue)

    return is_valid, issues


# ---------------------------------------------------------------------------
# Imputation
# ---------------------------------------------------------------------------

def impute_missing_features(
    df: pd.DataFrame,
    fill_values: dict[str, float] | None = None,
) -> tuple[pd.DataFrame, dict[str, float]]:
    """Fill NaN values in REQUIRED_FEATURE_COLUMNS.

    Strategy:
    - Boolean-like columns (edge_event, single_point_like): fill with 0.
    - Numeric columns: fill with median of available values; if all-NaN, fill 0.

    Parameters
    ----------
    df:
        Feature DataFrame (must contain REQUIRED_FEATURE_COLUMNS).
    fill_values:
        Pre-computed fill values from a training set.  When None, fill values
        are computed from *df* itself (fit-on-train pattern).

    Returns
    -------
    (imputed_df, fill_values)
        Imputed copy of *df* and the fill-value mapping for later use.
    """
    result = df.copy()
    computed: dict[str, float] = {}
    bool_cols = {"edge_event", "single_point_like"}

    for col in REQUIRED_FEATURE_COLUMNS:
        if col not in result.columns:
            result[col] = 0.0
            computed[col] = 0.0
            continue

        if fill_values is not None and col in fill_values:
            fill = fill_values[col]
        else:
            if col in bool_cols:
                fill = 0.0
            else:
                # Suppress numpy "Mean of empty slice" when series is all-NaN
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", RuntimeWarning)
                    med = result[col].median()
                fill = float(med) if np.isfinite(med) else 0.0

        computed[col] = fill
        result[col] = result[col].fillna(fill)

    merged_fills = {**computed, **(fill_values or {})}
    return result, merged_fills


# ---------------------------------------------------------------------------
# Quality score (rule-based)
# ---------------------------------------------------------------------------

def add_quality_score(df: pd.DataFrame) -> pd.DataFrame:
    """Attach a rule-based ``quality_score`` column in [0, 1].

    The quality score is a weighted combination of:
    - local_snr (higher is better, capped at 10σ)
    - egress_ingress_ratio (>1 preferred, capped at 6)
    - delta_chi2_asym (>0 preferred, capped at 100)

    Penalties are applied for edge_event and single_point_like.

    This score is distinct from the ML score and is documented as a
    heuristic prioritisation metric, not a confirmation probability.

    Parameters
    ----------
    df:
        Candidate or training feature DataFrame.

    Returns
    -------
    pd.DataFrame
        Copy of *df* with ``quality_score`` column added.
    """
    result = df.copy()
    idx = result.index

    def _col(name: str, default: float = 0.0) -> pd.Series:
        if name in result.columns:
            return pd.to_numeric(result[name], errors="coerce").fillna(default)
        return pd.Series(default, index=idx, dtype=float)

    snr = _col("local_snr", 0.0)
    ratio = _col("egress_ingress_ratio", 1.0)
    dchi2 = _col("delta_chi2_asym", 0.0)
    edge = _col("edge_event", 0.0)
    single = _col("single_point_like", 0.0)

    snr_score = (snr / 10.0).clip(0.0, 1.0)
    ratio_score = ((ratio - 1.0) / 5.0).clip(0.0, 1.0)
    dchi2_score = (dchi2 / 100.0).clip(0.0, 1.0)

    raw = 0.45 * snr_score + 0.30 * ratio_score + 0.25 * dchi2_score
    quality = (raw - 0.25 * edge - 0.25 * single).clip(0.0, 1.0)
    result["quality_score"] = quality
    return result
