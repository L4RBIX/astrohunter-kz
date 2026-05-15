"""Phase 4 ML event ranker for AstroHunter KZ.

Trains a simple, interpretable classifier on injection-recovery labels and
applies it to real-data candidate events to produce prioritisation scores.

SCIENTIFIC CONSTRAINTS:
- The model is trained on *synthetic* injection-recovery labels.
- ML scores are prioritisation aids for human review.
- ML scores are NOT confirmation probabilities.
- Injection-trained metrics do NOT equal real-data purity.
- Real candidates require multi-sector vetting and follow-up.

Model preference:
    XGBoost (if installed) → GradientBoostingClassifier (sklearn fallback)
"""

from __future__ import annotations

import logging
import warnings
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Version tag stamped into output tables
RANKER_VERSION = "phase4_v1"

# Features actually used by the ML model (subset of REQUIRED_FEATURE_COLUMNS
# that are available / non-constant in the injection-recovery training set).
# Populated at training time via _select_model_features().
_DEFAULT_MODEL_FEATURES: list[str] = [
    "depth_ppm",
    "local_snr",
    "noise_mad",
]


# ---------------------------------------------------------------------------
# Model factory
# ---------------------------------------------------------------------------

def _build_model(random_state: int = 42) -> Any:
    """Return an XGBoost or sklearn gradient-boosting classifier.

    XGBoost is preferred when the native library can be loaded.  If XGBoost is
    not installed or fails to load (e.g., missing ``libomp.dylib`` on macOS),
    falls back to sklearn ``GradientBoostingClassifier``.
    """
    # Attempt XGBoost with a full-exception guard (covers ImportError,
    # XGBoostError from missing libomp, TypeError from old API, etc.)
    try:
        from xgboost import XGBClassifier  # noqa: PLC0415

        # Probe the native library by constructing an instance.
        # XGBoostError is raised here if libxgboost.dylib can't be loaded.
        model = XGBClassifier(
            n_estimators=60,
            max_depth=3,
            learning_rate=0.1,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=random_state,
            eval_metric="logloss",
            verbosity=0,
        )
        return model
    except Exception as exc:  # noqa: BLE001
        logger.info(
            "XGBoost unavailable (%s: %s); falling back to sklearn GradientBoostingClassifier.",
            type(exc).__name__, exc,
        )

    from sklearn.ensemble import GradientBoostingClassifier  # noqa: PLC0415

    return GradientBoostingClassifier(
        n_estimators=60,
        max_depth=3,
        learning_rate=0.1,
        subsample=0.8,
        random_state=random_state,
    )


def _select_model_features(X: pd.DataFrame) -> list[str]:
    """Return columns in X that have at least 2 distinct non-NaN values."""
    usable = []
    for col in X.columns:
        vals = X[col].dropna()
        if len(vals) >= 2 and vals.nunique() > 1:
            usable.append(col)
    if not usable:
        usable = list(X.columns)  # last resort: use all
    return usable


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

def train_event_ranker(
    X: pd.DataFrame,
    y: pd.Series,
    random_state: int = 42,
) -> tuple[Any, list[str]]:
    """Train the event-prioritisation ranker on injection-recovery features.

    Parameters
    ----------
    X:
        Feature DataFrame (rows = injection trials, columns = features).
        Should not contain any injected ground-truth columns.
    y:
        Binary label Series (1 = recovered, 0 = not recovered).
    random_state:
        Fixed seed for reproducibility.

    Returns
    -------
    (model, feature_names)
        The fitted model and the ordered list of feature columns it was
        trained on.

    Raises
    ------
    ValueError
        If *y* contains fewer than 2 distinct classes.
    """
    if y.nunique() < 2:
        raise ValueError(
            f"Training labels have only one class ({y.unique().tolist()}). "
            "Both recovered (1) and not-recovered (0) examples are required. "
            "Check that your injection-recovery table has both outcomes."
        )

    feature_names = _select_model_features(X)
    X_fit = X[feature_names].copy()

    # Replace remaining NaN with 0 before fitting
    X_fit = X_fit.fillna(0.0)

    n_pos = int(y.sum())
    n_neg = int((y == 0).sum())
    logger.info(
        "Training ranker on %d rows (%d positive, %d negative) with %d features: %s",
        len(y), n_pos, n_neg, len(feature_names), feature_names,
    )

    model = _build_model(random_state)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model.fit(X_fit, y.values)

    logger.info("Ranker trained: %s", type(model).__name__)
    return model, feature_names


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

