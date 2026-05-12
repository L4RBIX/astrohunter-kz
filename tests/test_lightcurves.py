import numpy as np

from astrohunter.lightcurves import estimate_noise_mad, lightcurve_to_dataframe


class MinimalLightCurve:
    def __init__(self):
        self.time = np.array([1.0, 2.0, 3.0, np.nan, 4.0])
        self.flux = np.array([1.0, 0.99, 1.01, 1.0, np.nan])
        self.flux_err = np.array([0.001, 0.001, 0.001, 0.001, 0.001])
        self.quality = np.array([0, 0, 1, 0, 0])


def test_estimate_noise_mad_returns_positive_value():
    rng = np.random.default_rng(123)
    flux = 1.0 + rng.normal(0, 0.001, size=500)

    noise = estimate_noise_mad(flux)

    assert np.isfinite(noise)
    assert noise > 0


def test_lightcurve_to_dataframe_with_minimal_object():
    df = lightcurve_to_dataframe(MinimalLightCurve())

    assert list(df.columns) == ["time_btjd", "flux", "flux_err", "quality"]
    assert len(df) == 3
    assert df["time_btjd"].tolist() == [1.0, 2.0, 3.0]
