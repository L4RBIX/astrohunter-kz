import matplotlib.pyplot as plt
import numpy as np

def plot_full_lightcurve(time, flux, title, output_path=None):
    """
    Plots the full light curve and optionally saves it to a file.
    """
    plt.figure(figsize=(12, 4))
    plt.plot(time, flux, 'k.', markersize=2, alpha=0.5)
    plt.title(title)
    plt.xlabel('Time (BTJD)')
    plt.ylabel('Normalized Flux')
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    
    if output_path:
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        
    plt.show()
    plt.close()

def plot_event_window(time, flux, event_time, window_days=0.5, title=None, output_path=None):
    """
    Plots a specific event window around a candidate dip.
    """
    mask = (time >= event_time - window_days/2) & (time <= event_time + window_days/2)
    local_time = time[mask]
    local_flux = flux[mask]
    
    plt.figure(figsize=(8, 4))
    plt.plot(local_time, local_flux, 'k.-', markersize=4, alpha=0.7)
    plt.axvline(event_time, color='red', linestyle='--', alpha=0.7, label='Candidate Event')
    
    if title:
        plt.title(title)
    else:
        plt.title(f'Candidate Dip Window (BTJD {event_time:.2f})')
        
    plt.xlabel('Time (BTJD)')
    plt.ylabel('Normalized Flux')
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    
    if output_path:
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        
    plt.show()
    plt.close()
