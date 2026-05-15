"""Candidate dip detection and asymmetry metrics for AstroHunter KZ.

Phase 1 functions (detect_candidate_dips, compute_simple_asymmetry, …) are
preserved unchanged.  Phase 3 adds an improved scanner
(scan_lightcurve_for_asymmetric_dips) with richer per-event features and
optional symmetric/asymmetric model fitting.

IMPORTANT: all functions operate on *candidate* dip-like features.
They do not confirm exocomet detections.
"""

from __future__ import annotations

import logging
import warnings
from typing import Any

import numpy as np
import pandas as pd
from scipy.signal import find_peaks
from scipy.stats import kurtosis as scipy_kurtosis
from scipy.stats import skew as scipy_skew

from astrohunter.lightcurves import estimate_noise_mad

logger = logging.getLogger(__name__)

DETECTOR_VERSION = "phase3_v1"


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


# ---------------------------------------------------------------------------
# Phase 3: improved scanner and per-event feature extraction
# ---------------------------------------------------------------------------

# Window used to decide an event is near the edge of the baseline
_EDGE_BUFFER_DAYS = 0.5


def estimate_event_fwhm(
    time: np.ndarray,
    flux: np.ndarray,
    event_time: float,
    window_days: float = 1.0,
) -> float:
    """Estimate the full-width at half-maximum of a dip in hours.

    Uses linear interpolation to find the two half-depth crossing times.
    Returns NaN when there are too few points or the dip is not well defined.
    """
    t, f = _clean_arrays(time, flux)
    half = window_days / 2.0
    mask = (t >= event_time - half) & (t <= event_time + half)
    lt, lf = t[mask], f[mask]
    if lt.size < 4:
        return np.nan

    baseline = float(np.nanmedian(lf))
    min_idx = int(np.nanargmin(lf))
    depth = baseline - float(lf[min_idx])
    if not np.isfinite(depth) or depth <= 0:
        return np.nan

    half_depth_flux = baseline - depth / 2.0
    event_min_t = float(lt[min_idx])

    # Left crossing (ingress side)
    left_t = np.nan
    if min_idx > 0:
        pre = lf[: min_idx + 1]
        candidates = np.where(pre >= half_depth_flux)[0]
        if candidates.size > 0:
            i0 = int(candidates[-1])
            if i0 < min_idx:
                # linear interpolation
                t0, t1 = lt[i0], lt[i0 + 1]
                f0, f1 = lf[i0], lf[i0 + 1]
                if abs(f1 - f0) > 0:
                    frac = (half_depth_flux - f0) / (f1 - f0)
                    left_t = t0 + frac * (t1 - t0)
                else:
                    left_t = t0
            else:
                left_t = lt[i0]

    # Right crossing (egress side)
    right_t = np.nan
    if min_idx < lt.size - 1:
        post = lf[min_idx:]
        candidates = np.where(post >= half_depth_flux)[0]
        if candidates.size > 0:
            i0 = min_idx + int(candidates[0])
            if i0 > min_idx:
                t0, t1 = lt[i0 - 1], lt[i0]
                f0, f1 = lf[i0 - 1], lf[i0]
                if abs(f1 - f0) > 0:
                    frac = (half_depth_flux - f0) / (f1 - f0)
                    right_t = t0 + frac * (t1 - t0)
                else:
                    right_t = t0
            else:
                right_t = event_min_t

    if np.isfinite(left_t) and np.isfinite(right_t) and right_t > left_t:
        return float((right_t - left_t) * 24.0)  # days → hours
    return np.nan


def compute_ingress_egress_ratio(
    time: np.ndarray,
    flux: np.ndarray,
    event_time: float,
    window_days: float = 1.0,
) -> dict:
    """Return ingress_duration_hours, egress_duration_hours, egress_ingress_ratio.

    Durations are measured from the half-depth crossing to the dip minimum.
    Returns NaN values on failure.
    """
    result = compute_simple_asymmetry(time, flux, event_time, window_days=window_days)
    ingress_h = result["ingress_duration_days"] * 24.0
    egress_h = result["egress_duration_days"] * 24.0
    if np.isfinite(ingress_h) and np.isfinite(egress_h) and ingress_h > 0:
        ratio = egress_h / ingress_h
    else:
        ratio = np.nan
    return {
        "ingress_duration_hours": ingress_h,
        "egress_duration_hours": egress_h,
        "egress_ingress_ratio": ratio,
    }


# ---------------------------------------------------------------------------
# Symmetric and asymmetric model fitting
# ---------------------------------------------------------------------------

def _gaussian_dip(t: np.ndarray, t0: float, depth: float, sigma: float) -> np.ndarray:
    return 1.0 - depth * np.exp(-0.5 * ((t - t0) / sigma) ** 2)


