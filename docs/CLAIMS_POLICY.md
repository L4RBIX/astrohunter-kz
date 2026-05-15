# Claims Policy

AstroHunter KZ is a candidate-event search and statistical-comparison project.
It does not claim professional confirmation of exocomets.

Allowed wording:

- candidate dip-like feature
- candidate asymmetric event
- exocomet-like candidate
- positive-control recovery test
- requires follow-up validation

Forbidden wording unless professional confirmation exists:

- confirmed exocomet
- discovered exocomets
- AI discovered
- NASA-level model

Every result table, figure caption, README summary, notebook, and draft paper
must make clear that detections are candidates only. Strong events may be
instrumental/systematic until quality flags, multi-sector consistency, stellar
variability checks, background contamination checks, and independent review are
complete.

## Phase 4 ML-Specific Rules

Additional forbidden wording for ML outputs:

- "the ML model confirms"
- "AI discovered exocomets"
- "the model identified real exocomets"
- "AUC of X% means X% of candidates are real"

Required wording for ML outputs:

- "the ranker is trained on synthetic injection-recovery labels"
- "the score ranks candidates for human review"
- "injection-trained metrics do not describe real-data purity"
- "all ranked candidates require vetting and follow-up"

The `final_candidate_score` column is a prioritisation aid, not a posterior
probability of exocomet detection.  Feature importance plots describe what
makes a synthetic injection recoverable, not what distinguishes real exocomets
from noise.

## Phase 5 Vetting- and Statistics-Specific Rules

Additional forbidden wording for Phase 5 outputs:

- "automated vetting confirms"
- "the rate ratio proves debris-disk enhancement"
- "the rate ratio shows excess candidates"
- "Phase 5 statistics demonstrate an exocomet signal"
- "p-value of X means the result is significant"

Required wording for Phase 5 outputs:

- "automated vetting applies heuristic flags only"
- "all candidates require manual review"
- "external catalog crossmatches (EB/VSX/SIMBAD) are not implemented"
- "dev-sample rate statistics are preliminary and unstable"
- "rate ratios on N < 10 candidates have no scientific meaning"
- "full survey data are required before any interpretation"

The `automated_vetting_status` column is a heuristic filter aid, not a
astrophysical classification.  The rate ratio in `rate_ratio_summary.csv`
is a technical readiness demonstration for Phase 6, not a discovery claim.

## Phase 5C External-Catalog-Vetting-Specific Rules

Additional forbidden wording for Phase 5C outputs:

- "external catalog check confirms no false positive"
- "SIMBAD shows this is a real exocomet candidate"
- "no VSX match proves the event is astrophysical"
- "the TESS-EB catalog cleared this candidate"
- "external vetting confirms exocomet"

Required wording for Phase 5C outputs:

- "external catalog checks reduce false-positive contamination but do not
  confirm exocomet detections"
- "a catalog match indicates possible contamination, not definitive rejection"
- "lack of a catalog match does not prove astrophysical validity"
- "failed queries (status = failed) are inconclusive and must be re-run"
- "manual inspection of every candidate is still required"
- "one control candidate was flagged due to a VSX suspected-variable match;
  this is a precautionary demotion, not a confirmed false positive"

The `external_false_positive_flag` column is a heuristic classifier, not a
scientific verdict.  The `known_variable_match` flag on TIC 115598451 indicates
a known suspected variable in the same sky position; it does not confirm that
the candidate transit event is caused by the variable star, and it does not
rule out a genuine comet event hosted by a different star in the field.
