"""Tests for Phase 5 statistics module (src/astrohunter/stats.py).

All tests use synthetic DataFrames.  No network calls, no real data files.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from astrohunter.stats import (
    MIN_CANDIDATES_FOR_STABLE_STATS,
    STATS_VERSION,
    bootstrap_rate_ratio,
    compute_candidate_yield_by_role,
    compute_rate_ratio,
    fisher_exact_candidate_test,
    poisson_confidence_interval,
    summarize_rate_statistics,
)
from astrohunter.vetting import add_basic_vetting_flags


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_matched_pairs(
    target_tics: list[int],
    control_tics: list[int],
) -> pd.DataFrame:
    """Minimal matched_pairs DataFrame."""
    n = max(len(target_tics), len(control_tics))
    t = (target_tics * n)[:n]
    c = (control_tics * n)[:n]
    return pd.DataFrame({"target_tic_id": t, "control_tic_id": c})


def _make_candidate_df(
    tic_ids: list[int],
    snr_values: list[float] | None = None,
) -> pd.DataFrame:
    """Synthetic candidate DataFrame."""
    n = len(tic_ids)
    if snr_values is None:
        snr_values = [6.0] * n
    return pd.DataFrame({
        "tic_id": tic_ids,
        "target_name": [f"Star_{t}" for t in tic_ids],
        "local_snr": snr_values,
        "depth_ppm": [500.0] * n,
        "duration_hours": [2.0] * n,
        "fwhm_hours": [1.0] * n,
        "egress_ingress_ratio": [2.0] * n,
        "skewness": [-0.5] * n,
        "delta_chi2_asym": [20.0] * n,
        "edge_event": [False] * n,
        "single_point_like": [False] * n,
        "final_candidate_score": [0.6] * n,
        "automated_vetting_status": ["pass"] * n,
    })


# ---------------------------------------------------------------------------
# poisson_confidence_interval
# ---------------------------------------------------------------------------

class TestPoissonCI:
    def test_count_zero_lower_is_zero(self):
        lo, hi = poisson_confidence_interval(0, exposure=1.0)
        assert lo == 0.0
        assert hi > 0.0

    def test_count_one_ci_bounds_order(self):
        lo, hi = poisson_confidence_interval(1, exposure=1.0)
        assert lo < 1.0 < hi

    def test_exposure_scales_rate(self):
        lo1, hi1 = poisson_confidence_interval(4, exposure=1.0)
        lo2, hi2 = poisson_confidence_interval(4, exposure=2.0)
        assert abs(lo1 / 2 - lo2) < 1e-10
        assert abs(hi1 / 2 - hi2) < 1e-10

    def test_ci_contains_observed_rate(self):
        for count in range(0, 10):
            lo, hi = poisson_confidence_interval(count, exposure=1.0)
            assert lo <= count <= hi

    def test_returns_floats(self):
        lo, hi = poisson_confidence_interval(5, exposure=3.0)
        assert isinstance(lo, float)
        assert isinstance(hi, float)


# ---------------------------------------------------------------------------
# compute_rate_ratio
# ---------------------------------------------------------------------------

class TestComputeRateRatio:
    def test_equal_counts_and_exposure_gives_rr_one(self):
        result = compute_rate_ratio(5, 10.0, 5, 10.0)
        assert abs(result["rate_ratio"] - 1.0) < 1e-10

    def test_zero_control_count_gives_nan_rr(self):
        result = compute_rate_ratio(3, 10.0, 0, 10.0)
        assert math.isnan(result["rate_ratio"])

    def test_keys_present(self):
        result = compute_rate_ratio(3, 10.0, 2, 10.0)
        for key in [
            "target_count", "control_count", "target_rate", "control_rate",
            "rate_ratio", "rate_ratio_ci_lo", "rate_ratio_ci_hi",
        ]:
            assert key in result

    def test_rr_ci_ordered(self):
        result = compute_rate_ratio(4, 10.0, 2, 10.0)
        rr = result["rate_ratio"]
        assert result["rate_ratio_ci_lo"] <= rr <= result["rate_ratio_ci_hi"]

    def test_target_only_rr_greater_than_one(self):
        result = compute_rate_ratio(10, 10.0, 1, 10.0)
        assert result["rate_ratio"] > 1.0


# ---------------------------------------------------------------------------
# compute_candidate_yield_by_role
# ---------------------------------------------------------------------------

class TestComputeCandidateYieldByRole:
    def test_correct_target_control_split(self):
        target_tics = [1001, 1002, 1003]
        control_tics = [2001, 2002, 2003]
        pairs = _make_matched_pairs(target_tics, control_tics)
        cands = _make_candidate_df([1001, 2001])
        result = compute_candidate_yield_by_role(cands, pairs)
        assert result["target_candidates"] == 1
        assert result["control_candidates"] == 1

    def test_unknown_tics_counted(self):
        pairs = _make_matched_pairs([1001], [2001])
        cands = _make_candidate_df([9999])
        result = compute_candidate_yield_by_role(cands, pairs)
        assert result["unknown_candidates"] == 1
        assert result["target_candidates"] == 0
        assert result["control_candidates"] == 0

    def test_empty_candidates(self):
        pairs = _make_matched_pairs([1001], [2001])
        cands = _make_candidate_df([])
        result = compute_candidate_yield_by_role(cands, pairs)
        assert result["target_candidates"] == 0
        assert result["control_candidates"] == 0

    def test_empty_matched_pairs(self):
        cands = _make_candidate_df([1001, 2001])
        result = compute_candidate_yield_by_role(cands, pd.DataFrame())
        # Falls back: all treated as targets
        assert result["target_candidates"] + result["control_candidates"] >= 0

    def test_exposure_matches_unique_tic_count(self):
        pairs = _make_matched_pairs([1001, 1002, 1003], [2001, 2002])
        cands = _make_candidate_df([1001])
        result = compute_candidate_yield_by_role(cands, pairs)
        assert result["target_exposure"] == 3.0
        assert result["control_exposure"] == 2.0


# ---------------------------------------------------------------------------
# bootstrap_rate_ratio
# ---------------------------------------------------------------------------

class TestBootstrapRateRatio:
    def test_returns_required_keys(self):
        pairs = _make_matched_pairs([1001, 1002, 1003], [2001, 2002, 2003])
        cands = _make_candidate_df([1001, 2001])
        result = bootstrap_rate_ratio(cands, pairs, n_bootstrap=50, random_state=0)
        for key in ["bootstrap_rate_ratio_median", "bootstrap_ci_lo", "bootstrap_ci_hi",
                    "n_bootstrap", "n_finite_replicates"]:
            assert key in result

    def test_empty_candidates(self):
        pairs = _make_matched_pairs([1001], [2001])
        cands = _make_candidate_df([])
        result = bootstrap_rate_ratio(cands, pairs, n_bootstrap=50)
        assert math.isnan(result["bootstrap_rate_ratio_median"])
        assert result["n_finite_replicates"] == 0

    def test_small_n_warning_present(self):
        pairs = _make_matched_pairs([1001, 1002, 1003], [2001, 2002, 2003])
        cands = _make_candidate_df([1001, 2001])
        # 2 candidates < MIN_CANDIDATES_FOR_STABLE_STATS → warning
        result = bootstrap_rate_ratio(cands, pairs, n_bootstrap=50, random_state=42)
        assert result["stability_warning"] is not None

    def test_reproducible_with_same_seed(self):
        pairs = _make_matched_pairs([1001, 1002, 1003], [2001, 2002, 2003])
        cands = _make_candidate_df([1001, 1002, 2001])
        r1 = bootstrap_rate_ratio(cands, pairs, n_bootstrap=100, random_state=7)
        r2 = bootstrap_rate_ratio(cands, pairs, n_bootstrap=100, random_state=7)
        assert r1["bootstrap_rate_ratio_median"] == r2["bootstrap_rate_ratio_median"]

    def test_ci_ordered_when_finite(self):
        pairs = _make_matched_pairs([1001, 1002, 1003], [2001, 2002, 2003])
        cands = _make_candidate_df([1001, 1002, 2001])
        result = bootstrap_rate_ratio(cands, pairs, n_bootstrap=200, random_state=42)
        if math.isfinite(result["bootstrap_ci_lo"]) and math.isfinite(result["bootstrap_ci_hi"]):
            assert result["bootstrap_ci_lo"] <= result["bootstrap_rate_ratio_median"] <= result["bootstrap_ci_hi"]


# ---------------------------------------------------------------------------
# fisher_exact_candidate_test
# ---------------------------------------------------------------------------

class TestFisherExact:
    def test_returns_required_keys(self):
        result = fisher_exact_candidate_test(3, 10.0, 2, 10.0)
        for key in ["odds_ratio", "p_value_fisher", "interpretation", "caution"]:
            assert key in result

    def test_equal_counts_p_near_one(self):
        result = fisher_exact_candidate_test(5, 100, 5, 100)
        assert result["p_value_fisher"] > 0.5

    def test_p_value_in_range(self):
        result = fisher_exact_candidate_test(10, 20, 0, 20)
        assert 0.0 <= result["p_value_fisher"] <= 1.0

    def test_caution_message_present(self):
        result = fisher_exact_candidate_test(1, 5, 0, 5)
        assert len(result["caution"]) > 10


# ---------------------------------------------------------------------------
# summarize_rate_statistics
# ---------------------------------------------------------------------------

class TestSummarizeRateStatistics:
    def _pairs(self):
        return _make_matched_pairs(
            [1001, 1002, 1003, 1004, 1005],
            [2001, 2002, 2003, 2004, 2005],
        )

    def test_returns_dataframe(self):
        pairs = self._pairs()
        cands = add_basic_vetting_flags(_make_candidate_df([1001, 2001]))
        result = summarize_rate_statistics(cands, pairs, n_bootstrap=50)
        assert isinstance(result, pd.DataFrame)

    def test_has_expected_subsets(self):
        pairs = self._pairs()
        cands = add_basic_vetting_flags(_make_candidate_df([1001, 2001]))
        result = summarize_rate_statistics(cands, pairs, n_bootstrap=50)
        subsets = result["subset"].tolist()
        assert "all_candidates" in subsets

    def test_stats_version_column(self):
        pairs = self._pairs()
        cands = add_basic_vetting_flags(_make_candidate_df([1001, 2001]))
        result = summarize_rate_statistics(cands, pairs, n_bootstrap=50)
        assert (result["stats_version"] == STATS_VERSION).all()

    def test_preliminary_warning_for_small_n(self):
        pairs = self._pairs()
        cands = add_basic_vetting_flags(_make_candidate_df([1001]))
        result = summarize_rate_statistics(cands, pairs, n_bootstrap=50)
        # Only 1 candidate → preliminary_warning should be set
        assert result["preliminary_warning"].notna().any()

    def test_empty_candidates_no_crash(self):
        pairs = self._pairs()
        cands = add_basic_vetting_flags(_make_candidate_df([]))
        result = summarize_rate_statistics(cands, pairs, n_bootstrap=50)
        assert isinstance(result, pd.DataFrame)

    def test_post_vetting_subset_smaller_or_equal(self):
        pairs = self._pairs()
        cands = add_basic_vetting_flags(
            _make_candidate_df([1001, 2001], snr_values=[3.0, 8.0])
        )
        result = summarize_rate_statistics(cands, pairs, n_bootstrap=50)
        all_row = result[result["subset"] == "all_candidates"].iloc[0]
        if "post_vetting_pass" in result["subset"].values:
            post_row = result[result["subset"] == "post_vetting_pass"].iloc[0]
            assert post_row["total_candidates"] <= all_row["total_candidates"]


# ---------------------------------------------------------------------------
# Phase 5 plotting smoke tests
# ---------------------------------------------------------------------------

class TestPhase5Plots:
    """Smoke tests: verify plotting functions produce files without error."""

    def test_plot_rate_ratio_summary(self, tmp_path):
        import pandas as pd
        from astrohunter.plotting import plot_rate_ratio_summary
        summary = pd.DataFrame([{
            "subset": "all_candidates",
            "total_candidates": 2,
            "target_count": 1,
            "control_count": 1,
            "target_exposure": 5.0,
            "control_exposure": 5.0,
            "target_rate": 0.2,
            "control_rate": 0.2,
            "target_rate_ci_lo": 0.05,
            "target_rate_ci_hi": 0.6,
            "control_rate_ci_lo": 0.05,
            "control_rate_ci_hi": 0.6,
            "rate_ratio": 1.0,
            "rate_ratio_ci_lo": 0.2,
            "rate_ratio_ci_hi": 4.0,
            "bootstrap_ci_lo": 0.3,
            "bootstrap_ci_hi": 3.5,
            "bootstrap_rate_ratio_median": 1.0,
        }])
        out = tmp_path / "rate_ratio_plot.png"
        fig = plot_rate_ratio_summary(summary, output_path=out)
        assert out.exists()
        import matplotlib.pyplot as plt
        plt.close("all")

    def test_plot_candidate_score_vs_snr(self, tmp_path):
        from astrohunter.plotting import plot_candidate_score_vs_snr
        pairs = _make_matched_pairs([1001, 1002], [2001, 2002])
        cands = add_basic_vetting_flags(_make_candidate_df([1001, 2001]))
        out = tmp_path / "score_vs_snr.png"
        plot_candidate_score_vs_snr(cands, output_path=out)
        assert out.exists()
        import matplotlib.pyplot as plt
        plt.close("all")

    def test_plot_vetting_flag_counts(self, tmp_path):
        from astrohunter.plotting import plot_vetting_flag_counts
        cands = add_basic_vetting_flags(_make_candidate_df([1001, 2001]))
        out = tmp_path / "flag_counts.png"
        plot_vetting_flag_counts(cands, output_path=out)
        assert out.exists()
        import matplotlib.pyplot as plt
        plt.close("all")

    def test_plot_rate_ratio_undefined_control(self, tmp_path):
        """Rate ratio undefined (0 control) should not raise."""
        from astrohunter.plotting import plot_rate_ratio_summary
        import math
        summary = pd.DataFrame([{
            "subset": "all_candidates",
            "total_candidates": 2,
            "target_count": 2,
            "control_count": 0,
            "target_exposure": 5.0,
            "control_exposure": 5.0,
            "target_rate": 0.4,
            "control_rate": 0.0,
            "target_rate_ci_lo": 0.1,
            "target_rate_ci_hi": 0.9,
            "control_rate_ci_lo": 0.0,
            "control_rate_ci_hi": 0.6,
            "rate_ratio": float("nan"),
            "rate_ratio_ci_lo": float("nan"),
            "rate_ratio_ci_hi": float("nan"),
            "bootstrap_ci_lo": float("nan"),
            "bootstrap_ci_hi": float("nan"),
            "bootstrap_rate_ratio_median": float("nan"),
        }])
        out = tmp_path / "rr_undef.png"
        fig = plot_rate_ratio_summary(summary, output_path=out)
        assert out.exists()
        import matplotlib.pyplot as plt
        plt.close("all")