def _asym_triangle_dip(
    t: np.ndarray, t0: float, depth: float, tau_in: float, tau_eg: float
) -> np.ndarray:
    delta = np.zeros_like(t, dtype=float)
    if tau_in > 0:
        in_m = (t >= t0 - tau_in) & (t < t0)
        if in_m.any():
            delta[in_m] = depth * (t[in_m] - (t0 - tau_in)) / tau_in
    at_min = t == t0
    delta[at_min] = depth
    if tau_eg > 0:
        eg_m = (t > t0) & (t <= t0 + tau_eg)
        if eg_m.any():
            delta[eg_m] = depth * (1.0 - (t[eg_m] - t0) / tau_eg)
    return 1.0 - np.clip(delta, 0.0, depth)


def fit_symmetric_dip_model(
    time: np.ndarray,
    flux: np.ndarray,
    event_time: float,
    window_days: float = 1.0,
) -> dict:
    """Fit a Gaussian symmetric dip model to the local window.

    Returns dict with fit_t0, fit_depth, fit_sigma, chi2_sym, fit_status.
    On failure all numeric values are NaN and fit_status describes the error.
    """
    from scipy.optimize import curve_fit  # local import to keep startup fast

    t, f = _clean_arrays(time, flux)
    half = window_days / 2.0
    mask = (t >= event_time - half) & (t <= event_time + half)
    lt, lf = t[mask], f[mask]
    n = lt.size

    if n < 5:
        return {"fit_t0_sym": np.nan, "fit_depth_sym": np.nan, "fit_sigma_sym": np.nan,
                "chi2_sym": np.nan, "fit_status_sym": "too_few_points"}

    baseline = float(np.nanmedian(lf))
    depth_est = baseline - float(np.nanmin(lf))
    if depth_est <= 0:
        return {"fit_t0_sym": np.nan, "fit_depth_sym": np.nan, "fit_sigma_sym": np.nan,
                "chi2_sym": np.nan, "fit_status_sym": "non_positive_depth"}

    dt = float(np.median(np.diff(lt))) if n > 1 else half / 10.0
    p0 = [event_time, depth_est, max(dt * 3, window_days / 8.0)]
    bounds = (
        [event_time - half, 0.0, dt],
        [event_time + half, 1.0, half],
    )
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            popt, _ = curve_fit(_gaussian_dip, lt, lf, p0=p0, bounds=bounds, maxfev=2000)
        noise = estimate_noise_mad(lf)
        noise = noise if (np.isfinite(noise) and noise > 0) else 1e-6
        residuals = lf - _gaussian_dip(lt, *popt)
        chi2 = float(np.sum((residuals / noise) ** 2))
        return {"fit_t0_sym": popt[0], "fit_depth_sym": popt[1], "fit_sigma_sym": popt[2],
                "chi2_sym": chi2, "fit_status_sym": "ok"}
    except Exception as exc:  # noqa: BLE001
        return {"fit_t0_sym": np.nan, "fit_depth_sym": np.nan, "fit_sigma_sym": np.nan,
                "chi2_sym": np.nan, "fit_status_sym": f"failed:{type(exc).__name__}"}


def fit_asymmetric_dip_model(
    time: np.ndarray,
    flux: np.ndarray,
    event_time: float,
    window_days: float = 1.0,
) -> dict:
    """Fit a triangular asymmetric dip model to the local window.

    Returns dict with fit_t0_asym, fit_depth_asym, fit_tau_in_asym,
    fit_tau_eg_asym, chi2_asym, fit_status_asym.
    """
    from scipy.optimize import curve_fit

    t, f = _clean_arrays(time, flux)
    half = window_days / 2.0
    mask = (t >= event_time - half) & (t <= event_time + half)
    lt, lf = t[mask], f[mask]
    n = lt.size

    if n < 5:
        return {"fit_t0_asym": np.nan, "fit_depth_asym": np.nan,
                "fit_tau_in_asym": np.nan, "fit_tau_eg_asym": np.nan,
                "chi2_asym": np.nan, "fit_status_asym": "too_few_points"}

    baseline = float(np.nanmedian(lf))
    depth_est = baseline - float(np.nanmin(lf))
    if depth_est <= 0:
        return {"fit_t0_asym": np.nan, "fit_depth_asym": np.nan,
                "fit_tau_in_asym": np.nan, "fit_tau_eg_asym": np.nan,
                "chi2_asym": np.nan, "fit_status_asym": "non_positive_depth"}

    dt = float(np.median(np.diff(lt))) if n > 1 else half / 10.0
    p0 = [event_time, depth_est, max(dt * 2, window_days / 10.0), max(dt * 4, window_days / 5.0)]
    bounds = (
        [event_time - half / 2, 0.0, dt, dt],
        [event_time + half / 2, 1.0, half, half * 2],
    )

    def _model(t_arr, t0, d, ti, te):
        return _asym_triangle_dip(t_arr, t0, d, ti, te)

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            popt, _ = curve_fit(_model, lt, lf, p0=p0, bounds=bounds, maxfev=3000)
        noise = estimate_noise_mad(lf)
        noise = noise if (np.isfinite(noise) and noise > 0) else 1e-6
        residuals = lf - _model(lt, *popt)
        chi2 = float(np.sum((residuals / noise) ** 2))
        return {"fit_t0_asym": popt[0], "fit_depth_asym": popt[1],
                "fit_tau_in_asym": popt[2], "fit_tau_eg_asym": popt[3],
                "chi2_asym": chi2, "fit_status_asym": "ok"}
    except Exception as exc:  # noqa: BLE001
        return {"fit_t0_asym": np.nan, "fit_depth_asym": np.nan,
                "fit_tau_in_asym": np.nan, "fit_tau_eg_asym": np.nan,
                "chi2_asym": np.nan, "fit_status_asym": f"failed:{type(exc).__name__}"}


