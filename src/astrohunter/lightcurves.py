import numpy as np
import pandas as pd
import lightkurve as lk
from astropy.stats import median_absolute_deviation

def search_tess_lightcurves(target: str, mission="TESS"):
    """
    Searches for TESS light curves for a given target.
    """
    print(f"Searching for {mission} light curves for {target}...")
    search_result = lk.search_lightcurve(target, mission=mission, author="SPOC")
    return search_result

def download_and_stitch_lightcurves(target: str, mission="TESS"):
    """
    Searches, downloads, and stitches all available light curves for a target.
    Removes NaNs and normalizes the flux.
    """
    search_result = search_tess_lightcurves(target, mission=mission)
    
    if len(search_result) == 0:
        raise ValueError(f"No {mission} light curves found for target: {target}")
        
    print(f"Found {len(search_result)} light curves. Downloading and stitching...")
    lc_collection = search_result.download_all()
    
    if lc_collection is None or len(lc_collection) == 0:
        raise ValueError(f"Failed to download light curves for target: {target}")
        
    # Stitch the lightcurves together
    lc_stitched = lc_collection.stitch()
    
    # Clean the light curve
    lc_clean = lc_stitched.remove_nans()
    lc_norm = lc_clean.normalize()
    
    return lc_norm

def lightcurve_to_dataframe(lc):
    """
    Converts a lightkurve.LightCurve object into a pandas DataFrame.
    """
    data = {
        'time_btjd': lc.time.value,
        'flux': lc.flux.value,
    }
    
    if 'flux_err' in lc.columns:
        data['flux_err'] = lc.flux_err.value
        
    return pd.DataFrame(data)

def estimate_noise_mad(flux):
    """
    Robust noise estimation using Median Absolute Deviation (MAD).
    """
    mad = median_absolute_deviation(flux, ignore_nan=True)
    return mad * 1.4826  # Scale for normal distribution
