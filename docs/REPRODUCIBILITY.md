# Reproducibility

## Troubleshooting: `download_failed: IndentationError` / lightkurve import failure

**Symptom:** The scan reports `download_failed: IndentationError: expected an
indented block (__init__.py, line 7)` (or `SyntaxError`) for every star that
does not have a cached light curve.  Cached downloads work; uncached ones fail.

**Root cause:** A file in the installed lightkurve package was corrupted.
In this repository's history the file was:

```
.venv/lib/python3.9/site-packages/lightkurve/prf/__init__.py
```

Line 7 contained a stray Cyrillic character (`ф`) at the start of the line
instead of a 4-space indent, making the `except` block syntactically invalid.
Python raises `IndentationError` when importing `lightkurve`, and because the
old code only caught `ImportError`, the `IndentationError` propagated out of
`download_lightcurve_for_tic` and appeared as `download_failed: ...` in the
pipeline scan status.

**Fix (applied 2026-05-16):**

1. Identify the broken file by running the diagnostic script:

   ```bash
   python scripts/debug_lightcurve_download.py --tic-id 368404959 --verbose
   ```

   The full traceback shows the exact path of the broken `__init__.py`.

2. Reinstall lightkurve to get a clean copy:

   ```bash
   pip install --force-reinstall lightkurve
   ```

   OR manually repair the file — remove the stray character and ensure the
   line has 4-space indentation.

3. Verify the import is clean:

   ```bash
   python -c "import lightkurve; print(lightkurve.__version__)"
   ```

**Code-level fix (also applied):** `download_lightcurve_for_tic` now catches
`Exception` (not just `ImportError`) when importing lightkurve, so any
future package corruption produces a clear `None` return with a logger.error
message instead of crashing the pipeline.  The new `_format_download_error`
helper logs the exception class, message, and full traceback at DEBUG level.

**Verify with diagnostic:**

```bash
python scripts/debug_lightcurve_download.py --tic-id <TIC_ID> --max-lightcurves 1 --verbose
```

This prints Python version, sys.path, lightkurve/astroquery versions, full
traceback on import failure, MAST search product counts, and download results.

---

Phase 1 is designed to run from a clean clone without private API keys.

```bash
git clone https://github.com/L4RBIX/astrohunter-kz.git
cd astrohunter-kz
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Run the tests:

```bash
python -m pytest
```

Run the beta Pic positive-control pipeline:

```bash
python scripts/run_beta_pic_control.py --max-lightcurves 1
```

Build the Phase 2 development target catalog:

```bash
python scripts/build_catalogs.py --dev --max-targets 20 --output-dir catalogs
```

Build the Phase 2B TESS-enriched target catalog:

```bash
python scripts/build_catalogs.py \
  --dev \
  --max-targets 20 \
  --output-dir catalogs \
  --enrich-tess \
  --max-enrich-targets 20
```

Build the Phase 2C clean derived target table:

```bash
python scripts/build_catalogs.py \
  --dev \
  --max-targets 20 \
  --output-dir catalogs \
  --enrich-tess \
  --max-enrich-targets 20 \
  --clean
```

Verify a catalog:

```bash
python scripts/verify_catalogs.py --catalog catalogs/target_sample_enriched.csv
```

Normalize a real user-provided control pool:

```bash
python scripts/build_control_pool_from_user_csv.py path/to/user_control_pool.csv \
  --output catalogs/control_pool.csv
```

Attempt matched controls only after a real non-disk control pool exists:

```bash
python scripts/build_catalogs.py \
  --dev \
  --max-targets 20 \
  --output-dir catalogs \
  --enrich-tess \
  --max-enrich-targets 20 \
  --build-controls \
  --control-ratio 3 \
  --control-pool-csv catalogs/control_pool.csv