def compute_delta_chi2_symmetric_vs_asymmetric(
    time: np.ndarray,
    flux: np.ndarray,
    event_time: float,
    window_days: float = 1.0,
) -> float:
    """Return Δχ² = χ²_symmetric − χ²_asymmetric.

    Positive values indicate the asymmetric model fits better.
    Returns NaN if either model fails to fit.
    """
    sym = fit_symmetric_dip_model(time, flux, event_time, window_days)
    asym = fit_asymmetric_dip_model(time, flux, event_time, window_days)
    chi2_s = sym.get("chi2_sym", np.nan)
    chi2_a = asym.get("chi2_asym", np.nan)
    if np.isfinite(chi2_s) and np.isfinite(chi2_a):
        return float(chi2_s - chi2_a)
    return np.nan


# ---------------------------------------------------------------------------
# Full per-event feature computation
# ---------------------------------------------------------------------------

def compute_event_features(
    time: np.ndarray,
    flux: np.ndarray,
    event_time: float,
    window_days: float = 1.0,
) -> dict:
    """Compute the full Phase 3 feature set for one candidate event.

    Parameters
    ----------
    time, flux:
        Full light-curve arrays.
    event_time:
        BTJD time of the candidate dip minimum.
    window_days:
        Half-window size (total window = 2 × window_days days).

    Returns
    -------
    dict with all Phase 3 event feature keys.
    """
    t, f = _clean_arrays(time, flux)
    half = window_days / 2.0

    t_start, t_end = float(t[0]), float(t[-1])
    edge_event = bool(
        event_time < t_start + _EDGE_BUFFER_DAYS
        or event_time > t_end - _EDGE_BUFFER_DAYS
    )

    mask = (t >= event_time - half) & (t <= event_time + half)
    lt, lf = t[mask], f[mask]
    n_points = int(lt.size)

    # --- basic depth and SNR ---
    if n_points < 3:
        return _empty_event_features(event_time, n_points, edge_event)

    baseline = float(np.nanmedian(lf))
    min_flux = float(np.nanmin(lf))
    depth_frac = max(baseline - min_flux, 0.0)
    depth_ppm = depth_frac * 1e6

    noise = estimate_noise_mad(lf)
    global_noise = estimate_noise_mad(f)
    if not np.isfinite(noise) or noise <= 0:
        noise = global_noise if (np.isfinite(global_noise) and global_noise > 0) else np.nan
    local_snr = float(depth_frac / noise) if (np.isfinite(noise) and noise > 0) else np.nan

    # --- single-point-like flag ---
    if np.isfinite(noise) and noise > 0 and depth_frac > 0:
        below_half = lf < (baseline - depth_frac / 2.0)
        single_point_like = bool(np.count_nonzero(below_half) <= 1)
    else:
        single_point_like = True

    # --- duration (ingress to egress FWHM proxies) ---
    fwhm_h = estimate_event_fwhm(t, f, event_time, window_days)
    ie = compute_ingress_egress_ratio(t, f, event_time, window_days)

    # Rough total duration: from ingress start to egress end via FWHM or
    # ingress+egress durations
    in_h = ie["ingress_duration_hours"]
    eg_h = ie["egress_duration_hours"]
    if np.isfinite(in_h) and np.isfinite(eg_h):
        duration_h = in_h + eg_h
    elif np.isfinite(fwhm_h):
        duration_h = fwhm_h
    else:
        duration_h = np.nan

    # --- higher-order statistics of local window ---
    try:
        skewness = float(scipy_skew(lf))
    except Exception:  # noqa: BLE001
        skewness = np.nan
    try:
        kurt = float(scipy_kurtosis(lf))
    except Exception:  # noqa: BLE001
        kurt = np.nan

    # --- model comparison ---
    delta_chi2 = compute_delta_chi2_symmetric_vs_asymmetric(t, f, event_time, window_days)

    return {
        "event_time_btjd": event_time,
        "depth_ppm": depth_ppm,
        "local_snr": local_snr,
        "duration_hours": duration_h,
        "fwhm_hours": fwhm_h,
        "ingress_duration_hours": in_h,
        "egress_duration_hours": eg_h,
        "egress_ingress_ratio": ie["egress_ingress_ratio"],
        "skewness": skewness,
        "kurtosis": kurt,
        "delta_chi2_asym": delta_chi2,
        "n_points_window": n_points,
        "edge_event": edge_event,
        "single_point_like": single_point_like,
        "detector_version": DETECTOR_VERSION,
    }


