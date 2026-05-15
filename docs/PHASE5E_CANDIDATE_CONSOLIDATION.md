# Phase 5E: Candidate Consolidation and Manual Review Package

## Scientific Constraints

**Consolidation is NOT confirmation of exocomet detections.**

- Repeated events on one star may reflect stellar variability, systematics, or contamination — not multiple exocomet transits.
- Stars flagged as overtriggered require special scrutiny before any event on them is accepted as a candidate.
- Priority labels (`high`, `medium`, `low`, `overtriggered_review`) are heuristic classifiers, not scientific verdicts.
- Pass candidates on overtriggered stars are particularly suspect.
- All candidates require manual inspection of individual light curves and multi-sector confirmation.
- External catalog matches reduce false-positive contamination but do NOT confirm astrophysical validity.
- A full scientific result requires expert review, multi-sector consistency, and multi-instrument follow-up.

## Overview

Phase 5E takes the externally-checked candidate table produced by Phase 5D (or Phase 5C) and builds:

1. **Star-level summary** — one row per TIC with aggregate statistics and a recommended review priority.
2. **Top event per star** — the single highest-scoring event per TIC for quick inspection.
3. **Manual review priority table** — up to N events per TIC, sorted by score, with priority labels.
4. **Overtriggered stars list** — TICs with ≥ threshold events flagged for special scrutiny.
5. **Diagnostic figures** — candidates-per-star bar chart, top-score scatter, pass-candidate bar chart.

## Priority Labels

| Label | Meaning |
|---|---|
| `high` | ≥1 pass event, no concern-level external flag, not overtriggered |
| `medium` | ≥1 pass event with mild concern, OR high score/SNR with no external flags |
| `low` | No pass events and score/SNR below medium thresholds |
| `overtriggered_review` | TIC has ≥ overtrigger_threshold events — review all events for variability/systematics before accepting any |

Priority rules (applied in order):
1. `overtriggered_review` if `n_events >= overtrigger_threshold`
2. `high` if `n_pass > 0` AND no concern external flag AND no TESS-EB match
3. `medium` if `n_pass > 0`, OR `max_score >= 0.65` with zero external flags, OR `max_snr >= 6.0` with zero external flags
4. `low` otherwise

Concern-level external flags: `known_variable_match`, `possible_eclipsing_binary_match`, `simbad_nonstellar_or_problematic_type`.

## Star-Level Summary Columns

| Column | Description |
|---|---|
| `tic_id` | TESS Input Catalog ID |
| `target_name` | Human-readable name (first occurrence) |
| `sample_role` | `target` or `control` |
| `n_events` | Total candidate events on this TIC |
| `n_pass_automated_vetting` | Events with `automated_vetting_status == "pass"` |
| `n_external_flags` | Events with a positive `flag_external_catalog_match` |
| `max_final_candidate_score` | Highest ML score across all events |
| `max_local_snr` | Highest local SNR across all events |
| `median_local_snr` | Median local SNR across all events |
| `max_depth_ppm` | Deepest dip depth in ppm |
| `min_event_time_btjd` | Earliest event time (BTJD) |
| `max_event_time_btjd` | Latest event time (BTJD) |
| `has_known_variable_match` | True if any event has a concern-level external flag |
| `has_tess_eb_match` | True if any event matched TESS-EB catalog |
| `recommended_review_priority` | Heuristic priority label |
| `consolidation_version` | `phase5e_v1` |

## Running Phase 5E

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

### Arguments

| Argument | Default | Description |
|---|---|---|
| `--candidate-table` | `results/tables/full_matched_external_checked_candidates.csv` | Phase 5C/5D output |
| `--scan-status` | `results/tables/full_matched_scan_status.csv` | Per-star scan status (optional) |
| `--output-star-summary` | `results/tables/full_matched_star_level_summary.csv` | Star-level summary output |
| `--output-top-events` | `results/tables/full_matched_top_event_per_star.csv` | Top event per TIC output |
| `--output-review-priority` | `results/tables/full_matched_manual_review_priority.csv` | Review priority table output |
| `--output-overtriggered` | `results/tables/full_matched_overtriggered_stars.csv` | Overtriggered stars output |
| `--max-events-per-star` | 3 | Max events per TIC in the review table |
| `--overtrigger-threshold` | 5 | Min events to flag as overtriggered |

## Expected Outputs

| File | Description |
|---|---|
| `results/tables/full_matched_star_level_summary.csv` | One row per TIC with aggregated statistics and priority |
| `results/tables/full_matched_top_event_per_star.csv` | Single highest-scoring event per TIC |
| `results/tables/full_matched_manual_review_priority.csv` | Up to 3 events per TIC, prioritised for review |
| `results/tables/full_matched_overtriggered_stars.csv` | TICs with ≥ 5 events |
| `results/figures/full_matched_candidates_per_star.png` | Horizontal bar chart — events per TIC by role |
| `results/figures/full_matched_top_scores_by_star.png` | Score scatter — one point per TIC, shaped by priority |
| `results/figures/full_matched_pass_candidates_by_role.png` | Grouped bar chart — total vs pass events by role |

## Phase 5E Results (2026-05-16 run)

| Metric | Value |
|---|---|
| Total candidate events | 156 |
| Unique TICs | 36 |
| Target TICs | 15 |
| Control TICs | 21 |
| Overtriggered TICs (≥ 5 events) | 13 |
| High priority | 0 |
| Medium priority | 2 |
| Low priority | 21 |
| Overtriggered review | 13 |
| Pass-vetting candidates | 3 (all control) |

**Pass candidates note:** All 3 pass-vetting events are on TIC 444335503, a control star with 20 events — the highest event count in the survey. This star is labelled `overtriggered_review`. The high SNR (20–34) and score (0.84–0.85) on this control star most likely reflect persistent stellar variability or a systematic artifact, not exocomet transits. Manual inspection of the TIC 444335503 light curve is required before any interpretation.

**No target-star pass candidates** were identified in this survey run. This is consistent with the limited sky coverage and small matched sample; it does not rule out the presence of exocometss around target stars at detection thresholds below the current pipeline sensitivity.

## Code Location

| Component | File |
|---|---|
| Core logic | `src/astrohunter/consolidation.py` |
| Plotting | `src/astrohunter/plotting.py` (`plot_candidates_per_star`, `plot_top_scores_by_star`, `plot_pass_candidates_by_role`) |
| CLI script | `scripts/consolidate_candidates.py` |
| Tests | `tests/test_consolidation.py` (57 tests, all network-free) |

## Interpretation Reminders

- A `high` or `medium` label means "prioritise for manual review" — not "probable exocomet."
- An `overtriggered_review` star must have all its light curve sections inspected for periodic variability, instrumental artifacts, or contamination before any individual event is accepted.
- SIMBAD/VSX/TESS-EB matches are heuristic; a match indicates possible contamination, not definitive rejection. Lack of a match does not prove astrophysical validity.
- Pass-vetting is automated only; it cannot substitute for visual light-curve inspection.
- Rate statistics (Phase 5) have no scientific meaning until full-survey coverage and manual vetting are complete.
