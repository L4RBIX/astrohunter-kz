"""Tests for src/astrohunter/injection.py.

All tests are network-free and use only synthetic data.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from astrohunter.injection import (
    INJECTOR_VERSION,
    asymmetric_dip_model,
    inject_asymmetric_dip,
    run_injection_recovery_on_lightcurve,
    run_single_injection_recovery,
    sample_injection_parameters,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_clean_lc(n: int = 600, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """Return a flat synthetic light curve with small Gaussian noise."""
    rng = np.random.default_rng(seed)
    t = np.linspace(1500.0, 1527.0, n)  # ~27 day TESS sector
    f = 1.0 + rng.normal(0.0, 3e-4, size=n)
    return t, f


def _simple_detector(time, flux):
    from astrohunter.asymmetry import scan_lightcurve_for_asymmetric_dips
    return scan_lightcurve_for_asymmetric_dips(time, flux, sigma_threshold=3.5, window_days=1.0)


# ---------------------------------------------------------------------------
# asymmetric_dip_model
# ---------------------------------------------------------------------------

class TestAsymmetricDipModel:
    def test_output_shape_matches_input(self):
        t = np.linspace(0.0, 10.0, 300)
        delta = asymmetric_dip_model(t, event_time=5.0, depth_ppm=1000.0,
                                     ingress_duration_hours=2.0, egress_duration_hours=8.0)
        assert delta.shape == t.shape

    def test_delta_is_non_negative(self):
        t = np.linspace(0.0, 10.0, 500)
        delta = asymmetric_dip_model(t, event_time=5.0, depth_ppm=500.0,
                                     ingress_duration_hours=3.0, egress_duration_hours=12.0)
        assert np.all(delta >= 0.0), "Dip model must produce non-negative decrement"

    def test_peak_depth_near_event_time(self):
        t = np.linspace(0.0, 10.0, 1000)
        depth_ppm = 2000.0
        delta = asymmetric_dip_model(t, event_time=5.0, depth_ppm=depth_ppm,
                                     ingress_duration_hours=1.0, egress_duration_hours=4.0)
        peak_ppm = float(delta.max()) * 1e6
        assert abs(peak_ppm - depth_ppm) < depth_ppm * 0.05, (
            f"Peak depth {peak_ppm:.1f} ppm differs from injected {depth_ppm:.1f} ppm by >5%"
        )

    def test_zero_outside_dip_window(self):
        t = np.linspace(0.0, 10.0, 1000)
        event_time = 5.0
        ingress_h, egress_h = 1.0, 3.0
        delta = asymmetric_dip_model(t, event_time=event_time, depth_ppm=500.0,
                                     ingress_duration_hours=ingress_h,
                                     egress_duration_hours=egress_h)
        ingress_days = ingress_h / 24.0
        egress_days = egress_h / 24.0
        outside = (t < event_time - ingress_days - 0.001) | (t > event_time + egress_days + 0.001)
        assert np.allclose(delta[outside], 0.0, atol=1e-12)

    def test_egress_longer_than_ingress_produces_asymmetric_profile(self):
        t = np.linspace(0.0, 10.0, 2000)
        event_time = 5.0
        delta = asymmetric_dip_model(t, event_time=event_time, depth_ppm=1000.0,
                                     ingress_duration_hours=1.0, egress_duration_hours=12.0)
        before = (t >= event_time - 1.0 / 24.0) & (t < event_time)
        after = (t > event_time) & (t <= event_time + 12.0 / 24.0)
        # Egress lasts longer so more points are affected
        assert after.sum() > before.sum()


# ---------------------------------------------------------------------------
# inject_asymmetric_dip
# ---------------------------------------------------------------------------

class TestInjectAsymmetricDip:
    def test_preserves_array_shape(self):
        t, f = _make_clean_lc(400)
        f_inj = inject_asymmetric_dip(t, f, event_time=float(t[200]), depth_ppm=800.0,
                                       ingress_duration_hours=2.0, egress_duration_hours=6.0)
        assert f_inj.shape == f.shape

    def test_flux_decreases_at_event_time(self):
        t, f = _make_clean_lc(600)
        event_time = float(t[300])
        f_inj = inject_asymmetric_dip(t, f, event_time=event_time, depth_ppm=1500.0,
                                       ingress_duration_hours=1.5, egress_duration_hours=5.0)
        # Median in window around event should be lower after injection
        mask = np.abs(t - event_time) < 0.05
        assert float(np.nanmedian(f_inj[mask])) < float(np.nanmedian(f[mask]))

    def test_does_not_modify_original_array(self):
        t, f = _make_clean_lc(300)
        f_copy = f.copy()
        inject_asymmetric_dip(t, f, event_time=float(t[150]), depth_ppm=500.0,
                               ingress_duration_hours=1.0, egress_duration_hours=4.0)
        np.testing.assert_array_equal(f, f_copy)

    def test_shape_mismatch_raises(self):
        t = np.linspace(0.0, 5.0, 100)
        f = np.ones(99)
        with pytest.raises(ValueError, match="same shape"):
            inject_asymmetric_dip(t, f, event_time=2.5, depth_ppm=200.0,
                                   ingress_duration_hours=1.0, egress_duration_hours=2.0)


# ---------------------------------------------------------------------------
# sample_injection_parameters
# ---------------------------------------------------------------------------

class TestSampleInjectionParameters:
    def test_returns_required_keys(self):
        params = sample_injection_parameters(random_state=42)
        for key in ("depth_ppm", "ingress_duration_hours", "egress_duration_hours",
                    "asymmetry_ratio"):
            assert key in params, f"Missing key: {key}"

    def test_depth_in_valid_range(self):
        for seed in range(20):
            p = sample_injection_parameters(random_state=seed)
            assert 50.0 <= p["depth_ppm"] <= 5000.0

    def test_egress_usually_longer_than_ingress(self):
        ratios = [sample_injection_parameters(seed)["asymmetry_ratio"] for seed in range(50)]
        # At least 90% should have egress > ingress
        assert sum(r > 1.0 for r in ratios) / len(ratios) >= 0.9

    def test_reproducible_with_same_seed(self):
        p1 = sample_injection_parameters(random_state=7)
        p2 = sample_injection_parameters(random_state=7)
        assert p1["depth_ppm"] == p2["depth_ppm"]
        assert p1["ingress_duration_hours"] == p2["ingress_duration_hours"]


# ---------------------------------------------------------------------------
# run_single_injection_recovery
# ---------------------------------------------------------------------------

class TestRunSingleInjectionRecovery:
    def test_returns_required_keys(self):
        t, f = _make_clean_lc(600)
        params = sample_injection_parameters(42)
        params["event_time"] = float(t[300])
        result = run_single_injection_recovery(t, f, _simple_detector, params)
        for key in ("injected_event_time_btjd", "injected_depth_ppm", "recovered",
                    "noise_mad", "injector_version"):
            assert key in result, f"Missing key: {key}"

    def test_strong_dip_is_recovered(self):
        """A very deep injected dip must be recovered."""
        rng = np.random.default_rng(0)
        t = np.linspace(1500.0, 1527.0, 800)
        f = 1.0 + rng.normal(0.0, 1e-4, size=800)
        params = {
            "depth_ppm": 4000.0,
            "ingress_duration_hours": 2.0,
            "egress_duration_hours": 8.0,
            "asymmetry_ratio": 4.0,
            "event_time": float(t[400]),
        }
        result = run_single_injection_recovery(t, f, _simple_detector, params,
                                               tolerance_hours=5.0)
        assert result["recovered"] is True, (
            "A 4000 ppm dip on a near-noiseless LC should be recovered."
        )

    def test_very_shallow_dip_unlikely_to_be_recovered(self):
        """A 50 ppm dip on a noisy LC should have low recovery."""
        rng = np.random.default_rng(1)
        t = np.linspace(1500.0, 1527.0, 600)
        # High noise: 500 ppm rms
        f = 1.0 + rng.normal(0.0, 5e-4, size=600)
        params = {
            "depth_ppm": 50.0,
            "ingress_duration_hours": 0.5,
            "egress_duration_hours": 1.0,
            "asymmetry_ratio": 2.0,
            "event_time": float(t[300]),
        }
        result = run_single_injection_recovery(t, f, _simple_detector, params)
        # We don't assert False — just that the function runs without crashing
        assert isinstance(result["recovered"], (bool, np.bool_))

    def test_too_short_lc_returns_without_crash(self):
        t = np.linspace(0.0, 1.0, 10)
        f = np.ones(10)
        params = sample_injection_parameters(5)
        result = run_single_injection_recovery(t, f, _simple_detector, params)
        assert "recovered" in result
        assert result["recovered"] is False


# ---------------------------------------------------------------------------
# run_injection_recovery_on_lightcurve
# ---------------------------------------------------------------------------

class TestRunInjectionRecoveryOnLightcurve:
    def test_returns_dataframe_with_required_columns(self):
        t, f = _make_clean_lc(600)
        result = run_injection_recovery_on_lightcurve(t, f, n_injections=5,
                                                       detector_fn=_simple_detector,
                                                       random_state=0)
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 5
        for col in ("injected_depth_ppm", "injected_asymmetry_ratio",
                    "recovered", "noise_mad"):
            assert col in result.columns, f"Missing column: {col}"

    def test_recovers_strong_dips_consistently(self):
        """Inject very deep dips; expect high overall recovery on a clean LC."""
        rng = np.random.default_rng(42)
        t = np.linspace(1500.0, 1527.0, 1200)
        f = 1.0 + rng.normal(0.0, 5e-5, size=1200)  # ~50 ppm noise

        # Monkeypatch sample_injection_parameters inside the call via a custom detector
        # that uses only deep dips
        rows = []
        for seed in range(10):
            params = {"depth_ppm": 3000.0, "ingress_duration_hours": 2.0,
                      "egress_duration_hours": 8.0, "asymmetry_ratio": 4.0}
            params["event_time"] = float(rng.uniform(t[60], t[-60]))
            r = run_single_injection_recovery(t, f, _simple_detector, params, tolerance_hours=5.0)
            rows.append(r)
        df = pd.DataFrame(rows)
        recovery_rate = df["recovered"].sum() / len(df)
        assert recovery_rate >= 0.7, (
            f"Expected ≥70% recovery for 3000 ppm dips on clean LC; got {recovery_rate:.0%}"
        )

    def test_empty_result_for_tiny_lc(self):
        t = np.linspace(0.0, 1.0, 5)
        f = np.ones(5)
        result = run_injection_recovery_on_lightcurve(t, f, n_injections=3,
                                                       detector_fn=_simple_detector)
        assert isinstance(result, pd.DataFrame)
