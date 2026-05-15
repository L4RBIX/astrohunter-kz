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

## Phase 5B: Matched Target/Control Scan (complete)

Run the Phase 3 detector across all 28 matched target stars and 28 matched
control stars simultaneously.  Rerun ML ranking, automated vetting, and rate
statistics on the combined candidate table to produce honest target/control
candidate-yield statistics.

Constraints:
- Matched scan is still preliminary — limited to stars with cached TESS data.
- Candidates are NOT confirmed exocomets.
- Automated vetting is NOT scientific confirmation.
- Rate statistics are only as good as scan coverage: with < 10 candidates or
  < 5 stars per group scanned, rate ratios and bootstrap CIs are unstable.
- External catalog crossmatches (EB, VSX, SIMBAD) are NOT implemented.
- Full paper still requires manual vetting and external catalog checks.
- A rate ratio > 1 is NOT evidence for an exocomet excess without the above.

Key additions:
- `sample_role` column ('target'/'control') attached at scan time.
- Scan metadata JSON (`*.meta.json`) stores actual scanned TIC counts for
  accurate Poisson exposure estimation (`exposure_source = "scan_meta_actual"`).
- Zero-control-candidate handling and bootstrap NaN propagation are safe.

Outputs: detector_candidate_events_matched_scan.csv + .meta.json,
ranked_candidate_events_matched_scan.csv, vetted_candidate_events_matched_scan.csv,
rate_ratio_summary_matched_scan.csv, and five diagnostic figures.

See [docs/PHASE5B_MATCHED_SCAN.md](PHASE5B_MATCHED_SCAN.md) for full documentation.

## Phase 5C: External Catalog Crossmatch Vetting (complete)

Query VSX, SIMBAD, and the TESS Eclipsing Binary catalog for each candidate
host star to identify known false-positive contamination sources and integrate
the findings into the automated vetting status.

Constraints:
- External catalog checks are NOT scientific confirmation of exocomet absence
  or presence.
- A catalog match (VSX, SIMBAD, TESS-EB) indicates possible contamination only.
- Lack of a catalog match does NOT prove astrophysical validity.
- Failed or not-attempted queries must be reported transparently.
- Manual inspection remains mandatory for every candidate.

Dev-run results (5 matched-scan candidates, radius = 10″):
- VSX: 1 match — TIC 115598451 (control) matched to NSV 15119 (new suspected
  variable). Flagged `known_variable_match`. Automated vetting status demoted to
  `flagged`. This is a precautionary flag, not a definitive rejection.
- SIMBAD: 5 matches — four target candidates typed PM\* or generic star (no
  contamination concern); TIC 115598451 typed `**` (double star, not a concern).
- TESS-EB: 0 matches for any candidate in the current dev run.
- All results are preliminary; full-survey scanning required for interpretation.

Key additions:
- `external_false_positive_flag` column classifies the combined catalog result.
- `flag_external_catalog_match = True` for candidates with concern-level flags.
- External concern flags demote `automated_vetting_status` from `pass` →
  `flagged`; never promote `flagged` → `pass`.
- SIMBAD column names are handled robustly across astroquery versions
  (0.4.11 TAP: lowercase `main_id`, `otype`; older: uppercase).

Outputs: vetted_candidate_events_external_checked.csv,
external_crossmatch_summary.csv, external_catalog_flag_counts.png.

See [docs/PHASE5C_EXTERNAL_VETTING.md](PHASE5C_EXTERNAL_VETTING.md) for full
documentation.

## Phase 5D: Full Matched Survey Execution Support (complete)

Orchestrate the complete scan → rank → vet → external-check → stats
pipeline across all 28 matched target and control stars in a single
command.  Supports resumable execution via `--resume`, per-star scan
status tracking, and a pipeline-level run summary.

Constraints:
- All detected events are candidates only — not confirmed exocomets.
- Automated detection, ML ranking, and automated vetting are NOT
  scientific confirmation.
- External catalog checks reduce false-positive contamination but do
  NOT confirm or disprove exocomet detections.
- Scan failures must be reported transparently (`success = False` in
  the scan status table).  A failed download does not mean no candidates.
- Rate statistics from the full matched run are preliminary until manual
  vetting and full-survey coverage are complete.
- Manual inspection of every candidate remains mandatory.

Key additions:
- `{prefix}_scan_status.csv`: per-star scan status with `tic_id`,
  `sample_role`, `success`, `failure_reason`, `n_candidates`, `cache_used`.
- `{prefix}_run_summary.csv`: pipeline-level summary with phase list,
  star counts, candidate counts, and rate ratio (if stats ran).
- Resume logic: stars with `success = True` in an existing scan status
  table are skipped when `--resume` is set.
- `--limit-pairs N`: process only the first N matched pairs (smoke testing).
- `--skip-*` flags for each phase: scan, ranking, vetting, external, stats.

Outputs: `{prefix}_detector_candidates.csv`, `{prefix}_scan_status.csv`,
`{prefix}_ranked_candidates.csv`, `{prefix}_vetted_candidates.csv`,
`{prefix}_external_checked_candidates.csv`, `{prefix}_rate_ratio_summary.csv`,
`{prefix}_run_summary.csv`.

See [docs/PHASE5D_FULL_MATCHED_RUN.md](PHASE5D_FULL_MATCHED_RUN.md) for
full documentation.

## Phase 5E: Candidate Consolidation and Manual Review Package (complete)

Convert the event-level Phase 5D output into star-level summaries, identify
overtriggered stars, select top events per TIC, and build a prioritised manual
review table.

Constraints:
- Consolidation is NOT confirmation of exocomet detections.
- Repeated events on one TIC most likely reflect stellar variability,
  systematics, or contamination — not multiple exocomet transits.
- Stars flagged as overtriggered_review require special scrutiny before any
  individual event is accepted as a candidate.
- Priority labels (high/medium/low/overtriggered_review) are heuristic
  classifiers, not scientific verdicts.
- Pass candidates on overtriggered stars are particularly suspect.
- All candidates require manual inspection regardless of priority.

Key additions:
- `summarize_candidates_by_star()`: one-row-per-TIC aggregation with
  n_events, n_pass, max/median SNR, max score, external flag counts,
  and recommended_review_priority.
- `identify_overtriggered_stars()`: TICs with ≥ overtrigger_threshold events.
- `select_top_event_per_star()`: single highest-scoring event per TIC
  for quick inspection.
- `build_manual_review_priority_table()`: top N events per TIC with priority.
- Three diagnostic figures: candidates-per-star bar chart, score scatter,
  pass-candidate grouped bar chart.

Phase 5E run results (2026-05-16):
- 156 events across 36 TICs (15 target, 21 control).
- 13 overtriggered TICs (≥ 5 events); top: TIC 444335503 (control, 20 events).
- 0 high, 2 medium, 21 low, 13 overtriggered_review priority TICs.
- 3 pass-vetting candidates — all on TIC 444335503 (control, overtriggered).
- No pass candidates on any target star in this survey run.

Outputs: full_matched_star_level_summary.csv, full_matched_top_event_per_star.csv,
full_matched_manual_review_priority.csv, full_matched_overtriggered_stars.csv,
and three diagnostic figures.

See [docs/PHASE5E_CANDIDATE_CONSOLIDATION.md](PHASE5E_CANDIDATE_CONSOLIDATION.md) for
full documentation.

## Phase 6: Paper Draft and arXiv-Readiness Audit

Prepare a transparent methods/results draft, archive reproducible tables, audit
claims against `docs/CLAIMS_POLICY.md`, and keep candidate language unless
professional confirmation exists.
