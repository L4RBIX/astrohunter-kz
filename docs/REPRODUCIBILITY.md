# Reproducibility

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
exocomet detections.  External catalog crossmatches (EB/VSX/SIMBAD) are
not implemented.  Dev-sample rate statistics are preliminary and unstable
with N < 10 candidates.  See `docs/PHASE5_VETTING_STATISTICS.md`.

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