```

Expected Phase 1 outputs:

- `results/figures/beta_pic_full_lightcurve.png`
- `results/figures/beta_pic_zoom_strongest_dip.png`
- `results/figures/beta_pic_lightcurve_with_detected_dips.png`
- `results/tables/beta_pic_candidate_dips.csv`

The script downloads public TESS light curves through `lightkurve`/MAST. Network
availability, MAST service state, and upstream archive product changes can affect
runtime and exact search-result ordering. Use `--max-lightcurves 1` for the
default lightweight positive-control run.

The generated candidate table contains candidate dip-like features only. It is
not a confirmed exocomet catalog.

The generated catalog files are preliminary development samples. Control files
are written only when a real non-disk control pool is available; missing control
outputs should not be interpreted as a completed matched-sample analysis.

## Phase 3: Injection-Recovery and Real-Data Scan

Run the test suite (all tests are network-free):

```bash
python -m pytest
```

Run injection-recovery on a dev subset (downloads real TESS data on first run;
uses cache on subsequent runs):

```bash
python scripts/run_injection_recovery.py \
  --sample catalogs/matched_pairs.csv \
  --target-catalog catalogs/target_sample_enriched.csv \
  --control-pool catalogs/control_pool.csv \
  --n-lightcurves 4 \
  --n-injections 40 \
  --max-lightcurves-per-star 1 \
  --random-seed 42
```

Run the Phase 3 real-data dip scanner on a dev subset:

```bash
python scripts/run_scan.py \
  --sample catalogs/target_sample_enriched.csv \
  --max-targets 5 \
  --max-lightcurves-per-star 1 \
  --output results/tables/detector_candidate_events_dev.csv \
  --sigma-threshold 4.0 \
  --window-days 1.0
```

Expected Phase 3 outputs:

- `results/tables/injection_recovery.csv`
- `results/tables/detector_candidate_events_dev.csv`
- `results/figures/recovery_vs_depth.png`
- `results/figures/recovery_heatmap_depth_duration.png`
- `results/figures/example_injected_dip.png`

The injection-recovery table records synthetic signal sensitivity, not real
candidate purity.  The real-data scan table contains candidate dip-like
features that require multi-sector validation and quality-flag vetting before
any astrophysical interpretation can be attempted.

Processed light curves are cached in `cache/lightcurves/` (excluded from git).
Delete a `.parquet` file and re-run to force a fresh download.

## Phase 4: ML Event Ranker

Train and evaluate the injection-recovery ML ranker, then rank real candidates:

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

Expected Phase 4 outputs:

- `results/tables/ml_training_features.csv`
- `results/tables/ml_evaluation_summary.csv`
- `results/tables/ranked_candidate_events_dev.csv`
- `results/figures/ml_feature_importance.png`
- `results/figures/ml_precision_recall_curve.png`
- `results/figures/ml_roc_curve.png`
- `results/figures/candidate_score_distribution.png`

The ML ranker is trained on *synthetic* injection-recovery labels.  Its AUC
and F1 scores describe sensitivity on synthetic signals, not real-data
candidate purity.  Ranked candidates require vetting before any astrophysical
interpretation.  See `docs/PHASE4_ML_RANKER.md` for full documentation.

## Phase 5: Candidate Vetting and Rate Statistics

Apply automated vetting flags to ranked candidates, then compute preliminary
rate statistics.

```bash
python scripts/run_vetting.py \
  --candidate-table results/tables/ranked_candidate_events_dev.csv \
  --output-vetted results/tables/vetted_candidate_events_dev.csv \
  --output-manual results/tables/manual_vetting_sheet.csv \
  --snr-threshold 5.0

python scripts/run_stats.py \
  --vetted-candidates results/tables/vetted_candidate_events_dev.csv \
  --matched-pairs catalogs/matched_pairs.csv \
  --output results/tables/rate_ratio_summary.csv \
  --n-bootstrap 1000 \
  --random-seed 42
