"""Tests for src/astrohunter/ml.py.

All tests are network-free and use only synthetic data.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from astrohunter.features import (
    REQUIRED_FEATURE_COLUMNS,
    add_quality_score,
    impute_missing_features,
)
from astrohunter.ml import (
    RANKER_VERSION,
    compute_final_candidate_score,
    evaluate_event_ranker,
    score_candidate_events,
    train_event_ranker,
)


# ---------------------------------------------------------------------------
# Synthetic data helpers
# ---------------------------------------------------------------------------

def _synthetic_training_data(
    n: int = 60,
    seed: int = 0,
    n_features: int = 3,
) -> tuple[pd.DataFrame, pd.Series]:
    """Return synthetic X, y with two well-separated classes."""
    rng = np.random.default_rng(seed)
    n_pos = n // 2
    n_neg = n - n_pos

    # Positive: higher depth_ppm and local_snr
    pos = {
        "depth_ppm": rng.uniform(1000, 3000, n_pos),
        "local_snr": rng.uniform(4, 10, n_pos),
        "noise_mad": rng.uniform(1e-4, 5e-4, n_pos),
    }
    neg = {
        "depth_ppm": rng.uniform(0, 200, n_neg),
        "local_snr": rng.uniform(0, 3, n_neg),
        "noise_mad": rng.uniform(3e-4, 9e-4, n_neg),
    }
    X = pd.DataFrame({k: np.concatenate([pos[k], neg[k]]) for k in pos})
    y = pd.Series(np.concatenate([np.ones(n_pos, int), np.zeros(n_neg, int)]))
    return X, y


def _synthetic_candidate_df(n: int = 5, seed: int = 1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        rows.append({
            "tic_id": 100000 + i,
            "target_name": f"Star_{i}",
            "event_time_btjd": float(rng.uniform(1400, 1500)),
            "depth_ppm": float(rng.uniform(300, 3000)),
            "local_snr": float(rng.uniform(2, 8)),
            "noise_mad": float(rng.uniform(1e-4, 8e-4)),
            "duration_hours": float(rng.uniform(0.1, 1.0)),
            "fwhm_hours": float(rng.uniform(0.05, 0.5)),
            "ingress_duration_hours": float(rng.uniform(0.05, 0.3)),
            "egress_duration_hours": float(rng.uniform(0.1, 0.8)),
            "egress_ingress_ratio": float(rng.uniform(1.0, 5.0)),
            "skewness": float(rng.uniform(-1, 1)),
            "kurtosis": float(rng.uniform(-0.5, 2.0)),
            "delta_chi2_asym": float(rng.uniform(-5, 80)),
            "n_points_window": int(rng.integers(100, 600)),
            "edge_event": bool(rng.integers(0, 2)),
            "single_point_like": bool(rng.integers(0, 2)),
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# train_event_ranker
# ---------------------------------------------------------------------------

class TestTrainEventRanker:
    def test_trains_and_returns_model_and_features(self):
        X, y = _synthetic_training_data(n=60)
        model, feature_names = train_event_ranker(X, y, random_state=42)
        assert model is not None
        assert isinstance(feature_names, list)
        assert len(feature_names) > 0

    def test_raises_on_single_class(self):
        X, _ = _synthetic_training_data(n=20)
        y_single = pd.Series(np.ones(20, int))
        with pytest.raises(ValueError, match="one class"):
            train_event_ranker(X, y_single, random_state=0)

    def test_model_can_predict(self):
        X, y = _synthetic_training_data(n=60)
        model, feature_names = train_event_ranker(X, y, random_state=0)
        X_sub = X[feature_names].fillna(0.0)
        preds = model.predict(X_sub)
        assert preds.shape == (60,)

    def test_model_has_predict_proba(self):
        X, y = _synthetic_training_data(n=60)
        model, feature_names = train_event_ranker(X, y, random_state=42)
        if hasattr(model, "predict_proba"):
            X_sub = X[feature_names].fillna(0.0)
            proba = model.predict_proba(X_sub)
            assert proba.shape == (60, 2)
            np.testing.assert_allclose(proba.sum(axis=1), 1.0, atol=1e-5)

    def test_feature_importances_available(self):
        X, y = _synthetic_training_data(n=60)
        model, feature_names = train_event_ranker(X, y, random_state=42)
        assert hasattr(model, "feature_importances_")
        assert len(model.feature_importances_) == len(feature_names)

    def test_model_trained_on_well_separated_data_high_accuracy(self):
        X, y = _synthetic_training_data(n=100, seed=7)
        X_imp, _ = impute_missing_features(X)
        model, feature_names = train_event_ranker(X_imp, y, random_state=0)
        X_sub = X_imp[feature_names].fillna(0.0)
        preds = model.predict(X_sub)
        acc = float((preds == y.values).mean())
        assert acc >= 0.75, f"Expected ≥75% train accuracy on separated data; got {acc:.0%}"


# ---------------------------------------------------------------------------
# evaluate_event_ranker
# ---------------------------------------------------------------------------

class TestEvaluateEventRanker:
    def _fitted_model(self, seed=0):
        X, y = _synthetic_training_data(n=80, seed=seed)
        X_imp, _ = impute_missing_features(X)
        model, feature_names = train_event_ranker(X_imp, y, random_state=seed)
        return model, feature_names, X_imp, y

    def test_returns_required_metrics(self):
        model, feature_names, X, y = self._fitted_model()
        metrics = evaluate_event_ranker(model, X, y, feature_names)
        for key in ("accuracy", "precision", "recall", "f1", "n_test"):
            assert key in metrics, f"Missing metric: {key}"

    def test_accuracy_in_range(self):
        model, feature_names, X, y = self._fitted_model()
        metrics = evaluate_event_ranker(model, X, y, feature_names)
        assert 0.0 <= metrics["accuracy"] <= 1.0

    def test_auc_in_range_when_two_classes(self):
        model, feature_names, X, y = self._fitted_model()
        metrics = evaluate_event_ranker(model, X, y, feature_names)
        if not np.isnan(metrics.get("roc_auc", np.nan)):
            assert 0.0 <= metrics["roc_auc"] <= 1.0
        if not np.isnan(metrics.get("pr_auc", np.nan)):
            assert 0.0 <= metrics["pr_auc"] <= 1.0

    def test_single_class_test_set_does_not_crash(self):
        model, feature_names, X, y = self._fitted_model()
        y_single = pd.Series(np.ones(len(y), int))
        metrics = evaluate_event_ranker(model, X, y_single, feature_names)
        assert "warning" in metrics
        assert metrics["warning"] is not None
        assert np.isnan(metrics.get("f1", float("nan")))

    def test_model_type_in_metrics(self):
        model, feature_names, X, y = self._fitted_model()
        metrics = evaluate_event_ranker(model, X, y, feature_names)
        assert "model_type" in metrics
        assert isinstance(metrics["model_type"], str)

    def test_ranker_version_in_metrics(self):
        model, feature_names, X, y = self._fitted_model()
        metrics = evaluate_event_ranker(model, X, y, feature_names)
        assert metrics.get("ranker_version") == RANKER_VERSION


# ---------------------------------------------------------------------------
# score_candidate_events
# ---------------------------------------------------------------------------

class TestScoreCandidateEvents:
    def test_returns_ml_score_series(self):
        X, y = _synthetic_training_data(n=60)
        X_imp, _ = impute_missing_features(X)
        model, feature_names = train_event_ranker(X_imp, y, random_state=0)

        candidates = _synthetic_candidate_df(n=4)
        cand_imp, _ = impute_missing_features(candidates)
        scores = score_candidate_events(model, cand_imp, feature_names=feature_names)

        assert isinstance(scores, pd.Series)
        assert scores.name == "ml_score"
        assert len(scores) == 4
        assert scores.between(0.0, 1.0).all()

    def test_returns_empty_for_empty_candidate_df(self):
        X, y = _synthetic_training_data(n=40)
        X_imp, _ = impute_missing_features(X)
        model, feature_names = train_event_ranker(X_imp, y, random_state=0)
        scores = score_candidate_events(model, pd.DataFrame(), feature_names=feature_names)
        assert len(scores) == 0

    def test_handles_missing_feature_with_zero_fill(self):
        X, y = _synthetic_training_data(n=60)
        X_imp, _ = impute_missing_features(X)
        model, feature_names = train_event_ranker(X_imp, y, random_state=0)

        # Candidate with missing feature columns
        cand = pd.DataFrame({"depth_ppm": [1500.0]})
        scores = score_candidate_events(model, cand, feature_names=feature_names)
        assert len(scores) == 1
        assert float(scores.iloc[0]) >= 0.0


# ---------------------------------------------------------------------------
# compute_final_candidate_score
# ---------------------------------------------------------------------------

class TestComputeFinalCandidateScore:
    def _base_candidate(self, **kwargs) -> pd.DataFrame:
        defaults = {
            "ml_score": 0.7,
            "quality_score": 0.6,
            "local_snr": 5.0,
            "edge_event": False,
            "single_point_like": False,
        }
        defaults.update(kwargs)
        return pd.DataFrame([defaults])

    def test_final_score_column_added(self):
        df = self._base_candidate()
        result = compute_final_candidate_score(df)
        assert "final_candidate_score" in result.columns

    def test_ranker_version_stamped(self):
        df = self._base_candidate()
        result = compute_final_candidate_score(df)
        assert "ranker_version" in result.columns
        assert result["ranker_version"].iloc[0] == RANKER_VERSION

    def test_score_in_range(self):
        for seed in range(10):
            rng = np.random.default_rng(seed)
            df = self._base_candidate(
                ml_score=float(rng.uniform(0, 1)),
                quality_score=float(rng.uniform(0, 1)),
                local_snr=float(rng.uniform(0, 12)),
            )
            result = compute_final_candidate_score(df)
            score = result["final_candidate_score"].iloc[0]
            assert 0.0 <= score <= 1.0, f"Score {score} out of [0, 1]"

    def test_edge_event_penalizes_final_score(self):
        clean = compute_final_candidate_score(self._base_candidate(edge_event=False))
        penalized = compute_final_candidate_score(self._base_candidate(edge_event=True))
        assert penalized["final_candidate_score"].iloc[0] < clean["final_candidate_score"].iloc[0]

    def test_single_point_like_penalizes_final_score(self):
        clean = compute_final_candidate_score(self._base_candidate(single_point_like=False))
        penalized = compute_final_candidate_score(self._base_candidate(single_point_like=True))
        assert penalized["final_candidate_score"].iloc[0] < clean["final_candidate_score"].iloc[0]

    def test_missing_ml_score_uses_default(self):
        df = pd.DataFrame([{"quality_score": 0.5}])
        result = compute_final_candidate_score(df)
        assert "final_candidate_score" in result.columns
        assert not result["final_candidate_score"].isna().any()

    def test_both_flags_give_lower_score_than_neither(self):
        clean = compute_final_candidate_score(
            self._base_candidate(edge_event=False, single_point_like=False))
        both = compute_final_candidate_score(
            self._base_candidate(edge_event=True, single_point_like=True))
        assert both["final_candidate_score"].iloc[0] < clean["final_candidate_score"].iloc[0]

    def test_higher_ml_score_gives_higher_final_score_ceteris_paribus(self):
        low = compute_final_candidate_score(self._base_candidate(ml_score=0.1, quality_score=0.5))
        high = compute_final_candidate_score(self._base_candidate(ml_score=0.9, quality_score=0.5))
        assert high["final_candidate_score"].iloc[0] > low["final_candidate_score"].iloc[0]


# ---------------------------------------------------------------------------
# ML plotting functions (file creation tests)
# ---------------------------------------------------------------------------

class TestMLPlottingFunctions:
    def test_plot_ml_feature_importance_creates_file(self, tmp_path):
        from astrohunter.plotting import plot_ml_feature_importance
        X, y = _synthetic_training_data(n=60)
        X_imp, _ = impute_missing_features(X)
        model, feature_names = train_event_ranker(X_imp, y, random_state=0)
        out = tmp_path / "fi.png"
        plot_ml_feature_importance(model, feature_names, output_path=out)
        assert out.exists()

    def test_plot_precision_recall_curve_creates_file(self, tmp_path):
        from astrohunter.plotting import plot_precision_recall_curve
        y_true = np.array([1, 0, 1, 0, 1, 1, 0, 0])
        y_score = np.array([0.9, 0.2, 0.8, 0.3, 0.7, 0.85, 0.15, 0.25])
        out = tmp_path / "pr.png"
        plot_precision_recall_curve(y_true, y_score, output_path=out)
        assert out.exists()

    def test_plot_roc_curve_creates_file(self, tmp_path):
        from astrohunter.plotting import plot_roc_curve
        y_true = np.array([1, 0, 1, 0, 1, 1, 0, 0])
        y_score = np.array([0.9, 0.1, 0.8, 0.2, 0.7, 0.85, 0.15, 0.25])
        out = tmp_path / "roc.png"
        plot_roc_curve(y_true, y_score, output_path=out)
        assert out.exists()

    def test_plot_candidate_score_distribution_creates_file(self, tmp_path):
        from astrohunter.plotting import plot_candidate_score_distribution
        df = _synthetic_candidate_df(n=6)
        df = add_quality_score(df)
        df["ml_score"] = 0.6
        df["final_candidate_score"] = 0.55
        out = tmp_path / "scores.png"
        plot_candidate_score_distribution(df, output_path=out)
        assert out.exists()

    def test_plot_candidate_score_distribution_handles_empty(self, tmp_path):
        from astrohunter.plotting import plot_candidate_score_distribution
        out = tmp_path / "empty_scores.png"
        plot_candidate_score_distribution(pd.DataFrame(), output_path=out)
        assert out.exists()

    def test_pr_curve_handles_single_class(self, tmp_path):
        from astrohunter.plotting import plot_precision_recall_curve
        y_true = np.array([1, 1, 1, 1])
        y_score = np.array([0.9, 0.8, 0.7, 0.6])
        out = tmp_path / "pr_single.png"
        plot_precision_recall_curve(y_true, y_score, output_path=out)
        assert out.exists()
