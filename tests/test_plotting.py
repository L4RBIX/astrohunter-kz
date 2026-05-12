import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd

from astrohunter.asymmetry import make_synthetic_asymmetric_dip
from astrohunter.plotting import (
    plot_event_window,
    plot_full_lightcurve,
    plot_lightcurve_with_events,
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
