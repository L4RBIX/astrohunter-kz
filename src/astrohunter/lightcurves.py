import numpy as np
import pandas as pd
import lightkurve as lk
from astropy.stats import median_absolute_deviation


def search_tess_lightcurves(target: str, mission="TESS"):
    """
    Searches for TESS light curves for a given target.
    Prefer SPOC short cadence first, then fall back to all SPOC light curves.
    """
    print(f"Searching for {mission} SPOC short-cadence light curves for {target}...")
    search_result = lk.search_lightcurve(
        target,
        mission=mission,
        author="SPOC",
        cadence="short",
    )

    if len(search_result) == 0:
        print("No SPOC short-cadence results found. Trying all SPOC light curves...")
        search_result = lk.search_lightcurve(
            target,
            mission=mission,
            author="SPOC",
        )

    return search_result


def download_and_stitch_lightcurves(target: str, mission="TESS", max_lightcurves: int = 4):
    """
    Searches, downloads, and stitches a limited number of available light curves.
    Limiting downloads keeps the Beta Pic positive-control notebook fast.
    """
    search_result = search_tess_lightcurves(target, mission=mission)

    if len(search_result) == 0:
        raise ValueError(f"No {mission} light curves found for target: {target}")

    n_download = min(max_lightcurves, len(search_result))
    print(f"Found {len(search_result)} light curves. Downloading first {n_download}...")

    lc_collection = search_result[:n_download].download_all()

    if lc_collection is None or len(lc_collection) == 0:
        raise ValueError(f"Failed to download light curves for target: {target}")

    lc_stitched = lc_collection.stitch()
    lc_clean = lc_stitched.remove_nans().remove_outliers(sigma=10)
    lc_norm = lc_clean.normalize()

    return lc_norm


def lightcurve_to_dataframe(lc):
    """
    Converts a lightkurve.LightCurve object into a pandas DataFrame.
    """
    data = {
        "time_btjd": lc.time.value,
        "flux": lc.flux.value,
    }

    if hasattr(lc, "flux_err") and lc.flux_err is not None:
        data["flux_err"] = lc.flux_err.value

    return pd.DataFrame(data)


def estimate_noise_mad(flux):
    """
    Robust noise estimation using Median Absolute Deviation (MAD).
    """
    mad = median_absolute_deviation(flux, ignore_nan=True)
    return mad * 1.4826