```

Expected Phase 5 outputs:

- `results/tables/vetted_candidate_events_dev.csv`
- `results/tables/manual_vetting_sheet.csv`
- `results/tables/rate_ratio_summary.csv`
- `results/figures/rate_ratio_plot.png`
- `results/figures/candidate_score_vs_snr.png`
- `results/figures/vetting_flag_counts.png`

Automated vetting applies heuristic flags only.  It does NOT confirm
exocomet detections.  External catalog checks are handled in the later
VSX/SIMBAD/TESS-EB vetting step.  Dev-sample rate statistics are preliminary
and unstable with small candidate counts.  See
`docs/PHASE5_VETTING_STATISTICS.md`.

## Phase 5B: Matched Target/Control Scan

Run the asymmetric-dip detector across all matched target and control stars,
then rerun ML ranking, automated vetting, and rate statistics on the combined
candidate table.

```bash
# Step 1: Scan all matched pairs (uses cached light curves; warns on failures)
python scripts/run_matched_scan.py \
  --matched-pairs catalogs/matched_pairs.csv \
  --target-catalog catalogs/target_sample_enriched.csv \
  --control-pool catalogs/control_pool.csv \
  --output results/tables/detector_candidate_events_matched_scan.csv \
  --max-pairs 28 \
  --max-lightcurves-per-star 1 \
  --sigma-threshold 4.0

# Step 2: ML ranking (preserves sample_role column)
python scripts/rank_matched_scan.py \
  --injection-table results/tables/injection_recovery.csv \
  --candidate-table results/tables/detector_candidate_events_matched_scan.csv \
  --output-ranked results/tables/ranked_candidate_events_matched_scan.csv \
  --output-eval results/tables/ml_evaluation_summary_matched_scan.csv

# Step 3: Automated vetting
python scripts/run_vetting.py \
  --candidate-table results/tables/ranked_candidate_events_matched_scan.csv \
  --output-vetted results/tables/vetted_candidate_events_matched_scan.csv \
  --output-manual results/tables/manual_vetting_sheet_matched_scan.csv

# Step 4: Rate statistics (auto-detects .meta.json for accurate exposure)
python scripts/run_stats.py \
  --vetted-candidates results/tables/vetted_candidate_events_matched_scan.csv \
  --matched-pairs catalogs/matched_pairs.csv \
  --output results/tables/rate_ratio_summary_matched_scan.csv \
  --n-bootstrap 1000 \
  --random-seed 42
```

Expected Phase 5B outputs:

- `results/tables/detector_candidate_events_matched_scan.csv`
- `results/tables/detector_candidate_events_matched_scan.meta.json`
- `results/tables/ranked_candidate_events_matched_scan.csv`
- `results/tables/ml_evaluation_summary_matched_scan.csv`
- `results/tables/vetted_candidate_events_matched_scan.csv`
- `results/tables/manual_vetting_sheet_matched_scan.csv`
- `results/tables/rate_ratio_summary_matched_scan.csv`
- `results/figures/matched_scan_candidate_score_distribution.png`
- `results/figures/rate_ratio_matched_scan_plot.png`
- `results/figures/target_control_counts_matched_scan.png`

Phase 5B rate statistics are PRELIMINARY.  Coverage is limited to stars with
cached TESS light curves.  A rate ratio near 1 with a wide Poisson CI indicates
insufficient data, not equivalence.  All candidates require manual vetting and
external catalog crossmatches before any astrophysical interpretation.
See `docs/PHASE5B_MATCHED_SCAN.md` for full documentation.

## Phase 5C: External Catalog Crossmatch Vetting

Query VSX, SIMBAD, and the TESS Eclipsing Binary catalog for each candidate
host star to identify known false-positive or variable-star sources.  Requires
network access to VizieR and SIMBAD.  Failed queries are logged transparently
as `status = failed`; use `--skip-*` flags to run offline.

```bash
python scripts/run_external_vetting.py \
  --candidate-table results/tables/vetted_candidate_events_matched_scan.csv \
  --output results/tables/vetted_candidate_events_external_checked.csv \
  --summary-output results/tables/external_crossmatch_summary.csv \
  --radius-arcsec 10
```

Offline mode (skip all remote queries):

```bash
python scripts/run_external_vetting.py \
  --candidate-table results/tables/vetted_candidate_events_matched_scan.csv \
  --output results/tables/vetted_candidate_events_external_checked.csv \
  --summary-output results/tables/external_crossmatch_summary.csv \
  --skip-vsx --skip-simbad --skip-tess-eb
