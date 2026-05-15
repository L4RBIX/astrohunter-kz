# Phase 5: Candidate Vetting and Rate Statistics

## Purpose

Phase 5 applies a transparent, reproducible automated vetting cascade to the
ranked candidate event table from Phase 4, and computes preliminary
target/control candidate-yield rate statistics.

**Phase 5 does NOT confirm exocomet detections.**
**Automated vetting is NOT scientific confirmation.**
**All candidates require manual review and multi-sector validation.**
**Rate statistics on the dev sample are preliminary and unstable.**

---

## Scientific Constraints

| Claim | Status |
|---|---|
| "Automated vetting confirms an exocomet" | **Forbidden** |
| "Rate ratio proves debris-disk enhancement" | **Forbidden** |
| External catalog crossmatches performed | **NOT implemented** — placeholder only |
| Manual review completed | **NOT done here** — worksheet output only |
| Dev-sample rate ratio is scientifically significant | **NOT claimed** |
| Candidates are confirmed exocomets | **NOT claimed** |

---

## What Automated Vetting Does

Automated vetting applies transparent heuristic flag criteria to each
candidate event.  A flagged event is NOT rejected — it is labelled for
priority manual attention.  A passing event is NOT confirmed — it is simply
a candidate that did not trigger any automated flag.

### Automated Flag Criteria

| Flag | Condition | Threshold |
|---|---|---|
| `flag_low_snr` | local_snr < SNR threshold | default 5.0σ |
| `flag_edge_event` | event within 0.5 days of LC start/end | — |
| `flag_single_point_like` | single-point morphology detected | — |
| `flag_likely_flare_shape` | skewness > 0 AND egress_ingress_ratio < 1.0 | heuristic |
| `flag_low_delta_chi2` | Δχ²(asym − sym) < threshold | default 5.0 |
| `flag_poor_asymmetry_fit` | ratio ≈ 1.0 or NaN (symmetric or failed fit) | — |

A candidate with any flag set gets `automated_vetting_status = "flagged"`.
A candidate with no flags gets `automated_vetting_status = "pass"`.
All candidates get `needs_manual_review = True` if any flag is set.

### External Crossmatch Placeholders

External catalog checks (eclipsing binary catalogs, VSX, SIMBAD) are
**not implemented** in Phase 5.  Placeholder columns are added to the
output table:

- `eb_catalog_check_status = not_attempted`
- `vsx_check_status = not_attempted`
- `simbad_check_status = not_attempted`

These checks are planned for Phase 6 / post-vetting cascade.

---

## Rate Statistics

### What Is Computed

Rate statistics compare the candidate yield rate between the target sample
(debris-disk / IR-excess stars) and the matched control sample (non-disk
stars of similar magnitude and stellar parameters).

- **Target rate** = target_candidates / target_exposure (star-count proxy)
- **Control rate** = control_candidates / control_exposure
- **Rate ratio** = target_rate / control_rate
- **Exposure proxy** = number of unique TIC IDs in each role from matched_pairs.csv

Exposure is a star-count proxy, not a survey-time measurement.  Per-star
lightcurve baseline lengths are not currently measured.

### Confidence Intervals

Two CI methods are reported:

1. **Poisson 95% CI** (Garwood exact method) on the observed counts.
2. **Bootstrap 95% CI** (percentile method, N=1000 replicates default) on
   the rate ratio, resampling the candidate table with replacement.

### Small-Sample Warnings

With fewer than 10 total post-vetting candidates, rate statistics are
**highly preliminary and unstable**.  Specifically:

- Poisson CIs on counts < 5 are very wide.
- Bootstrap CIs on counts < 3 per group are unreliable.
- Fisher exact p-values with small expected counts are conservative.
- A rate ratio of 2× on 1 vs. 0 candidates has no scientific meaning.

The statistics module emits explicit warnings when the candidate count
is below the stability threshold.

### Fisher Exact Test

A two-sided Fisher exact test compares target vs. control candidate counts
using the matched-pairs star counts as exposure proxies.  **p-values on
dev-sample data are not interpretable as scientific evidence**.  They are
provided for completeness only and require full-survey validation.

