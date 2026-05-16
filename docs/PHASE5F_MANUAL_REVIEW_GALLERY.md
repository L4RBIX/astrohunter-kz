# Phase 5F: Manual Review Gallery and Candidate Inspection Package

## Scientific Constraints

**Visual review does NOT confirm exocomet detections.**

- Disposition labels assigned during manual review are preliminary and must not
  be presented as scientific results without further validation.
- TIC 444335503 (control, 20 events, 3 automated pass events) must be treated
  as likely overtriggered until all events have been individually inspected and
  the light curve has been checked for periodic variability, instrumental
  systematics, and contamination.
- A visually clean event is NOT a confirmed exocomet transit.
- Final paper/report requires completed manual review, multi-sector
  confirmation, and expert validation.
- All overtriggered-star events require special scrutiny before any individual
  event on them can be considered a serious candidate.

## Overview

Phase 5F takes the Phase 5E consolidated tables and produces visual inspection
materials for the highest-priority and most suspicious candidates:

1. **Inspection target list** — events selected by priority criteria.
2. **Per-TIC gallery** — one folder per TIC with full LC plot, per-event zoom
   plots, events summary CSV, and metadata JSON.
3. **Disposition template** — CSV with empty manual review fields for a
   reviewer to fill in.
4. **Priority overview figure** — three-panel summary of the review package.

## Inspection Target Selection Criteria

Events are selected if they satisfy at least one of:

| Criterion | Label | Description |
|---|---|---|
| Medium-priority TIC | `medium_priority` | Up to `max_events_per_star` events per medium-priority TIC |
| Automated pass | `pass_vetting` | All events with `automated_vetting_status == "pass"` |
| Overtriggered top-5 | `overtriggered_top5` | Top `max_events_per_star` events on the 5 TICs with highest event counts |
| Target top event | `target_top_event` | Highest-scoring event on every target TIC not already covered |

Events satisfying multiple criteria receive a comma-separated `inspection_reason`.
Sort order: pass events first, then medium-priority, overtriggered, target-top.

## Per-TIC Gallery Contents

For each selected TIC, a subfolder `results/candidates/manual_review_gallery/tic_{tic_id}/` is created containing:

| File | Description |
|---|---|
| `tic_{tic_id}_full_lc_with_events.png` | Full light curve with all inspection event times marked |
| `event_{i:02d}_BTJD{time:.3f}.png` | Per-event 2-panel figure (full LC + zoom + annotation) |
| `events_summary.csv` | All inspection events for this TIC |
| `metadata.json` | TIC-level metadata (priority, role, SNR, score, LC availability) |

## Disposition Template

The disposition template (`full_matched_manual_review_disposition_template.csv`)
contains one row per inspection event. Manual fields are blank for the reviewer
to fill in:

| Column | Description |
|---|---|
| `manual_label` | Reviewer's assessment (see allowed values below) |
| `reviewer_name` | Reviewer identifier |
| `review_date` | Date of review (YYYY-MM-DD) |
| `visual_event_quality` | `good`, `marginal`, or `poor` |
| `likely_artifact_reason` | Free text if labelled as artifact |
| `notes` | Free text notes |
| `followup_priority` | `high`, `medium`, `low`, or `none` |

**Allowed `manual_label` values:**

| Value | Meaning |
|---|---|
| `keep_candidate` | Event merits further investigation as a candidate |
| `likely_systematic` | Instrumental or processing artifact |
| `likely_variable_star` | Stellar variability (pulsation, flares, etc.) |
| `likely_flare` | Flare-like brightening or its recovery |
| `likely_eb_or_contamination` | Contamination from an eclipsing binary or nearby source |
| `insufficient_data` | Too few in-window points to assess |
| `unsure` | Cannot determine without further information |

Labels are documented here but not programmatically enforced. A reviewer may
use any value; only the labels above will be recognised by downstream analysis.

## Running Phase 5F

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

### Arguments

| Argument | Default | Description |
|---|---|---|
| `--candidate-table` | `…external_checked_candidates.csv` | Phase 5D/5E event table |
| `--priority-table` | `…manual_review_priority.csv` | Phase 5E priority table |
| `--star-summary` | `…star_level_summary.csv` | Phase 5E star summary |
| `--overtriggered` | `…overtriggered_stars.csv` | Phase 5E overtriggered table |
| `--output-dir` | `results/candidates/manual_review_gallery` | Gallery root directory |
| `--disposition-output` | `…disposition_template.csv` | Disposition template output |
| `--inspection-targets-output` | `…inspection_targets.csv` | Inspection target list output |
| `--max-events-per-star` | 5 | Max events per TIC in inspection list |
| `--window-days` | 1.0 | Total zoom window width in days |
| `--cache-dir` | `cache/lightcurves` | Parquet cache directory |

