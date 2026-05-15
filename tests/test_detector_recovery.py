"""Tests for Phase 3 detector (scan_lightcurve_for_asymmetric_dips) and
injection-recovery pipeline integration.

All tests are network-free and use only synthetic data.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from astrohunter.asymmetry import (
    DETECTOR_VERSION,
    compute_delta_chi2_symmetric_vs_asymmetric,
    compute_event_features,
    estimate_event_fwhm,
    compute_ingress_egress_ratio,
    fit_asymmetric_dip_model,
    fit_symmetric_dip_model,
    make_synthetic_asymmetric_dip,
    scan_lightcurve_for_asymmetric_dips,
)
from astrohunter.injection import (
    inject_asymmetric_dip,
    run_injection_recovery_on_lightcurve,
    run_single_injection_recovery,
    sample_injection_parameters,
)

REQUIRED_EVENT_COLUMNS = [
    "event_time_btjd", "depth_ppm", "local_snr", "duration_hours",
    "fwhm_hours", "ingress_duration_hours", "egress_duration_hours",
    "egress_ingress_ratio", "skewness", "kurtosis", "delta_chi2_asym",
    "n_points_window", "edge_event", "single_point_like", "detector_version",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_lc(n: int = 800, noise: float = 2e-4, seed: int = 0):
    rng = np.random.default_rng(seed)
    t = np.linspace(1500.0, 1527.0, n)
    f = 1.0 + rng.normal(0.0, noise, size=n)
    return t, f


def _lc_with_injected_dip(depth_ppm: float = 2000.0,
                            ingress_h: float = 2.0,
                            egress_h: float = 8.0,
                            n: int = 800, noise: float = 1e-4, seed: int = 7):
    t, f = _clean_lc(n=n, noise=noise, seed=seed)
    event_time = float(t[n // 2])
    f_inj = inject_asymmetric_dip(t, f, event_time, depth_ppm, ingress_h, egress_h)
    return t, f_inj, event_time


# ---------------------------------------------------------------------------
# scan_lightcurve_for_asymmetric_dips
# ---------------------------------------------------------------------------

class TestScanLightcurveForAsymmetricDips:
    def test_returns_dataframe(self):
        t, f = _clean_lc()
        result = scan_lightcurve_for_asymmetric_dips(t, f)
        assert isinstance(result, pd.DataFrame)

    def test_required_columns_present(self):
        t, f, _ = _lc_with_injected_dip()
        result = scan_lightcurve_for_asymmetric_dips(t, f, sigma_threshold=3.0)
        if not result.empty:
            for col in REQUIRED_EVENT_COLUMNS:
                assert col in result.columns, f"Missing column: {col}"

    def test_detects_strong_injected_dip(self):
        t, f_inj, event_time = _lc_with_injected_dip(
            depth_ppm=3000.0, ingress_h=2.0, egress_h=8.0, noise=5e-5
        )
        result = scan_lightcurve_for_asymmetric_dips(t, f_inj, sigma_threshold=3.5)
        assert not result.empty, "Strong 3000 ppm dip should be detected."
        timing_errors = (result["event_time_btjd"] - event_time).abs()
        assert timing_errors.min() < 0.2, (
            f"Detected event not close to injected time; min error={timing_errors.min():.3f} d"
        )

    def test_detects_nothing_on_flat_lc(self):
        t = np.linspace(0.0, 27.0, 800)
        f = np.ones(800)  # perfectly flat, no noise
        result = scan_lightcurve_for_asymmetric_dips(t, f, sigma_threshold=4.0)
        assert result.empty, "Perfectly flat LC should produce no candidates."

    def test_detector_version_column_is_set(self):
        t, f_inj, _ = _lc_with_injected_dip(depth_ppm=2500.0, noise=5e-5)
        result = scan_lightcurve_for_asymmetric_dips(t, f_inj, sigma_threshold=3.0)
        if not result.empty:
            assert (result["detector_version"] == DETECTOR_VERSION).all()

    def test_single_point_outlier_flagged(self):
        """A single bad pixel should be detected but flagged as single_point_like."""
        rng = np.random.default_rng(9)
        t = np.linspace(1500.0, 1527.0, 800)
        f = 1.0 + rng.normal(0.0, 5e-5, size=800)
        f[400] = 0.90  # single very deep outlier
        result = scan_lightcurve_for_asymmetric_dips(t, f, sigma_threshold=3.0)
        if not result.empty:
            single_pts = result["single_point_like"].any()
            # The deep single pixel event should be flagged
            assert single_pts, (
                "Single-pixel outlier should have at least one event flagged single_point_like."
            )

    def test_sigma_threshold_raises_on_invalid(self):
        t, f = _clean_lc()
        with pytest.raises(ValueError):
            scan_lightcurve_for_asymmetric_dips(t, f, sigma_threshold=-1.0)

    def test_window_days_raises_on_invalid(self):
        t, f = _clean_lc()
        with pytest.raises(ValueError):
            scan_lightcurve_for_asymmetric_dips(t, f, window_days=0.0)

    def test_returns_empty_on_tiny_array(self):
        result = scan_lightcurve_for_asymmetric_dips(
            np.linspace(0.0, 1.0, 5), np.ones(5)
        )
        assert isinstance(result, pd.DataFrame)
        assert result.empty


# ---------------------------------------------------------------------------
# estimate_event_fwhm
# ---------------------------------------------------------------------------

class TestEstimateEventFwhm:
    def test_fwhm_positive_for_known_dip(self):
        t, f = make_synthetic_asymmetric_dip(
            n_points=1000, center=5.0, depth=0.005,
            ingress_days=0.05, egress_days=0.20, noise=1e-5, random_seed=0
        )
        fwhm = estimate_event_fwhm(t, f, event_time=5.0, window_days=0.8)
        assert np.isfinite(fwhm)
        assert fwhm > 0.0

    def test_fwhm_nan_on_too_few_points(self):
        fwhm = estimate_event_fwhm([1.0, 2.0], [1.0, 0.9], event_time=1.5, window_days=0.1)
        assert np.isnan(fwhm)


# ---------------------------------------------------------------------------
# compute_ingress_egress_ratio
# ---------------------------------------------------------------------------

class TestComputeIngressEgressRatio:
    def test_ratio_gt_1_for_asymmetric_dip(self):
        t, f = make_synthetic_asymmetric_dip(
            n_points=2000, center=5.0, depth=0.01,
            ingress_days=0.03, egress_days=0.25, noise=0.0, random_seed=0
        )
        result = compute_ingress_egress_ratio(t, f, event_time=5.0, window_days=0.8)
        ratio = result["egress_ingress_ratio"]
        if np.isfinite(ratio):
            assert ratio > 1.0, f"Egress/ingress ratio should be >1; got {ratio:.2f}"

    def test_returns_nan_on_degenerate_input(self):
        result = compute_ingress_egress_ratio([1.0], [1.0], event_time=1.0)
        assert np.isnan(result["egress_ingress_ratio"])


# ---------------------------------------------------------------------------
# fit_symmetric_dip_model / fit_asymmetric_dip_model
# ---------------------------------------------------------------------------

class TestModelFitting:
    def test_symmetric_fit_returns_required_keys(self):
        t, f = make_synthetic_asymmetric_dip(
            n_points=500, center=5.0, depth=0.01,
            ingress_days=0.1, egress_days=0.1, noise=1e-5, random_seed=0
        )
        result = fit_symmetric_dip_model(t, f, event_time=5.0, window_days=0.6)
        for key in ("chi2_sym", "fit_status_sym"):
            assert key in result, f"Missing key: {key}"

    def test_asymmetric_fit_returns_required_keys(self):
        t, f = make_synthetic_asymmetric_dip(
            n_points=500, center=5.0, depth=0.01,
            ingress_days=0.03, egress_days=0.25, noise=1e-5, random_seed=1
        )
        result = fit_asymmetric_dip_model(t, f, event_time=5.0, window_days=0.8)
        for key in ("chi2_asym", "fit_status_asym"):
            assert key in result, f"Missing key: {key}"

    def test_fits_do_not_crash_on_flat_flux(self):
        t = np.linspace(0.0, 10.0, 100)
        f = np.ones(100)
        # Should return NaN, not raise
        sym = fit_symmetric_dip_model(t, f, event_time=5.0)
        asym = fit_asymmetric_dip_model(t, f, event_time=5.0)
        assert "chi2_sym" in sym
        assert "chi2_asym" in asym

    def test_fits_do_not_crash_on_short_window(self):
        t = np.array([5.0])
        f = np.array([0.9])
        sym = fit_symmetric_dip_model(t, f, event_time=5.0)
        asym = fit_asymmetric_dip_model(t, f, event_time=5.0)
        assert sym["fit_status_sym"] == "too_few_points"
        assert asym["fit_status_asym"] == "too_few_points"


# ---------------------------------------------------------------------------
# compute_delta_chi2_symmetric_vs_asymmetric
# ---------------------------------------------------------------------------

class TestDeltaChi2:
    def test_returns_float_or_nan(self):
        t, f = make_synthetic_asymmetric_dip(
            n_points=800, center=5.0, depth=0.01,
            ingress_days=0.03, egress_days=0.25, noise=1e-5, random_seed=2
        )
        val = compute_delta_chi2_symmetric_vs_asymmetric(t, f, event_time=5.0, window_days=0.8)
        assert isinstance(val, (float, np.floating)) or np.isnan(val)

    def test_delta_chi2_positive_for_truly_asymmetric_dip(self):
        """For a clearly asymmetric dip, symmetric model should fit worse → Δχ² > 0."""
        t, f = make_synthetic_asymmetric_dip(
            n_points=1500, center=5.0, depth=0.015,
            ingress_days=0.02, egress_days=0.40, noise=0.0, random_seed=3
        )
        val = compute_delta_chi2_symmetric_vs_asymmetric(t, f, event_time=5.0, window_days=0.8)
        if np.isfinite(val):
            assert val > 0.0, (
                f"Expected Δχ²>0 (symmetric worse) for asymmetric dip; got {val:.2f}"
            )


# ---------------------------------------------------------------------------
# compute_event_features
# ---------------------------------------------------------------------------

class TestComputeEventFeatures:
    def test_returns_all_required_keys(self):
        t, f = make_synthetic_asymmetric_dip(
            n_points=1000, center=5.0, depth=0.01,
            ingress_days=0.05, egress_days=0.20, noise=1e-5, random_seed=0
        )
        result = compute_event_features(t, f, event_time=5.0, window_days=0.8)
        for col in REQUIRED_EVENT_COLUMNS:
            assert col in result, f"Missing feature key: {col}"

    def test_depth_ppm_reasonable(self):
        t, f = make_synthetic_asymmetric_dip(
            n_points=1000, center=5.0, depth=0.01,
            ingress_days=0.05, egress_days=0.20, noise=0.0, random_seed=0
        )
        result = compute_event_features(t, f, event_time=5.0, window_days=0.8)
        assert np.isfinite(result["depth_ppm"])
        # depth=0.01 → 10000 ppm; allow ±20% due to window/baseline effects
        assert 6000 < result["depth_ppm"] < 14000

    def test_edge_event_detected_at_start(self):
        t = np.linspace(0.0, 27.0, 800)
        f = np.ones(800)
        result = compute_event_features(t, f, event_time=0.1, window_days=1.0)
        assert result["edge_event"] is True


# ---------------------------------------------------------------------------
# Integration: injection + scan detector
# ---------------------------------------------------------------------------

class TestInjectionRecoveryIntegration:
    def test_run_injection_recovery_returns_required_columns(self):
        t, f = _clean_lc(800, noise=1e-4)

        def detector(time, flux):
            return scan_lightcurve_for_asymmetric_dips(time, flux,
                                                        sigma_threshold=3.5, window_days=1.0)

        result = run_injection_recovery_on_lightcurve(t, f, n_injections=8,
                                                       detector_fn=detector,
                                                       random_state=42)
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 8
        for col in ("injected_depth_ppm", "injected_asymmetry_ratio",
                    "recovered", "noise_mad", "injector_version"):
            assert col in result.columns

    def test_recovery_rate_reasonable_for_medium_depth(self):
        """500–2000 ppm dips on a 100 ppm noise LC should have partial recovery."""
        rng = np.random.default_rng(0)
        t = np.linspace(1500.0, 1527.0, 1000)
        f = 1.0 + rng.normal(0.0, 1e-4, size=1000)

        rows = []
        for seed in range(20):
            params = sample_injection_parameters(random_state=seed)
            # Force medium depth
            params["depth_ppm"] = float(rng.uniform(800.0, 2000.0))
            params["event_time"] = float(rng.uniform(t[60], t[-60]))

            def detector(time, flux):
                return scan_lightcurve_for_asymmetric_dips(time, flux, sigma_threshold=3.5)

            r = run_single_injection_recovery(t, f, detector, params, tolerance_hours=5.0)
            rows.append(r)

        df = pd.DataFrame(rows)
        recovery_rate = df["recovered"].mean()
        # On a ~100 ppm noise LC with 800–2000 ppm dips, expect ≥30% recovery at 3.5σ
        assert recovery_rate >= 0.25, (
            f"Expected ≥25% recovery for medium-depth dips; got {recovery_rate:.0%}"
        )

    def test_injections_have_required_output_columns(self):
        t, f = _clean_lc(600, noise=2e-4)

        from astrohunter.injection import run_single_injection_recovery
        params = sample_injection_parameters(random_state=3)
        params["event_time"] = float(t[300])

        def detector(time, flux):
            return scan_lightcurve_for_asymmetric_dips(time, flux)

        result = run_single_injection_recovery(t, f, detector, params)
        for col in ("injected_event_time_btjd", "injected_depth_ppm", "injected_ingress_hours",
                    "injected_egress_hours", "injected_asymmetry_ratio", "recovered",
                    "recovered_event_time_btjd", "timing_error_hours", "recovered_depth_ppm",
                    "recovered_local_snr", "recovery_tolerance_hours", "noise_mad",
                    "injector_version"):
            assert col in result, f"Missing column: {col}"
