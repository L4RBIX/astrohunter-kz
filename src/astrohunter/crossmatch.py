"""Small, transparent crossmatch utilities for Phase 2 catalog building."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class MatchResult:
    """Result from a nearest-neighbor sky-position match."""

    left_index: int
    right_index: int
    separation_arcsec: float


def angular_separation_arcsec(
    ra1_deg,
    dec1_deg,
    ra2_deg,
    dec2_deg,
) -> np.ndarray:
    """Return great-circle angular separation in arcseconds.

    Inputs may be scalars or numpy-compatible arrays in decimal degrees.
    """
    ra1 = np.deg2rad(np.asarray(ra1_deg, dtype=float))
    dec1 = np.deg2rad(np.asarray(dec1_deg, dtype=float))
    ra2 = np.deg2rad(np.asarray(ra2_deg, dtype=float))
    dec2 = np.deg2rad(np.asarray(dec2_deg, dtype=float))

    sin_ddec = np.sin((dec2 - dec1) / 2.0)
    sin_dra = np.sin((ra2 - ra1) / 2.0)
    hav = sin_ddec**2 + np.cos(dec1) * np.cos(dec2) * sin_dra**2
    angle = 2.0 * np.arcsin(np.sqrt(np.clip(hav, 0.0, 1.0)))
    return np.rad2deg(angle) * 3600.0


def safe_column_lookup(df: pd.DataFrame, candidates: list[str]) -> str | None:
    """Return the first matching column name, case-insensitively."""
    if df is None or df.empty:
        return None
    lookup = {str(column).lower(): column for column in df.columns}
    for candidate in candidates:
        found = lookup.get(candidate.lower())
        if found is not None:
            return found
    return None


def add_skycoord_columns(
    df: pd.DataFrame,
    ra_col: str = "ra_deg",
    dec_col: str = "dec_deg",
) -> pd.DataFrame:
    """Add normalized decimal-degree sky-coordinate columns.

    Astropy ``SkyCoord`` objects are intentionally not stored in the DataFrame
    because CSV output must remain portable. The boolean column records whether a
    row has finite coordinates suitable for matching.
    """
    work = df.copy()
    if ra_col not in work.columns or dec_col not in work.columns:
        work["ra_deg"] = pd.NA
        work["dec_deg"] = pd.NA
        work["has_skycoord"] = False
        return work

    work["ra_deg"] = pd.to_numeric(work[ra_col], errors="coerce")
    work["dec_deg"] = pd.to_numeric(work[dec_col], errors="coerce")
    work["has_skycoord"] = np.isfinite(work["ra_deg"]) & np.isfinite(work["dec_deg"])
    return work


def has_coordinate_columns(df: pd.DataFrame) -> bool:
    """Return True when normalized decimal-degree coordinates are present."""
    return {"ra_deg", "dec_deg"}.issubset(df.columns)


def deduplicate_by_coordinates(
    df: pd.DataFrame,
    radius_arcsec: float = 3.0,
    keep: str = "first",
) -> pd.DataFrame:
    """Deduplicate rows whose coordinates fall within ``radius_arcsec``.

    This is an O(N^2) implementation intended for small Phase 2 development
    samples, not final survey-scale catalog work.
    """
    if radius_arcsec <= 0:
        raise ValueError("radius_arcsec must be positive")
    if keep not in {"first", "last"}:
        raise ValueError("keep must be 'first' or 'last'")
    if df.empty or not has_coordinate_columns(df):
        return df.copy().reset_index(drop=True)

    work = df.reset_index(drop=True).copy()
    valid = np.isfinite(work["ra_deg"].to_numpy(dtype=float)) & np.isfinite(
        work["dec_deg"].to_numpy(dtype=float)
    )
    keep_mask = np.ones(len(work), dtype=bool)
    order = range(len(work)) if keep == "first" else range(len(work) - 1, -1, -1)

    for i in order:
        if not valid[i] or not keep_mask[i]:
            continue
        candidate_indices = np.flatnonzero(keep_mask & valid)
        candidate_indices = candidate_indices[candidate_indices != i]
        if candidate_indices.size == 0:
            continue
        sep = angular_separation_arcsec(
            work.loc[i, "ra_deg"],
            work.loc[i, "dec_deg"],
            work.loc[candidate_indices, "ra_deg"].to_numpy(dtype=float),
            work.loc[candidate_indices, "dec_deg"].to_numpy(dtype=float),
        )
        duplicates = candidate_indices[sep <= radius_arcsec]
        keep_mask[duplicates] = False

    return work.loc[keep_mask].reset_index(drop=True)


def deduplicate_by_skycoord(
    df: pd.DataFrame,
    max_sep_arcsec: float = 3.0,
    keep: str = "first",
) -> pd.DataFrame:
    """Deduplicate rows by sky position using normalized RA/Dec columns."""
    return deduplicate_by_coordinates(df, radius_arcsec=max_sep_arcsec, keep=keep)


def nearest_coordinate_matches(
    left: pd.DataFrame,
    right: pd.DataFrame,
    radius_arcsec: float = 3.0,
) -> pd.DataFrame:
    """Find nearest right-side coordinate match for each left row.

    Returns only matches within ``radius_arcsec``. No external catalog identity is
    inferred from this helper alone.
    """
    if radius_arcsec <= 0:
        raise ValueError("radius_arcsec must be positive")
    columns = ["left_index", "right_index", "separation_arcsec"]
    if (
        left.empty
        or right.empty
        or not has_coordinate_columns(left)
        or not has_coordinate_columns(right)
    ):
        return pd.DataFrame(columns=columns)

    rows: list[dict[str, float | int]] = []
    right_ra = right["ra_deg"].to_numpy(dtype=float)
    right_dec = right["dec_deg"].to_numpy(dtype=float)
    right_valid = np.isfinite(right_ra) & np.isfinite(right_dec)

    for left_idx, row in left.reset_index(drop=True).iterrows():
        left_ra = row.get("ra_deg")
        left_dec = row.get("dec_deg")
        if pd.isna(left_ra) or pd.isna(left_dec):
            continue
        if not math.isfinite(float(left_ra)) or not math.isfinite(float(left_dec)):
            continue
        valid_indices = np.flatnonzero(right_valid)
        if valid_indices.size == 0:
            continue
        sep = angular_separation_arcsec(
            left_ra,
            left_dec,
            right_ra[valid_indices],
            right_dec[valid_indices],
        )
        best_local = int(np.nanargmin(sep))
        best_sep = float(sep[best_local])
        if best_sep <= radius_arcsec:
            rows.append(
                {
                    "left_index": int(left_idx),
                    "right_index": int(valid_indices[best_local]),
                    "separation_arcsec": best_sep,
                }
            )

    return pd.DataFrame(rows, columns=columns)


def crossmatch_by_coordinates(
    left_df: pd.DataFrame,
    right_df: pd.DataFrame,
    max_sep_arcsec: float = 3.0,
) -> pd.DataFrame:
    """Crossmatch two DataFrames by nearest sky position within a radius."""
    return nearest_coordinate_matches(
        left_df,
        right_df,
        radius_arcsec=max_sep_arcsec,
    )


def add_placeholder_crossmatch_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Add documented TIC/Gaia placeholder columns without claiming matches."""
    work = df.copy()
    for column in ["tic_id", "gaia_dr3_source_id", "simbad_main_id"]:
        if column not in work.columns:
            work[column] = pd.NA
    if "crossmatch_status" not in work.columns:
        work["crossmatch_status"] = "not_attempted"
    return work