```

Expected Phase 5C outputs:

- `results/tables/vetted_candidate_events_external_checked.csv`
- `results/tables/external_crossmatch_summary.csv`
- `results/figures/external_catalog_flag_counts.png`

External catalog checks reduce false-positive contamination but do NOT confirm
exocomet detections.  A catalog match indicates possible contamination, not
definitive rejection.  Lack of a match does NOT prove astrophysical validity.
Failed queries (`status = failed`) must be re-run with network access before
interpreting "no match" as meaningful.  All candidates require manual review.
See `docs/PHASE5C_EXTERNAL_VETTING.md` for full documentation.

## Phase 5D: Full Matched Survey Pipeline

Orchestrate the complete scan → rank → vet → external-check → stats pipeline
in one command.  Requires network access for TESS downloads and catalog queries.
Use `--limit-pairs` and `--skip-*` flags for offline or smoke-test runs.

```bash
# Full pipeline (all phases, requires network)
python scripts/run_full_matched_pipeline.py \
  --matched-pairs catalogs/matched_pairs.csv \
  --target-catalog catalogs/target_sample_enriched.csv \
  --control-pool catalogs/control_pool.csv \
  --injection-table results/tables/injection_recovery.csv \
  --output-prefix full_matched \
  --max-lightcurves-per-star 1 \
  --sigma-threshold 4.0

# Resume an interrupted run (skips successfully-scanned stars)
python scripts/run_full_matched_pipeline.py \
  --matched-pairs catalogs/matched_pairs.csv \
  --target-catalog catalogs/target_sample_enriched.csv \
  --control-pool catalogs/control_pool.csv \
  --injection-table results/tables/injection_recovery.csv \
  --output-prefix full_matched \
  --resume

# Offline smoke test (2 pairs, no remote catalog queries)
python scripts/run_full_matched_pipeline.py \
  --matched-pairs catalogs/matched_pairs.csv \
  --target-catalog catalogs/target_sample_enriched.csv \
  --control-pool catalogs/control_pool.csv \
  --injection-table results/tables/injection_recovery.csv \
  --output-prefix smoke_test \
  --limit-pairs 2 --skip-vsx --skip-simbad --skip-tess-eb
```

Expected Phase 5D outputs (with prefix `full_matched`):

- `results/tables/full_matched_detector_candidates.csv`
- `results/tables/full_matched_detector_candidates.meta.json`
- `results/tables/full_matched_scan_status.csv`
- `results/tables/full_matched_ranked_candidates.csv`
- `results/tables/full_matched_ml_eval.csv`
- `results/tables/full_matched_vetted_candidates.csv`
- `results/tables/full_matched_manual_vetting_sheet.csv`
- `results/tables/full_matched_external_checked_candidates.csv`
- `results/tables/full_matched_external_crossmatch_summary.csv`
- `results/tables/full_matched_rate_ratio_summary.csv`
- `results/tables/full_matched_run_summary.csv`

Phase 5D results are PRELIMINARY.  All candidates require manual vetting and
multi-sector confirmation.  Scan failures must be re-run with network access.
External catalog checks reduce false positives but do NOT confirm exocomet
detections.  Rate statistics have no scientific meaning until full-survey
coverage and manual vetting are complete.
See `docs/PHASE5D_FULL_MATCHED_RUN.md` for full documentation.

## Phase 5E: Candidate Consolidation and Manual Review Package

Build star-level summaries, identify overtriggered stars, and produce a
prioritised manual review table from the Phase 5D externally-checked candidates.

```bash
python scripts/consolidate_candidates.py \
  --candidate-table results/tables/full_matched_external_checked_candidates.csv \
  --scan-status results/tables/full_matched_scan_status.csv \
  --output-star-summary results/tables/full_matched_star_level_summary.csv \
  --output-top-events results/tables/full_matched_top_event_per_star.csv \
  --output-review-priority results/tables/full_matched_manual_review_priority.csv \
  --output-overtriggered results/tables/full_matched_overtriggered_stars.csv \
  --max-events-per-star 3 \
  --overtrigger-threshold 5
