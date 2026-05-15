# AstroHunter KZ

Controlled TESS search for exocomet-like asymmetric transit candidates around
debris-disk stars.

## Summary

AstroHunter KZ is an astrophysics and machine-learning research repository for
testing whether debris-disk / infrared-excess target selection improves the
yield and post-vetting purity of candidate asymmetric TESS transit events.

This repository identifies candidate events only. It does not claim confirmed
exocomet discovery.

## Long-Term Research Question

Does pre-filtering a TESS exocomet-transit search to IR-excess /
debris-disk-hosting stars produce a statistically significant increase in
candidate yield and/or post-vetting purity relative to a matched non-disk
control sample drawn from similar TESS sectors, magnitudes, and stellar
parameters?

## Phase 1 Current Status

Phase 1 is a Beta Pic / TIC 270577175 technical positive control. It verifies
that the repository can:

- download public TESS light curves without API keys,
- clean and normalize a light curve,
- plot the light curve,
- detect simple candidate dip-like features,
- compute simple asymmetry-related features,
- save reproducible figures and tables,
- run from both a notebook and a terminal script.

The strongest Phase 1 features may be instrumental/systematic and require
quality-flag and multi-sector validation.

## Phase 2 Current Status

Phase 2 builds preliminary development catalogs from real public debris-disk /
IR-excess sources. It creates a small target sample for pipeline development and
keeps control-sample matching explicit and incomplete until a real non-disk
candidate pool with TIC/Gaia/TESS metadata is available.

These target/control files are preliminary development samples, not final science
catalogs and not candidate-event results.

Phase 2B adds TESS metadata enrichment and a real-control matching path. It can
write `target_sample_enriched.csv` after metadata-only lightkurve/MAST searches.
Matched controls are generated only from a real non-disk control pool supplied by
the user or stored as `catalogs/control_pool.csv`.

Phase 2C adds a clean derived target table and safe TIC/Gaia crossmatch hooks.
The clean table keeps catalog values separate from crossmatch values and leaves
TIC/Gaia scientific fields empty unless real remote matches are found.

## Relation to Prior TESS Exocomet Work

AstroHunter KZ does not claim novelty from "AI discovers exocomets." Its
long-term novelty is a controlled matched-sample comparison between
debris-disk / IR-excess targets and matched non-disk controls.

Dobrycheva et al. 2024 used simulated asymmetric profiles, TSFresh features, and
Random Forest classification for a TESS exocomet search. Norazman et al. 2025
performed a large TESS exocomet search with Beta Pic recovery and occurrence-rate
analysis. AstroHunter KZ aims to build on these ideas by making the primary
scientific test a target/control rate-ratio comparison motivated by debris-disk
physics.

## Installation

```bash
git clone https://github.com/L4RBIX/astrohunter-kz.git
cd astrohunter-kz
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Run the Beta Pic Script

```bash
python scripts/run_beta_pic_control.py --max-lightcurves 1
```

Optional arguments:

```bash
python scripts/run_beta_pic_control.py \
  --target "TIC 270577175" \
  --max-lightcurves 1 \
  --output-dir results \
  --sigma-threshold 4.0 \
  --window-days 0.5
```

## Build Phase 2 Development Catalogs

```bash
python scripts/build_catalogs.py --dev --max-targets 20 --output-dir catalogs
```

This writes `catalogs/target_sample.csv` when public VizieR queries succeed.
`catalogs/control_sample.csv` and `catalogs/matched_pairs.csv` are written only
when enough real non-disk control metadata is available. The current Phase 2
builder does not fabricate controls.

For TESS availability enrichment:

```bash
python scripts/build_catalogs.py \
  --dev \
  --max-targets 20 \
  --output-dir catalogs \
  --enrich-tess \
  --max-enrich-targets 20
```

For the clean Phase 2C derived table:

```bash
python scripts/build_catalogs.py \
  --dev \
  --max-targets 20 \
  --output-dir catalogs \
  --enrich-tess \
  --max-enrich-targets 20 \
  --clean
```

Optional TIC/Gaia crossmatch hooks:

```bash
python scripts/build_catalogs.py \
  --dev \
  --max-targets 20 \
  --output-dir catalogs \
  --enrich-tess \
  --max-enrich-targets 20 \
  --crossmatch-tic \
  --crossmatch-gaia \
  --max-crossmatch-targets 20 \
  --clean
```

Verify catalog completeness:

```bash
python scripts/verify_catalogs.py --catalog catalogs/target_sample_enriched.csv
```

For matching controls from a real user-provided pool:

```bash
python scripts/build_control_pool_from_user_csv.py path/to/user_control_pool.csv \
  --output catalogs/control_pool.csv

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

## Run the Notebook

```bash
jupyter notebook notebooks/00_quickstart_beta_pic.ipynb
```

For Phase 2 catalog development:

```bash
jupyter notebook notebooks/01_catalog_build.ipynb
```

The older proof-of-concept notebook is preserved as:

```text
notebooks/01_beta_pic_positive_control.ipynb
```

## Run Tests

```bash
python -m pytest
```

## Data Policy

Raw downloaded light curves, cache files, and large catalog products should not
be committed. Public archive data should be re-downloadable through documented
scripts. Small Phase 1 example figures/tables may be kept for portfolio and
sanity-check purposes when they are clearly labeled as candidate-only outputs.