def _boolean_series(df: pd.DataFrame, column: str, default: bool) -> pd.Series:
    if column not in df.columns:
        return pd.Series(default, index=df.index)
    values = df[column]
    if values.dtype == bool:
        return values.fillna(default)
    normalized = values.astype(str).str.lower().str.strip()
    return normalized.isin(["true", "1", "yes", "y"]).fillna(default)


def _available_numeric_column(
    target: pd.Series,
    controls: pd.DataFrame,
    candidates: list[str],
) -> str | None:
    for column in candidates:
        if column in controls.columns and column in target.index and pd.notna(target[column]):
            return column
    return None


def match_controls_to_targets(
    targets: pd.DataFrame,
    control_pool: pd.DataFrame,
    control_ratio: int = 3,
    tmag_tolerance: float = 1.0,
    color_tolerance: float = 0.35,
    teff_tolerance: float = 400.0,
    parallax_fraction_tolerance: float = 0.5,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Match each target to up to ``control_ratio`` real non-disk controls.

    Criteria are applied only when the needed columns exist in both target and
    control data. Missing metadata is reported via printed warnings and does not
    crash the build.
    """
    if control_ratio < 1:
        raise ValueError("control_ratio must be at least 1")
    pair_columns = [
        "target_index",
        "control_index",
        "target_name",
        "control_name",
        "match_rank",
        "match_score",
    ]
    if targets.empty or control_pool.empty:
        print("Warning: cannot match controls because targets or control pool is empty.")
        return pd.DataFrame(), pd.DataFrame(columns=pair_columns)

    pool = control_pool.copy().reset_index(drop=True)
    targets_work = targets.copy().reset_index(drop=True)

    if "has_tess_lightcurve" in pool.columns:
        pool = pool[_boolean_series(pool, "has_tess_lightcurve", default=False)].copy()
    else:
        print("Warning: control pool missing has_tess_lightcurve; TESS criterion skipped.")

    if "ir_excess_flag" in pool.columns:
        ir_excess = _boolean_series(pool, "ir_excess_flag", default=True)
        pool = pool[~ir_excess].copy()
    else:
        print("Warning: control pool missing ir_excess_flag; cannot reject disk/IR-excess controls.")

    if pool.empty:
        print("Warning: no controls remain after TESS/IR-excess filtering.")
        return pd.DataFrame(), pd.DataFrame(columns=pair_columns)

    used_control_indices: set[int] = set()
    pair_rows: list[dict[str, object]] = []

    for target_idx, target in targets_work.iterrows():
        candidates = pool.copy()
        score = pd.Series(0.0, index=candidates.index)

        tmag_col = _available_numeric_column(target, candidates, ["tmag", "Tmag", "TESSMAG"])
        if tmag_col is None:
            print("Warning: Tmag unavailable for at least one target/control match; criterion skipped.")
        else:
            target_tmag = float(target[tmag_col])
            candidate_tmag = pd.to_numeric(candidates[tmag_col], errors="coerce")
            delta = (candidate_tmag - target_tmag).abs()
            candidates = candidates[delta <= tmag_tolerance]
            score = score.loc[candidates.index] + delta.loc[candidates.index] / tmag_tolerance

        color_col = _available_numeric_column(target, candidates, ["bp_rp", "BP_RP", "bp-rp"])
        teff_col = None
        if color_col is None:
            teff_col = _available_numeric_column(target, candidates, ["teff", "Teff", "TEFF"])
        if color_col is not None:
            target_color = float(target[color_col])
            candidate_color = pd.to_numeric(candidates[color_col], errors="coerce")
            delta = (candidate_color - target_color).abs()
            candidates = candidates[delta <= color_tolerance]
            score = score.loc[candidates.index] + delta.loc[candidates.index] / color_tolerance
        elif teff_col is not None:
            target_teff = float(target[teff_col])
            candidate_teff = pd.to_numeric(candidates[teff_col], errors="coerce")
            delta = (candidate_teff - target_teff).abs()
            candidates = candidates[delta <= teff_tolerance]
            score = score.loc[candidates.index] + delta.loc[candidates.index] / teff_tolerance
        else:
            print("Warning: BP-RP/Teff unavailable for at least one match; color criterion skipped.")

        parallax_col = _available_numeric_column(target, candidates, ["parallax", "plx", "Plx"])
        if parallax_col is None:
            print("Warning: parallax unavailable for at least one match; distance criterion skipped.")
        else:
            target_parallax = float(target[parallax_col])
            candidate_parallax = pd.to_numeric(candidates[parallax_col], errors="coerce")
            if target_parallax > 0:
                frac = (candidate_parallax - target_parallax).abs() / target_parallax
                candidates = candidates[frac <= parallax_fraction_tolerance]
                score = (
                    score.loc[candidates.index]
                    + frac.loc[candidates.index] / parallax_fraction_tolerance
                )
            else:
                print("Warning: non-positive target parallax; distance criterion skipped.")

        if candidates.empty:
            continue

        available = [idx for idx in candidates.index if idx not in used_control_indices]
        if not available:
            continue
        ranked = score.loc[available].sort_values().head(control_ratio)
        for rank, (control_idx, match_score) in enumerate(ranked.items(), start=1):
            used_control_indices.add(int(control_idx))
            pair_rows.append(
                {
                    "target_index": int(target_idx),
                    "control_index": int(control_idx),
                    "target_name": target.get("target_name", pd.NA),
                    "control_name": pool.loc[control_idx].get("target_name", pd.NA),
                    "match_rank": rank,
                    "match_score": float(match_score),
                }
            )

    if not pair_rows:
        print("Warning: no matched controls satisfied the available criteria.")
        return pd.DataFrame(), pd.DataFrame(columns=pair_columns)

    pairs = pd.DataFrame(pair_rows, columns=pair_columns)
    controls = pool.loc[pairs["control_index"].to_numpy()].copy().reset_index(drop=True)
    return controls, pairs.reset_index(drop=True)


def build_approximate_matched_controls(
    targets: pd.DataFrame,
    candidate_pool: pd.DataFrame,
    max_controls: int | None = None,
    radius_arcsec: float = 30.0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build an approximate control sample from a real candidate pool.

    This helper is intentionally conservative. It only returns controls when a
    caller supplies a real non-target pool with coordinates. It does not invent
    stars and it does not query TIC/Gaia by itself.
    """
    matches = nearest_coordinate_matches(
        targets,
        candidate_pool,
        radius_arcsec=radius_arcsec,
    )
    if matches.empty:
        return (
            pd.DataFrame(columns=candidate_pool.columns),
            pd.DataFrame(columns=["target_index", "control_index", "separation_arcsec"]),
        )

    pairs = matches.rename(
        columns={"left_index": "target_index", "right_index": "control_index"}
    )
    if max_controls is not None:
        pairs = pairs.head(max_controls)

    controls = candidate_pool.reset_index(drop=True).iloc[pairs["control_index"]].copy()
    controls = controls.reset_index(drop=True)
    pairs = pairs.reset_index(drop=True)
    return controls, pairs
