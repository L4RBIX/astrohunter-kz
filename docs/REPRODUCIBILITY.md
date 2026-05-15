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