## Phase 3: Injection-Recovery and Improved Detector

Phase 3 builds a reproducible injection-recovery pipeline to measure how
sensitive the improved asymmetric-dip detector is to synthetic exocomet-like
signals injected into real TESS noise.

These results measure detector sensitivity on synthetic signals.  They do NOT
measure the purity of real candidates and do NOT confirm exocomet detections.

### Run injection-recovery (dev subset)

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

### Run real-data scan (dev subset)

```bash
python scripts/run_scan.py \
  --sample catalogs/target_sample_enriched.csv \
  --max-targets 5 \
  --max-lightcurves-per-star 1 \
  --output results/tables/detector_candidate_events_dev.csv
```

Phase 3 outputs: `results/tables/injection_recovery.csv`,
`results/tables/detector_candidate_events_dev.csv`,
`results/figures/recovery_vs_depth.png`,
`results/figures/recovery_heatmap_depth_duration.png`,
`results/figures/example_injected_dip.png`.

See [docs/PHASE3_INJECTION_RECOVERY.md](docs/PHASE3_INJECTION_RECOVERY.md) for
full documentation including the dip model, feature definitions, and
Phase 4 readiness notes.

## Phase 4: Interpretable ML Event Ranker

Phase 4 trains an XGBoost ranker on injection-recovery labels and applies it
to real-data candidate events to produce a prioritisation score for review.

**The ranker ranks events for review — it does not confirm exocomet detections.**
Injection-trained AUC/F1 metrics describe synthetic-signal sensitivity, not
real-data purity.

### Run the ML ranker

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

Phase 4 outputs: `results/tables/ml_training_features.csv`,
`results/tables/ml_evaluation_summary.csv`,
`results/tables/ranked_candidate_events_dev.csv`,
`results/figures/ml_feature_importance.png`,
`results/figures/ml_precision_recall_curve.png`,
`results/figures/ml_roc_curve.png`,
`results/figures/candidate_score_distribution.png`.

See [docs/PHASE4_ML_RANKER.md](docs/PHASE4_ML_RANKER.md) for full documentation.

## Phase 5: Candidate Vetting and Rate Statistics

Phase 5 applies automated vetting flags to ranked candidate events and computes
preliminary target/control candidate-yield rate statistics.

**Automated vetting is NOT scientific confirmation.**
**All candidates require manual review.**
**Dev-sample rate statistics are preliminary (N < 10 candidates).**
External catalog crossmatches (EB, VSX, SIMBAD) are not implemented.

### Run automated vetting

```bash
python scripts/run_vetting.py \
  --candidate-table results/tables/ranked_candidate_events_dev.csv \
  --output-vetted results/tables/vetted_candidate_events_dev.csv \
  --output-manual results/tables/manual_vetting_sheet.csv \
  --snr-threshold 5.0
```

### Run rate statistics

```bash
python scripts/run_stats.py \
  --vetted-candidates results/tables/vetted_candidate_events_dev.csv \
  --matched-pairs catalogs/matched_pairs.csv \
  --output results/tables/rate_ratio_summary.csv \
  --n-bootstrap 1000 \
  --random-seed 42
```

Phase 5 outputs: `results/tables/vetted_candidate_events_dev.csv`,
`results/tables/manual_vetting_sheet.csv`,
`results/tables/rate_ratio_summary.csv`,
`results/figures/rate_ratio_plot.png`,
`results/figures/candidate_score_vs_snr.png`,
`results/figures/vetting_flag_counts.png`.

See [docs/PHASE5_VETTING_STATISTICS.md](docs/PHASE5_VETTING_STATISTICS.md) for full documentation.

## Repository Structure

```text
src/astrohunter/
  lightcurves.py      TESS search, download, cleaning, normalization, cache
  asymmetry.py        Phase 1+3 dip detection and asymmetry feature extraction
  injection.py        Synthetic dip injection and injection-recovery framework
  features.py         Phase 4 feature engineering for the ML ranker
  ml.py               Phase 4 ML ranker: training, evaluation, scoring
  vetting.py          Phase 5 automated vetting flags
  stats.py            Phase 5 candidate yield rate statistics
  plotting.py         Matplotlib figure helpers (Phase 1–5)
  catalogs.py         VizieR catalog loading and target-sample normalization
  crossmatch.py       Coordinate matching and control-sample building
scripts/
  run_beta_pic_control.py
  run_injection_recovery.py   Phase 3 injection-recovery CLI
  run_scan.py                 Phase 3 real-data scan CLI
  train_event_ranker.py       Phase 4 ML ranker training and candidate scoring
  run_vetting.py              Phase 5 automated vetting CLI
  run_stats.py                Phase 5 rate statistics CLI
  build_catalogs.py
  build_control_pool_from_user_csv.py
  verify_catalogs.py
docs/
  CLAIMS_POLICY.md
  CONTROL_POOL_GUIDE.md
  DATA_SOURCES.md
  REPRODUCIBILITY.md
  PROJECT_SCOPE.md
  PHASE3_INJECTION_RECOVERY.md
  PHASE4_ML_RANKER.md
  PHASE5_VETTING_STATISTICS.md
cache/lightcurves/   Parquet cache (git-ignored)
results/figures/
results/tables/
tests/
```

## Next Phases

- Phase 6: full survey scan (all matched-pair targets + controls), manual vetting, and paper draft.