```

Expected Phase 5E outputs:

- `results/tables/full_matched_star_level_summary.csv`
- `results/tables/full_matched_top_event_per_star.csv`
- `results/tables/full_matched_manual_review_priority.csv`
- `results/tables/full_matched_overtriggered_stars.csv`
- `results/figures/full_matched_candidates_per_star.png`
- `results/figures/full_matched_top_scores_by_star.png`
- `results/figures/full_matched_pass_candidates_by_role.png`

Consolidation is NOT confirmation of exocomet detections.  Priority labels
are heuristic — all candidates require manual inspection.  Pass candidates
on overtriggered stars are particularly suspect.
See `docs/PHASE5E_CANDIDATE_CONSOLIDATION.md` for full documentation.

## Phase 5F: Manual Review Gallery

Build the visual inspection package from the Phase 5E consolidated tables.

```bash
python scripts/build_manual_review_gallery.py \
  --candidate-table results/tables/full_matched_external_checked_candidates.csv \
  --priority-table results/tables/full_matched_manual_review_priority.csv \
  --star-summary results/tables/full_matched_star_level_summary.csv \
  --overtriggered results/tables/full_matched_overtriggered_stars.csv \
  --output-dir results/candidates/manual_review_gallery \
  --disposition-output results/tables/full_matched_manual_review_disposition_template.csv \
  --inspection-targets-output results/tables/full_matched_inspection_targets.csv \
  --max-events-per-star 5 \
  --window-days 1.0
```

Expected Phase 5F outputs:

- `results/tables/full_matched_inspection_targets.csv`
- `results/tables/full_matched_manual_review_disposition_template.csv`
- `results/figures/manual_review_priority_overview.png`
- `results/candidates/manual_review_gallery/tic_{tic_id}/` (one per inspection TIC)
  - `tic_{tic_id}_full_lc_with_events.png`
  - `event_{i:02d}_BTJD{time:.3f}.png`
  - `events_summary.csv`
  - `metadata.json`

Visual review does NOT confirm exocomet detections.  Disposition labels
are preliminary.  TIC 444335503 must be treated as likely overtriggered until
its light curve has been inspected for periodic variability.
See `docs/PHASE5F_MANUAL_REVIEW_GALLERY.md` for the disposition label guide
and interpretation notes.

## Phase 6A: Science-Fair / Portfolio Communication Package

Phase 6A is documentation only — no pipeline scripts to run.

The communication package was created by reading the actual pipeline outputs and
documenting them honestly. All numbers in Phase 6A documents come from the real
pipeline result tables.

To verify that all Phase 6A documents are present:

```bash
ls docs/SCIENCE_FAIR_REPORT.md \
   docs/PROJECT_PRESENTATION_SCRIPT.md \
   docs/POSTER_OUTLINE.md \
   docs/SOCIAL_MEDIA_POSTS.md \
   docs/GITHUB_PORTFOLIO_SUMMARY.md \
   docs/PHASE6A_COMMUNICATION_PACKAGE.md \
   results/tables/communication_key_messages.csv
```

All seven files should exist and be non-empty.

To verify the claims audit CSV:

```bash
python -c "
import csv
with open('results/tables/communication_key_messages.csv') as f:
    rows = list(csv.DictReader(f))
print(f'{len(rows)} message scenarios documented')
print('Columns:', list(rows[0].keys()) if rows else 'empty')
"
```

Expected output: 10 message scenarios, columns: message_type, approved_message,
forbidden_overclaim, reason.

Phase 6A adds no new source code. The test suite is unaffected.

```bash
python -m pytest tests/ -q
# Expected: 453 passed (all tests pass; Phase 6A adds no new code)
```

Key result numbers communicated in all Phase 6A documents:
- 28 target stars, 28 control stars
- 156 raw events (57 target, 99 control)
- Rate ratio 0.58
- 3 automated pass events (all on TIC 444335503, control)
- 0 manual keep_candidate
- 0 surviving candidates