def evaluate_event_ranker(
    model: Any,
    X_test: pd.DataFrame,
    y_test: pd.Series,
    feature_names: list[str] | None = None,
) -> dict[str, Any]:
    """Evaluate the trained model on held-out injection-recovery rows.

    Parameters
    ----------
    model:
        Trained classifier (from :func:`train_event_ranker`).
    X_test:
        Test feature DataFrame.
    y_test:
        True binary labels.
    feature_names:
        Feature columns the model was trained on.  Inferred from model when None.

    Returns
    -------
    dict
        Metric dictionary including accuracy, precision, recall, F1, ROC-AUC,
        PR-AUC, confusion-matrix values, and class balance statistics.
        Metrics that require two classes in y_test are NaN when only one class
        is present.

    Notes
    -----
    These metrics describe sensitivity on *synthetic* injection trials.
    They do not measure real-data candidate purity.
    """
    from sklearn.metrics import (  # noqa: PLC0415
        accuracy_score,
        average_precision_score,
        confusion_matrix,
        f1_score,
        precision_score,
        recall_score,
        roc_auc_score,
    )

    if feature_names is None:
        feature_names = list(X_test.columns)

    cols_available = [c for c in feature_names if c in X_test.columns]
    X_eval = X_test[cols_available].fillna(0.0)

    y_pred = model.predict(X_eval)
    has_proba = hasattr(model, "predict_proba")
    y_score: np.ndarray | None = None
    if has_proba:
        y_score = model.predict_proba(X_eval)[:, 1]

    metrics: dict[str, Any] = {
        "n_test": int(len(y_test)),
        "n_train_positive": None,   # filled by caller
        "n_train_negative": None,
        "n_test_positive": int(y_test.sum()),
        "n_test_negative": int((y_test == 0).sum()),
        "accuracy": float(accuracy_score(y_test, y_pred)),
        "ranker_version": RANKER_VERSION,
        "model_type": type(model).__name__,
        "feature_names": feature_names,
        "warning": None,
    }

    if y_test.nunique() < 2:
        msg = (
            "Test set contains only one class; precision/recall/F1/AUC are not applicable. "
            "This can happen with small test sets. Report accuracy with caution."
        )
        logger.warning(msg)
        metrics["warning"] = msg
        for key in ("precision", "recall", "f1", "roc_auc", "pr_auc",
                    "tn", "fp", "fn", "tp"):
            metrics[key] = np.nan
        return metrics

    metrics["precision"] = float(precision_score(y_test, y_pred, zero_division=0))
    metrics["recall"] = float(recall_score(y_test, y_pred, zero_division=0))
    metrics["f1"] = float(f1_score(y_test, y_pred, zero_division=0))

    if y_score is not None:
        try:
            metrics["roc_auc"] = float(roc_auc_score(y_test, y_score))
        except Exception as exc:  # noqa: BLE001
            metrics["roc_auc"] = np.nan
            logger.debug("ROC-AUC failed: %s", exc)
        try:
            metrics["pr_auc"] = float(average_precision_score(y_test, y_score))
        except Exception as exc:  # noqa: BLE001
            metrics["pr_auc"] = np.nan
            logger.debug("PR-AUC failed: %s", exc)
    else:
        metrics["roc_auc"] = np.nan
        metrics["pr_auc"] = np.nan

    cm = confusion_matrix(y_test, y_pred)
    if cm.shape == (2, 2):
        tn, fp, fn, tp = cm.ravel()
        metrics["tn"] = int(tn)
        metrics["fp"] = int(fp)
        metrics["fn"] = int(fn)
        metrics["tp"] = int(tp)
    else:
        for k in ("tn", "fp", "fn", "tp"):
            metrics[k] = np.nan

    return metrics


