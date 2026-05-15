import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd

from astrohunter.asymmetry import make_synthetic_asymmetric_dip
from astrohunter.plotting import (
    plot_event_window,
    plot_full_lightcurve,
    plot_lightcurve_with_events,
    plot_target_control_balance,
    plot_zoom_window,
)


def test_plotting_functions_create_files(tmp_path):
    time, flux = make_synthetic_asymmetric_dip()
    events = pd.DataFrame({"event_time_btjd": [5.0]})

    outputs = [
        tmp_path / "full.png",
        tmp_path / "event.png",
        tmp_path / "zoom.png",
        tmp_path / "with_events.png",
    ]

    figs = [
        plot_full_lightcurve(time, flux, "Full", outputs[0]),
        plot_event_window(time, flux, 5.0, output_path=outputs[1]),
        plot_zoom_window(time, flux, 4.7, 5.4, "Zoom", outputs[2]),
        plot_lightcurve_with_events(time, flux, events, "Events", outputs[3]),
    ]

    for fig in figs:
        plt.close(fig)
    for output in outputs:
        assert output.exists()
        assert output.stat().st_size > 0


def test_plot_target_control_balance_creates_file(tmp_path):
    targets = pd.DataFrame({"tmag": [8.0, 8.5], "bp_rp": [0.5, 0.6]})
    controls = pd.DataFrame({"tmag": [8.1, 8.7, 8.4], "bp_rp": [0.55, 0.65, 0.58]})
    output = tmp_path / "balance.png"

    fig = plot_target_control_balance(targets, controls, ["tmag", "bp_rp"], output)
    plt.close(fig)

    assert output.exists()
    assert output.stat().st_size > 0
