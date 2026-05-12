# Master Blueprint

AstroHunter KZ is a controlled TESS search for exocomet-like asymmetric transit
candidates around debris-disk / infrared-excess stars.

Long-term design:

- Build a debris-disk / infrared-excess target sample from public catalogs.
- Build a matched non-disk control sample with similar TESS sectors,
  magnitudes, and stellar parameters.
- Use a Kennedy-style asymmetric-transit detector as the transparent detection
  backbone.
- Use a Dobrycheva-style Random Forest only as a baseline ML comparator.
- Run injection-recovery experiments on real TESS light curves to quantify
  sensitivity and completeness.
- Train an XGBoost event ranker after detector and feature definitions are
  stable.
- Apply a vetting cascade for quality flags, background contamination,
  eclipsing binaries, periodic variables, systematics, and multi-sector
  consistency.
- Estimate target/control rate-ratio statistics with uncertainty instead of
  making sensational discovery claims.
- Add Kazakhstan observability as a secondary follow-up-planning layer after
  candidates are vetted and ranked.

Current implementation boundary:

Phase 1 only implements the Beta Pic technical positive control. It does not
implement catalog matching, full ML training, injection recovery, rate-ratio
statistics, paper results, or fake candidate catalogs.
