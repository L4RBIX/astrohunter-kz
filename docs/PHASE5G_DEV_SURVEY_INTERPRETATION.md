# Phase 5G: Development-Survey Interpretation

Date: 2026-05-16

This document interprets the current AstroHunter KZ development survey using
the Phase 5D/5E/5F outputs.  It is a conservative scientific status report,
not a discovery report.

## Source Tables

Primary inputs:

- `results/tables/full_matched_rate_ratio_summary.csv`
- `results/tables/full_matched_run_summary.csv`
- `results/tables/full_matched_star_level_summary.csv`
- `results/tables/full_matched_overtriggered_stars.csv`
- `results/tables/full_matched_manual_review_disposition_filled.csv`
- `results/tables/full_matched_manual_review_summary.csv`

Derived Phase 5G outputs:

- `results/tables/final_dev_survey_key_numbers.csv`
- `results/tables/final_dev_survey_claims_audit.csv`

## Key Numbers

The development survey successfully scanned 28 debris-disk / IR-excess target
stars and 28 matched control stars.  The detector produced 156 raw candidate
events before vetting:

- Target raw triggers: 57
- Control raw triggers: 99
- Raw target/control rate ratio: 0.576

Automated vetting left only 3 pass events.  All 3 automated-pass events are on
one overtriggered control star:

- TIC `444335503`
- sample role: control
- Phase 5E priority: `overtriggered_review`
- total detector events on that TIC: 20

The Phase 5F manual-review prefill found:

- `keep_candidate`: 0 rows
- `likely_variable_star`: 23 rows
- `likely_systematic`: 9 rows
- `insufficient_data`: 7 rows
- `unsure`: 2 rows

Manual prefill found 0 `keep_candidate` rows.

The manual prefill is conservative and metadata-based.  It is not a substitute
for final expert visual review, but it is sufficient to prevent discovery or
confirmation claims from the current dev run.

## Interpretation

No current result supports an exocomet claim.

The present development survey does not support the working hypothesis that
debris-disk / IR-excess targets have a higher candidate yield than matched
non-disk controls.  In this run, controls produced more raw triggers than
targets, and the only automated-pass events occurred on one overtriggered
control star.

This should not be interpreted as evidence against exocomets around debris-disk
systems in general.  The current sample is a development sample, the detector is
still being tuned, and the false-positive burden is high.  The defensible
interpretation is narrower:

- the current detector configuration overtriggers on some stars;
- automated pass status alone is not reliable;
- repeated deep dips on one control star can dominate apparent post-vetting
  results;
- manual vetting and overtrigger controls are essential before any yield
  comparison can be scientifically meaningful.

## Control-Sample Overtriggering

TIC `444335503` is the central cautionary case.  It is a control star with 20
raw detector events and the only 3 automated-pass events.  The manual prefill
labels those pass events as `likely_variable_star` because the dips are repeated
and deep across the light curve rather than isolated exocomet-like events.

This control-sample overtriggering demonstrates why the project cannot rely on
raw detector counts or automated vetting alone.  A small number of problematic
stars can dominate the apparent candidate yield.

The control sample overtriggering shows why manual vetting is essential.

## Hypothesis Status

Current dev-survey status:

**Not supported in the current run.**

Reason:

- 28 target and 28 control stars were scanned.
- 156 raw candidate events were detected.
- Raw controls outnumbered raw targets: 99 vs 57.
- Automated vetting left 3 pass events, all on overtriggered control TIC
  `444335503`.
- Manual prefill retained 0 `keep_candidate` rows.

The appropriate wording is:

> This development run does not currently support a higher candidate yield for
> debris-disk / IR-excess targets relative to matched controls.

The inappropriate wording is:

> AstroHunter KZ discovered exocomets.

## Claims Policy

The following statements are allowed:

- The current pipeline identifies candidate-like detector triggers.
- The Phase 5G development survey found no retained `keep_candidate` rows.
- The current dev result does not support the target-yield enhancement
  hypothesis.
- The control-sample overtriggering shows why manual vetting is essential.

The following statements are not allowed:

- confirmed exocomet
- discovered exocomets
- AI discovered exocomets
- NASA-level model
- professional confirmation

## Scientific Next Step

The next scientific step is detector tuning and/or a larger matched sample, not
discovery claims.

Near-term priorities:

1. Tune the detector to reduce repeated-event overtriggering.
2. Add stronger periodic/repeated-dip rejection before candidate ranking.
3. Require per-star overtrigger caps or separate variability classification.
4. Re-run injection recovery after detector changes.
5. Expand the matched target/control sample only after the detector behavior is
   stable.
6. Keep all language at the candidate/preliminary level until expert review and
   follow-up validation exist.
