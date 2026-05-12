"""Light-curve retrieval and normalization helpers for AstroHunter KZ."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from astropy.stats import median_absolute_deviation


def _as_numpy(values: Any) -> np.ndarray:
    """Return plain finite-friendly numpy values from astropy/lightkurve columns."""
    if hasattr(values, "value"):
        values = values.value
    return np.asarray(values, dtype=float)


def search_tess_lightcurves(
    target: str,
    mission: str = "TESS",
    author: str | None = None,
    cadence: str | None = None,
):
    """Search MAST for TESS light curves without downloading data.

    Parameters are passed through to ``lightkurve.search_lightcurve``. The
    default intentionally does not constrain author/cadence so that public TESS
    products can be found for common targets without API keys.
    """
    try:
        import lightkurve as lk
    except ImportError as exc:
        raise ImportError(
            "lightkurve is required for MAST searches. Install requirements.txt."
        ) from exc

    kwargs: dict[str, Any] = {"mission": mission}
    if author is not None:
        kwargs["author"] = author
    if cadence is not None:
        kwargs["cadence"] = cadence

    print(f"Searching {mission} light curves for {target!r}...")
    if author:
        print(f"  author={author}")
    if cadence:
        print(f"  cadence={cadence}")

    try:
        search_result = lk.search_lightcurve(target, **kwargs)
    except Exception as exc:  # MAST/network failures should not look like science failures.
        print(f"MAST/lightkurve search failed for {target!r}: {exc}")
        return []

    print(f"Found {len(search_result)} light-curve products.")
    return search_result


def download_one_lightcurve(
    target: str,
    mission: str = "TESS",
    index: int = 0,
):
    """Download one TESS light curve by search-result index."""
    if index < 0:
        raise ValueError("index must be non-negative")

    search_result = search_tess_lightcurves(target, mission=mission)
    if len(search_result) == 0:
        raise RuntimeError(f"No {mission} light curves found for target {target!r}.")
    if index >= len(search_result):
        raise IndexError(
            f"Requested index {index}, but only {len(search_result)} products were found."
        )

    print(f"Downloading light curve {index + 1} of {len(search_result)}...")
    try:
        collection = search_result[index : index + 1].download_all()
    except Exception as exc:
        raise RuntimeError(f"Failed to download light curve for {target!r}: {exc}") from exc

    if collection is None or len(collection) == 0:
        raise RuntimeError(f"Download returned no light curves for {target!r}.")
    return collection[0]


def download_limited_lightcurves(
    target: str,
    mission: str = "TESS",
    max_lightcurves: int = 1,
):
    """Download at most ``max_lightcurves`` products for a target.

    This guard prevents accidental downloads of every available TESS sector.
    """
    if max_lightcurves < 1:
        raise ValueError("max_lightcurves must be at least 1")

    search_result = search_tess_lightcurves(target, mission=mission)
    if len(search_result) == 0:
        raise RuntimeError(f"No {mission} light curves found for target {target!r}.")

    n_download = min(max_lightcurves, len(search_result))
    print(
        f"Downloading {n_download} of {len(search_result)} available products "
        f"for {target!r}."
    )
    try:
        collection = search_result[:n_download].download_all()
    except Exception as exc:
        raise RuntimeError(f"Failed to download light curves for {target!r}: {exc}") from exc

    if collection is None or len(collection) == 0:
        raise RuntimeError(f"Download returned no light curves for {target!r}.")
    return collection


def clean_normalize_lightcurve(lc):
    """Remove invalid points, clip extreme outliers, and normalize a light curve."""
    if lc is None:
        raise ValueError("lc must not be None")

    cleaned = lc
    for method_name, kwargs in (
        ("remove_nans", {}),
        ("remove_outliers", {"sigma": 10}),
        ("normalize", {}),
    ):
        method = getattr(cleaned, method_name, None)
        if callable(method):
            try:
                cleaned = method(**kwargs)
            except Exception as exc:
                print(f"Warning: lightkurve.{method_name} failed: {exc}")

    return cleaned


def lightcurve_to_dataframe(lc) -> pd.DataFrame:
    """Convert a lightkurve-like object into a tidy pandas DataFrame."""
    if lc is None:
        raise ValueError("lc must not be None")
    if not hasattr(lc, "time") or not hasattr(lc, "flux"):
        raise AttributeError("lc must expose time and flux attributes")

    time = _as_numpy(lc.time)
    flux = _as_numpy(lc.flux)
    finite = np.isfinite(time) & np.isfinite(flux)

    data: dict[str, np.ndarray] = {
        "time_btjd": time[finite],
        "flux": flux[finite],
    }

    flux_err = getattr(lc, "flux_err", None)
    if flux_err is not None:
        flux_err_values = _as_numpy(flux_err)
        if flux_err_values.shape == flux.shape:
            data["flux_err"] = flux_err_values[finite]

    quality = getattr(lc, "quality", None)
    if quality is not None:
        quality_values = np.asarray(quality)
        if quality_values.shape == flux.shape:
            data["quality"] = quality_values[finite]

    return pd.DataFrame(data)


def estimate_noise_mad(flux) -> float:
    """Estimate robust scatter using 1.4826 scaled median absolute deviation."""
    values = _as_numpy(flux)
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return float("nan")

    mad = median_absolute_deviation(finite, ignore_nan=True)
    noise = float(1.4826 * mad)
    if noise <= 0 and finite.size > 1:
        noise = float(np.nanstd(finite))
    return noise