# ---------------------------------------------------------------------------
# Candidate scoring
# ---------------------------------------------------------------------------

def score_candidate_events(
    model: Any,
    candidate_features: pd.DataFrame,
    feature_names: list[str] | None = None,
) -> pd.Series:
    """Apply the trained ranker to real-data candidate events.

    Only features in *feature_names* are used.  Missing or NaN features
    are zero-filled (same strategy used during training imputation).

    The returned series contains values in [0, 1] representing the model's
    estimated probability that the event resembles a *recovered* synthetic
    injection.  This is a prioritisation score, NOT a discovery probability.

    Parameters
    ----------
    model:
        Fitted classifier from :func:`train_event_ranker`.
    candidate_features:
        Candidate event feature DataFrame.
    feature_names:
        Ordered feature columns matching training input.

    Returns
    -------
    pd.Series
        Named ``ml_score``, same index as *candidate_features*.
    """
    if candidate_features.empty:
        return pd.Series(dtype=float, name="ml_score")

    if feature_names is None:
        feature_names = list(candidate_features.columns)

    cols_available = [c for c in feature_names if c in candidate_features.columns]
    missing = [c for c in feature_names if c not in candidate_features.columns]
    if missing:
        logger.warning(
            "Candidate table missing training features (zero-filling): %s", missing
        )

    X_score = candidate_features[cols_available].copy()
    for col in missing:
        X_score[col] = 0.0
    X_score = X_score[feature_names].fillna(0.0)

    if hasattr(model, "predict_proba"):
        raw = model.predict_proba(X_score)[:, 1]
    else:
        raw = model.predict(X_score).astype(float)

    return pd.Series(raw, index=candidate_features.index, name="ml_score")


# ---------------------------------------------------------------------------
# Final composite score
# ---------------------------------------------------------------------------

def compute_final_candidate_score(candidate_df: pd.DataFrame) -> pd.DataFrame:
    """Compute a composite ``final_candidate_score`` combining ML + quality scores.

    The final score is a weighted combination of:
    - ml_score (0.50): probability from the injection-trained ranker
    - quality_score (0.40): rule-based heuristic from feature.py
    - snr_bonus (0.10): small boost for high local_snr events

    Penalties:
    - –0.15 for edge_event = True
    - –0.15 for single_point_like = True

    Result is clipped to [0, 1].

    **This score ranks candidates for review priority. It does not confirm
    any astrophysical interpretation.**

    Parameters
    ----------
    candidate_df:
        Candidate DataFrame containing ml_score and quality_score columns.

    Returns
    -------
    pd.DataFrame
        Copy of *candidate_df* with ``final_candidate_score`` and
        ``ranker_version`` columns added.
    """
    result = candidate_df.copy()
    idx = result.index

    def _num(col: str, default: float) -> pd.Series:
        if col in result.columns:
            return pd.to_numeric(result[col], errors="coerce").fillna(default)
        return pd.Series(default, index=idx, dtype=float)

    ml_score = _num("ml_score", 0.5)
    quality_score = _num("quality_score", 0.0)
    snr = _num("local_snr", 0.0)
    edge = _num("edge_event", 0.0)
    single = _num("single_point_like", 0.0)

    snr_bonus = (snr / 10.0).clip(0.0, 1.0) * 0.10

    final = (
        0.50 * ml_score
        + 0.40 * quality_score
        + snr_bonus
        - 0.15 * edge
        - 0.15 * single
    ).clip(0.0, 1.0)

    result["final_candidate_score"] = final
    result["ranker_version"] = RANKER_VERSION
    return result
