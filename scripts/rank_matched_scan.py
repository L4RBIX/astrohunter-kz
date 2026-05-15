#!/usr/bin/env python3
"""Phase 5B ML ranking for matched-scan candidate events.

Trains the Phase 4 event ranker on injection-recovery labels and applies it
to the matched-scan candidate table (which includes both target and control
candidates).  Preserves sample_role and pair metadata columns.

SCIENTIFIC CONSTRAINTS:
- The ranker is trained on *synthetic* injection-recovery labels.
- ML scores rank candidates for human review — NOT confirmation probabilities.
- Injection-trained metrics do NOT describe real-data candidate purity.
- Target and control candidates are ranked on the same score scale.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sklearn.model_selection import train_test_split

from astrohunter.features import (
    REQUIRED_FEATURE_COLUMNS,
    add_quality_score,
    build_candidate_feature_table,
    build_training_feature_table,
    impute_missing_features,
    select_event_feature_columns,
    validate_feature_table,
)
from astrohunter.ml import (
    RANKER_VERSION,
    compute_final_candidate_score,
    evaluate_event_ranker,
    score_candidate_events,
    train_event_ranker,
)
from astrohunter.plotting import plot_candidate_score_distribution

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("rank_matched_scan")

FIGURES_DIR = Path("results/figures")
TABLES_DIR = Path("results/tables")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Phase 5B: Apply ML event ranker to matched-scan candidate events.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--injection-table",
                   default="results/tables/injection_recovery.csv",
                   help="Injection-recovery table for training the ranker.")
    p.add_argument("--candidate-table",
                   default="results/tables/detector_candidate_events_matched_scan.csv",
                   help="Matched-scan detector candidate event table.")
    p.add_argument("--output-ranked",
                   default="results/tables/ranked_candidate_events_matched_scan.csv",
                   help="Output path for ranked candidate table.")
    p.add_argument("--output-eval",
                   default="results/tables/ml_evaluation_summary_matched_scan.csv",
                   help="Output path for ML evaluation summary.")
    p.add_argument("--random-seed", type=int, default=42)
    p.add_argument("--test-size", type=float, default=0.25,
                   help="Fraction of injection rows held out for evaluation.")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    print("=" * 70)
    print("AstroHunter KZ — Phase 5B: ML Ranking of Matched-Scan Candidates")
    print(f"Ranker version: {RANKER_VERSION}")
    print()
    print("SCIENTIFIC CONSTRAINTS:")
    print("  Ranker trained on synthetic injection-recovery labels.")
    print("  ML scores rank candidates for review — NOT confirmation.")
    print("  Target and control candidates are scored on the same scale.")
    print("=" * 70)

    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ train
    inj_path = Path(args.injection_table)
    if not inj_path.exists():
        logger.error("Injection table not found: %s", inj_path)
        logger.error("Run scripts/run_injection_recovery.py first.")
        return 1

    injection_df = pd.read_csv(inj_path, low_memory=False)
    logger.info("Loaded injection table: %d rows", len(injection_df))

    training_df = build_training_feature_table(injection_df)
    training_df = add_quality_score(training_df)

    is_valid, issues = validate_feature_table(training_df, require_label=True)
    if not is_valid:
        logger.error("Training validation failed: %s", issues)
        return 1

    feature_cols = select_event_feature_columns(training_df)
    X_all = training_df[feature_cols].copy()
    y_all = training_df["label"].copy()

    if y_all.nunique() < 2:
        logger.error("Only one class in training labels. Cannot train ranker.")
        return 1

    n_test = max(1, int(len(X_all) * args.test_size))
    X_train, X_test, y_train, y_test = train_test_split(
        X_all, y_all,
        test_size=n_test,
        random_state=args.random_seed,
        stratify=y_all if y_all.nunique() >= 2 else None,
    )

    X_train_imp, fill_values = impute_missing_features(X_train)
    X_test_imp, _ = impute_missing_features(X_test, fill_values=fill_values)

    try:
        model, model_feature_names = train_event_ranker(
            X_train_imp, y_train, random_state=args.random_seed
        )
    except ValueError as exc:
        logger.error("Training failed: %s", exc)
        return 1

    logger.info("Trained %s on features: %s", type(model).__name__, model_feature_names)

    # Evaluate
    eval_metrics = evaluate_event_ranker(model, X_test_imp, y_test, model_feature_names)
    eval_metrics["n_train"] = len(X_train)
    eval_metrics["n_train_positive"] = int(y_train.sum())
    eval_metrics["n_train_negative"] = int((y_train == 0).sum())

    print(f"\n  Model type : {eval_metrics['model_type']}")
    print(f"  Features   : {model_feature_names}")
    print(f"  Accuracy   : {eval_metrics.get('accuracy', float('nan')):.3f}")
    print(f"  ROC-AUC    : {eval_metrics.get('roc_auc', float('nan')):.3f}")
    if eval_metrics.get("warning"):
        print(f"  WARNING    : {eval_metrics['warning']}")
    print()
    print("  REMINDER: Metrics are on synthetic injection data, NOT real candidates.")

    eval_df = pd.DataFrame([{
        k: (", ".join(v) if isinstance(v, list) else v)
        for k, v in eval_metrics.items()
    }])
    eval_df.to_csv(args.output_eval, index=False)
    logger.info("Saved evaluation summary: %s", args.output_eval)

    # ----------------------------------------------------------------- score
    cand_path = Path(args.candidate_table)
    ranked_path = Path(args.output_ranked)
    ranked_path.parent.mkdir(parents=True, exist_ok=True)

    if not cand_path.exists():
        logger.warning("Candidate table not found: %s. Saving empty ranked table.", cand_path)
        pd.DataFrame(columns=["tic_id", "sample_role", "ml_score",
                               "final_candidate_score", "ranker_version"]).to_csv(
            ranked_path, index=False
        )
        print("No candidate table found; empty ranked table saved.")
        return 0

    candidate_df = pd.read_csv(cand_path, low_memory=False)
    logger.info("Loaded %d candidates from %s", len(candidate_df), cand_path)

    if candidate_df.empty:
        logger.warning("Candidate table is empty.")
        candidate_df.to_csv(ranked_path, index=False)
        print("No candidates to rank.")
        return 0

    cand_feat_df = build_candidate_feature_table(candidate_df)
    cand_feat_imp, _ = impute_missing_features(cand_feat_df, fill_values=fill_values)

    ml_scores = score_candidate_events(model, cand_feat_imp, feature_names=model_feature_names)
    candidate_df["ml_score"] = ml_scores.values
    candidate_df = add_quality_score(candidate_df)
    candidate_df = compute_final_candidate_score(candidate_df)
    candidate_df = candidate_df.sort_values("final_candidate_score", ascending=False).reset_index(drop=True)
    candidate_df.to_csv(ranked_path, index=False)
    logger.info("Saved ranked table: %s (%d rows)", ranked_path, len(candidate_df))

    # Per-role summary
    if "sample_role" in candidate_df.columns:
        for role in ["target", "control"]:
            sub = candidate_df[candidate_df["sample_role"] == role]
            logger.info("  %s candidates: %d", role, len(sub))

    # Score distribution plot (split by role)
    try:
        score_fig_path = FIGURES_DIR / "matched_scan_candidate_score_distribution.png"
        _plot_matched_score_distribution(candidate_df, score_fig_path)
        logger.info("Saved score distribution plot: %s", score_fig_path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Score distribution plot failed: %s", exc)

    # ----------------------------------------------------------- print summary
    print("\n" + "=" * 70)
    print(f"Matched-scan ranked candidates: {len(candidate_df)} total")
    if "sample_role" in candidate_df.columns:
        for role in ["target", "control"]:
            n = int((candidate_df["sample_role"] == role).sum())
            print(f"  {role.capitalize()} candidates: {n}")
    print(f"\nTop-ranked candidates (review priority order):")
    disp_cols = [c for c in [
        "tic_id", "target_name", "sample_role", "event_time_btjd",
        "depth_ppm", "local_snr", "delta_chi2_asym",
        "ml_score", "final_candidate_score",
    ] if c in candidate_df.columns]
    with pd.option_context("display.max_columns", None, "display.width", 120,
                           "display.float_format", "{:.3f}".format):
        print(candidate_df[disp_cols].head(8).to_string(index=False))
    print(f"\nFull ranked table: {ranked_path}")
    print()
    print("REMINDER: Ranked candidates require manual vetting and")
    print("          multi-sector confirmation before any interpretation.")
    print("=" * 70)

    return 0


def _plot_matched_score_distribution(candidate_df: pd.DataFrame, output_path: Path) -> None:
    """Score distribution split by sample_role."""
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8, 4))
    score_col = "final_candidate_score"

    if score_col not in candidate_df.columns or candidate_df.empty:
        ax.text(0.5, 0.5, "No data", ha="center", va="center", transform=ax.transAxes)
        fig.savefig(output_path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        return

    bins = np.linspace(0, 1, 21)
    for role, color, label in [
        ("target", "tab:blue", "Target"),
        ("control", "tab:orange", "Control"),
    ]:
        if "sample_role" in candidate_df.columns:
            sub = candidate_df[candidate_df["sample_role"] == role][score_col].dropna()
        else:
            sub = candidate_df[score_col].dropna()
            label = "All"
        if not sub.empty:
            ax.hist(sub, bins=bins, alpha=0.65, color=color, label=f"{label} (n={len(sub)})", edgecolor="white")

    ax.set_xlabel("Final candidate score")
    ax.set_ylabel("Count")
    ax.set_title("Matched Scan — Candidate Score Distribution by Role")
    ax.legend(loc="upper left")
    ax.grid(alpha=0.25)

    note = "Scores rank candidates for review. Not confirmation probabilities."
    fig.text(0.5, -0.04, note, ha="center", fontsize=8, color="gray", style="italic")
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    sys.exit(main())
