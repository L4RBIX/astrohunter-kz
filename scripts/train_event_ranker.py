"""Phase 4 ML event ranker training and candidate scoring script.

Trains an interpretable event-prioritisation ranker on injection-recovery
labels, evaluates it on held-out injection rows, and applies it to real-data
candidate events from the Phase 3 dev scan.

SCIENTIFIC CONSTRAINTS:
- The ranker is trained on *synthetic* injection-recovery labels.
- ML scores rank candidate events for human review — they are NOT
  confirmation probabilities.
- Injection-trained evaluation metrics (AUC, F1, …) do NOT describe
  real-data candidate purity.
- Real candidates require multi-sector vetting and independent review.

Usage:
    python scripts/train_event_ranker.py \\
        --injection-table results/tables/injection_recovery.csv \\
        --candidate-table results/tables/detector_candidate_events_dev.csv \\
        --output-ranked results/tables/ranked_candidate_events_dev.csv \\
        --output-training results/tables/ml_training_features.csv \\
        --output-eval results/tables/ml_evaluation_summary.csv \\
        --random-seed 42 \\
        --test-size 0.25
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sklearn.model_selection import train_test_split

from astrohunter.features import (
    add_quality_score,
    build_candidate_feature_table,
    build_training_feature_table,
    impute_missing_features,
    select_event_feature_columns,
    validate_feature_table,
    REQUIRED_FEATURE_COLUMNS,
)
from astrohunter.ml import (
    RANKER_VERSION,
    compute_final_candidate_score,
    evaluate_event_ranker,
    score_candidate_events,
    train_event_ranker,
)
from astrohunter.plotting import (
    plot_candidate_score_distribution,
    plot_ml_feature_importance,
    plot_precision_recall_curve,
    plot_roc_curve,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("train_event_ranker")

TABLES_DIR = Path("results/tables")
FIGURES_DIR = Path("results/figures")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Phase 4 ML event ranker")
    p.add_argument("--injection-table",
                   default="results/tables/injection_recovery.csv")
    p.add_argument("--candidate-table",
                   default="results/tables/detector_candidate_events_dev.csv")
    p.add_argument("--output-ranked",
                   default="results/tables/ranked_candidate_events_dev.csv")
    p.add_argument("--output-training",
                   default="results/tables/ml_training_features.csv")
    p.add_argument("--output-eval",
                   default="results/tables/ml_evaluation_summary.csv")
    p.add_argument("--random-seed", type=int, default=42)
    p.add_argument("--test-size", type=float, default=0.25,
                   help="Fraction of injection rows held out for evaluation")
    return p.parse_args()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    args = _parse_args()

    print("\n" + "=" * 68)
    print("AstroHunter KZ — Phase 4 ML Event Ranker")
    print()
    print("SCIENTIFIC CONSTRAINTS:")
    print("  Ranker trained on synthetic injection-recovery labels.")
    print("  ML scores rank candidates for review — NOT confirmation.")
    print("  AUC/F1 metrics describe sensitivity on synthetic signals only.")
    print("  Real candidates require multi-sector vetting and follow-up.")
    print("=" * 68 + "\n")

    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # 1. Load injection-recovery table
    # ------------------------------------------------------------------
    inj_path = Path(args.injection_table)
    if not inj_path.exists():
        logger.error("Injection table not found: %s", inj_path)
        logger.error("Run scripts/run_injection_recovery.py first.")
        sys.exit(1)

    injection_df = pd.read_csv(inj_path, low_memory=False)
    logger.info("Loaded injection table: %d rows from %s", len(injection_df), inj_path)

    # ------------------------------------------------------------------
    # 2. Build training feature table
    # ------------------------------------------------------------------
    training_df = build_training_feature_table(injection_df)
    training_df = add_quality_score(training_df)

    is_valid, issues = validate_feature_table(training_df, require_label=True)
    if not is_valid:
        logger.error("Training feature table validation failed:\n  %s",
                     "\n  ".join(issues))
        sys.exit(1)

    # Save training feature table for inspection
    training_df.to_csv(args.output_training, index=False)
    logger.info("Saved training feature table: %s (%d rows)", args.output_training, len(training_df))

    # ------------------------------------------------------------------
    # 3. Feature selection and train/test split
    # ------------------------------------------------------------------
    feature_cols = select_event_feature_columns(training_df)
    if not feature_cols:
        logger.error("No valid feature columns found in training data.")
        sys.exit(1)

    X_all = training_df[feature_cols].copy()
    y_all = training_df["label"].copy()

    # Check class balance
    n_pos = int(y_all.sum())
    n_neg = int((y_all == 0).sum())
    logger.info("Class balance: %d recovered (positive), %d not-recovered (negative).",
                n_pos, n_neg)

    if y_all.nunique() < 2:
        logger.error(
            "Only one class in labels (%s). Cannot train. "
            "Check injection-recovery results.", y_all.unique().tolist()
        )
        sys.exit(1)

    n_test = max(1, int(len(X_all) * args.test_size))
    if n_test >= len(X_all):
        n_test = max(1, len(X_all) // 4)

    X_train, X_test, y_train, y_test = train_test_split(
        X_all, y_all,
        test_size=n_test,
        random_state=args.random_seed,
        stratify=y_all if y_all.nunique() >= 2 else None,
    )
    logger.info("Train rows: %d, Test rows: %d", len(X_train), len(X_test))

    # ------------------------------------------------------------------
    # 4. Impute missing features
    # ------------------------------------------------------------------
    X_train_imp, fill_values = impute_missing_features(X_train)
    X_test_imp, _ = impute_missing_features(X_test, fill_values=fill_values)

    # ------------------------------------------------------------------
    # 5. Train ranker
    # ------------------------------------------------------------------
    try:
        model, model_feature_names = train_event_ranker(
            X_train_imp, y_train, random_state=args.random_seed
        )
    except ValueError as exc:
        logger.error("Training failed: %s", exc)
        sys.exit(1)

    logger.info("Trained model: %s on features: %s", type(model).__name__, model_feature_names)

    # ------------------------------------------------------------------
    # 6. Evaluate on test set
    # ------------------------------------------------------------------
    eval_metrics = evaluate_event_ranker(model, X_test_imp, y_test, model_feature_names)
    eval_metrics["n_train"] = len(X_train)
    eval_metrics["n_train_positive"] = int(y_train.sum())
    eval_metrics["n_train_negative"] = int((y_train == 0).sum())
    eval_metrics["n_test"] = len(X_test)
    eval_metrics["test_size_fraction"] = args.test_size
    eval_metrics["random_seed"] = args.random_seed
    eval_metrics["injection_table"] = str(inj_path)

    # Print summary
    print("\n--- ML Evaluation Summary ---")
    print(f"  Model type      : {eval_metrics['model_type']}")
    print(f"  Features used   : {model_feature_names}")
    print(f"  Train rows      : {eval_metrics['n_train']} "
          f"(+{eval_metrics['n_train_positive']} / -{eval_metrics['n_train_negative']})")
    print(f"  Test rows       : {eval_metrics['n_test']}")
    print(f"  Accuracy        : {eval_metrics.get('accuracy', float('nan')):.3f}")
    print(f"  Precision       : {eval_metrics.get('precision', float('nan')):.3f}")
    print(f"  Recall          : {eval_metrics.get('recall', float('nan')):.3f}")
    print(f"  F1              : {eval_metrics.get('f1', float('nan')):.3f}")
    print(f"  ROC-AUC         : {eval_metrics.get('roc_auc', float('nan')):.3f}")
    print(f"  PR-AUC          : {eval_metrics.get('pr_auc', float('nan')):.3f}")
    if eval_metrics.get("warning"):
        print(f"  WARNING         : {eval_metrics['warning']}")
    print()
    print("REMINDER: Metrics above describe synthetic injection sensitivity,")
    print("          not real-data candidate purity.\n")

    # Flatten feature_names list for CSV serialisation
    eval_df = pd.DataFrame([{
        k: (", ".join(v) if isinstance(v, list) else v)
        for k, v in eval_metrics.items()
    }])
    eval_df.to_csv(args.output_eval, index=False)
    logger.info("Saved evaluation summary: %s", args.output_eval)

    # ------------------------------------------------------------------
    # 7. Generate ML diagnostic plots
    # ------------------------------------------------------------------
    try:
        plot_ml_feature_importance(
            model, model_feature_names,
            output_path=FIGURES_DIR / "ml_feature_importance.png",
        )
        logger.info("Saved ml_feature_importance.png")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Feature importance plot failed: %s", exc)

    # PR and ROC curves require scored test set
    y_score_test: np.ndarray | None = None
    if hasattr(model, "predict_proba"):
        X_test_for_score = X_test_imp[model_feature_names].fillna(0.0)
        try:
            y_score_test = model.predict_proba(X_test_for_score)[:, 1]
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not get predict_proba: %s", exc)

    if y_score_test is not None:
        try:
            plot_precision_recall_curve(
                y_test, y_score_test,
                pr_auc=eval_metrics.get("pr_auc"),
                output_path=FIGURES_DIR / "ml_precision_recall_curve.png",
            )
            plot_roc_curve(
                y_test, y_score_test,
                roc_auc=eval_metrics.get("roc_auc"),
                output_path=FIGURES_DIR / "ml_roc_curve.png",
            )
            logger.info("Saved ml_precision_recall_curve.png, ml_roc_curve.png")
        except Exception as exc:  # noqa: BLE001
            logger.warning("PR/ROC plot failed: %s", exc)

    # ------------------------------------------------------------------
    # 8. Load and score candidate events
    # ------------------------------------------------------------------
    cand_path = Path(args.candidate_table)
    ranked_path = Path(args.output_ranked)
    ranked_path.parent.mkdir(parents=True, exist_ok=True)

    if not cand_path.exists():
        logger.warning("Candidate table not found: %s. Saving empty ranked table.", cand_path)
        pd.DataFrame(columns=["tic_id", "ml_score", "quality_score",
                               "final_candidate_score", "ranker_version"]).to_csv(
            ranked_path, index=False
        )
        print("No candidate table found; empty ranked table saved.")
        return

    candidate_df = pd.read_csv(cand_path, low_memory=False)
    logger.info("Loaded %d candidate events from %s", len(candidate_df), cand_path)

    if candidate_df.empty:
        logger.warning("Candidate table is empty. Saving empty ranked table.")
        candidate_df.to_csv(ranked_path, index=False)
        print("Candidate table is empty; nothing to rank.")
        _save_empty_score_plot()
        return

    # Build candidate features
    cand_feat_df = build_candidate_feature_table(candidate_df)
    cand_feat_imp, _ = impute_missing_features(cand_feat_df, fill_values=fill_values)

    # ML score
    ml_scores = score_candidate_events(model, cand_feat_imp, feature_names=model_feature_names)
    candidate_df["ml_score"] = ml_scores.values

    # Quality score
    candidate_df = add_quality_score(candidate_df)

    # Final composite score
    candidate_df = compute_final_candidate_score(candidate_df)

    # Sort descending by final_candidate_score
    candidate_df = candidate_df.sort_values("final_candidate_score", ascending=False).reset_index(drop=True)
    candidate_df.to_csv(ranked_path, index=False)
    logger.info("Saved ranked candidate table: %s (%d rows)", ranked_path, len(candidate_df))

    # Score distribution plot
    try:
        plot_candidate_score_distribution(
            candidate_df,
            output_path=FIGURES_DIR / "candidate_score_distribution.png",
        )
        logger.info("Saved candidate_score_distribution.png")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Score distribution plot failed: %s", exc)

    # ------------------------------------------------------------------
    # 9. Print ranked candidate summary
    # ------------------------------------------------------------------
    print("\n" + "=" * 68)
    print(f"Phase 4 ranked candidates: {len(candidate_df)} events")
    print("=" * 68)
    print()
    print("Top-ranked candidate dip-like features (review priority order):")
    print("(All require quality vetting before astrophysical interpretation)")
    print()

    display_cols = [c for c in [
        "tic_id", "target_name", "event_time_btjd",
        "depth_ppm", "local_snr", "egress_ingress_ratio", "delta_chi2_asym",
        "ml_score", "quality_score", "final_candidate_score",
        "edge_event", "single_point_like",
    ] if c in candidate_df.columns]

    top = candidate_df[display_cols].head(5)
    with pd.option_context("display.max_columns", None, "display.width", 120,
                           "display.float_format", "{:.3f}".format):
        print(top.to_string(index=False))
    print()
    print(f"Full ranked table saved to: {ranked_path}")
    print()
    print("REMINDER: All ranked candidates require:")
    print("  - Multi-sector confirmation")
    print("  - Quality-flag and systematics vetting")
    print("  - Stellar context checks")
    print("  before any astrophysical interpretation.")
    print()


def _save_empty_score_plot() -> None:
    """Save a placeholder score-distribution plot when there are no candidates."""
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.text(0.5, 0.5,
            "No candidate events to score.\nRun run_scan.py with more targets first.",
            ha="center", va="center", transform=ax.transAxes)
    ax.set_title("Candidate ranking score distribution (no data)")
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURES_DIR / "candidate_score_distribution.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
