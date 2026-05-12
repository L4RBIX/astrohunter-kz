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
        if not math.isfinite(left_ra) or not math.isfinite(left_dec):
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


def add_placeholder_crossmatch_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Add documented TIC/Gaia placeholder columns without claiming matches."""
    work = df.copy()
    for column in ["tic_id", "gaia_dr3_source_id", "simbad_main_id"]:
        if column not in work.columns:
            work[column] = pd.NA
    if "crossmatch_status" not in work.columns:
        work["crossmatch_status"] = "not_attempted"
    return work


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
