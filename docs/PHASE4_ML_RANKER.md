# Phase 4: Interpretable ML Event Ranker

## Purpose

Phase 4 trains a simple, interpretable event-prioritisation ranker on
injection-recovery labels and applies it to real-data candidate events from
the Phase 3 dev scan.

**The ranker ranks events for human review.  It does not confirm exocomets.**

---

## Scientific Constraints

| Statement | Status |
|-----------|--------|
| ML ranker trained on synthetic injection labels | True |
| ML scores are confirmation probabilities | **False — prohibited** |
| Injection-trained AUC = real-data purity | **False — prohibited** |
| Real candidates confirmed by ranking score | **False — requires vetting** |
| Ranking aids human review prioritisation | True |

---

## Model

- **Primary model**: XGBoost (`XGBClassifier`, 60 estimators, max_depth=3)
- **Fallback model**: sklearn `GradientBoostingClassifier` if XGBoost is unavailable
- **Training label**: `recovered` (1 = synthetic dip was found by detector, 0 = missed)
- **Train/test split**: stratified, fixed seed (default 75/25)

---

## Feature Design

### Features Used for ML Training

Derived from `results/tables/injection_recovery.csv`:

| Column | Source in injection table | Notes |
|--------|--------------------------|-------|
| `depth_ppm` | `recovered_depth_ppm` | NaN for missed injections |
| `local_snr` | `recovered_local_snr` | NaN for missed injections |
| `noise_mad` | `noise_mad` | Always available |

Other REQUIRED_FEATURE_COLUMNS are all-NaN in the injection table (not stored
in Phase 3) and are zero-filled during imputation.  They do not contribute to
the injection-trained ML model but are used in the rule-based quality score.

### Features Excluded from Model (Ground-Truth Leakage)

The following columns are **never** used as model features:

- `injected_depth_ppm`
- `injected_ingress_hours`
- `injected_egress_hours`
- `injected_asymmetry_ratio`
- `injected_event_time_btjd`

These values are known for injected signals but unavailable for real events.

### Features Used for Candidate Scoring

When applied to real-data candidates, the full Phase 3 feature set is available:

`depth_ppm`, `local_snr`, `noise_mad`, `duration_hours`, `fwhm_hours`,
`ingress_duration_hours`, `egress_duration_hours`, `egress_ingress_ratio`,
`skewness`, `kurtosis`, `delta_chi2_asym`, `n_points_window`,
`edge_event`, `single_point_like`

---

## Score Definitions

### `ml_score`
Probability from the injection-trained ranker (0–1).  Reflects how similar
an event's detected features are to *recovered* synthetic injections.

### `quality_score`
Rule-based heuristic (0–1) computed from local_snr, egress_ingress_ratio, and
delta_chi2_asym.  Penalised for edge_event and single_point_like.

### `final_candidate_score`
Composite ranking score (0–1):

```
final_candidate_score = (
    0.50 × ml_score
  + 0.40 × quality_score
  + 0.10 × min(local_snr / 10, 1)
  − 0.15 × edge_event
  − 0.15 × single_point_like
).clip(0, 1)
```

Events are sorted by `final_candidate_score` descending for review.

**This score is a prioritisation aid, not a confirmation probability.**

---

## Output Files

| File | Description |
|------|-------------|
| `results/tables/ml_training_features.csv` | Training feature table with label |
| `results/tables/ml_evaluation_summary.csv` | Evaluation metrics on test injections |
| `results/tables/ranked_candidate_events_dev.csv` | Real candidates ranked by final score |
| `results/figures/ml_feature_importance.png` | Feature importance from trained ranker |
| `results/figures/ml_precision_recall_curve.png` | PR curve on injection test set |
| `results/figures/ml_roc_curve.png` | ROC curve on injection test set |
| `results/figures/candidate_score_distribution.png` | Score histogram for candidates |

---

## Running Phase 4

```bash
python scripts/train_event_ranker.py \
  --injection-table results/tables/injection_recovery.csv \
  --candidate-table results/tables/detector_candidate_events_dev.csv \
  --output-ranked results/tables/ranked_candidate_events_dev.csv \
  --output-training results/tables/ml_training_features.csv \
  --output-eval results/tables/ml_evaluation_summary.csv \
  --random-seed 42 \
  --test-size 0.25
```

---

## Interpreting Results

### Evaluation metrics
The AUC, F1, and precision/recall values are measured on held-out
*synthetic injection* rows.  They describe how well the detector and ranker
work together on injected signals of known amplitude.

**They do NOT measure how many real candidates are genuine astrophysical events.**

### Ranked candidates
The ranked candidate table orders real-data events by `final_candidate_score`.
High-scoring events should be inspected first.  Inspecting means:

1. Visual inspection of the TESS light curve
2. Quality-flag check (DQMASK)
3. Multi-sector consistency check
4. Stellar variability context (spectral type, rotation)
5. Background contamination check
6. Comparison with known eclipsing binaries and periodic variables

Only after vetting should any astrophysical interpretation be attempted.

### Small sample caveats
The Phase 3 dev injection table has ~40 rows.  With 25% test size, this gives
~10 test rows.  All evaluation metrics must be interpreted with caution given
this small test set.  Phase 5 full-sample analysis will provide more robust
statistics.

---

## Phase 5 Readiness

Phase 4 outputs are designed to feed Phase 5:

- `ranked_candidate_events_dev.csv` provides a prioritised review queue
- `ml_training_features.csv` documents the feature-label mapping for audit
- The `final_candidate_score` column can be used as a pre-filter before rate-ratio statistics

Phase 5 should:
1. Apply the detector and ranker to the full target + control samples
2. Apply the vetting cascade
3. Compute yield rates (candidates per star) for targets vs. controls
4. Perform binomial or bootstrap comparison of yield ratios
