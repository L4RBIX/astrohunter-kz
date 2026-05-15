# Phase 5B: Matched Target/Control Scan

Phase 5B runs the Phase 3 asymmetric-dip detector across all matched target and
control stars simultaneously, then reruns ML ranking (Phase 4), automated vetting
(Phase 5), and rate statistics (Phase 5) on the combined candidate table.

## Scientific Constraints

**These results are preliminary. Read this section before interpreting any output.**

- The matched scan is limited to stars with cached TESS light curves. On a first
  run without network access, only a small fraction of the 28 target + 28 control
  stars may have cached data.
- Candidates are NOT confirmed exocomets. They are candidate asymmetric-dip
  events that require multi-sector validation and manual vetting.
- Automated vetting applies heuristic flags (SNR, edge position, asymmetry shape).
  It is NOT scientific confirmation and does NOT perform external catalog
  crossmatches (EB, VSX, SIMBAD).
- ML scores rank candidates for human review. They are trained on synthetic
  injection-recovery labels and do NOT represent real-data purity or confirmation
  probability.
- Rate statistics are preliminary. With fewer than 10 total candidates or fewer
  than 5 stars per group scanned, Poisson rate ratios and bootstrap CIs are
  unstable. A rate ratio near 1 with a wide CI means the data are insufficient,
  not that target and control rates are equal.
- A rate ratio > 1 does NOT constitute evidence for exocomet excess. Full-survey
  scanning, manual vetting, and external catalog checks are required before any
  astrophysical interpretation.
- External catalog crossmatches (EB/VSX/SIMBAD) are NOT implemented in any
  automated step.
- This phase does NOT write a paper, does NOT claim discovery, and does NOT
  claim to have confirmed exocomets.

## What Phase 5B Produces

| File | Description |
|---|---|
| `results/tables/detector_candidate_events_matched_scan.csv` | Raw candidate events from both target and control stars, with `sample_role` and `pair_id` columns |
| `results/tables/detector_candidate_events_matched_scan.meta.json` | Scan metadata: actual TIC IDs scanned per role, failure counts, detector version |
| `results/tables/ranked_candidate_events_matched_scan.csv` | ML-ranked candidates (same table + `ml_score`, `final_candidate_score`) |
| `results/tables/ml_evaluation_summary_matched_scan.csv` | ML evaluation on synthetic injection data |
| `results/tables/vetted_candidate_events_matched_scan.csv` | Automated vetting flags applied |
| `results/tables/manual_vetting_sheet_matched_scan.csv` | Spreadsheet for human review |
| `results/tables/rate_ratio_summary_matched_scan.csv` | Preliminary target/control rate statistics |
| `results/figures/matched_scan_candidate_score_distribution.png` | Score histogram split by target/control role |
| `results/figures/rate_ratio_matched_scan_plot.png` | Rate ratio forest plot |
| `results/figures/candidate_score_vs_snr_matched_scan.png` | Score vs SNR scatter |
| `results/figures/vetting_flag_counts_matched_scan.png` | Vetting flag bar chart |
| `results/figures/target_control_counts_matched_scan.png` | Target vs control candidate counts |

## Exposure Estimation

The scan saves `detector_candidate_events_matched_scan.meta.json` with:

```json
{
  "target_tics_scanned": [...],
  "control_tics_scanned": [...],
  "n_target_success": 3,
  "n_control_success": 2,
  ...
}
```

`run_stats.py` auto-detects this file and uses the actual scanned star count
(e.g., 3 targets, 2 controls) as the exposure proxy rather than the total
matched-pairs catalog size (28). This prevents exposure inflation and keeps
rate estimates honest. The `exposure_source` column in the rate summary
will read `"scan_meta_actual"` when this file is used.

## `sample_role` Column

Every row in the candidate table carries a `sample_role` column (`"target"` or
`"control"`) assigned at scan time. This column drives all downstream role
assignment in statistics and plotting; it does not require TIC lookup fallbacks.

## How to Run

```bash
# Step 1: Scan matched target + control stars
python scripts/run_matched_scan.py \
  --matched-pairs catalogs/matched_pairs.csv \
  --target-catalog catalogs/target_sample_enriched.csv \
  --control-pool catalogs/control_pool.csv \
  --output results/tables/detector_candidate_events_matched_scan.csv \
  --max-pairs 28 \
  --max-lightcurves-per-star 1 \
  --sigma-threshold 4.0

# Step 2: ML ranking
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

# Step 4: Rate statistics
python scripts/run_stats.py \
  --vetted-candidates results/tables/vetted_candidate_events_matched_scan.csv \
  --matched-pairs catalogs/matched_pairs.csv \
  --output results/tables/rate_ratio_summary_matched_scan.csv \
  --n-bootstrap 1000 \
  --random-seed 42
```

## Failure Handling

- Stars that fail to download are logged as warnings; the scan continues.
- Partial results are saved incrementally so a crash mid-scan loses at most
  one star's worth of work.
- If all stars fail, an empty candidate table is saved cleanly.
- `--no-targets` and `--no-controls` flags allow scanning one group only.

## Interpreting the Rate Summary

The `rate_ratio_summary_matched_scan.csv` contains columns including:

| Column | Meaning |
|---|---|
| `target_rate` | Candidates per target star scanned |
| `control_rate` | Candidates per control star scanned |
| `rate_ratio` | `target_rate / control_rate` (undefined if control count = 0) |
| `rate_ratio_ci_lo/hi` | Poisson 95% CI (Garwood exact) |
| `bootstrap_rate_ratio_median` | Bootstrap median ratio |
| `bootstrap_ci_lo/hi` | Bootstrap 95% CI |
| `p_value_fisher` | Fisher exact p-value |
| `preliminary_warning` | Non-empty when N < 10 — statistics are unreliable |
| `exposure_source` | `"scan_meta_actual"` or `"matched_pairs_total"` |

A `preliminary_warning` in every row means the statistics must not be
interpreted as evidence for or against an exocomet excess.

## What Must Still Be Done Before Interpretation

1. Download and scan all 28 matched-pair targets and controls (requires network).
2. Manual vetting of every automated-pass candidate.
3. External catalog crossmatches (EB, VSX, SIMBAD) for contamination exclusion.
4. Multi-sector confirmation for top candidates.
5. Statistical power analysis: how many stars are needed for a meaningful rate
   ratio test?
6. Review by a qualified astrophysicist.
