# Next Steps to Publication

Date: 2026-05-16

This document outlines a conservative publication path after the Phase 5G
development-survey interpretation.  The current results do not support an
exocomet discovery claim.

## Current Scientific Position

The development survey scanned 28 target stars and 28 matched control stars.
It produced 156 raw detector triggers, but automated vetting left only 3 pass
events, all on one overtriggered control star, TIC `444335503`.  The Phase 5F
manual prefill retained 0 `keep_candidate` rows.

Therefore, the current result should be treated as a detector-validation and
false-positive-control milestone.  It is not evidence for confirmed exocomets.

## Publication-Ready Claim Boundary

Allowed:

- AstroHunter KZ implements a reproducible matched-sample TESS search workflow.
- The current development run found no retained candidate events after
  conservative manual prefill.
- The current detector configuration shows overtriggering that must be fixed
  before a larger statistical comparison.
- The development run does not support higher candidate yield for
  debris-disk / IR-excess targets.

Not allowed:

- discovery claims;
- confirmed exocomet language;
- claims that automated vetting is sufficient;
- rate-ratio conclusions beyond this small development sample.

## Required Work Before Publication

1. Detector tuning

   Reduce repeated-event overtriggering.  Add explicit rejection or downranking
   for periodic/repeated dips, edge/gap events, and single-star event clusters.

2. Injection-recovery rerun

   After detector changes, rerun injection recovery to measure completeness,
   false negatives, depth/duration sensitivity, and asymmetry recovery.

3. False-positive validation

   Expand external checks beyond the current catalogs where practical:
   Gaia variability, ASAS-SN, ZTF, TESS eclipsing binary products, SIMBAD/VSX,
   and sector-level quality/systematics review.

4. Manual review protocol

   Convert the metadata-based prefill into a true human visual review.  Each
   row should receive a final reviewer disposition, notes, and a reproducible
   rationale.  Keep candidate language unless follow-up validation exists.

5. Larger matched sample

   Only after detector behavior stabilizes, expand the matched target/control
   sample.  Preserve matching criteria and report failed downloads or
   unavailable light curves explicitly.

6. Statistical analysis

   Recompute rate ratios on post-vetting and post-manual-review candidates.
   Report confidence intervals, bootstrap stability, and the impact of
   overtriggered-star removal.

7. Reproducibility package

   Freeze code versions, command logs, input tables, generated outputs, and
   environment requirements.  Do not include large raw MAST downloads in the
   repository; document how to regenerate them.

## Suggested Paper Framing

Working title:

`A Reproducible Matched-Sample TESS Search Framework for Exocomet-Like
Asymmetric Transit Candidates Around Debris-Disk Stars`

Recommended framing:

- methods paper / reproducible pipeline paper;
- development-survey null or cautionary result;
- emphasis on matched controls and false-positive pressure;
- no discovery claim.

Core result statement:

> In the current development sample, AstroHunter KZ does not find evidence for
> an enhanced debris-disk target yield after automated and conservative manual
> vetting.  The dominant lesson is that overtriggering and stellar variability
> controls are essential before a larger yield comparison.

## Exit Criteria for an arXiv-Ready Draft

- Detector tuning completed and documented.
- Injection recovery rerun with updated detector.
- Manual visual review completed for all retained inspection rows.
- Candidate table contains only defensible `keep_candidate` rows, if any.
- Matched-sample rate statistics recomputed after final vetting.
- Claims audit passes `docs/CLAIMS_POLICY.md`.
- README and reproducibility docs allow a clean rerun of the published
  pipeline.

