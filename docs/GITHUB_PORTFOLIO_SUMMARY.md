# AstroHunter KZ — GitHub Portfolio Summary

**Author:** Bekarys Kydyrbekov
**Repository:** https://github.com/L4RBIX/astrohunter-kz
**Date:** 2026-05-16

---

## Project Overview

AstroHunter KZ is an end-to-end, fully tested Python pipeline for searching
NASA TESS photometry for exocomet-like asymmetric transit candidates around
debris-disk stars, using a matched target/control statistical design.

The development survey produced **zero surviving candidates** after conservative
multi-stage vetting. This is an **honest negative result** — and the most
defensible scientific output the project can make given the current data.

---

## Why This Is Technically Impressive

| Aspect | Detail |
|---|---|
| **End-to-end automation** | Six sequential pipeline stages from public archive to reviewed results — no manual steps between |
| **Matched-control design** | 28 debris-disk target stars paired with 28 matched non-disk control stars for statistically sound comparison |
| **Injection-recovery testing** | Thousands of synthetic comet signals injected into real TESS noise to measure detector sensitivity |
| **ML ranking** | GradientBoostingClassifier trained on injection labels, not hand-picked real events — model is a triage tool, not a discovery engine |
| **Six automated vetting flags** | SNR threshold, edge artifact detection, morphology checks, asymmetry chi-squared, shape flags |
| **Three external catalog crossmatches** | VSX (variable stars), SIMBAD (object types), TESS Eclipsing Binary catalog |
| **Manual review gallery** | Per-TIC light curve inspection plots, zoom panels, metadata JSON, CSV disposition templates |
| **Claims audit trail** | Explicit CSV table documenting every public claim the project can and cannot make |
| **453 automated tests** | Full unit and integration test suite — network-free, reproducible from any environment |
| **Zero private data** | All inputs from public archives (MAST/lightkurve, public catalogs) |

---

## Architecture Summary

```
Public TESS data (MAST/lightkurve)
           │
           ▼
  Phase 1: Matched Catalog Builder
  → debris-disk targets + matched controls
           │
           ▼
  Phase 2: Asymmetric-Dip Detector
  → rolling window, ingress/egress ratio, local SNR
           │
           ▼
  Phase 2E: Injection-Recovery Sensitivity Test
  → synthetic signals injected into real noise
           │
           ▼
  Phase 4: ML Ranker (GradientBoostingClassifier)
  → trained on injection-recovery labels, NOT real candidates
           │
           ▼
  Phase 5: Automated Vetting (6 quality flags)
  → SNR, edge, morphology, asymmetry
           │
           ▼
  Phase 5D: External Catalog Crossmatch
  → VSX + SIMBAD + TESS-EB
           │
           ▼
  Phase 5E: Candidate Consolidation
  → star-level summaries, overtrigger detection, priority tiers
           │
           ▼
  Phase 5F: Manual Review Gallery
  → per-TIC plots, zoom events, disposition template
           │
           ▼
  Phase 6A: Communication Package
  → science-fair report, presentation script, poster outline, social media
```

Every stage writes auditable output tables. No stage skips vetting. All code
is version-controlled, linted, and covered by automated tests.

---

## Data Sources

| Source | What It Provides |
|---|---|
| NASA TESS (MAST) | Public 2-minute photometry via lightkurve |
| Cotten & Song (2016) | Debris-disk / IR-excess star catalog |
| Chen et al. (2014) | Additional infrared-excess targets |
| TESS Input Catalog (TIC) | Stellar parameters for sample matching |
| VSX | Known variable star crossmatch |
| SIMBAD | Object-type crossmatch |
| TESS Eclipsing Binary catalog | Known EB contamination crossmatch |

All data are freely and publicly available. No proprietary observations,
private APIs, or unpublished datasets were used.

---

## Key Pipeline Components

### `src/astrohunter/`

| Module | Role |
|---|---|
| `catalog.py` | Build matched target/control sample from public catalogs |
| `detector.py` | Asymmetric-dip detection (rolling window, SNR, ingress/egress ratio) |
| `injection.py` | Injection-recovery sensitivity testing |
| `ml_ranker.py` | GradientBoosting ML event ranker (trained on injections) |
| `vetting.py` | Six-flag automated quality vetting |
| `external_check.py` | VSX / SIMBAD / TESS-EB catalog crossmatch |
| `consolidation.py` | Star-level summaries, overtrigger detection, priority assignment |
| `inspection.py` | Manual review gallery builder, disposition template |
| `plotting.py` | All figures — rate ratio, event counts, injection recovery, priority overview |
| `stats.py` | Garwood Poisson CI, bootstrap rate ratio, Fisher exact p-value |

### `scripts/`

Each pipeline stage has a standalone CLI script that reads input tables and
writes output tables. They can be run independently and are fully documented
with `--help`.

### `tests/`

