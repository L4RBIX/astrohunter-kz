# Phase 5D: Full Matched Survey Execution Support

Phase 5D adds a single-command orchestrator that chains the complete
scan → rank → vet → external-check → stats pipeline across all 28 matched
target and control stars, with resumable execution, per-star status
tracking, and a pipeline-level run summary.

## Scientific Constraints

**Read this section before interpreting any Phase 5D output.**

- All detected events are **candidates only** — not confirmed exocomets.
- Automated detection, ML ranking, and automated vetting are **NOT**
  scientific confirmation.
- External catalog checks (VSX / SIMBAD / TESS-EB) **reduce**
  false-positive contamination but do **NOT** confirm or disprove
  exocomet detections.
- Rate statistics from the full matched run are **preliminary** until
  manual vetting, multi-sector confirmation, and full-survey coverage
  are complete.
- **Scan failures must be reported transparently.** Stars that fail to
  download appear in the per-star scan status table with
  `success = False` and a `failure_reason` string.  Failure to download
  a star does **not** mean that star has no candidates.
- The `rate_ratio` in the run summary is a technical readiness metric,
  not a scientific discovery claim.
- **Manual inspection of every candidate remains mandatory.**

## How It Works

The orchestrator calls the Phase 5B scan, Phase 4 ML ranking, Phase 5
automated vetting, Phase 5C external crossmatching, and Phase 5 rate
statistics in sequence.  Each phase writes its output to disk.  If a
phase fails, a warning is logged and downstream phases continue using
the best available input.

### Resume Logic

When `--resume` is set, the orchestrator loads
`{prefix}_scan_status.csv` from a previous run, finds all TIC IDs where
`success = True`, and skips those stars in the scan phase.  Partially
downloaded candidates are also loaded from the existing scan output and
merged with newly detected candidates.

### Per-Star Scan Status

After each star is scanned, a row is appended to the scan status table:

| Column | Description |
|---|---|
| `tic_id` | TESS Input Catalog ID |
| `sample_role` | `target` or `control` |
| `matched_pair_id` | Row index in matched_pairs.csv |
| `star_name` | Resolved star name or `TIC {tic_id}` |
| `attempted` | Always `True` (scan was attempted) |
| `success` | `True` if scan returned data or no-candidates; `False` on error |
| `failure_reason` | Error string (e.g., `download_failed: timeout`); empty on success |
| `n_candidates` | Number of asymmetric-dip candidates detected |
| `cache_used` | `True` if a `.parquet` cache file existed before the scan |
| `scan_timestamp` | ISO-8601 UTC timestamp of when this star was scanned |

`success = True` includes both `ok:N_candidates` and `no_candidates`
results — a star with no candidates above threshold is a valid,
successful scan.  `success = False` means the scan produced no usable
data (download error, too few points, etc.) and must be re-run.

### Run Summary

After all phases complete, `{prefix}_run_summary.csv` is written with
one row summarising the entire pipeline execution.

## Output Files

All outputs use the `--output-prefix` value (default: `full_matched`):

| File | Description |
|---|---|
| `{prefix}_detector_candidates.csv` | Raw asymmetric-dip candidates from the scan |
| `{prefix}_detector_candidates.meta.json` | Scan metadata for exposure estimation |
| `{prefix}_scan_status.csv` | Per-star scan status table |
| `{prefix}_ranked_candidates.csv` | ML-ranked candidate table |
| `{prefix}_ml_eval.csv` | ML evaluation summary (synthetic-data metrics) |
| `{prefix}_vetted_candidates.csv` | Automated-vetting output |
| `{prefix}_manual_vetting_sheet.csv` | Manual review worksheet |
| `{prefix}_external_checked_candidates.csv` | External crossmatch output |
| `{prefix}_external_crossmatch_summary.csv` | Per-catalog match counts |
| `{prefix}_rate_ratio_summary.csv` | Target/control rate statistics |
| `{prefix}_run_summary.csv` | Pipeline-level run summary |

## How to Run

### Full pipeline (all phases, online)

```bash
python scripts/run_full_matched_pipeline.py \
  --matched-pairs catalogs/matched_pairs.csv \
  --target-catalog catalogs/target_sample_enriched.csv \
  --control-pool catalogs/control_pool.csv \
  --injection-table results/tables/injection_recovery.csv \
  --output-prefix full_matched \
  --max-lightcurves-per-star 1 \
  --sigma-threshold 4.0 \
  --snr-threshold 5.0
```

### Resume an interrupted run

