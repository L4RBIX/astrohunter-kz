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

## Run the Notebook

```bash
jupyter notebook notebooks/00_quickstart_beta_pic.ipynb
```

The older proof-of-concept notebook is preserved as:

```text
notebooks/01_beta_pic_positive_control.ipynb
```

## Run Tests

```bash
python -m pytest
```

## Repository Structure

```text
src/astrohunter/
  lightcurves.py      TESS search, download, cleaning, normalization helpers
  asymmetry.py        Candidate dip detection and simple asymmetry metrics
  plotting.py         Matplotlib figure helpers
scripts/
  run_beta_pic_control.py
notebooks/
  00_quickstart_beta_pic.ipynb
  01_beta_pic_positive_control.ipynb
docs/
  CLAIMS_POLICY.md
  REPRODUCIBILITY.md
  PROJECT_SCOPE.md
  MASTER_BLUEPRINT.md
results/
  figures/
  tables/
tests/
```

## Data Policy

Raw downloaded light curves, cache files, and large catalog products should not
be committed. Public archive data should be re-downloadable through documented
scripts. Small Phase 1 example figures/tables may be kept for portfolio and
sanity-check purposes when they are clearly labeled as candidate-only outputs.

## Next Phases

- Phase 2: build real debris-disk / IR-excess target and matched-control samples.
- Phase 3: implement detector improvements and injection-recovery experiments.
- Phase 4: add an ML event ranker after features and labels are stable.
- Phase 5: implement vetting and rate-ratio statistics.
- Phase 6: prepare a paper draft and claims/reproducibility audit.
