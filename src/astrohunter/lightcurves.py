"""Light-curve retrieval, normalization, and caching helpers for AstroHunter KZ."""

from __future__ import annotations

import logging
import traceback
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from astropy.stats import median_absolute_deviation

logger = logging.getLogger(__name__)


def _format_download_error(exc: BaseException, tic_id: int | str, author: str | None = None) -> str:
    """Return a one-line rich error string including exception class, message, and traceback tip.

    Logs the full traceback at DEBUG level so it is available in verbose runs
    without cluttering normal pipeline output.
    """
    exc_class = type(exc).__name__
    exc_msg = str(exc)
    tb_str = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    short = f"{exc_class}: {exc_msg}"
    logger.debug(
        "Download error for TIC %s (author=%s).\n%s: %s\nTraceback:\n%s",
        tic_id, author, exc_class, exc_msg, tb_str,
    )
    return short


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


# ---------------------------------------------------------------------------
# Phase 3: TIC-based download and parquet cache
# ---------------------------------------------------------------------------

def download_lightcurve_for_tic(
    tic_id: int | str,
    max_lightcurves: int = 1,
    author_preference: tuple[str, ...] = ("SPOC", "QLP"),
) -> pd.DataFrame | None:
    """Download and process the first available TESS light curve for a TIC ID.

    Tries each author in *author_preference* in order; falls back to any
    available product when none match.  Applies the standard clean-normalize
    pipeline and returns a tidy DataFrame.

    Parameters
    ----------
    tic_id:
        TIC identifier (integer or string, without the "TIC " prefix).
    max_lightcurves:
        Maximum number of products to download (usually 1 in dev mode).
    author_preference:
        Pipeline authors to try first (SPOC is highest quality).

    Returns
    -------
    pd.DataFrame or None
        DataFrame with columns time_btjd, flux, (flux_err, quality) if
        available, plus tic_id and product_label columns.
        Returns None on any failure.
    """
    try:
        import lightkurve as lk
    except Exception as exc:  # noqa: BLE001 — catches SyntaxError/IndentationError in lk deps
        short = _format_download_error(exc, tic_id)
        logger.error(
            "lightkurve import failed for TIC %s (%s). "
            "Check .venv/lib/python*/site-packages/lightkurve/ for corrupted files. "
            "Run: python scripts/debug_lightcurve_download.py --tic-id %s --verbose",
            tic_id, short, tic_id,
        )
        return None

    target_str = f"TIC {tic_id}"

    # Try preferred authors first, then unconstrained
    search_result = None
    for author in list(author_preference) + [None]:
        try:
            kwargs: dict[str, Any] = {"mission": "TESS"}
            if author is not None:
                kwargs["author"] = author
            sr = lk.search_lightcurve(target_str, **kwargs)
            if sr is not None and len(sr) > 0:
                search_result = sr
                logger.debug("TIC %s: found %d products (author=%s).", tic_id, len(sr), author)
                break
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "MAST search for TIC %s (author=%s) failed: %s",
                tic_id, author, _format_download_error(exc, tic_id, author=author),
            )

    if search_result is None or len(search_result) == 0:
        logger.warning("No TESS products found for TIC %s.", tic_id)
        return None

    n_download = min(max_lightcurves, len(search_result))
    try:
        collection = search_result[:n_download].download_all()
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Download failed for TIC %s: %s",
            tic_id, _format_download_error(exc, tic_id),
        )
        return None

    if collection is None or len(collection) == 0:
        logger.warning("Empty download for TIC %s.", tic_id)
        return None

    frames: list[pd.DataFrame] = []
    for i, lc in enumerate(collection):
        try:
            cleaned = clean_normalize_lightcurve(lc)
            df = lightcurve_to_dataframe(cleaned)
            df["tic_id"] = int(tic_id)
            label = getattr(lc, "label", None) or getattr(search_result[i], "target_name", None) or ""
            df["product_label"] = str(label)
            if not df.empty:
                frames.append(df)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Processing lc %d for TIC %s failed: %s", i, tic_id, exc)

    if not frames:
        return None

    return pd.concat(frames, ignore_index=True)


def save_processed_lightcurve_cache(df: pd.DataFrame, path: Path | str) -> None:
    """Save a processed light-curve DataFrame as a parquet file.

    Creates parent directories as needed.  Byte-swapped array columns (common
    from FITS-derived lightkurve output) are converted to native byte order
    before serialisation so pyarrow can write them without error.

    Parameters
    ----------
    df:
        Processed light-curve DataFrame (output of download_lightcurve_for_tic).
    path:
        Destination file path (should end in .parquet).
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    # Normalise byte order: pyarrow rejects non-native (e.g. >i4 from FITS)
    df_out = df.copy()
    for col in df_out.columns:
        arr = df_out[col].to_numpy()
        if hasattr(arr.dtype, "byteorder") and arr.dtype.byteorder not in ("=", "|", "<"):
            df_out[col] = arr.astype(arr.dtype.newbyteorder("="), copy=False)

    df_out.to_parquet(p, index=False)
    logger.debug("Saved light-curve cache to %s (%d rows).", p, len(df))


def load_processed_lightcurve_cache(path: Path | str) -> pd.DataFrame | None:
    """Load a previously cached processed light-curve parquet file.

    Returns None if the file does not exist or cannot be read.
    """
    p = Path(path)
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
        logger.debug("Loaded light-curve cache from %s (%d rows).", p, len(df))
        return df
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to read cache file %s: %s", p, exc)
        return None


def load_or_download_lightcurve_cache(
    tic_id: int | str,
    cache_dir: Path | str,
    max_lightcurves: int = 1,
    author_preference: tuple[str, ...] = ("SPOC", "QLP"),
    force_download: bool = False,
) -> pd.DataFrame | None:
    """Return a processed light curve for *tic_id*, using a parquet cache.

    On the first call, the light curve is downloaded and saved to
    ``cache_dir/tic_{tic_id}.parquet``.  Subsequent calls load from disk.

    Parameters
    ----------
    tic_id:
        TIC identifier.
    cache_dir:
        Directory for parquet cache files (created if absent).
    max_lightcurves:
        Passed to download_lightcurve_for_tic on cache miss.
    author_preference:
        Preferred pipeline authors.
    force_download:
        If True, skip the cache and re-download.

    Returns
    -------
    pd.DataFrame or None
    """
    cache_path = Path(cache_dir) / f"tic_{tic_id}.parquet"

    if not force_download:
        cached = load_processed_lightcurve_cache(cache_path)
        if cached is not None:
            return cached

    logger.info("Downloading light curve for TIC %s...", tic_id)
    df = download_lightcurve_for_tic(tic_id, max_lightcurves=max_lightcurves,
                                     author_preference=author_preference)
    if df is not None and not df.empty:
        try:
            save_processed_lightcurve_cache(df, cache_path)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not save cache for TIC %s: %s", tic_id, exc)
    return df
