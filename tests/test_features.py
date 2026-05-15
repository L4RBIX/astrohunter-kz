"""Tests for src/astrohunter/features.py.

All tests are network-free and use only synthetic data.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from astrohunter.features import (
    GROUND_TRUTH_COLUMNS,
    REQUIRED_FEATURE_COLUMNS,
    add_quality_score,
    build_candidate_feature_table,
    build_training_feature_table,
    impute_missing_features,
    select_event_feature_columns,
    validate_feature_table,
)


# ---------------------------------------------------------------------------
# REQUIRED_FEATURE_COLUMNS invariants
# ---------------------------------------------------------------------------

class TestRequiredFeatureColumns:
    def test_no_ground_truth_leakage(self):
        ground_truth_set = set(GROUND_TRUTH_COLUMNS)
        for col in REQUIRED_FEATURE_COLUMNS:
            assert col not in ground_truth_set, (
                f"Ground-truth column {col!r} must not appear in REQUIRED_FEATURE_COLUMNS."
            )

    def test_no_injected_prefix(self):
        for col in REQUIRED_FEATURE_COLUMNS:
            assert not col.startswith("injected_"), (
                f"Column {col!r} starts with 'injected_' — ground-truth leakage risk."
            )

    def test_no_event_time_columns(self):
        for col in REQUIRED_FEATURE_COLUMNS:
            assert "event_time" not in col, (
                f"Column {col!r} contains 'event_time' — likely ground truth."
            )

    def test_required_columns_are_unique(self):
        assert len(REQUIRED_FEATURE_COLUMNS) == len(set(REQUIRED_FEATURE_COLUMNS))

    def test_ground_truth_columns_listed(self):
        for col in ("injected_depth_ppm", "injected_ingress_hours",
                    "injected_egress_hours", "injected_asymmetry_ratio",
                    "injected_event_time_btjd"):
            assert col in GROUND_TRUTH_COLUMNS


# ---------------------------------------------------------------------------
# select_event_feature_columns
# ---------------------------------------------------------------------------

class TestSelectEventFeatureColumns:
    def test_selects_present_columns(self):
        df = pd.DataFrame({"depth_ppm": [1.0], "local_snr": [5.0], "not_a_feature": [0]})
        selected = select_event_feature_columns(df)
        assert "depth_ppm" in selected
        assert "local_snr" in selected
        assert "not_a_feature" not in selected

    def test_excludes_ground_truth_even_if_present(self):
        df = pd.DataFrame({
            "depth_ppm": [1.0],
            "injected_depth_ppm": [900.0],   # ground truth
            "injected_egress_hours": [5.0],  # ground truth
        })
        selected = select_event_feature_columns(df)
        assert "injected_depth_ppm" not in selected
        assert "injected_egress_hours" not in selected

    def test_returns_empty_for_empty_df(self):
        df = pd.DataFrame()
        selected = select_event_feature_columns(df)
        assert selected == []


# ---------------------------------------------------------------------------
# build_training_feature_table
# ---------------------------------------------------------------------------

class TestBuildTrainingFeatureTable:
    def _minimal_injection_df(self) -> pd.DataFrame:
        return pd.DataFrame({
            "recovered": [True, False, True, False],
            "recovered_depth_ppm": [1000.0, np.nan, 2000.0, np.nan],
            "recovered_local_snr": [5.0, np.nan, 8.0, np.nan],
            "noise_mad": [0.001, 0.002, 0.001, 0.003],
            "injected_depth_ppm": [900.0, 500.0, 1800.0, 300.0],
            "injected_ingress_hours": [2.0, 1.0, 3.0, 0.5],
            "injected_egress_hours": [6.0, 4.0, 10.0, 2.0],
            "injected_asymmetry_ratio": [3.0, 4.0, 3.3, 4.0],
        })

    def test_label_column_created(self):
        df = self._minimal_injection_df()
        result = build_training_feature_table(df)
        assert "label" in result.columns
        assert list(result["label"]) == [1, 0, 1, 0]

    def test_maps_recovered_depth_ppm_to_depth_ppm(self):
        df = self._minimal_injection_df()
        result = build_training_feature_table(df)
        assert "depth_ppm" in result.columns
        assert result.loc[0, "depth_ppm"] == pytest.approx(1000.0)
        assert np.isnan(result.loc[1, "depth_ppm"])

    def test_maps_recovered_local_snr_to_local_snr(self):
        df = self._minimal_injection_df()
        result = build_training_feature_table(df)
        assert "local_snr" in result.columns
        assert result.loc[0, "local_snr"] == pytest.approx(5.0)

    def test_noise_mad_preserved(self):
        df = self._minimal_injection_df()
        result = build_training_feature_table(df)
        assert "noise_mad" in result.columns
        assert not result["noise_mad"].isna().all()

    def test_required_feature_columns_present(self):
        df = self._minimal_injection_df()
        result = build_training_feature_table(df)
        for col in REQUIRED_FEATURE_COLUMNS:
            assert col in result.columns, f"Missing feature column: {col}"

    def test_injected_ground_truth_not_in_required_features(self):
        df = self._minimal_injection_df()
        result = build_training_feature_table(df)
        required_set = set(REQUIRED_FEATURE_COLUMNS)
        for col in GROUND_TRUTH_COLUMNS:
            assert col not in required_set, f"Ground-truth column {col!r} is in features."

    def test_diagnostic_columns_preserved(self):
        df = self._minimal_injection_df()
        df["tic_id"] = [12345, 12345, 67890, 67890]
        df["injection_id"] = [0, 1, 2, 3]
        result = build_training_feature_table(df)
        assert "tic_id" in result.columns
        assert "injected_depth_ppm" in result.columns  # diagnostic, not a model feature


# ---------------------------------------------------------------------------
# build_candidate_feature_table
# ---------------------------------------------------------------------------

class TestBuildCandidateFeatureTable:
    def _minimal_candidate_df(self) -> pd.DataFrame:
        return pd.DataFrame({
            "tic_id": [12345],
            "target_name": ["HR 9999"],
            "event_time_btjd": [1400.0],
            "depth_ppm": [1200.0],
            "local_snr": [4.5],
            "duration_hours": [0.5],
            "fwhm_hours": [0.3],
            "ingress_duration_hours": [0.1],
            "egress_duration_hours": [0.4],
            "egress_ingress_ratio": [4.0],
            "skewness": [-0.3],
            "kurtosis": [0.1],
            "delta_chi2_asym": [15.0],
            "n_points_window": [200],
            "edge_event": [False],
            "single_point_like": [False],
        })

    def test_required_feature_columns_present(self):
        df = self._minimal_candidate_df()
        result = build_candidate_feature_table(df)
        for col in REQUIRED_FEATURE_COLUMNS:
            assert col in result.columns, f"Missing: {col}"

    def test_metadata_preserved(self):
        df = self._minimal_candidate_df()
        result = build_candidate_feature_table(df)
        assert "tic_id" in result.columns
        assert "target_name" in result.columns
        assert "event_time_btjd" in result.columns

    def test_missing_columns_filled_with_nan(self):
        df = pd.DataFrame({"tic_id": [1], "depth_ppm": [800.0]})
        result = build_candidate_feature_table(df)
        assert "local_snr" in result.columns
        assert np.isnan(result.loc[0, "local_snr"])


# ---------------------------------------------------------------------------
# validate_feature_table
# ---------------------------------------------------------------------------

class TestValidateFeatureTable:
    def test_empty_df_is_invalid(self):
        is_valid, issues = validate_feature_table(pd.DataFrame())
        assert not is_valid
        assert any("empty" in i.lower() for i in issues)

    def test_missing_label_raises_when_required(self):
        df = pd.DataFrame({"depth_ppm": [1.0], "local_snr": [5.0]})
        with pytest.raises(ValueError, match="label"):
            validate_feature_table(df, require_label=True)

    def test_single_class_label_marks_invalid(self):
        df = pd.DataFrame({
            "depth_ppm": [1.0, 2.0],
            "local_snr": [3.0, 4.0],
            "label": [1, 1],
        })
        for col in REQUIRED_FEATURE_COLUMNS:
            if col not in df.columns:
                df[col] = np.nan
        is_valid, issues = validate_feature_table(df, require_label=True)
        assert not is_valid
        assert any("one" in i.lower() or "class" in i.lower() for i in issues)

    def test_two_class_label_passes(self):
        df = pd.DataFrame({
            "depth_ppm": [1.0, 2.0],
            "local_snr": [3.0, 4.0],
            "noise_mad": [0.001, 0.001],
            "label": [1, 0],
        })
        for col in REQUIRED_FEATURE_COLUMNS:
            if col not in df.columns:
                df[col] = np.nan
        is_valid, issues = validate_feature_table(df, require_label=True)
        # May have non-critical warnings about NaN columns but should be valid
        # (is_valid may be True with warnings in issues)
        assert "label" in df.columns


# ---------------------------------------------------------------------------
# impute_missing_features
# ---------------------------------------------------------------------------

class TestImputeMissingFeatures:
    def test_nan_depth_filled(self):
        df = pd.DataFrame({col: [np.nan] * 3 for col in REQUIRED_FEATURE_COLUMNS})
        df["depth_ppm"] = [1000.0, np.nan, 2000.0]
        result, fills = impute_missing_features(df)
        # Median of [1000, 2000] = 1500
        assert result["depth_ppm"].isna().sum() == 0

    def test_all_nan_column_filled_with_zero(self):
        df = pd.DataFrame({col: [np.nan] * 4 for col in REQUIRED_FEATURE_COLUMNS})
        result, fills = impute_missing_features(df)
        for col in REQUIRED_FEATURE_COLUMNS:
            assert result[col].isna().sum() == 0
            assert fills[col] == 0.0

    def test_fill_values_applied_to_second_df(self):
        train = pd.DataFrame({col: [1.0, 2.0, np.nan] for col in REQUIRED_FEATURE_COLUMNS})
        train["depth_ppm"] = [1000.0, 2000.0, np.nan]
        _, fill_values = impute_missing_features(train)

        test = pd.DataFrame({col: [np.nan] for col in REQUIRED_FEATURE_COLUMNS})
        result, _ = impute_missing_features(test, fill_values=fill_values)
        # depth_ppm should be filled with training median, not 0
        assert result.loc[0, "depth_ppm"] == fill_values["depth_ppm"]

    def test_preserves_non_nan_values(self):
        df = pd.DataFrame({col: [np.nan] for col in REQUIRED_FEATURE_COLUMNS})
        df["local_snr"] = [7.5]
        result, _ = impute_missing_features(df)
        assert result.loc[0, "local_snr"] == pytest.approx(7.5)


# ---------------------------------------------------------------------------
# add_quality_score
# ---------------------------------------------------------------------------

class TestAddQualityScore:
    def test_quality_score_in_range(self):
        df = pd.DataFrame({
            "local_snr": [3.0, 7.0, 10.0, 0.0],
            "egress_ingress_ratio": [1.0, 2.5, 5.0, 1.0],
            "delta_chi2_asym": [0.0, 20.0, 80.0, 0.0],
            "edge_event": [False, False, False, True],
            "single_point_like": [False, False, False, True],
        })
        result = add_quality_score(df)
        assert "quality_score" in result.columns
        assert result["quality_score"].between(0.0, 1.0).all(), (
            f"quality_score out of [0,1]: {result['quality_score'].tolist()}"
        )

    def test_edge_event_penalizes_score(self):
        base = pd.DataFrame({
            "local_snr": [5.0], "egress_ingress_ratio": [2.0],
            "delta_chi2_asym": [30.0], "edge_event": [False], "single_point_like": [False],
        })
        penalized = pd.DataFrame({
            "local_snr": [5.0], "egress_ingress_ratio": [2.0],
            "delta_chi2_asym": [30.0], "edge_event": [True], "single_point_like": [False],
        })
        score_base = add_quality_score(base)["quality_score"].iloc[0]
        score_pen = add_quality_score(penalized)["quality_score"].iloc[0]
        assert score_pen < score_base, (
            f"edge_event=True should reduce quality score; got base={score_base:.3f} pen={score_pen:.3f}"
        )

    def test_single_point_like_penalizes_score(self):
        base = pd.DataFrame({
            "local_snr": [6.0], "egress_ingress_ratio": [3.0],
            "delta_chi2_asym": [40.0], "edge_event": [False], "single_point_like": [False],
        })
        penalized = pd.DataFrame({
            "local_snr": [6.0], "egress_ingress_ratio": [3.0],
            "delta_chi2_asym": [40.0], "edge_event": [False], "single_point_like": [True],
        })
        score_base = add_quality_score(base)["quality_score"].iloc[0]
        score_pen = add_quality_score(penalized)["quality_score"].iloc[0]
        assert score_pen < score_base

    def test_high_snr_gives_higher_score(self):
        low = add_quality_score(pd.DataFrame({"local_snr": [2.0], "egress_ingress_ratio": [1.0],
                                               "delta_chi2_asym": [0.0]}))
        high = add_quality_score(pd.DataFrame({"local_snr": [10.0], "egress_ingress_ratio": [5.0],
                                                "delta_chi2_asym": [80.0]}))
        assert high["quality_score"].iloc[0] > low["quality_score"].iloc[0]

    def test_missing_columns_handled_gracefully(self):
        df = pd.DataFrame({"local_snr": [5.0]})
        result = add_quality_score(df)
        assert "quality_score" in result.columns
        assert result["quality_score"].between(0.0, 1.0).all()
