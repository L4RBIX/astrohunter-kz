"""Simple candidate dip detection and asymmetry metrics."""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.signal import find_peaks

from astrohunter.lightcurves import estimate_noise_mad


EVENT_COLUMNS = [
    "event_time_btjd",
    "depth",
    "depth_ppm",
    "local_noise",
    "local_snr",
    "n_points_window",
    "window_start",
    "window_end",
    "is_single_point_like",
    "ingress_duration_days",
    "egress_duration_days",
    "asymmetry_score",
]


def _clean_arrays(time, flux) -> tuple[np.ndarray, np.ndarray]:
    time_values = np.asarray(time, dtype=float)
    flux_values = np.asarray(flux, dtype=float)
    if time_values.shape != flux_values.shape:
        raise ValueError("time and flux must have the same shape")
    finite = np.isfinite(time_values) & np.isfinite(flux_values)
    return time_values[finite], flux_values[finite]


def _empty_events() -> pd.DataFrame:
    return pd.DataFrame(columns=EVENT_COLUMNS)


def detect_candidate_dips(
    time,
    flux,
    sigma_threshold: float = 4.0,
    min_distance: int = 5,
    window_days: float = 0.5,
) -> pd.DataFrame:
    """Detect simple candidate dip-like features in a normalized light curve.

    The detector is intentionally conservative and transparent for Phase 1. It
    identifies local minima whose depth is large relative to robust scatter, then
    attaches local S/N and a single-point-like flag for later vetting.
    """
    if sigma_threshold <= 0:
        raise ValueError("sigma_threshold must be positive")
    if min_distance < 1:
        raise ValueError("min_distance must be at least 1")
    if window_days <= 0:
        raise ValueError("window_days must be positive")

    time_values, flux_values = _clean_arrays(time, flux)
    if time_values.size < 5:
        return _empty_events()

    baseline = float(np.nanmedian(flux_values))
    inverted_flux = baseline - flux_values
    global_noise = estimate_noise_mad(flux_values)
    if not np.isfinite(global_noise) or global_noise <= 0:
        return _empty_events()

    peaks, properties = find_peaks(
        inverted_flux,
        height=sigma_threshold * global_noise,
        distance=min_distance,
    )
    if peaks.size == 0:
        return _empty_events()

    rows: list[dict[str, float | int | bool]] = []
    for peak_idx, peak_height in zip(peaks, properties["peak_heights"]):
        event_time = float(time_values[peak_idx])
        window_start = event_time - window_days / 2.0
        window_end = event_time + window_days / 2.0
        mask = (time_values >= window_start) & (time_values <= window_end)
        local_time = time_values[mask]
        local_flux = flux_values[mask]
        n_points = int(local_time.size)
        if n_points < 3:
            continue

        local_baseline = float(np.nanmedian(local_flux))
        local_depth = float(local_baseline - flux_values[peak_idx])
        if not np.isfinite(local_depth) or local_depth <= 0:
            local_depth = float(peak_height)

        local_noise = estimate_noise_mad(local_flux)
        if not np.isfinite(local_noise) or local_noise <= 0:
            local_noise = global_noise

        local_snr = float(local_depth / local_noise) if local_noise > 0 else np.nan
        below_half = local_flux < (local_baseline - local_depth / 2.0)
        is_single_point_like = bool(np.count_nonzero(below_half) <= 1)

        asymmetry = compute_simple_asymmetry(
            time_values,
            flux_values,
            event_time,
            window_days=window_days,
        )

        rows.append(
            {
                "event_time_btjd": event_time,
                "depth": local_depth,
                "depth_ppm": local_depth * 1e6,
                "local_noise": float(local_noise),
                "local_snr": local_snr,
                "n_points_window": n_points,
                "window_start": float(window_start),
                "window_end": float(window_end),
                "is_single_point_like": is_single_point_like,
                **asymmetry,
            }
        )

    if not rows:
        return _empty_events()

    events = pd.DataFrame(rows)
    return events.sort_values("depth", ascending=False).reset_index(drop=True)