def _empty_event_features(event_time: float, n_points: int, edge_event: bool) -> dict:
    return {
        "event_time_btjd": event_time,
        "depth_ppm": np.nan,
        "local_snr": np.nan,
        "duration_hours": np.nan,
        "fwhm_hours": np.nan,
        "ingress_duration_hours": np.nan,
        "egress_duration_hours": np.nan,
        "egress_ingress_ratio": np.nan,
        "skewness": np.nan,
        "kurtosis": np.nan,
        "delta_chi2_asym": np.nan,
        "n_points_window": n_points,
        "edge_event": edge_event,
        "single_point_like": True,
        "detector_version": DETECTOR_VERSION,
    }


# ---------------------------------------------------------------------------
# Improved Phase 3 scanner
# ---------------------------------------------------------------------------

def scan_lightcurve_for_asymmetric_dips(
    time: np.ndarray,
    flux: np.ndarray,
    sigma_threshold: float = 4.0,
    window_days: float = 1.0,
) -> pd.DataFrame:
    """Improved asymmetric-dip scanner returning the full Phase 3 feature set.

    Finds local minima above *sigma_threshold* × global MAD noise and
    computes per-event features including FWHM, ingress/egress duration,
    skewness, kurtosis, and Δχ² from symmetric vs. asymmetric model fits.

    Parameters
    ----------
    time:
        BTJD time array.
    flux:
        Normalized flux array.
    sigma_threshold:
        Minimum depth in units of global MAD noise.
    window_days:
        Total window width (in days) used for per-event feature extraction.

    Returns
    -------
    pd.DataFrame
        One row per candidate event, sorted by depth_ppm descending.
        Returns empty DataFrame when no candidates are found.

    Notes
    -----
    This scanner identifies *candidate dip-like features* only.
    It does not confirm astrophysical events.
    """
    if sigma_threshold <= 0:
        raise ValueError("sigma_threshold must be positive")
    if window_days <= 0:
        raise ValueError("window_days must be positive")

    t, f = _clean_arrays(time, flux)
    if t.size < 10:
        return pd.DataFrame(columns=_PHASE3_EVENT_COLUMNS)

    baseline = float(np.nanmedian(f))
    inv_flux = baseline - f
    global_noise = estimate_noise_mad(f)
    if not np.isfinite(global_noise) or global_noise <= 0:
        return pd.DataFrame(columns=_PHASE3_EVENT_COLUMNS)

    min_distance = max(3, int(window_days / (2.0 * np.median(np.diff(t))) // 2))
    peaks, props = find_peaks(
        inv_flux,
        height=sigma_threshold * global_noise,
        distance=min_distance,
    )
    if peaks.size == 0:
        return pd.DataFrame(columns=_PHASE3_EVENT_COLUMNS)

    rows: list[dict] = []
    for peak_idx in peaks:
        event_time = float(t[peak_idx])
        feats = compute_event_features(t, f, event_time, window_days)
        rows.append(feats)

    if not rows:
        return pd.DataFrame(columns=_PHASE3_EVENT_COLUMNS)

    result = pd.DataFrame(rows)
    result = result.sort_values("depth_ppm", ascending=False).reset_index(drop=True)
    return result


_PHASE3_EVENT_COLUMNS = [
    "event_time_btjd", "depth_ppm", "local_snr", "duration_hours",
    "fwhm_hours", "ingress_duration_hours", "egress_duration_hours",
    "egress_ingress_ratio", "skewness", "kurtosis", "delta_chi2_asym",
    "n_points_window", "edge_event", "single_point_like", "detector_version",
]
