# Project Scope

AstroHunter KZ asks whether physically motivated target selection improves the
yield and purity of TESS candidate asymmetric transit searches.

## Phase 1: Beta Pic Technical Positive Control

Build a reproducible pipeline that downloads public TESS data for Beta Pic /
TIC 270577175, cleans and normalizes the light curve, detects simple candidate
dip-like features, computes transparent asymmetry metrics, and saves figures and
tables. This phase is a technical foundation, not a discovery claim.

## Phase 2: Catalog Builder and Development Samples

Build debris-disk / infrared-excess target samples and matched non-disk control
samples using public catalogs such as Cotten & Song, Chen, McDonald, TIC, Gaia,
and TESS availability metadata. Do not fabricate target samples.

## Phase 3: Detector and Injection Recovery

Implement a Kennedy-style asymmetric-transit detector and injection-recovery
experiments on real TESS light curves to measure sensitivity, false positives,
and completeness.

## Phase 4: Machine-Learning Ranker (complete)

Train an interpretable event-level ranker on injection-recovery labels.
XGBoost (primary) or sklearn GradientBoostingClassifier (fallback).
The ranker produces a prioritisation score for human review.

Constraints:
- Trained on *synthetic* injection-recovery labels only.
- ML scores are NOT confirmation probabilities.
- Injection-set AUC/F1 does NOT equal real-data purity.
- Real candidates require vetting cascade before interpretation.

Outputs: ml_training_features.csv, ml_evaluation_summary.csv,
ranked_candidate_events_dev.csv, and four ML diagnostic figures.

## Phase 5: Vetting and Statistics (complete)

Apply automated vetting flags to ranked candidate events and compute preliminary
target/control candidate-yield rate statistics.

Constraints:
- Automated vetting is NOT scientific confirmation.
- All candidates require manual review.
- External catalog crossmatches (EB, VSX, SIMBAD) are NOT implemented — placeholders only.
- Dev-sample rate statistics are preliminary and unstable (N < 10 candidates).
- Rate ratios do not constitute a scientific claim.

Outputs: vetted_candidate_events_dev.csv, manual_vetting_sheet.csv,
rate_ratio_summary.csv, and three diagnostic figures.

See [docs/PHASE5_VETTING_STATISTICS.md](PHASE5_VETTING_STATISTICS.md) for full documentation.

## Phase 6: Paper Draft and arXiv-Readiness Audit

Prepare a transparent methods/results draft, archive reproducible tables, audit
claims against `docs/CLAIMS_POLICY.md`, and keep candidate language unless
professional confirmation exists.
