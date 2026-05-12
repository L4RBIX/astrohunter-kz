# Project Scope

AstroHunter KZ asks whether physically motivated target selection improves the
yield and purity of TESS candidate asymmetric transit searches.

## Phase 1: Beta Pic Technical Positive Control

Build a reproducible pipeline that downloads public TESS data for Beta Pic /
TIC 270577175, cleans and normalizes the light curve, detects simple candidate
dip-like features, computes transparent asymmetry metrics, and saves figures and
tables. This phase is a technical foundation, not a discovery claim.

## Phase 2: Catalog Builder and Development Samples

Build debris-disk / infrared-excess target samples and matched non-disk control
samples using public catalogs such as Cotten & Song, Chen, McDonald, TIC, Gaia,
and TESS availability metadata. Do not fabricate target samples.

## Phase 3: Detector and Injection Recovery

Implement a Kennedy-style asymmetric-transit detector and injection-recovery
experiments on real TESS light curves to measure sensitivity, false positives,
and completeness.

## Phase 4: Machine-Learning Ranker

Train an event-level ranker, likely using XGBoost as the main model and a
Dobrycheva-style Random Forest as a baseline. ML should rank candidates, not
claim confirmation.

## Phase 5: Vetting and Statistics

Apply a vetting cascade for quality flags, background contamination, eclipsing
binaries, periodic variables, spacecraft/systematic artifacts, and multi-sector
checks. Estimate candidate-yield rate ratios and uncertainty for target versus
matched-control samples.

## Phase 6: Paper Draft and arXiv-Readiness Audit

Prepare a transparent methods/results draft, archive reproducible tables, audit
claims against `docs/CLAIMS_POLICY.md`, and keep candidate language unless
professional confirmation exists.
