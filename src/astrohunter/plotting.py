"""Matplotlib plotting helpers for Phase 1 light-curve outputs."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def _prepare_output_path(output_path) -> Path | None:
    if output_path is None:
        return None
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _finish_figure(fig, output_path=None):
    path = _prepare_output_path(output_path)
    if path is not None:
        fig.savefig(path, dpi=180, bbox_inches="tight")
    return fig


def plot_full_lightcurve(time, flux, title, output_path=None):
    """Plot the full normalized light curve."""
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.plot(time, flux, "k.", markersize=2, alpha=0.55)
    ax.set_title(title)
    ax.set_xlabel("Time (BTJD days)")
    ax.set_ylabel("Normalized flux")
    ax.grid(alpha=0.25)
    fig.tight_layout()
    return _finish_figure(fig, output_path)


def plot_event_window(
    time,
    flux,
    event_time,
    window_days: float = 0.5,
    title: str | None = None,
    output_path=None,
):
    """Plot a local window around one candidate dip-like feature."""
    half_window = window_days / 2.0
    time_values = np.asarray(time, dtype=float)
    flux_values = np.asarray(flux, dtype=float)
    mask = (time_values >= event_time - half_window) & (
        time_values <= event_time + half_window
    )

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(time_values[mask], flux_values[mask], "k.-", markersize=3, alpha=0.75)
    ax.axvline(
        event_time,
        color="tab:red",
        linestyle="--",
        linewidth=1.2,
        label="Candidate event",
    )
    ax.set_title(title or f"Candidate Dip-Like Feature near BTJD {event_time:.3f}")
    ax.set_xlabel("Time (BTJD days)")
    ax.set_ylabel("Normalized flux")
    ax.grid(alpha=0.25)
    ax.legend(loc="best")
    fig.tight_layout()
    return _finish_figure(fig, output_path)


def plot_zoom_window(time, flux, start, end, title, output_path=None):
    """Plot a user-selected time interval."""
    if end <= start:
        raise ValueError("end must be greater than start")

    time_values = np.asarray(time, dtype=float)
    flux_values = np.asarray(flux, dtype=float)
    mask = (time_values >= start) & (time_values <= end)

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(time_values[mask], flux_values[mask], "k.-", markersize=3, alpha=0.75)
    ax.set_title(title)
    ax.set_xlabel("Time (BTJD days)")
    ax.set_ylabel("Normalized flux")
    ax.grid(alpha=0.25)
    fig.tight_layout()
    return _finish_figure(fig, output_path)


def plot_lightcurve_with_events(time, flux, events_df, title, output_path=None):
    """Plot the full light curve and mark candidate event times."""
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.plot(time, flux, "k.", markersize=2, alpha=0.5)

    if isinstance(events_df, pd.DataFrame) and not events_df.empty:
        for event_time in events_df["event_time_btjd"].to_numpy(dtype=float):
            ax.axvline(event_time, color="tab:red", alpha=0.35, linewidth=0.8)
        ax.plot(
            events_df["event_time_btjd"],
            np.interp(events_df["event_time_btjd"], time, flux),
            "v",
            color="tab:red",
            markersize=5,
            label="Candidate dip-like feature",
        )
        ax.legend(loc="best")

    ax.set_title(title)
    ax.set_xlabel("Time (BTJD days)")
    ax.set_ylabel("Normalized flux")
    ax.grid(alpha=0.25)
    fig.tight_layout()
    return _finish_figure(fig, output_path)