def compute_simple_asymmetry(
    time,
    flux,
    event_time: float,
    window_days: float = 0.5,
) -> dict[str, float]:
    """Estimate ingress/egress duration around an event using half-depth crossings."""
    if window_days <= 0:
        raise ValueError("window_days must be positive")

    time_values, flux_values = _clean_arrays(time, flux)
    if time_values.size < 5 or not np.isfinite(event_time):
        return {
            "ingress_duration_days": np.nan,
            "egress_duration_days": np.nan,
            "asymmetry_score": np.nan,
        }

    half_window = window_days / 2.0
    mask = (time_values >= event_time - half_window) & (
        time_values <= event_time + half_window
    )
    local_time = time_values[mask]
    local_flux = flux_values[mask]
    if local_time.size < 5:
        return {
            "ingress_duration_days": np.nan,
            "egress_duration_days": np.nan,
            "asymmetry_score": np.nan,
        }

    min_idx = int(np.nanargmin(local_flux))
    baseline = float(np.nanmedian(local_flux))
    min_flux = float(local_flux[min_idx])
    depth = baseline - min_flux
    if not np.isfinite(depth) or depth <= 0:
        return {
            "ingress_duration_days": np.nan,
            "egress_duration_days": np.nan,
            "asymmetry_score": np.nan,
        }

    half_depth_flux = baseline - depth / 2.0
    event_min_time = float(local_time[min_idx])

    ingress_duration = np.nan
    if min_idx > 0:
        pre_flux = local_flux[: min_idx + 1]
        crossing_candidates = np.where(pre_flux >= half_depth_flux)[0]
        if crossing_candidates.size > 0:
            ingress_start_idx = int(crossing_candidates[-1])
            ingress_duration = event_min_time - float(local_time[ingress_start_idx])

    egress_duration = np.nan
    if min_idx < local_time.size - 1:
        post_flux = local_flux[min_idx:]
        crossing_candidates = np.where(post_flux >= half_depth_flux)[0]
        if crossing_candidates.size > 0:
            egress_end_idx = min_idx + int(crossing_candidates[0])
            egress_duration = float(local_time[egress_end_idx]) - event_min_time

    asymmetry_score = np.nan
    if (
        np.isfinite(ingress_duration)
        and np.isfinite(egress_duration)
        and ingress_duration > 0
    ):
        asymmetry_score = float(egress_duration / ingress_duration)

    return {
        "ingress_duration_days": float(ingress_duration),
        "egress_duration_days": float(egress_duration),
        "asymmetry_score": asymmetry_score,
    }


def add_asymmetry_scores(
    events_df: pd.DataFrame,
    time,
    flux,
    window_days: float = 0.5,
) -> pd.DataFrame:
    """Attach or refresh simple asymmetry columns for candidate events."""
    if events_df is None or events_df.empty:
        return _empty_events()
    if "event_time_btjd" not in events_df.columns:
        raise KeyError("events_df must contain event_time_btjd")

    asymmetry_rows = [
        compute_simple_asymmetry(time, flux, row.event_time_btjd, window_days=window_days)
        for row in events_df.itertuples(index=False)
    ]
    asymmetry_df = pd.DataFrame(asymmetry_rows)
    without_old = events_df.drop(
        columns=[
            "ingress_duration_days",
            "egress_duration_days",
            "asymmetry_score",
        ],
        errors="ignore",
    )
    return pd.concat(
        [without_old.reset_index(drop=True), asymmetry_df.reset_index(drop=True)],
        axis=1,
    )


def make_synthetic_asymmetric_dip(
    n_points: int = 500,
    center: float = 5.0,
    depth: float = 0.01,
    ingress_days: float = 0.03,
    egress_days: float = 0.20,
    noise: float = 0.0005,
    random_seed: int = 42,
) -> tuple[np.ndarray, np.ndarray]:
    """Generate a small asymmetric dip for tests and examples."""
    if n_points < 10:
        raise ValueError("n_points must be at least 10")
    rng = np.random.default_rng(random_seed)
    time = np.linspace(0.0, 10.0, n_points)
    flux = np.ones_like(time)

    before = (time >= center - ingress_days) & (time < center)
    after = (time >= center) & (time <= center + egress_days)
    flux[before] -= depth * (time[before] - (center - ingress_days)) / ingress_days
    flux[after] -= depth * (1.0 - (time[after] - center) / egress_days)
    flux += rng.normal(0.0, noise, size=n_points)
    return time, flux