```bash
python scripts/run_full_matched_pipeline.py \
  --matched-pairs catalogs/matched_pairs.csv \
  --target-catalog catalogs/target_sample_enriched.csv \
  --control-pool catalogs/control_pool.csv \
  --injection-table results/tables/injection_recovery.csv \
  --output-prefix full_matched \
  --resume
```

### Skip external catalog queries (offline mode)

```bash
python scripts/run_full_matched_pipeline.py \
  --matched-pairs catalogs/matched_pairs.csv \
  --target-catalog catalogs/target_sample_enriched.csv \
  --control-pool catalogs/control_pool.csv \
  --injection-table results/tables/injection_recovery.csv \
  --output-prefix full_matched \
  --skip-vsx --skip-simbad --skip-tess-eb
```

### Smoke test with 2 pairs only

```bash
python scripts/run_full_matched_pipeline.py \
  --matched-pairs catalogs/matched_pairs.csv \
  --target-catalog catalogs/target_sample_enriched.csv \
  --control-pool catalogs/control_pool.csv \
  --injection-table results/tables/injection_recovery.csv \
  --output-prefix smoke_test \
  --limit-pairs 2 \
  --skip-vsx --skip-simbad --skip-tess-eb
```

### Skip individual phases (to rerun specific steps)

```bash
# Re-run only external vetting and stats on an existing vetted table
python scripts/run_full_matched_pipeline.py \
  --matched-pairs catalogs/matched_pairs.csv \
  --target-catalog catalogs/target_sample_enriched.csv \
  --control-pool catalogs/control_pool.csv \
  --injection-table results/tables/injection_recovery.csv \
  --output-prefix full_matched \
  --skip-scan --skip-ranking --skip-vetting
```

## Arguments

| Argument | Default | Description |
|---|---|---|
| `--matched-pairs` | `catalogs/matched_pairs.csv` | Matched target/control pairs |
| `--target-catalog` | `catalogs/target_sample_enriched.csv` | Target catalog with coordinates |
| `--control-pool` | `catalogs/control_pool.csv` | Control pool with coordinates |
| `--injection-table` | `results/tables/injection_recovery.csv` | Injection-recovery table for ML |
| `--output-prefix` | `full_matched` | Prefix for all output files |
| `--max-lightcurves-per-star` | `1` | Max TESS sectors per star |
| `--sigma-threshold` | `4.0` | Dip detection σ threshold |
| `--window-days` | `1.0` | Feature extraction window (days) |
| `--snr-threshold` | `5.0` | SNR threshold for vetting flag |
| `--external-radius-arcsec` | `10.0` | Position match radius for VSX/SIMBAD |
| `--random-seed` | `42` | Random seed for ML ranking and stats |
| `--resume` | off | Skip stars with `success = True` in scan status |
| `--skip-scan` | off | Skip scan; load existing scan output |
| `--skip-ranking` | off | Skip ML ranking |
| `--skip-vetting` | off | Skip automated vetting |
| `--skip-external` | off | Skip external catalog crossmatch |
| `--skip-stats` | off | Skip rate statistics |
| `--skip-vsx` | off | Skip VSX queries |
| `--skip-simbad` | off | Skip SIMBAD queries |
| `--skip-tess-eb` | off | Skip TESS-EB catalog queries |
| `--limit-pairs` | none | Process only the first N matched pairs |

## Prerequisites

Before running the full pipeline, ensure the following outputs exist:

1. `catalogs/matched_pairs.csv` — from Phase 2E (`build_catalogs.py --build-controls`)
2. `catalogs/target_sample_enriched.csv` — from Phase 2B
3. `catalogs/control_pool.csv` — from Phase 2E
4. `results/tables/injection_recovery.csv` — from Phase 3 (`run_injection_recovery.py`)

The injection-recovery table is needed for ML ranking.  If it does not
exist, the ranking phase is skipped with a warning and downstream phases
proceed without ML scores.

## What Still Must Be Done Before Any Astrophysical Interpretation

1. Achieve full-survey scan coverage (all 28 target + 28 control stars
   with cached TESS data).
2. Re-run any failed queries (scan failures, external-catalog failures)
   with stable network access.
3. Manual inspection of every candidate light curve.
4. Multi-sector confirmation for any candidate that passes automated vetting.
5. Cross-check against additional catalogs (Gaia variability, ASAS-SN, ZTF).
6. Statistical power analysis: is the sample large enough for rate-ratio claims?
7. Review by a qualified astrophysicist.
8. Audit all output language against `docs/CLAIMS_POLICY.md`.

The full matched pipeline is a technical execution tool, not a
scientific analysis.  Its outputs require all of the above steps before
any conclusions can be drawn.
