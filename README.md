# AstroHunter KZ

A reproducible Python pipeline for testing whether debris-disk stars produce
more exocomet-like asymmetric TESS dip candidates than matched non-disk control
stars.

AstroHunter KZ uses public NASA TESS light curves and public stellar catalogs to
build a controlled target/control experiment.  The project is intentionally
conservative: it treats detector outputs as candidate dip-like events until they
survive automated vetting, external catalog checks, and visual review.

## Current Result

| Item | Result |
| --- | --- |
| Target stars scanned | 28 |
| Control stars scanned | 28 |
| Raw candidate events | 156 |
| Automated-pass events | 3 |
| Manual keep candidates | 0 |
| Exocomet discovery claim | Not supported |

In the current development survey, the pipeline did not find a visually credible
exocomet candidate. The strongest automated detections were concentrated in a
control star, TIC 444335503, indicating likely variability or systematic
overtriggering. This negative result is scientifically useful because it
validates the need for matched controls and conservative vetting.

## Why This Project Matters

TESS records the brightness of stars over time. If an object passes in front of
a star, the light curve can dip. Dusty comet-like material could produce an
asymmetric dip: a sharper drop followed by a slower recovery. In practice,
blind searches produce many false positives from stellar variability,
instrumental effects, eclipsing binaries, and noise.

AstroHunter KZ asks a testable question: does selecting stars with debris disks
or infrared excess improve the yield of plausible asymmetric-dip candidates
compared with matched non-disk controls? The control sample is the important
part. It prevents the project from mistaking detector overtriggering for an
astrophysical result.

## What the Pipeline Does

- Builds debris-disk / IR-excess target samples from public catalogs.
- Crossmatches TIC, Gaia-like, and TESS availability metadata where available.
- Builds matched non-disk controls for a target/control comparison.
- Downloads, cleans, normalizes, and caches public TESS light curves.
- Detects asymmetric dip-like features in real light curves.
- Runs injection-recovery sensitivity tests with synthetic asymmetric dips.
- Ranks events with an interpretable ML model trained on synthetic injections.
- Applies automated vetting flags for low SNR, edge events, poor shapes, and
  repeated triggers.
- Checks VSX, SIMBAD, and TESS Eclipsing Binary external catalogs.
- Builds manual-review galleries with event windows and full light curves.
- Summarizes target/control candidate rates and audits communication claims.

## Key Technical Features

- Python package under `src/astrohunter/`.
- Reproducible command-line scripts under `scripts/`.
- Public archive data only; no private telescope data.
- No API keys required for basic public TESS usage.
- Matched target/control design instead of a one-sided candidate search.
- Injection recovery for detector sensitivity testing.
- ML ranking kept separate from scientific confirmation.
- External false-positive checks using VSX, SIMBAD, and TESS-EB metadata.
- Manual-review gallery for transparent event inspection.
- Candidate-only claims policy documented in `docs/CLAIMS_POLICY.md`.
- Test suite: `453` passing tests in the current environment.

## Key Outputs

Important result tables and reports include:

- `results/tables/full_matched_run_summary.csv`
- `results/tables/full_matched_rate_ratio_summary.csv`
- `results/tables/full_matched_star_level_summary.csv`
- `results/tables/full_matched_manual_review_disposition_filled.csv`
- `results/tables/final_dev_survey_key_numbers.csv`
- `results/tables/final_dev_survey_claims_audit.csv`
- `results/candidates/manual_review_gallery/`
- `docs/PHASE5G_DEV_SURVEY_INTERPRETATION.md`

The current development sample produced zero `keep_candidate` rows after
conservative manual disposition.

## Quickstart

```bash
git clone https://github.com/L4RBIX/astrohunter-kz.git
cd astrohunter-kz
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pytest
```

For full pipeline commands, including catalog building, light-curve scans,
injection recovery, ML ranking, external vetting, and manual-review gallery
generation, see [docs/REPRODUCIBILITY.md](docs/REPRODUCIBILITY.md).

## Repository Structure

```text
src/astrohunter/
  lightcurves.py       TESS search, download, cleaning, normalization, cache
  catalogs.py          Public catalog loading and target-sample normalization
  crossmatch.py        Coordinate matching and control-sample utilities
  asymmetry.py         Dip detection and asymmetry feature extraction
  injection.py         Synthetic dip injection and recovery experiments
  features.py          Event feature engineering
  ml.py                Interpretable event ranker
  vetting.py           Automated candidate-vetting flags
  external_vetting.py  VSX, SIMBAD, and TESS-EB checks
  stats.py             Target/control rate statistics
  consolidation.py     Star-level summaries and review-priority tables
  inspection.py        Manual-review target selection and gallery creation
  plotting.py          Matplotlib figure helpers

scripts/               Reproducible command-line entry points
notebooks/             Lightweight exploratory notebooks
catalogs/              Small derived target/control catalog products
results/tables/        Reproducible CSV outputs and claims audits
results/figures/       Diagnostic figures
results/candidates/    Manual-review gallery outputs
docs/                  Methods, reproducibility, interpretation, and outreach docs
tests/                 Pytest suite
```

## Scientific Integrity

This repository identifies candidate dip-like events only. It does not claim
confirmed exocomets. The current development survey produced zero manual
`keep_candidate` rows. All results should be interpreted as
pipeline-development outputs unless independently confirmed.

The negative result is part of the contribution: it shows that a detector can
produce convincing-looking automated triggers on control stars, and that
matched controls plus conservative vetting are necessary before making
astrophysical claims.

## Communication-Safe Wording

Good wording:

- "candidate dip-like events"
- "asymmetric TESS dip candidates"
- "development-survey negative result"
- "no candidate survived conservative manual review"
- "pipeline validation with matched controls"

Avoid:

- "confirmed exocomet"
- "discovered exocomets"
- "AI discovered"
- "NASA-level model"
- "fully confirmed"

## Development Milestones

This repository now includes:

- Beta Pic positive-control light-curve workflow.
- Local public-catalog target loading and TIC/Gaia/TESS metadata enrichment.
- Matched target/control sample preparation.
- Real TESS light-curve scan with caching.
- Injection-recovery experiments for detector sensitivity.
- Interpretable ML event ranking.
- Automated vetting and rate-ratio statistics.
- External catalog crossmatching with VSX, SIMBAD, and TESS-EB.
- Manual-review gallery and conservative disposition table.
- Final development-survey interpretation and claims audit.

Detailed commands and phase-level notes live in the documentation rather than
the main README.

## Documentation

- [GitHub portfolio summary](docs/GITHUB_PORTFOLIO_SUMMARY.md)
- [Science fair report](docs/SCIENCE_FAIR_REPORT.md)
- [Presentation script](docs/PROJECT_PRESENTATION_SCRIPT.md)
- [Poster outline](docs/POSTER_OUTLINE.md)
- [Development-survey interpretation](docs/PHASE5G_DEV_SURVEY_INTERPRETATION.md)
- [Next steps to publication](docs/NEXT_STEPS_TO_PUBLICATION.md)
- [Reproducibility guide](docs/REPRODUCIBILITY.md)
- [Claims policy](docs/CLAIMS_POLICY.md)

