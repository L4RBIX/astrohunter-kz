import numpy as np
import pandas as pd

from astrohunter.asymmetry import (
    add_asymmetry_scores,
    compute_simple_asymmetry,
    detect_candidate_dips,
    make_synthetic_asymmetric_dip,
)


def test_synthetic_dip_detection_finds_injected_event():
    time, flux = make_synthetic_asymmetric_dip(
        n_points=800,
        center=5.0,
        depth=0.02,
        ingress_days=0.04,
        egress_days=0.25,
        noise=0.0002,
    )

    events = detect_candidate_dips(
        time,
        flux,
        sigma_threshold=4.0,
        min_distance=8,
        window_days=0.7,
    )

    assert not events.empty
    assert np.any(np.abs(events["event_time_btjd"] - 5.0) < 0.08)
    assert {"depth_ppm", "local_noise", "local_snr", "asymmetry_score"}.issubset(
        events.columns
    )


def test_compute_simple_asymmetry_handles_short_window():
    result = compute_simple_asymmetry([1, 2, 3], [1, 0.9, 1], 2, window_days=0.1)

    assert np.isnan(result["ingress_duration_days"])
    assert np.isnan(result["egress_duration_days"])
    assert np.isnan(result["asymmetry_score"])


def test_add_asymmetry_scores_refreshes_columns():
    time, flux = make_synthetic_asymmetric_dip(noise=0.0)
    events = pd.DataFrame(
        {
            "event_time_btjd": [5.0],
            "ingress_duration_days": [999.0],
            "egress_duration_days": [999.0],
            "asymmetry_score": [999.0],
        }
    )

    scored = add_asymmetry_scores(events, time, flux, window_days=0.7)

    assert len(scored) == 1
    assert scored.loc[0, "ingress_duration_days"] != 999.0
    assert "asymmetry_score" in scored.columns