42 tests for `inspection.py` alone; 453 tests total across all pipeline modules.
Tests use synthetic data factories — no network calls, no private data required.

---

## Testing and Reproducibility

```
pytest tests/ -q
# 453 passed (as of 2026-05-16)
```

The full pipeline can be reproduced from a fresh clone:

```bash
git clone https://github.com/L4RBIX/astrohunter-kz
cd astrohunter-kz
pip install -e ".[dev]"
pytest tests/ -q

# Run pipeline stages in order — see docs/REPRODUCIBILITY.md
```

No private API keys, no proprietary data, no manual configuration. All cached
inputs are either downloaded from public archives or regenerated by the pipeline.

See [docs/REPRODUCIBILITY.md](REPRODUCIBILITY.md) for the step-by-step
reproduction guide.

---

## Results

| Metric | Value |
|---|---|
| Target stars scanned | 28 |
| Control stars scanned | 28 |
| Raw candidate events (target) | 57 |
| Raw candidate events (control) | 99 |
| Raw rate ratio (target / control) | 0.58 |
| Automated vetting pass events | 3 (all on 1 control star) |
| Manual review `keep_candidate` | **0** |
| **Surviving candidates** | **0** |

The development survey produced **no surviving exocomet-like candidates** after
conservative vetting. The hypothesis — that debris-disk stars show more
asymmetric dip-like events than matched controls — was **not supported** in
this development run.

The three most impressive-looking events (SNR up to 34, ML score 0.85) all
came from TIC 444335503, a **control star** that produced 20 detector triggers.
Without the matched-control design, those events might have been reported as
candidates. With the controls, they were immediately flagged as false positives.

**No discovery claim is made. The result is a negative result.**

---

## What I Learned

**Scientific rigor:**
- Matched-control design is essential in photometric surveys. False-positive
  candidates look exactly like real ones when viewed in isolation.
- A single sector of TESS data is insufficient for any exocomet claim. Multi-sector
  confirmation and expert review are the minimum bar.
- Negative results are publishable, defensible, and valuable — they redirect
  future work and prevent overclaiming.

**Software engineering:**
- Modular pipeline design (one script per stage) makes debugging tractable.
- Writing tests before running on real data caught several edge cases that would
  have silently corrupted results.
- Claims auditing (an explicit CSV of what can and cannot be said) should be
  part of any research project from day one.

**Machine learning in science:**
- ML is a triage tool in this context, not a discovery engine. The model ranks
  events by similarity to synthetic injections — it says nothing about whether
  an event is astrophysically real.
- Training labels from synthetic data are not training labels from confirmed
  detections. The model's AUC/F1 describes sensitivity to synthetic signals,
  not accuracy on real events.

---

## Future Roadmap

1. **Detector tuning** — Add explicit overtrigger cap; suppress repeated events
   on the same star; add periodic-variability rejection.
2. **Larger sample** — Expand target and control pools to 100+ stars per group
   for statistically reliable rate comparison.
3. **Multi-sector confirmation** — Require candidate events to appear in at
   least two independently observed TESS sectors, months apart.
4. **Expert visual review** — Replace metadata-based prefill with genuine
   astrophysical review by an experienced astronomer.
5. **Additional external catalogs** — Add Gaia variability flags, ASAS-SN, and
   ZTF crossmatches to the external vetting step.
6. **Research note** — Write up the methodology and negative result for a
   student journal or preprint, with claims at the appropriate conservative level.

---

## Scientific Honesty Statement

This project makes no discovery claim. The following language is prohibited in
any public communication about this work:

> "confirmed exocomet" / "discovered exocomets" / "AI found comets" /
> "NASA-level discovery" / "Kazakhstan discovered exocomets"

The correct characterization of this project's result is:

> **Zero candidates survived conservative multi-stage vetting. The development
> survey produced an honest negative result. The hypothesis was not supported.**

All claims are documented in `results/tables/final_dev_survey_claims_audit.csv`.

The pipeline, methodology, and honest null result are the contribution — not
any astrophysical detection.

---

## Repository Structure (key paths)

```
astrohunter-kz/
├── src/astrohunter/          # Core pipeline modules
├── scripts/                  # CLI scripts for each pipeline stage
├── tests/                    # 453 automated tests
├── results/
│   ├── tables/               # All output CSV tables
│   ├── figures/              # All output figures
│   └── candidates/           # Manual review gallery
├── docs/                     # Documentation and communication package
│   ├── SCIENCE_FAIR_REPORT.md
│   ├── PROJECT_PRESENTATION_SCRIPT.md
│   ├── POSTER_OUTLINE.md
│   ├── SOCIAL_MEDIA_POSTS.md
│   └── GITHUB_PORTFOLIO_SUMMARY.md
├── cache/lightcurves/        # Cached TESS light curves (Parquet)
└── REPRODUCIBILITY.md        # Step-by-step reproduction guide
```