---

## Outputs

| File | Description |
|---|---|
| `results/tables/vetted_candidate_events_dev.csv` | Full candidate table with all vetting flags |
| `results/tables/manual_vetting_sheet.csv` | Worksheet for human annotators |
| `results/tables/rate_ratio_summary.csv` | Rate-ratio statistics table (all_candidates, post_vetting_pass) |
| `results/figures/rate_ratio_plot.png` | Rate ratio with Poisson + bootstrap CIs |
| `results/figures/candidate_score_vs_snr.png` | Score vs. SNR scatter, coloured by vetting status |
| `results/figures/vetting_flag_counts.png` | Flag count horizontal bar chart |

---

## Running Phase 5

### Step 1: Automated Vetting

```bash
python scripts/run_vetting.py \
  --candidate-table results/tables/ranked_candidate_events_dev.csv \
  --output-vetted results/tables/vetted_candidate_events_dev.csv \
  --output-manual results/tables/manual_vetting_sheet.csv \
  --snr-threshold 5.0
```

### Step 2: Manual Review (Human Step)

Open `results/tables/manual_vetting_sheet.csv` and fill in:
- `manual_reviewer`: reviewer name or initials
- `manual_review_date`: date of review
- `manual_review_notes`: free-text observations
- `manual_disposition`: e.g., "needs follow-up", "likely systematic", "promising"

### Step 3: Rate Statistics

```bash
python scripts/run_stats.py \
  --vetted-candidates results/tables/vetted_candidate_events_dev.csv \
  --matched-pairs catalogs/matched_pairs.csv \
  --output results/tables/rate_ratio_summary.csv \
  --n-bootstrap 1000 \
  --random-seed 42
```

---

## Vetting Column Definitions

| Column | Type | Description |
|---|---|---|
| `flag_low_snr` | bool | local_snr below threshold |
| `flag_edge_event` | bool | event at LC edge |
| `flag_single_point_like` | bool | single-point morphology |
| `flag_likely_flare_shape` | bool | positive skew + low ratio (flare-like) |
| `flag_low_delta_chi2` | bool | weak asymmetric model evidence |
| `flag_poor_asymmetry_fit` | bool | symmetric or failed model fit |
| `needs_manual_review` | bool | any flag set |
| `automated_vetting_status` | str | "pass" or "flagged" |
| `eb_catalog_check_status` | str | "not_attempted" |
| `vsx_check_status` | str | "not_attempted" |
| `simbad_check_status` | str | "not_attempted" |
| `vetter_version` | str | software version tag |
| `manual_reviewer` | str | human reviewer (blank) |
| `manual_review_date` | str | review date (blank) |
| `manual_review_notes` | str | free-text notes (blank) |
| `manual_disposition` | str | reviewer decision (blank) |

---

## Interpretation Guidance

- A `final_candidate_score` above 0.6 and `automated_vetting_status = "pass"`
  makes a candidate a priority for manual follow-up.  It does **not** confirm
  any astrophysical interpretation.
- The `flag_likely_flare_shape` heuristic may misclassify genuine asymmetric
  events near SNR threshold.  Treat it as a caution flag, not a rejection.
- Candidates not in `matched_pairs.csv` receive `unknown_role` in rate
  statistics and do not contribute to target or control counts.
- Rate ratios on the dev sample (2 candidates, 5 stars scanned) are
  meaningless as scientific evidence.  Phase 5 rate statistics are a
  technical readiness demonstration for Phase 6.

---

## Phase 6 Readiness

Phase 6 (paper draft) requires:

1. Full survey scan over all matched-pairs targets and controls.
2. Manual vetting review of all passing candidates.
3. Multi-sector consistency check for high-priority events.
4. External catalog crossmatch implementation (EB, VSX, SIMBAD).
5. Sufficient candidate counts (ideally > 20 per group) for stable rate statistics.
6. Claims audit against `docs/CLAIMS_POLICY.md`.

The dev-sample rate statistics in Phase 5 **do not meet Phase 6 requirements**.
