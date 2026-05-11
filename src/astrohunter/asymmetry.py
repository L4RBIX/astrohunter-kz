import numpy as np
import pandas as pd
from scipy.signal import find_peaks
from astropy.stats import median_absolute_deviation

def detect_candidate_dips(time, flux, sigma_threshold=4.0, min_distance=5, window_days=0.5):
    """
    Detects candidate dips in the light curve.
    """
    # Use global median as a simple baseline
    baseline = np.nanmedian(flux)
    
    # Invert flux so dips become peaks for find_peaks
    inverted_flux = baseline - flux
    
    # Global robust noise estimate
    noise_est = median_absolute_deviation(flux, ignore_nan=True) * 1.4826
    
    # Find peaks in the inverted flux (dips in original flux)
    peaks, _ = find_peaks(inverted_flux, height=sigma_threshold * noise_est, distance=min_distance)
    
    candidates = []
    
    for peak_idx in peaks:
        event_time = time[peak_idx]
        depth = inverted_flux[peak_idx]
        depth_ppm = depth * 1e6
        
        # Extract local window
        mask = (time >= event_time - window_days/2) & (time <= event_time + window_days/2)
        local_time = time[mask]
        local_flux = flux[mask]
        n_points_window = len(local_time)
        
        if n_points_window == 0:
            continue
            
        # Local noise estimate
        local_sigma = median_absolute_deviation(local_flux, ignore_nan=True) * 1.4826
        if local_sigma == 0 or np.isnan(local_sigma):
            local_sigma = noise_est
            
        snr_approx = depth / local_sigma
        
        candidates.append({
            'event_time_btjd': event_time,
            'depth': depth,
            'depth_ppm': depth_ppm,
            'local_sigma': local_sigma,
            'snr_approx': snr_approx,
            'n_points_window': n_points_window,
            'window_start': event_time - window_days/2,
            'window_end': event_time + window_days/2
        })
        
    return pd.DataFrame(candidates)

def compute_simple_asymmetry(time, flux, event_time, window_days=0.5):
    """
    Computes a simple asymmetry score for a candidate dip.
    Asymmetry score = egress_duration / ingress_duration
    """
    # Extract local window
    mask = (time >= event_time - window_days/2) & (time <= event_time + window_days/2)
    local_time = time[mask]
    local_flux = flux[mask]
    
    if len(local_time) < 10:
        return {'ingress_duration_days': np.nan, 'egress_duration_days': np.nan, 'asymmetry_score': np.nan}
        
    baseline = np.nanmedian(local_flux)
    min_flux = np.nanmin(local_flux)
    depth = baseline - min_flux
    half_depth_flux = baseline - (depth / 2.0)
    
    # Find the minimum point in the window
    min_idx = np.argmin(local_flux)
    
    # Split into ingress (pre-minimum) and egress (post-minimum)
    pre_time = local_time[:min_idx+1]
    pre_flux = local_flux[:min_idx+1]
    
    post_time = local_time[min_idx:]
    post_flux = local_flux[min_idx:]
    
    ingress_duration = np.nan
    egress_duration = np.nan
    
    # Ingress duration: from last half-depth crossing before minimum to minimum
    try:
        crossings = np.where(pre_flux > half_depth_flux)[0]
        if len(crossings) > 0:
            ingress_start_idx = crossings[-1]
            ingress_duration = local_time[min_idx] - pre_time[ingress_start_idx]
    except Exception:
        pass
        
    # Egress duration: from minimum to first half-depth crossing after minimum
    try:
        crossings = np.where(post_flux > half_depth_flux)[0]
        if len(crossings) > 0:
            egress_end_idx = crossings[0]
            egress_duration = post_time[egress_end_idx] - local_time[min_idx]
    except Exception:
        pass
        
    asymmetry_score = np.nan
    if ingress_duration > 0 and not np.isnan(ingress_duration) and not np.isnan(egress_duration):
        asymmetry_score = egress_duration / ingress_duration
        
    return {
        'ingress_duration_days': ingress_duration,
        'egress_duration_days': egress_duration,
        'asymmetry_score': asymmetry_score
    }

def add_asymmetry_scores(events_df, time, flux, window_days=0.5):
    """
    Applies compute_simple_asymmetry to all events in the DataFrame.
    """
    if events_df.empty:
        return events_df
        
    results = []
    for _, row in events_df.iterrows():
        res = compute_simple_asymmetry(time, flux, row['event_time_btjd'], window_days)
        results.append(res)
        
    asym_df = pd.DataFrame(results)
    return pd.concat([events_df.reset_index(drop=True), asym_df.reset_index(drop=True)], axis=1)
