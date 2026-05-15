"""Tests for Phase 5 vetting module (src/astrohunter/vetting.py).

All tests use synthetic DataFrames.  No network calls, no real data files.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from astrohunter.vetting import (
    AUTOMATED_FLAG_COLUMNS,
    EXTERNAL_CHECK_COLUMNS,
    MANUAL_REVIEW_COLUMNS,
    VETTER_VERSION,
    add_basic_vetting_flags,
    add_manual_review_columns,
    compute_vetting_summary,
    create_manual_vetting_sheet,
    flag_edge_events,
    flag_likely_flare_shape,
    flag_low_quality_fit,
    flag_low_snr,
    flag_single_point_like,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_candidate_df(n: int = 5) -> pd.DataFrame:
    """Synthetic candidate DataFrame with all Phase 3/4 feature columns."""
    rng = np.random.default_rng(0)
    return pd.DataFrame({
        "tic_id": [100_000 + i for i in range(n)],
        "target_name": [f"Star_{i}" for i in range(n)],
        "event_time_btjd": rng.uniform(1000, 3000, n),
        "local_snr": [3.0, 6.0, 8.0, 1.5, 5.5],        # 0,3 below 5.0; rest above
        "depth_ppm": rng.uniform(100, 2000, n),
        "duration_hours": rng.uniform(0.1, 4.0, n),
        "fwhm_hours": rng.uniform(0.05, 2.0, n),
        "ingress_duration_hours": rng.uniform(0.05, 1.0, n),
        "egress_duration_hours": rng.uniform(0.05, 2.0, n),
        "egress_ingress_ratio": [0.8, 2.5, 3.0, 0.5, 1.0],   # 0,3 < 1; 4 == 1
        "skewness": [0.5, -0.3, -0.8, 0.7, 0.0],             # 0,3 > 0
        "kurtosis": rng.uniform(-1, 2, n),
        "delta_chi2_asym": [2.0, 20.0, 50.0, 1.0, 5.5],      # 0,3 < 5
        "n_points_window": rng.integers(10, 200, n),
        "edge_event": [False, False, False, True, False],
        "single_point_like": [False, False, False, False, True],
        "final_candidate_score": [0.3, 0.7, 0.9, 0.1, 0.5],
        "ml_score": rng.uniform(0, 1, n),
        "quality_score": rng.uniform(0, 1, n),
        "detector_version": ["phase3_v1"] * n,
        "ranker_version": ["phase4_v1"] * n,
    })


# ---------------------------------------------------------------------------
# flag_low_snr
# ---------------------------------------------------------------------------

class TestFlagLowSnr:
    def test_flags_below_threshold(self):
        df = _make_candidate_df()
        flags = flag_low_snr(df, snr_threshold=5.0)
        # SNR values: [3.0, 6.0, 8.0, 1.5, 5.5]
        expected = pd.Series([True, False, False, True, False], name="flag_low_snr")
        pd.testing.assert_series_equal(flags.reset_index(drop=True), expected)

    def test_returns_series_named_flag_low_snr(self):
        df = _make_candidate_df()
        flags = flag_low_snr(df)
        assert flags.name == "flag_low_snr"

    def test_missing_snr_column_all_flagged(self):
        df = pd.DataFrame({"depth_ppm": [100, 200]})
        flags = flag_low_snr(df)
        assert flags.all()

    def test_custom_threshold(self):
        df = _make_candidate_df()
        flags = flag_low_snr(df, snr_threshold=10.0)
        # All SNR values < 10 → all True
        assert flags.all()


# ---------------------------------------------------------------------------
# flag_edge_events
# ---------------------------------------------------------------------------

class TestFlagEdgeEvents:
    def test_flags_edge_events(self):
        df = _make_candidate_df()
        flags = flag_edge_events(df)
        # edge_event column: [F, F, F, T, F]
        assert flags.iloc[3] is True or bool(flags.iloc[3])
        assert not bool(flags.iloc[0])

    def test_returns_series_named_flag_edge_event(self):
        df = _make_candidate_df()
        assert flag_edge_events(df).name == "flag_edge_event"

    def test_missing_column_returns_false(self):
        df = pd.DataFrame({"local_snr": [1.0]})
        flags = flag_edge_events(df)
        assert not flags.any()


# ---------------------------------------------------------------------------
# flag_single_point_like
# ---------------------------------------------------------------------------

class TestFlagSinglePointLike:
    def test_flags_correctly(self):
        df = _make_candidate_df()
        flags = flag_single_point_like(df)
        # single_point_like: [F, F, F, F, T]
        assert bool(flags.iloc[4])
        assert not bool(flags.iloc[0])

    def test_returns_series_named_flag_single_point_like(self):
        df = _make_candidate_df()
        assert flag_single_point_like(df).name == "flag_single_point_like"


# ---------------------------------------------------------------------------
# flag_likely_flare_shape
# ---------------------------------------------------------------------------

class TestFlagLikelyFlareShape:
    def test_flags_positive_skew_and_low_ratio(self):
        df = _make_candidate_df()
        flags = flag_likely_flare_shape(df)
        # skewness=[0.5, -0.3, -0.8, 0.7, 0.0]; ratio=[0.8, 2.5, 3.0, 0.5, 1.0]
        # row 0: skew>0 AND ratio<1 → True
        # row 3: skew>0 AND ratio<1 → True
        assert bool(flags.iloc[0])
        assert bool(flags.iloc[3])
        assert not bool(flags.iloc[1])  # negative skew
        assert not bool(flags.iloc[2])  # negative skew

    def test_missing_columns_returns_false(self):
        df = pd.DataFrame({"local_snr": [5.0]})
        flags = flag_likely_flare_shape(df)
        assert not flags.any()


# ---------------------------------------------------------------------------
# flag_low_quality_fit
# ---------------------------------------------------------------------------

class TestFlagLowQualityFit:
    def test_returns_two_columns(self):
        df = _make_candidate_df()
        result = flag_low_quality_fit(df)
        assert "flag_low_delta_chi2" in result.columns
        assert "flag_poor_asymmetry_fit" in result.columns

    def test_low_delta_chi2_flagged(self):
        df = _make_candidate_df()
        result = flag_low_quality_fit(df, delta_chi2_threshold=5.0)
        # delta_chi2: [2.0, 20.0, 50.0, 1.0, 5.5]
        # rows 0,3 → < 5 → True
        assert bool(result["flag_low_delta_chi2"].iloc[0])
        assert bool(result["flag_low_delta_chi2"].iloc[3])
        assert not bool(result["flag_low_delta_chi2"].iloc[1])


# ---------------------------------------------------------------------------
# add_basic_vetting_flags
# ---------------------------------------------------------------------------

class TestAddBasicVettingFlags:
    def test_adds_all_flag_columns(self):
        df = _make_candidate_df()
        result = add_basic_vetting_flags(df)
        for col in AUTOMATED_FLAG_COLUMNS:
            assert col in result.columns, f"Missing column: {col}"

    def test_adds_external_check_columns(self):
        df = _make_candidate_df()
        result = add_basic_vetting_flags(df)
        for col in EXTERNAL_CHECK_COLUMNS:
            assert col in result.columns
            assert (result[col] == "not_attempted").all()

    def test_adds_vetter_version(self):
        df = _make_candidate_df()
        result = add_basic_vetting_flags(df)
        assert "vetter_version" in result.columns
        assert (result["vetter_version"] == VETTER_VERSION).all()

    def test_automated_vetting_status_values(self):
        df = _make_candidate_df()
        result = add_basic_vetting_flags(df)
        assert set(result["automated_vetting_status"].unique()).issubset({"pass", "flagged"})

    def test_needs_manual_review_consistent_with_flags(self):
        df = _make_candidate_df()
        result = add_basic_vetting_flags(df)
        flag_cols = [c for c in AUTOMATED_FLAG_COLUMNS if c in result.columns]
        expected_any = result[flag_cols].any(axis=1)
        pd.testing.assert_series_equal(
            result["needs_manual_review"].reset_index(drop=True),
            expected_any.reset_index(drop=True),
            check_names=False,
        )

    def test_preserves_original_columns(self):
        df = _make_candidate_df()
        result = add_basic_vetting_flags(df)
        for col in df.columns:
            assert col in result.columns

    def test_does_not_modify_input(self):
        df = _make_candidate_df()
        original_cols = set(df.columns)
        _ = add_basic_vetting_flags(df)
        assert set(df.columns) == original_cols


# ---------------------------------------------------------------------------
# add_manual_review_columns
# ---------------------------------------------------------------------------

class TestAddManualReviewColumns:
    def test_adds_all_manual_columns(self):
        df = _make_candidate_df()
        result = add_manual_review_columns(df)
        for col in MANUAL_REVIEW_COLUMNS:
            assert col in result.columns

    def test_manual_columns_are_blank(self):
        df = _make_candidate_df()
        result = add_manual_review_columns(df)
        for col in MANUAL_REVIEW_COLUMNS:
            assert (result[col] == "").all()

    def test_does_not_overwrite_existing(self):
        df = _make_candidate_df()
        df["manual_reviewer"] = "Alice"
        result = add_manual_review_columns(df)
        assert (result["manual_reviewer"] == "Alice").all()


# ---------------------------------------------------------------------------
# compute_vetting_summary
# ---------------------------------------------------------------------------

class TestComputeVettingSummary:
    def test_returns_dict(self):
        df = add_basic_vetting_flags(_make_candidate_df())
        summary = compute_vetting_summary(df)
        assert isinstance(summary, dict)

    def test_total_candidates_correct(self):
        df = add_basic_vetting_flags(_make_candidate_df())
        summary = compute_vetting_summary(df)
        assert summary["total_candidates"] == len(df)

    def test_n_pass_plus_n_flagged_equals_total(self):
        df = add_basic_vetting_flags(_make_candidate_df())
        summary = compute_vetting_summary(df)
        assert summary["n_pass"] + summary["n_flagged"] == summary["total_candidates"]

    def test_fraction_flagged_in_range(self):
        df = add_basic_vetting_flags(_make_candidate_df())
        summary = compute_vetting_summary(df)
        assert 0.0 <= summary["fraction_flagged"] <= 1.0


# ---------------------------------------------------------------------------
# create_manual_vetting_sheet
# ---------------------------------------------------------------------------

class TestCreateManualVettingSheet:
    def test_returns_dataframe(self):
        df = add_basic_vetting_flags(_make_candidate_df())
        sheet = create_manual_vetting_sheet(df)
        assert isinstance(sheet, pd.DataFrame)

    def test_sorted_by_final_candidate_score(self):
        df = add_basic_vetting_flags(_make_candidate_df())
        sheet = create_manual_vetting_sheet(df)
        if "final_candidate_score" in sheet.columns:
            scores = sheet["final_candidate_score"].tolist()
            assert scores == sorted(scores, reverse=True)

    def test_has_manual_columns(self):
        df = add_basic_vetting_flags(_make_candidate_df())
        sheet = create_manual_vetting_sheet(df)
        for col in MANUAL_REVIEW_COLUMNS:
            assert col in sheet.columns

    def test_empty_input(self):
        df = pd.DataFrame()
        sheet = create_manual_vetting_sheet(df)
        assert isinstance(sheet, pd.DataFrame)
        assert len(sheet) == 0