## Expected Outputs

| Path | Description |
|---|---|
| `results/tables/full_matched_inspection_targets.csv` | 41 events, 18 TICs |
| `results/tables/full_matched_manual_review_disposition_template.csv` | 41 rows, blank manual fields |
| `results/figures/manual_review_priority_overview.png` | 3-panel priority summary figure |
| `results/candidates/manual_review_gallery/tic_{tic_id}/` | 18 per-TIC gallery folders |

## Phase 5F Results (2026-05-16 run)

| Metric | Value |
|---|---|
| Total inspection events | 41 |
| TICs selected for inspection | 18 |
| Pass-vetting events | 3 (all TIC 444335503) |
| Medium-priority events | 5 (TIC 234309613: 4, HD 203: 1) |
| Overtriggered-top5 events | 25 (top 5 OT TICs × up to 5 events) |
| Target top events | 15 (one per uncovered target TIC) |
| Total plots generated | 59 |
| LC coverage | 18/18 TICs have cached light curves |

### Manual disposition update

The two manually inspected `unsure` cases, TIC 229012143 / HD 203 and
TIC 91529289 / phi For, were conservatively changed to `insufficient_data`
after visual review. No row remains labelled `keep_candidate`.

### TIC-level inspection summary

| TIC | Role | Name | Priority | Events | Plots |
|---|---|---|---|---|---|
| 444335503 | control | TIC 444335503 | overtriggered_review | 5 | 6 |
| 229012143 | target | HD 203 | medium | 1 | 2 |
| 234309613 | control | TIC 234309613 | medium | 4 | 5 |
| 63790159 | target | gam Tri | overtriggered_review | 5 | 6 |
| 436840249 | target | 33 Ari | overtriggered_review | 5 | 6 |
| 417236897 | control | TIC 417236897 | overtriggered_review | 5 | 6 |
| 194503676 | target | sig And | overtriggered_review | 5 | 6 |
| 12 target TICs | target | Various | low / overtriggered_review | 1 each | 2 each |

### Scientific interpretation notes

**TIC 444335503 (control, 20 events, overtriggered_review):**
All 3 automated pass events are on this control star with high SNR (20–34) and
scores (0.84–0.85). The very high event rate on a control star is the strongest
indication that these events are NOT astrophysical exocomet transits. Possible
explanations include: periodic stellar variability producing repeated
asymmetric-looking dips, instrumental systematics in this TESS pixel region,
or contamination from a nearby variable. Manual inspection of the full light
curve for periodicity is the first step.

**TIC 234309613 (control, medium):**
4 events, max SNR 6.5, max score 0.59. No pass events. Medium priority due to
high SNR relative to threshold. These events must be inspected for variability
patterns before any further consideration.

**HD 203 / TIC 229012143 (target, medium):**
1 event, SNR 3.96, score 0.657 (above the 0.65 medium-score threshold). Low
SNR makes this a marginal candidate. Multi-sector confirmation is needed.

**Target overtriggered stars (gam Tri, 33 Ari, sig And):**
These are target (debris-disk) stars with high event counts. High event counts
on any star — including targets — are more likely to reflect variability,
systematics, or detector over-sensitivity than multiple exocomet transits.
All events on these stars require the same rigorous inspection as the control
overtriggered star.

## How to Proceed with Manual Review

1. Open `results/tables/full_matched_manual_review_disposition_template.csv`.
2. For each row, open the corresponding gallery folder and inspect the event
   zoom plot and full light curve.
3. Fill in `manual_label`, `reviewer_name`, `review_date`, and any notes.
4. Start with pass events on TIC 444335503 — assess whether the full LC shows
   periodic variability or a single real event.
5. Next review the 2 medium-priority TICs (TIC 234309613 and HD 203).
6. For overtriggered target stars, look for periodicity in the full LC before
   accepting any individual event.
7. Save the filled disposition template. Do NOT modify the automated pipeline
   columns.

## Code Location

| Component | File |
|---|---|
| Core functions | `src/astrohunter/inspection.py` |
| Overview figure | `src/astrohunter/plotting.py` (`plot_manual_review_priority_overview`) |
| CLI script | `scripts/build_manual_review_gallery.py` |
| Tests | `tests/test_inspection.py` (42 tests, all network-free) |
