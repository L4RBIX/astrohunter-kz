"""Synthetic asymmetric dip injection and injection-recovery framework.

This module generates and injects synthetic exocomet-like asymmetric dips into
real TESS light curves, then runs a detector to measure recovery fractions.

PURPOSE — sensitivity testing only.
Injection-recovery metrics tell you how well the pipeline can *find* an
injected signal of known amplitude.  They do NOT measure the purity of
real candidates, do NOT confirm real exocomet detections, and must NOT be
reported as discovery statistics.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

import numpy as np
import pandas as pd

from astrohunter.lightcurves import estimate_noise_mad

logger = logging.getLogger(__name__)

# Depth range in ppm
DEPTH_PPM_MIN = 50.0
DEPTH_PPM_MAX = 5000.0

# Duration ranges in hours
INGRESS_HOURS_MIN = 0.5
INGRESS_HOURS_MAX = 8.0
EGRESS_HOURS_MIN = 1.0
EGRESS_HOURS_MAX = 24.0

# Edge buffer as fraction of total baseline span to avoid injecting at edges
EDGE_BUFFER_FRACTION = 0.10

INJECTOR_VERSION = "phase3_v1"


# ---------------------------------------------------------------------------
# Core model
# ---------------------------------------------------------------------------

def asymmetric_dip_model(
    time: np.ndarray,
    event_time: float,
    depth_ppm: float,
    ingress_duration_hours: float,
    egress_duration_hours: float,
) -> np.ndarray:
    """Return the fractional flux *decrement* for a triangular asymmetric dip.

    The profile is:
    - Linear ingress from ``event_time - ingress_days`` to ``event_time``.
    - Linear egress from ``event_time`` to ``event_time + egress_days``.
    - Zero elsewhere.

    Returns a non-negative array.  Subtract this from normalized flux to apply
    the dip.

    Parameters
    ----------
    time:
        Time array in BTJD days.
    event_time:
        Time of dip minimum in BTJD days.
    depth_ppm:
        Dip depth in parts per million.
    ingress_duration_hours:
        Full ingress duration in hours.
    egress_duration_hours:
        Full egress duration in hours.

    Returns
    -------
    np.ndarray
        Non-negative fractional decrement, same shape as ``time``.
    """
    depth_frac = float(depth_ppm) * 1e-6
    ingress_days = float(ingress_duration_hours) / 24.0
    egress_days = float(egress_duration_hours) / 24.0

    t = np.asarray(time, dtype=float)
    delta = np.zeros_like(t)

    if ingress_days > 0:
        in_mask = (t >= event_time - ingress_days) & (t < event_time)
        if in_mask.any():
            delta[in_mask] = depth_frac * (t[in_mask] - (event_time - ingress_days)) / ingress_days

    # Point at minimum
    at_min = t == event_time
    delta[at_min] = depth_frac

    if egress_days > 0:
        eg_mask = (t > event_time) & (t <= event_time + egress_days)
        if eg_mask.any():
            delta[eg_mask] = depth_frac * (1.0 - (t[eg_mask] - event_time) / egress_days)

    return np.clip(delta, 0.0, depth_frac)


def inject_asymmetric_dip(
    time: np.ndarray,
    flux: np.ndarray,
    event_time: float,
    depth_ppm: float,
    ingress_duration_hours: float,
    egress_duration_hours: float,
) -> np.ndarray:
    """Return a copy of *flux* with one synthetic asymmetric dip injected.

    The original array is not modified.

    Parameters
    ----------
    time:
        Time array in BTJD days.
    flux:
        Normalized flux array (1.0 = baseline).
    event_time:
        Time of dip minimum in BTJD days.
    depth_ppm:
        Injected depth in parts per million.
    ingress_duration_hours:
        Ingress duration in hours.
    egress_duration_hours:
        Egress duration in hours.

    Returns
    -------
    np.ndarray
        New flux array with dip injected, same shape as input.
    """
    t = np.asarray(time, dtype=float)
    f = np.asarray(flux, dtype=float)
    if t.shape != f.shape:
        raise ValueError("time and flux must have the same shape")
    delta = asymmetric_dip_model(t, event_time, depth_ppm, ingress_duration_hours, egress_duration_hours)
    return f - delta


# ---------------------------------------------------------------------------
# Parameter sampling
# ---------------------------------------------------------------------------

def sample_injection_parameters(random_state: Any = None) -> dict:
    """Sample random injection parameters for one synthetic dip.

    Depth is uniform in [50, 5000] ppm.
    Ingress is uniform in [0.5, 8] hours.
    Egress is biased to be longer than ingress: egress = ingress * ratio
    where ratio ~ LogUniform(log(1.5), log(8)), capped at 24 hours.

    Returns
    -------
    dict with keys:
        depth_ppm, ingress_duration_hours, egress_duration_hours,
        asymmetry_ratio
    """
    rng = np.random.default_rng(random_state)

    depth_ppm = float(rng.uniform(DEPTH_PPM_MIN, DEPTH_PPM_MAX))
    ingress_hours = float(rng.uniform(INGRESS_HOURS_MIN, INGRESS_HOURS_MAX))

    # Egress ratio log-uniform in [1.2, 8.0] so egress is usually longer
    log_ratio = rng.uniform(np.log(1.2), np.log(8.0))
    ratio = float(np.exp(log_ratio))
    egress_hours = float(np.clip(ingress_hours * ratio, EGRESS_HOURS_MIN, EGRESS_HOURS_MAX))
    asymmetry_ratio = egress_hours / max(ingress_hours, 1e-9)

    return {
        "depth_ppm": depth_ppm,
        "ingress_duration_hours": ingress_hours,
        "egress_duration_hours": egress_hours,
        "asymmetry_ratio": asymmetry_ratio,
    }


# ---------------------------------------------------------------------------
# Single injection-recovery trial
# ---------------------------------------------------------------------------

def run_single_injection_recovery(
    time: np.ndarray,
    flux: np.ndarray,
    detector_fn: Callable[[np.ndarray, np.ndarray], pd.DataFrame],
    params: dict,
    tolerance_hours: float = 3.0,
) -> dict:
    """Inject one synthetic dip and check whether the detector recovers it.

    Parameters
    ----------
    time:
        Time array in BTJD days (finite, sorted).
    flux:
        Normalized flux array.
    detector_fn:
        Callable with signature ``detector_fn(time, flux) -> pd.DataFrame``
        where the DataFrame has at least ``event_time_btjd``.
    params:
        Dict from :func:`sample_injection_parameters`.  If ``event_time`` key
        is present it is used directly; otherwise one is chosen randomly
        inside the array bounds with an edge buffer.
    tolerance_hours:
        Maximum timing offset in hours for a match to count as recovered.

    Returns
    -------
    dict with injection ground truth and recovery result columns.
    """
    t = np.asarray(time, dtype=float)
    f = np.asarray(flux, dtype=float)

    finite = np.isfinite(t) & np.isfinite(f)
    t_clean = t[finite]
    f_clean = f[finite]

    if t_clean.size < 20:
        return _empty_recovery_row(params, tolerance_hours, noise_mad=np.nan)

    t_min, t_max = float(t_clean[0]), float(t_clean[-1])
    span = t_max - t_min
    buffer = max(EDGE_BUFFER_FRACTION * span, 0.5 / 24.0)  # at least 30 min

    event_time = params.get("event_time")
    if event_time is None or not np.isfinite(event_time):
        rng = np.random.default_rng(None)
        event_time = float(rng.uniform(t_min + buffer, t_max - buffer))

    depth_ppm = float(params["depth_ppm"])
    ingress_hours = float(params["ingress_duration_hours"])
    egress_hours = float(params["egress_duration_hours"])
    asymmetry_ratio = float(params.get("asymmetry_ratio", egress_hours / max(ingress_hours, 1e-9)))

    noise_mad = float(estimate_noise_mad(f_clean))
    injected_flux = inject_asymmetric_dip(t_clean, f_clean, event_time, depth_ppm, ingress_hours, egress_hours)

    try:
        events = detector_fn(t_clean, injected_flux)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Detector raised exception during injection trial: %s", exc)
        events = pd.DataFrame()

    tolerance_days = tolerance_hours / 24.0
    recovered = False
    recovered_event_time = np.nan
    timing_error_hours = np.nan
    recovered_depth_ppm = np.nan
    recovered_snr = np.nan

    if isinstance(events, pd.DataFrame) and not events.empty and "event_time_btjd" in events.columns:
        timing_errors = (events["event_time_btjd"] - event_time).abs()
        best_idx = timing_errors.idxmin()
        best_error_days = float(timing_errors.loc[best_idx])
        if best_error_days <= tolerance_days:
            recovered = True
            recovered_event_time = float(events.loc[best_idx, "event_time_btjd"])
            timing_error_hours = best_error_days * 24.0
            if "depth_ppm" in events.columns:
                recovered_depth_ppm = float(events.loc[best_idx, "depth_ppm"])
            if "local_snr" in events.columns:
                recovered_snr = float(events.loc[best_idx, "local_snr"])

    return {
        "injected_event_time_btjd": event_time,
        "injected_depth_ppm": depth_ppm,
        "injected_ingress_hours": ingress_hours,
        "injected_egress_hours": egress_hours,
        "injected_asymmetry_ratio": asymmetry_ratio,
        "recovered": recovered,
        "recovered_event_time_btjd": recovered_event_time,
        "timing_error_hours": timing_error_hours,
        "recovered_depth_ppm": recovered_depth_ppm,
        "recovered_local_snr": recovered_snr,
        "recovery_tolerance_hours": tolerance_hours,
        "noise_mad": noise_mad,
        "injector_version": INJECTOR_VERSION,
    }


def _empty_recovery_row(params: dict, tolerance_hours: float, noise_mad: float) -> dict:
    return {
        "injected_event_time_btjd": np.nan,
        "injected_depth_ppm": params.get("depth_ppm", np.nan),
        "injected_ingress_hours": params.get("ingress_duration_hours", np.nan),
        "injected_egress_hours": params.get("egress_duration_hours", np.nan),
        "injected_asymmetry_ratio": params.get("asymmetry_ratio", np.nan),
        "recovered": False,
        "recovered_event_time_btjd": np.nan,
        "timing_error_hours": np.nan,
        "recovered_depth_ppm": np.nan,
        "recovered_local_snr": np.nan,
        "recovery_tolerance_hours": tolerance_hours,
        "noise_mad": noise_mad,
        "injector_version": INJECTOR_VERSION,
    }


# ---------------------------------------------------------------------------
# Batch injection-recovery on one light curve
# ---------------------------------------------------------------------------

def run_injection_recovery_on_lightcurve(
    time: np.ndarray,
    flux: np.ndarray,
    n_injections: int,
    detector_fn: Callable[[np.ndarray, np.ndarray], pd.DataFrame],
    tolerance_hours: float = 3.0,
    random_state: Any = None,
) -> pd.DataFrame:
    """Run *n_injections* independent injection-recovery trials on one light curve.

    Each trial injects a fresh synthetic dip at a different random position
    and with independently sampled parameters.  The ground truth parameters
    are recorded alongside the detector's response.

    Parameters
    ----------
    time:
        BTJD time array.
    flux:
        Normalized flux array.
    n_injections:
        Number of independent trials to run.
    detector_fn:
        Callable ``(time, flux) -> events_df``.
    tolerance_hours:
        Timing tolerance for recovery matching.
    random_state:
        Seed or ``np.random.Generator`` for reproducibility.

    Returns
    -------
    pd.DataFrame
        One row per injection trial with ground truth and recovery columns.
    """
    rng = np.random.default_rng(random_state)

    t_clean = np.asarray(time, dtype=float)
    f_clean = np.asarray(flux, dtype=float)
    finite = np.isfinite(t_clean) & np.isfinite(f_clean)
    t_clean = t_clean[finite]
    f_clean = f_clean[finite]

    if t_clean.size < 20:
        logger.warning("Light curve too short for injection-recovery (%d points).", t_clean.size)
        return pd.DataFrame()

    t_min, t_max = float(t_clean[0]), float(t_clean[-1])
    span = t_max - t_min
    buffer = max(EDGE_BUFFER_FRACTION * span, 0.5 / 24.0)

    rows: list[dict] = []
    for i in range(n_injections):
        seed = int(rng.integers(0, 2**31))
        params = sample_injection_parameters(random_state=seed)
        params["event_time"] = float(rng.uniform(t_min + buffer, t_max - buffer))
        row = run_single_injection_recovery(t_clean, f_clean, detector_fn, params, tolerance_hours)
        rows.append(row)

    return pd.DataFrame(rows)
